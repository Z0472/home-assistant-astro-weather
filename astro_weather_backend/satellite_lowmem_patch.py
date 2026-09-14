"""Bounded-memory MTG/FCI CLM sampler for Astro Weather Backend 12.4.14.

The FCI full-disc CLM field contains more than 31 million grid points. ecCodes
``grib_get -i`` materializes the decoded values array before returning one item,
which can consume ~600 MiB on a 2 GiB Raspberry Pi and trigger the kernel OOM
killer. This patch keeps ecCodes only for cheap GRIB metadata reads and decodes
the requested packed values directly from GRIB2 Section 7.

Only GRIB2 simple packing without a bitmap is accepted. If EUMETSAT changes the
packing template, the satellite path fails open with a clear diagnostic instead
of falling back to a memory-hungry full-field decode.
"""
from __future__ import annotations

import gc
import math
import shutil
from pathlib import Path
from typing import Any, BinaryIO

import satellite_nowcast_patch as sat
import satellite_index_sampler_patch as index_sampler
import storage_protection_patch as storage
import satellite_card_map_patch as clm_map
import satellite_lowload_patch as lowload
import satellite_ui_patch as satellite_ui
import spatial_cloud_patch as spatial

RELEASE_VERSION = "12.4.14"
MIN_AVAILABLE_MEMORY_BYTES = 192 * 1024 * 1024

_METADATA_KEYS = (
    "gridType,Nx,Ny,iScansNegatively,jScansPositively,"
    "jPointsAreConsecutive,alternativeRowScanning,"
    "latitudeOfSubSatellitePointInDegrees,longitudeOfSubSatellitePointInDegrees,"
    "dataRepresentationTemplateNumber,packingType,bitsPerValue,referenceValue,"
    "binaryScaleFactor,decimalScaleFactor,bitmapPresent"
)


def _mem_available_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            if line.startswith("MemAvailable:"):
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1]) * 1024
    except (OSError, ValueError):
        return None
    return None


def _ensure_memory_headroom() -> None:
    available = _mem_available_bytes()
    if available is not None and available < MIN_AVAILABLE_MEMORY_BYTES:
        raise RuntimeError(
            "Nedostatek volne RAM pro bezpecne zpracovani CLM: "
            f"MemAvailable={available / (1024 * 1024):.0f} MiB, "
            f"minimum={MIN_AVAILABLE_MEMORY_BYTES / (1024 * 1024):.0f} MiB"
        )


def _metadata(core: Any, grib_path: Path) -> dict[str, Any]:
    out = core.run_cmd(["grib_get", "-p", _METADATA_KEYS, str(grib_path)], timeout=30)
    parts = str(out).strip().split()
    if len(parts) < 16:
        raise RuntimeError(f"FCI GRIB metadata jsou neuplna: {out!r}")

    try:
        meta = {
            "grid_type": parts[0],
            "nx": int(parts[1]),
            "ny": int(parts[2]),
            "i_negative": int(parts[3]),
            "j_positive": int(parts[4]),
            "j_consecutive": int(parts[5]),
            "alternate_rows": int(parts[6]),
            "sub_satellite_lat": float(parts[7]),
            "sub_satellite_lon": float(parts[8]),
            "data_representation_template": int(parts[9]),
            "packing_type": parts[10],
            "bits_per_value": int(parts[11]),
            "reference_value": float(parts[12]),
            "binary_scale_factor": int(parts[13]),
            "decimal_scale_factor": int(parts[14]),
            "bitmap_present": int(parts[15]),
        }
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"FCI GRIB metadata nelze precist: {out!r}") from exc

    index_sampler._validate_grid(meta)

    if meta["data_representation_template"] != 0 or meta["packing_type"] != "grid_simple":
        raise RuntimeError(
            "FCI CLM pouziva nepodporovane GRIB2 baleni "
            f"template={meta['data_representation_template']}, "
            f"packingType={meta['packing_type']!r}; "
            "z bezpecnostnich duvodu nepouzivam pametove narocny full-field decode"
        )
    if meta["bitmap_present"] != 0:
        raise RuntimeError(
            "FCI CLM obsahuje bitmapu; low-memory sampler ji zatim nepodporuje "
            "a full-field decode je z bezpecnostnich duvodu zakazan"
        )
    if not 0 <= meta["bits_per_value"] <= 32:
        raise RuntimeError(f"Neocekavane bitsPerValue={meta['bits_per_value']}")

    return meta


def _section7_range(grib_path: Path) -> tuple[int, int]:
    size = grib_path.stat().st_size
    with grib_path.open("rb") as handle:
        header = handle.read(16)
        if len(header) != 16 or header[:4] != b"GRIB":
            raise RuntimeError("FCI soubor nema platnou GRIB hlavicku")
        if header[7] != 2:
            raise RuntimeError(f"FCI soubor neni GRIB edition 2 (edition={header[7]})")

        total_length = int.from_bytes(header[8:16], "big")
        if total_length < 20 or total_length > size:
            raise RuntimeError(
                f"Neplatna delka GRIB zpravy {total_length} B pro soubor {size} B"
            )

        pos = 16
        while pos + 5 <= total_length - 4:
            handle.seek(pos)
            prefix = handle.read(5)
            if len(prefix) != 5:
                break
            section_length = int.from_bytes(prefix[:4], "big")
            section_number = prefix[4]
            if section_length < 5 or pos + section_length > total_length:
                raise RuntimeError(
                    f"Neplatna GRIB sekce {section_number} na offsetu {pos}: "
                    f"delka={section_length}"
                )
            if section_number == 7:
                return pos + 5, section_length - 5
            pos += section_length

    raise RuntimeError("FCI GRIB neobsahuje Section 7 s packed daty")


def _read_packed_uint(
    handle: BinaryIO,
    payload_offset: int,
    payload_length: int,
    value_index: int,
    bits_per_value: int,
) -> int:
    if value_index < 0:
        raise RuntimeError(f"Zaporny index packed hodnoty: {value_index}")
    if bits_per_value == 0:
        return 0

    bit_start = value_index * bits_per_value
    bit_end = bit_start + bits_per_value
    if bit_end > payload_length * 8:
        raise RuntimeError(
            f"Index {value_index} je mimo packed Section 7 "
            f"({payload_length} B, {bits_per_value} bit/value)"
        )

    byte_start = bit_start // 8
    bit_offset = bit_start % 8
    byte_count = (bit_offset + bits_per_value + 7) // 8
    handle.seek(payload_offset + byte_start)
    blob = handle.read(byte_count)
    if len(blob) != byte_count:
        raise RuntimeError("FCI Section 7 skoncila drive nez ocekavano")

    container = int.from_bytes(blob, "big")
    shift = byte_count * 8 - bit_offset - bits_per_value
    return (container >> shift) & ((1 << bits_per_value) - 1)


def _decode_simple(raw: int, meta: dict[str, Any]) -> float:
    # WMO GRIB2 Template 5.0: Y = (R + X * 2^E) * 10^-D.
    return (
        float(meta["reference_value"])
        + float(raw) * math.ldexp(1.0, int(meta["binary_scale_factor"]))
    ) * (10.0 ** (-int(meta["decimal_scale_factor"])))


def _sample_product(
    core: Any,
    options: dict[str, Any],
    product: dict[str, Any],
    token: str,
) -> dict[str, Any]:
    if shutil.which("grib_get") is None:
        raise RuntimeError("ecCodes/grib_get neni v kontejneru k dispozici")

    _ensure_memory_headroom()
    payload = sat._download_product(str(product["product_id"]), token)

    with storage._RAM_IO_LOCK:
        grib_path = storage._write_satellite_grib_to_ram(payload)
        # Release the compressed HTTP payload before touching the GRIB. The
        # remaining scratch file is a small packed field in tmpfs, not a decoded
        # 31-million-value array.
        del payload
        gc.collect()

        sampled: dict[str, int | None] = {}
        point_indexes: dict[str, int] = {}
        try:
            meta = _metadata(core, grib_path)
            payload_offset, payload_length = _section7_range(grib_path)
            points = spatial.build_spatial_points(
                float(options["latitude"]),
                float(options["longitude"]),
                int(options["satellite_radius_km"]),
            )

            with grib_path.open("rb") as handle:
                for point in points:
                    row, col = index_sampler._reference_pixel(
                        point["latitude"],
                        point["longitude"],
                        float(meta["sub_satellite_lon"]),
                    )
                    index = index_sampler._grid_index(row, col)
                    raw = _read_packed_uint(
                        handle,
                        payload_offset,
                        payload_length,
                        index,
                        int(meta["bits_per_value"]),
                    )
                    value = _decode_simple(raw, meta)
                    point_indexes[point["id"]] = index
                    sampled[point["id"]] = sat._cloud_category(value)
        finally:
            grib_path.unlink(missing_ok=True)

    valid = [value for value in sampled.values() if value is not None]
    if not valid:
        raise RuntimeError("FCI CLM neposkytl platne low-memory vzorky v okoli observatore")

    cloudy = sum(valid)
    center = sampled.get("C")
    return {
        "product_id": product["product_id"],
        "time": product.get("time") or core.iso_z(core.utc_now()),
        "cloud_pct": round(100.0 * cloudy / len(valid), 1),
        "center_cloud_pct": None if center is None else float(center * 100),
        "valid_samples": len(valid),
        "sample_count": len(sampled),
        "points": sampled,
        "point_indexes": point_indexes,
        "sampler": "python-grib2-simple-packed",
        "packing_type": meta["packing_type"],
        "bits_per_value": meta["bits_per_value"],
        "grid": "MTG/FCI 2km 5568x5568",
        "processing_storage": "ram:/dev/shm",
    }


def install(core: Any) -> None:
    if getattr(core, "_SATELLITE_LOWMEM_PATCH_INSTALLED", False):
        return

    # Installed last: this intentionally replaces both the original nearest
    # neighbour sampler and the 12.4.2 ecCodes -i sampler.
    sat._sample_product = _sample_product

    sat.RELEASE_VERSION = RELEASE_VERSION
    index_sampler.RELEASE_VERSION = RELEASE_VERSION
    storage.RELEASE_VERSION = RELEASE_VERSION
    clm_map.RELEASE_VERSION = RELEASE_VERSION
    lowload.RELEASE_VERSION = RELEASE_VERSION
    satellite_ui.RELEASE_VERSION = RELEASE_VERSION
    core.APP_VERSION = RELEASE_VERSION
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._SATELLITE_LOWMEM_PATCH_INSTALLED = True
