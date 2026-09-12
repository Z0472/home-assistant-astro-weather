"""RAM-backed temporary GRIB processing for Astro Weather Backend 12.4.0.

Large transient satellite and decompressed ALADIN files must not churn the Home
Assistant SD card.  Persistent compressed ALADIN cache and tiny state JSON files
remain under /data/cache, while transient GRIB payloads are processed in the
container tmpfs (/dev/shm) and removed immediately after point extraction.
"""
from __future__ import annotations

import bz2
import io
import os
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Any

import satellite_nowcast_patch as sat

RELEASE_VERSION = "12.4.0"
RAM_TMP_DIR = Path("/dev/shm")
RAM_RESERVE_BYTES = 4 * 1024 * 1024
ALADIN_START_HEADROOM_BYTES = 24 * 1024 * 1024
_RAM_IO_LOCK = threading.Lock()


def _human_mib(value: int) -> str:
    return f"{value / (1024 * 1024):.1f} MiB"


def _ram_root(required_bytes: int = 0) -> Path:
    root = RAM_TMP_DIR
    if not root.exists() or not root.is_dir():
        raise RuntimeError(f"RAM tmpfs {root} neni dostupny; odmitam zapisovat velky GRIB na SD kartu")
    if not os.access(root, os.W_OK | os.X_OK):
        raise RuntimeError(f"RAM tmpfs {root} neni zapisovatelny")

    usage = shutil.disk_usage(root)
    required = max(0, int(required_bytes)) + RAM_RESERVE_BYTES
    if usage.free < required:
        raise RuntimeError(
            f"RAM tmpfs {root} nema dost mista: volno {_human_mib(usage.free)}, "
            f"potreba alespon {_human_mib(required)}"
        )
    return root


def _new_ram_file(prefix: str, suffix: str, required_bytes: int = 0) -> Path:
    root = _ram_root(required_bytes)
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=str(root))
    os.close(fd)
    return Path(name)


def _write_satellite_grib_to_ram(payload: bytes) -> Path:
    """Return a temporary GRIB2 path in tmpfs without ever writing the SIP ZIP to disk."""
    if payload[:4] == b"GRIB":
        target = _new_ram_file("astro_sat_", ".grib2", len(payload))
        try:
            target.write_bytes(payload)
            return target
        except Exception:
            target.unlink(missing_ok=True)
            raise

    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise RuntimeError("EUMETSAT CLM download neni GRIB ani platny ZIP/SIP") from exc

    with archive:
        candidates = [
            info for info in archive.infolist()
            if not info.is_dir()
            and info.filename.lower().endswith((".bin", ".grb", ".grib", ".grib2"))
        ]
        if not candidates:
            raise RuntimeError("EUMETSAT CLM balicek neobsahuje GRIB-2 soubor")

        info = candidates[0]
        target = _new_ram_file("astro_sat_", ".grib2", int(info.file_size))
        try:
            with archive.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
        except Exception:
            target.unlink(missing_ok=True)
            raise

    try:
        with target.open("rb") as handle:
            magic = handle.read(4)
        if magic != b"GRIB":
            raise RuntimeError("Rozbaleny EUMETSAT .bin nema signaturu GRIB")
        return target
    except Exception:
        target.unlink(missing_ok=True)
        raise


def _sample_satellite_product_ram(
    core: Any,
    options: dict[str, Any],
    product: dict[str, Any],
    token: str,
) -> dict[str, Any]:
    if shutil.which("grib_get") is None:
        raise RuntimeError("ecCodes/grib_get neni v kontejneru k dispozici")

    # The compressed SIP is kept only in Python memory.  Serialize the large
    # tmpfs work with ALADIN so the Raspberry Pi never needs two large GRIB
    # scratch files at once.
    payload = sat._download_product(str(product["product_id"]), token)
    with _RAM_IO_LOCK:
        grib_path = _write_satellite_grib_to_ram(payload)
        points = sat.spatial.build_spatial_points(
            float(options["latitude"]),
            float(options["longitude"]),
            int(options["satellite_radius_km"]),
        )
        sampled: dict[str, int | None] = {}
        try:
            for point in points:
                out = core.run_cmd([
                    "grib_get",
                    "-F", "%.8f",
                    "-l", f"{point['latitude']:.6f},{point['longitude']:.6f},1",
                    str(grib_path),
                ], timeout=60)
                values = core.parse_number_lines(out)
                sampled[point["id"]] = sat._cloud_category(values[-1] if values else None)
        finally:
            grib_path.unlink(missing_ok=True)

    valid = [value for value in sampled.values() if value is not None]
    if not valid:
        raise RuntimeError("FCI CLM neposkytl platne vzorky v okoli observatore")

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
        "processing_storage": f"ram:{RAM_TMP_DIR}",
    }


def _extract_aladin_point_series_ram(core: Any, bz_path: Path, lat: float, lon: float) -> dict[str, float]:
    """Decompress an ALADIN .bz2 cache entry into tmpfs, never next to the SD cache file."""
    with _RAM_IO_LOCK:
        grib_path = _new_ram_file(
            "astro_aladin_",
            ".grb",
            ALADIN_START_HEADROOM_BYTES,
        )
        try:
            try:
                with bz2.open(bz_path, "rb") as src, grib_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
            except OSError as exc:
                raise RuntimeError(
                    f"ALADIN GRIB se nevejde do RAM tmpfs {RAM_TMP_DIR}; "
                    "na SD kartu z bezpecnostnich duvodu nepadam"
                ) from exc

            times = core.grib_message_times(grib_path)
            values_out = core.run_cmd([
                "grib_get",
                "-F", "%.8f",
                "-l", f"{lat:.6f},{lon:.6f},1",
                str(grib_path),
            ], timeout=180)
            values = core.parse_number_lines(values_out)

            if len(times) != len(values):
                raise RuntimeError(
                    f"GRIB pocet casu {len(times)} != pocet hodnot {len(values)} ({bz_path.name})"
                )

            unit, global_max = core.grib_unit_and_global_max(grib_path)
            return {
                stamp: core.cloud_to_percent(raw, unit, global_max)
                for stamp, raw in zip(times, values)
            }
        finally:
            grib_path.unlink(missing_ok=True)


def install(core: Any) -> None:
    if getattr(core, "_STORAGE_PROTECTION_PATCH_INSTALLED", False):
        return

    # Keep the persistent compressed ALADIN cache as-is, but replace only its
    # decompression/extraction stage.  Satellite download/extraction is fully
    # transient and stays in RAM.
    core.extract_grib_point_series = lambda bz_path, lat, lon: _extract_aladin_point_series_ram(
        core, bz_path, lat, lon
    )
    sat._sample_product = lambda core_arg, options, product, token: _sample_satellite_product_ram(
        core_arg, options, product, token
    )

    core.log(
        f"SD OCHRANA: satelitni a rozbalena ALADIN GRIB data se zpracovavaji v RAM ({RAM_TMP_DIR}); "
        "na /data zustava jen mala cache a komprimovany aktualni ALADIN run."
    )
    core._STORAGE_PROTECTION_PATCH_INSTALLED = True
