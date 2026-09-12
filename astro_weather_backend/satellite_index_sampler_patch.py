"""Low-memory MTG/FCI CLM sampler for Astro Weather Backend 12.4.2.

The ecCodes nearest-neighbour path (``grib_get -l``) builds geolocation state for
the 5568x5568 MTG full-disc ``space_view`` grid.  On small Home Assistant hosts
that process can be killed by the kernel before it returns even one value.

FCI CLM uses the fixed 2 km MTG reference grid, so this patch performs the
geostationary navigation in Python, converts each requested lat/lon to the
corresponding grid index, and asks ecCodes only for that indexed value via
``grib_get -i``.  No full latitude/longitude arrays are constructed.
"""
from __future__ import annotations

import math
import shutil
from typing import Any

import satellite_nowcast_patch as sat
import satellite_lowload_patch as lowload
import satellite_card_map_patch as clm_map
import storage_protection_patch as storage
import spatial_cloud_patch as spatial

RELEASE_VERSION = "12.4.2"

# MTG/FCI 2 km full-disc reference grid, EUMETSAT FCI L1c reference grid.
FCI_NX = 5568
FCI_NY = 5568
FCI_FIRST_AZIMUTH_RAD = 0.1555618893
FCI_FIRST_ELEVATION_RAD = -0.1555618893
FCI_GRID_SAMPLING_RAD = 5.5887153e-05

# MTG geostationary projection parameters.
MTG_SEMI_MAJOR_M = 6378137.0
MTG_SEMI_MINOR_M = 6356752.0
MTG_PERSPECTIVE_HEIGHT_M = 35786400.0


def _nearest_int(value: float) -> int:
    return int(math.floor(value + 0.5))


def _scan_angles(latitude: float, longitude: float, sub_satellite_lon: float) -> tuple[float, float]:
    """Return Meteosat geostationary scan angles (x east-positive, y north-positive).

    This is the ellipsoidal forward ``geos`` navigation with the Meteosat
    sweep-y convention.  The equations match the normalized geostationary
    projection used by the MTG reference grid.
    """
    phi = math.radians(float(latitude))
    lon_delta = ((float(longitude) - float(sub_satellite_lon) + 180.0) % 360.0) - 180.0
    lam = math.radians(lon_delta)

    radius_p = MTG_SEMI_MINOR_M / MTG_SEMI_MAJOR_M
    radius_p2 = radius_p * radius_p
    phi_gc = math.atan(radius_p2 * math.tan(phi))
    cos_phi = math.cos(phi_gc)
    sin_phi = math.sin(phi_gc)
    r = radius_p / math.hypot(radius_p * cos_phi, sin_phi)

    vx = r * math.cos(lam) * cos_phi
    vy = r * math.sin(lam) * cos_phi
    vz = r * sin_phi
    radius_g = 1.0 + MTG_PERSPECTIVE_HEIGHT_M / MTG_SEMI_MAJOR_M

    # Same visibility test used by the ellipsoidal geostationary projection.
    if ((radius_g - vx) * vx - vy * vy - vz * vz / radius_p2) < 0.0:
        raise ValueError("Bod nelezi ve viditelnem disku MTG")

    tmp = radius_g - vx
    x_angle = math.atan(vy / tmp)
    y_angle = math.atan(vz / math.hypot(vy, tmp))
    return x_angle, y_angle


def _reference_pixel(latitude: float, longitude: float, sub_satellite_lon: float) -> tuple[int, int]:
    """Map WGS84 lat/lon to the nearest zero-based FCI 2 km row/column."""
    x_angle, y_angle = _scan_angles(latitude, longitude, sub_satellite_lon)

    # FCI defines its E-W viewing angle with the opposite sign to the standard
    # geostationary x scan angle.  The first reference-grid pixel is SW.
    fci_azimuth = -x_angle
    col_f = (FCI_FIRST_AZIMUTH_RAD - fci_azimuth) / FCI_GRID_SAMPLING_RAD
    row_f = (y_angle - FCI_FIRST_ELEVATION_RAD) / FCI_GRID_SAMPLING_RAD
    col = _nearest_int(col_f)
    row = _nearest_int(row_f)
    if not (0 <= col < FCI_NX and 0 <= row < FCI_NY):
        raise ValueError(f"Vypocteny MTG pixel je mimo full-disc mrizku: row={row}, col={col}")
    return row, col


def _grid_metadata(core: Any, grib_path: Any) -> dict[str, Any]:
    keys = (
        "gridType,Nx,Ny,iScansNegatively,jScansPositively,"
        "jPointsAreConsecutive,alternativeRowScanning,"
        "latitudeOfSubSatellitePointInDegrees,longitudeOfSubSatellitePointInDegrees"
    )
    out = core.run_cmd(["grib_get", "-p", keys, str(grib_path)], timeout=30)
    parts = str(out).strip().split()
    if len(parts) < 9:
        raise RuntimeError(f"FCI GRIB metadata jsou neuplna: {out!r}")
    try:
        return {
            "grid_type": parts[0],
            "nx": int(parts[1]),
            "ny": int(parts[2]),
            "i_negative": int(parts[3]),
            "j_positive": int(parts[4]),
            "j_consecutive": int(parts[5]),
            "alternate_rows": int(parts[6]),
            "sub_satellite_lat": float(parts[7]),
            "sub_satellite_lon": float(parts[8]),
        }
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"FCI GRIB metadata nelze precist: {out!r}") from exc


def _validate_grid(meta: dict[str, Any]) -> None:
    if meta["grid_type"] != "space_view":
        raise RuntimeError(f"Neocekavany FCI gridType={meta['grid_type']!r}, ocekavan space_view")
    if (meta["nx"], meta["ny"]) != (FCI_NX, FCI_NY):
        raise RuntimeError(
            f"Neocekavana FCI mrizka {meta['nx']}x{meta['ny']}, ocekavano {FCI_NX}x{FCI_NY}"
        )
    if abs(meta["sub_satellite_lat"]) > 0.01:
        raise RuntimeError(f"Neocekavana sub-satelitni sirka {meta['sub_satellite_lat']}")
    # Operational FCI full-disc CLM is row-major from SW to NE.  Reject rather
    # than guess if the producer ever changes scanning order.
    expected = (0, 1, 0, 0)
    actual = (
        meta["i_negative"], meta["j_positive"],
        meta["j_consecutive"], meta["alternate_rows"],
    )
    if actual != expected:
        raise RuntimeError(
            "Neocekavany scanningMode FCI "
            f"(iNeg,jPos,jConsecutive,alternate)={actual}, ocekavano {expected}"
        )


def _grid_index(row: int, col: int) -> int:
    return row * FCI_NX + col


def _sample_product(core: Any, options: dict[str, Any], product: dict[str, Any], token: str) -> dict[str, Any]:
    if shutil.which("grib_get") is None:
        raise RuntimeError("ecCodes/grib_get neni v kontejneru k dispozici")

    payload = sat._download_product(str(product["product_id"]), token)
    grib_path = sat._write_grib_from_download(core, str(product["product_id"]), payload)
    points = spatial.build_spatial_points(
        float(options["latitude"]),
        float(options["longitude"]),
        int(options["satellite_radius_km"]),
    )

    sampled: dict[str, int | None] = {}
    point_indexes: dict[str, int] = {}
    try:
        meta = _grid_metadata(core, grib_path)
        _validate_grid(meta)
        lon0 = float(meta["sub_satellite_lon"])

        for point in points:
            row, col = _reference_pixel(point["latitude"], point["longitude"], lon0)
            index = _grid_index(row, col)
            point_indexes[point["id"]] = index
            out = core.run_cmd([
                "grib_get", "-F", "%.8f", "-i", str(index), str(grib_path),
            ], timeout=30)
            values = core.parse_number_lines(out)
            sampled[point["id"]] = sat._cloud_category(values[-1] if values else None)
    finally:
        grib_path.unlink(missing_ok=True)

    valid = [value for value in sampled.values() if value is not None]
    if not valid:
        raise RuntimeError("FCI CLM neposkytl platne indexove vzorky v okoli observatore")
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
        "sampler": "eccodes-direct-index",
        "grid": "MTG/FCI 2km 5568x5568",
        "processing_storage": "ram:/dev/shm",
    }


def install(core: Any) -> None:
    if getattr(core, "_SATELLITE_INDEX_SAMPLER_PATCH_INSTALLED", False):
        return

    sat._sample_product = _sample_product
    sat.RELEASE_VERSION = RELEASE_VERSION
    storage.RELEASE_VERSION = RELEASE_VERSION
    clm_map.RELEASE_VERSION = RELEASE_VERSION
    lowload.RELEASE_VERSION = RELEASE_VERSION
    core.APP_VERSION = RELEASE_VERSION
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._SATELLITE_INDEX_SAMPLER_PATCH_INSTALLED = True
