"""Satellite/UI refinements for Astro Weather Backend 12.4.12.

Keeps the spatially-correct satellite comparison from 12.4.9, the compact main
card from 12.4.10, and the EUMETView IR10.5 history player from 12.4.11.
Main card v35 removes the duplicate selected-night date from the expanded
section and places the decision reason beside the verdict on wide screens.
"""
from __future__ import annotations

import math
from typing import Any

import satellite_nowcast_patch as sat
import satellite_card_map_patch as clm_map
import satellite_lowload_patch as lowload
import satellite_index_sampler_patch as index_sampler
import storage_protection_patch as storage

RELEASE_VERSION = "12.4.12"
ASTRO_CARD_VERSION = 35
SATELLITE_CARD_VERSION = 9
VISUAL_RADIUS_KM = 150.0
VISUAL_SIZE_PX = 900
VISUAL_HISTORY_FRAMES = 20
VISUAL_HISTORY_STEP_MINUTES = 10


def _regional_ir_url(options: dict[str, Any], radius_km: float = VISUAL_RADIUS_KM) -> str:
    """Build a latest-image EUMETView WMS request around the observatory."""
    lat = float(options["latitude"])
    lon = float(options["longitude"])
    radius = max(50.0, min(250.0, float(radius_km)))

    lat_delta = radius / 111.32
    cos_lat = max(0.20, abs(math.cos(math.radians(lat))))
    lon_delta = radius / (111.32 * cos_lat)

    south = max(-79.0, lat - lat_delta)
    north = min(79.0, lat + lat_delta)
    west = max(-79.0, lon - lon_delta)
    east = min(79.0, lon + lon_delta)

    bbox = f"{south:.5f},{west:.5f},{north:.5f},{east:.5f}"
    return (
        "https://view.eumetsat.int/geoserver/wms?"
        "service=WMS&version=1.3.0&request=GetMap&"
        "layers=mtg_fd:ir105_hrfi,backgrounds:ne_10m_coastline,backgrounds:ne_boundary_lines_land&"
        f"bbox={bbox}&width={VISUAL_SIZE_PX}&height={VISUAL_SIZE_PX}&crs=EPSG:4326&"
        "styles=&format=image/jpeg&bgcolor=0xCCCCCC"
    )


def _comparison_using_center(core: Any, options: dict[str, Any], satellite: dict[str, Any], original: Any) -> dict[str, Any]:
    """Compare point-model cloud with the CLM sample at the same location."""
    center = sat._safe(satellite.get("center_cloud_pct"))
    area = sat._safe(satellite.get("cloud_pct"))
    radius = int(satellite.get("radius_km") or options.get("satellite_radius_km") or 30)
    if center is None:
        return {
            "state": "unavailable",
            "available": False,
            "backend_version": RELEASE_VERSION,
            "satellite_area_cloud_pct": area,
            "satellite_as_of": satellite.get("as_of"),
            "satellite_scope": "observatory_center",
            "satellite_radius_km": radius,
            "reason": "CLM vzorek přímo nad observatoří není k dispozici.",
        }

    local_satellite = dict(satellite)
    local_satellite["cloud_pct"] = center
    result = dict(original(core, options, local_satellite))
    result["satellite_local_cloud_pct"] = round(center, 1)
    result["satellite_area_cloud_pct"] = None if area is None else round(area, 1)
    result["satellite_scope"] = "observatory_center"
    result["satellite_radius_km"] = radius
    return result


def install(core: Any) -> None:
    if getattr(core, "_SATELLITE_UI_PATCH_INSTALLED", False):
        return

    old_document = sat._satellite_document
    old_comparison = sat._comparison

    def satellite_document(core_arg: Any, options: dict[str, Any]) -> dict[str, Any]:
        document = dict(old_document(core_arg, options))
        document["visual_url"] = _regional_ir_url(options)
        document["visual_radius_km"] = int(VISUAL_RADIUS_KM)
        document["visual_size_px"] = VISUAL_SIZE_PX
        document["visual_center"] = {
            "latitude": round(float(options["latitude"]), 5),
            "longitude": round(float(options["longitude"]), 5),
        }
        document["visual_history_supported"] = True
        document["visual_history_frames"] = VISUAL_HISTORY_FRAMES
        document["visual_history_step_minutes"] = VISUAL_HISTORY_STEP_MINUTES
        document["visual_history_source"] = "EUMETView WMS time dimension"
        return document

    sat._satellite_document = satellite_document
    sat._comparison = lambda core_arg, options, satellite: _comparison_using_center(
        core_arg, options, satellite, old_comparison
    )

    # v35 imports v34 -> v33 -> v32 -> v31 -> v30. v9 imports v8 -> v7 -> v6
    # -> v5 -> v4 -> v3. Install the full dependency chain so clean Home
    # Assistant installs are self-contained and independent of browser cache.
    core.ASTRO_START_CARD_VERSION = ASTRO_CARD_VERSION
    sat.SATELLITE_CARD_VERSION = SATELLITE_CARD_VERSION

    installs = []
    for source, target in core.DASHBOARD_CARD_INSTALLS:
        if target.startswith("astro-satellite-card-v"):
            continue
        if (
            target.startswith("astro-start-card-v31")
            or target.startswith("astro-start-card-v32")
            or target.startswith("astro-start-card-v33")
            or target.startswith("astro-start-card-v34")
            or target.startswith("astro-start-card-v35")
        ):
            continue
        installs.append((source, target))

    if not any(target == "astro-start-card-v30.js" for _, target in installs):
        installs.append(("astro-start-card-v30.js", "astro-start-card-v30.js"))
    installs.append(("astro-start-card-v31.js", "astro-start-card-v31.js"))
    installs.append(("astro-start-card-v32.js", "astro-start-card-v32.js"))
    installs.append(("astro-start-card-v33.js", "astro-start-card-v33.js"))
    installs.append(("astro-start-card-v34.js", "astro-start-card-v34.js"))
    installs.append(("astro-start-card-v35.js", "astro-start-card-v35.js"))

    installs.append(("astro-satellite-card.js", "astro-satellite-card-v3.js"))
    installs.append(("astro-satellite-card-v4.js", "astro-satellite-card-v4.js"))
    installs.append(("astro-satellite-card-v5.js", "astro-satellite-card-v5.js"))
    installs.append(("astro-satellite-card-v6.js", "astro-satellite-card-v6.js"))
    installs.append(("astro-satellite-card-v7.js", "astro-satellite-card-v7.js"))
    installs.append(("astro-satellite-card-v8.js", "astro-satellite-card-v8.js"))
    installs.append(("astro-satellite-card-v9.js", "astro-satellite-card-v9.js"))
    core.DASHBOARD_CARD_INSTALLS = tuple(installs)

    sat.RELEASE_VERSION = RELEASE_VERSION
    clm_map.RELEASE_VERSION = RELEASE_VERSION
    lowload.RELEASE_VERSION = RELEASE_VERSION
    index_sampler.RELEASE_VERSION = RELEASE_VERSION
    storage.RELEASE_VERSION = RELEASE_VERSION
    core.APP_VERSION = RELEASE_VERSION
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._SATELLITE_UI_PATCH_INSTALLED = True
