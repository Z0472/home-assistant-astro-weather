"""Bounded-memory MTG/FCI CLM sampler for Astro Weather Backend 12.4.15.

The operational MTG/FCI Cloud Mask product currently uses EUMETSAT local
GRIB2 template 5.50002 (``grid_second_order``). ecCodes decodes that template
by materialising the complete 5568 x 5568 field, so even an indexed
``grib_get -i`` can consume roughly 600 MiB on a 2 GiB Raspberry Pi.

This patch keeps ecCodes only for small metadata reads. Simple packing is read
directly as before. Template 50002 is decoded as a bounded-memory stream:
the three compact group descriptor arrays are read from Section 7, spatial
differencing is reconstructed incrementally, and only the requested 17 CLM
samples are retained. There is deliberately no fallback to a full-field
eCodes decode.
"""
from __future__ import annotations

import gc
import math
import re
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

RELEASE_VERSION = "12.4.15"
MIN_AVAILABLE_MEMORY_BYTES = 192 * 1024 * 1024

_METADATA_KEYS = (
    "gridType,Nx,Ny,iScansNegatively,jScansPositively,"
    "jPointsAreConsecutive,alternativeRowScanning,"
    "latitudeOfSubSatellitePointInDegrees,longitudeOfSubSatellitePointInDegrees,"
    "dataRepresentationTemplateNumber,packingType,bitsPerValue,referenceValue,"
    "binaryScaleFactor,decimalScaleFactor,bitmapPresent"
)

_SECOND_ORDER_KEYS = (
    "widthOfFirstOrderValues,numberOfGroups,numberOfSecondOrderPackedValues,"
    "widthOfWidths,widthOfLengths,orderOfSPD,boustrophedonicOrdering,numberOfPoints"
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


def _parse_ints(text: str) -> list[int]:
    return [int(token) for token in re.findall(r"[-+]?\d+", str(text))]


def _load_second_order_metadata(core: Any, grib_path: Path, meta: dict[str, Any]) -> None:
    out = core.run_cmd(["grib_get", "-p", _SECOND_ORDER_KEYS, str(grib_path)], timeout=30)
    parts = str(out).strip().split()
    if len(parts) < 8:
        raise RuntimeError(f"FCI second-order metadata jsou neuplna: {out!r}")

    try:
        meta.update({
            "width_of_first_order_values": int(parts[0]),
            "number_of_groups": int(parts[1]),
            "number_of_second_order_values": int(parts[2]),
            "width_of_widths": int(parts[3]),
            "width_of_lengths": int(parts[4]),
            "order_of_spd": int(parts[5]),
            "boustrophedonic": int(parts[6]),
            "number_of_points": int(parts[7]),
        })
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"FCI second-order metadata nelze precist: {out!r}") from exc

    groups = int(meta["number_of_groups"])
    if not 0 < groups <= 65534:
        raise RuntimeError(f"Neocekavany numberOfGroups={groups}")

    for key in ("width_of_first_order_values", "width_of_widths", "width_of_lengths"):
        width = int(meta[key])
        if not 0 <= width <= 64:
            raise RuntimeError(f"Neocekavana sirka {key}={width}")

    order = int(meta["order_of_spd"])
    if not 0 <= order <= 3:
        raise RuntimeError(f"Nepodporovany orderOfSPD={order}")

    if int(meta["boustrophedonic"]) not in (0, 1):
        raise RuntimeError(f"Neocekavany boustrophedonicOrdering={meta['boustrophedonic']}")

    if order:
        width_out = core.run_cmd(["grib_get", "-p", "widthOfSPD", str(grib_path)], timeout=30)
        width_tokens = _parse_ints(str(width_out))
        if not width_tokens:
            raise RuntimeError(f"FCI widthOfSPD nelze precist: {width_out!r}")
        meta["width_of_spd"] = int(width_tokens[0])
        if not 1 <= int(meta["width_of_spd"]) <= 64:
            raise RuntimeError(f"Neocekavane widthOfSPD={meta['width_of_spd']}")

        spd_out = core.run_cmd(["grib_get", "-p", "SPD", str(grib_path)], timeout=30)
        spd = _parse_ints(str(spd_out))
        expected = order + 1
        if len(spd) != expected:
            raise RuntimeError(
                f"FCI SPD ma {len(spd)} hodnot, ocekavano {expected}: {spd_out!r}"
            )
        meta["spd"] = spd
    else:
        meta["width_of_spd"] = 0
        meta["spd"] = []


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

    if meta["bitmap_present"] != 0:
        raise RuntimeError(
            "FCI CLM obsahuje bitmapu; low-memory sampler ji zatim nepodporuje "
            "a full-field decode je z bezpecnostnich duvodu zakazan"
        )

    template = int(meta["data_representation_template"])
    packing = str(meta["packing_type"])

    if template == 0 and packing == "grid_simple":
        if not 0 <= meta["bits_per_value"] <= 32:
            raise RuntimeError(f"Neocekavane bitsPerValue={meta['bits_per_value']}")
        meta["lowmem_mode"] = "simple"
        return meta

    if template == 50002 and packing in (
        "grid_second_order",
        "grid_second_order_boustrophedonic",
    ):
        _load_second_order_metadata(core, grib_path, meta)
        meta["lowmem_mode"] = "second_order_50002"
        return meta

    raise RuntimeError(
        "FCI CLM pouziva nepodporovane GRIB2 baleni "
        f"template={template}, packingType={packing!r}; "
        "z bezpecnostnich duvodu nepouzivam pametove narocny full-field decode"
    )


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
    return (
        float(meta["reference_value"])
        + float(raw) * math.ldexp(1.0, int(meta["binary_scale_factor"]))
    ) * (10.0 ** (-int(meta["decimal_scale_factor"])))


def _read_aligned_uint_array(
    handle: BinaryIO,
    offset: int,
    payload_end: int,
    count: int,
    width: int,
) -> tuple[list[int], int]:
    if count < 0:
        raise RuntimeError(f"Zaporny pocet packed hodnot: {count}")
    if width == 0:
        return [0] * count, offset

    byte_count = (count * width + 7) // 8
    if offset + byte_count > payload_end:
        raise RuntimeError(
            f"FCI descriptor pole presahuje Section 7: offset={offset}, bytes={byte_count}"
        )
    handle.seek(offset)
    blob = handle.read(byte_count)
    if len(blob) != byte_count:
        raise RuntimeError("FCI descriptor pole je zkracene")

    values: list[int] = []
    mask = (1 << width) - 1
    bit_pos = 0
    for _ in range(count):
        byte_start = bit_pos // 8
        bit_offset = bit_pos % 8
        width_bytes = (bit_offset + width + 7) // 8
        chunk = int.from_bytes(blob[byte_start:byte_start + width_bytes], "big")
        shift = width_bytes * 8 - bit_offset - width
        values.append((chunk >> shift) & mask)
        bit_pos += width

    return values, offset + byte_count


def _second_order_layout(
    handle: BinaryIO,
    payload_offset: int,
    payload_length: int,
    meta: dict[str, Any],
) -> tuple[list[int], list[int], list[int], int, int]:
    end = payload_offset + payload_length
    groups = int(meta["number_of_groups"])
    cursor = payload_offset

    widths, cursor = _read_aligned_uint_array(
        handle, cursor, end, groups, int(meta["width_of_widths"])
    )
    lengths, cursor = _read_aligned_uint_array(
        handle, cursor, end, groups, int(meta["width_of_lengths"])
    )
    first_orders, cursor = _read_aligned_uint_array(
        handle, cursor, end, groups, int(meta["width_of_first_order_values"])
    )

    order = int(meta["order_of_spd"])
    count = sum(lengths)
    expected_packed = int(meta["number_of_second_order_values"])
    if count != expected_packed:
        raise RuntimeError(
            f"FCI second-order groupLengths suma={count}, "
            f"numberOfSecondOrderPackedValues={expected_packed}"
        )

    number_of_points = int(meta["number_of_points"])
    if count + order != number_of_points:
        raise RuntimeError(
            f"FCI second-order pocet bodu nesedi: groups={count} + SPD={order}, "
            f"numberOfPoints={number_of_points}"
        )

    needed_bits = sum(width * length for width, length in zip(widths, lengths))
    residual_bytes = end - cursor
    if needed_bits > residual_bytes * 8:
        raise RuntimeError(
            f"FCI second-order residualy jsou zkracene: potreba {needed_bits} bitu, "
            f"k dispozici {residual_bytes * 8}"
        )

    return widths, lengths, first_orders, cursor, residual_bytes


def _group_blob(
    handle: BinaryIO,
    residual_offset: int,
    residual_length: int,
    bit_pos: int,
    width: int,
    count: int,
) -> tuple[bytes, int]:
    if width == 0 or count == 0:
        return b"", 0

    bit_count = width * count
    first_byte = bit_pos // 8
    start_bit = bit_pos % 8
    byte_count = (start_bit + bit_count + 7) // 8
    if first_byte + byte_count > residual_length:
        raise RuntimeError("FCI second-order group presahuje packed residualy")

    handle.seek(residual_offset + first_byte)
    blob = handle.read(byte_count)
    if len(blob) != byte_count:
        raise RuntimeError("FCI second-order group je zkracena")
    return blob, start_bit


def _raw_from_blob(blob: bytes, bit_pos: int, width: int) -> int:
    byte_start = bit_pos // 8
    bit_offset = bit_pos % 8
    byte_count = (bit_offset + width + 7) // 8
    chunk = int.from_bytes(blob[byte_start:byte_start + byte_count], "big")
    shift = byte_count * 8 - bit_offset - width
    return (chunk >> shift) & ((1 << width) - 1)


def _bulk_advance(
    order: int,
    state: dict[str, int],
    first_order: int,
    bias: int,
    group_width: int,
    group_length: int,
    blob: bytes,
    blob_start_bit: int,
) -> None:
    if group_length <= 0 or order == 0:
        return

    raw1 = raw2 = raw3 = 0
    if group_width:
        local_bit = blob_start_bit
        for j in range(group_length):
            raw = _raw_from_blob(blob, local_bit, group_width)
            local_bit += group_width
            raw1 += raw
            if order >= 2:
                k = group_length - j
                raw2 += k * raw
                if order >= 3:
                    raw3 += (k * (k + 1) // 2) * raw

    base = int(first_order) + int(bias)
    s1 = group_length * base + raw1

    if order == 1:
        state["value"] += s1
        return

    triangle = group_length * (group_length + 1) // 2
    s2 = triangle * base + raw2

    if order == 2:
        old_d1 = state["d1"]
        state["value"] += group_length * old_d1 + s2
        state["d1"] = old_d1 + s1
        return

    tetrahedron = group_length * (group_length + 1) * (group_length + 2) // 6
    s3 = tetrahedron * base + raw3
    old_d1 = state["d1"]
    old_d2 = state["d2"]
    state["value"] += group_length * old_d1 + triangle * old_d2 + s3
    state["d1"] = old_d1 + group_length * old_d2 + s2
    state["d2"] = old_d2 + s1


def _decode_second_order_targets(
    handle: BinaryIO,
    payload_offset: int,
    payload_length: int,
    meta: dict[str, Any],
    target_indexes: list[int],
) -> dict[int, int]:
    targets = sorted(set(int(value) for value in target_indexes))
    if not targets:
        return {}

    number_of_points = int(meta["number_of_points"])
    if targets[0] < 0 or targets[-1] >= number_of_points:
        raise RuntimeError(
            f"FCI cilovy index je mimo pole 0..{number_of_points - 1}: "
            f"{targets[0]}..{targets[-1]}"
        )

    widths, lengths, first_orders, residual_offset, residual_length = _second_order_layout(
        handle, payload_offset, payload_length, meta
    )

    order = int(meta["order_of_spd"])
    spd = [int(value) for value in meta.get("spd", [])]
    bias = spd[order] if order else 0
    results: dict[int, int] = {}
    target_set = set(targets)
    max_target = targets[-1]

    state: dict[str, int] = {}
    if order == 1:
        state["value"] = spd[0]
        if 0 in target_set:
            results[0] = spd[0]
    elif order == 2:
        state["d1"] = spd[1] - spd[0]
        state["value"] = spd[1]
        if 0 in target_set:
            results[0] = spd[0]
        if 1 in target_set:
            results[1] = spd[1]
    elif order == 3:
        state["d1"] = spd[2] - spd[1]
        state["d2"] = state["d1"] - (spd[1] - spd[0])
        state["value"] = spd[2]
        if 0 in target_set:
            results[0] = spd[0]
        if 1 in target_set:
            results[1] = spd[1]
        if 2 in target_set:
            results[2] = spd[2]

    current_index = order
    residual_bit_pos = 0

    for width, length, first_order in zip(widths, lengths, first_orders):
        length = int(length)
        width = int(width)
        if length < 0:
            raise RuntimeError(f"FCI groupLength je zaporna: {length}")
        if current_index > max_target:
            break

        group_end = current_index + length - 1
        has_target = (
            length > 0
            and any(current_index <= target <= group_end for target in targets)
        )

        if order == 0 and not has_target:
            current_index += length
            residual_bit_pos += width * length
            continue

        blob, start_bit = _group_blob(
            handle,
            residual_offset,
            residual_length,
            residual_bit_pos,
            width,
            length,
        )

        if not has_target and group_end < max_target:
            _bulk_advance(
                order,
                state,
                int(first_order),
                bias,
                width,
                length,
                blob,
                start_bit,
            )
            current_index += length
            residual_bit_pos += width * length
            continue

        local_bit = start_bit
        for _ in range(length):
            if current_index > max_target:
                break
            raw = 0
            if width:
                raw = _raw_from_blob(blob, local_bit, width)
                local_bit += width
            packed = int(first_order) + raw

            if order == 0:
                value = packed
            elif order == 1:
                state["value"] += packed + bias
                value = state["value"]
            elif order == 2:
                state["d1"] += packed + bias
                state["value"] += state["d1"]
                value = state["value"]
            else:
                state["d2"] += packed + bias
                state["d1"] += state["d2"]
                state["value"] += state["d1"]
                value = state["value"]

            if current_index in target_set:
                results[current_index] = int(value)
            current_index += 1

        residual_bit_pos += width * length

    missing = [index for index in targets if index not in results]
    if missing:
        raise RuntimeError(f"FCI second-order decoder nenasel cilove indexy: {missing}")
    return results


def _coded_index(row: int, col: int, meta: dict[str, Any]) -> int:
    nx = int(meta["nx"])
    if int(meta.get("boustrophedonic", 0)) and row % 2:
        col = nx - 1 - col
    return row * nx + col


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
        del payload
        gc.collect()

        sampled: dict[str, int | None] = {}
        point_indexes: dict[str, int] = {}
        coded_indexes: dict[str, int] = {}
        try:
            meta = _metadata(core, grib_path)
            payload_offset, payload_length = _section7_range(grib_path)
            points = spatial.build_spatial_points(
                float(options["latitude"]),
                float(options["longitude"]),
                int(options["satellite_radius_km"]),
            )

            with grib_path.open("rb") as handle:
                if meta["lowmem_mode"] == "simple":
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
                        coded_indexes[point["id"]] = index
                        sampled[point["id"]] = sat._cloud_category(value)
                    sampler = "python-grib2-simple-packed"
                else:
                    for point in points:
                        row, col = index_sampler._reference_pixel(
                            point["latitude"],
                            point["longitude"],
                            float(meta["sub_satellite_lon"]),
                        )
                        normal_index = index_sampler._grid_index(row, col)
                        coded_index = _coded_index(row, col, meta)
                        point_indexes[point["id"]] = normal_index
                        coded_indexes[point["id"]] = coded_index

                    raw_targets = _decode_second_order_targets(
                        handle,
                        payload_offset,
                        payload_length,
                        meta,
                        list(coded_indexes.values()),
                    )
                    for point in points:
                        raw = raw_targets[coded_indexes[point["id"]]]
                        value = _decode_simple(raw, meta)
                        sampled[point["id"]] = sat._cloud_category(value)
                    sampler = "python-grib2-second-order-stream"
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
        "coded_indexes": coded_indexes,
        "sampler": sampler,
        "packing_type": meta["packing_type"],
        "packing_template": meta["data_representation_template"],
        "order_of_spd": meta.get("order_of_spd"),
        "grid": "MTG/FCI 2km 5568x5568",
        "processing_storage": "ram:/dev/shm",
    }


def install(core: Any) -> None:
    if getattr(core, "_SATELLITE_LOWMEM_PATCH_INSTALLED", False):
        return

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
