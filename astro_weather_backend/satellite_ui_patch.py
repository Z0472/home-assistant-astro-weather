"""Satellite UI refinements for Astro Weather Backend 12.4.5.

Keeps the live satellite/model agreement only in today's top summary card and
serves a compact 150 km radius EUMETView IR10.5 view centred on the configured
observatory. The IR image remains square; satellite card v4 renders a larger,
cleaner panel and overlays only the essential 15/30 km CLM geometry without
labels inside the image.
"""
from __future__ import annotations

import math
from typing import Any

import satellite_nowcast_patch as sat
import satellite_card_map_patch as clm_map
import satellite_lowload_patch as lowload
import satellite_index_sampler_patch as index_sampler
import storage_protection_patch as storage

RELEASE_VERSION = "12.4.5"
ASTRO_CARD_VERSION = 30
SATELLITE_CARD_VERSION = 4
VISUAL_RADIUS_KM = 150.0
VISUAL_SIZE_PX = 900


def _regional_ir_url(options: dict[str, Any], radius_km: float = VISUAL_RADIUS_KM) -> str:
    """Build a latest-image EUMETView WMS request around the observatory.

    WMS 1.3.0 + EPSG:4326 uses latitude/longitude axis order in BBOX. The
    longitude extent is adjusted for latitude so the requested physical area is
    approximately square with the chosen radius in kilometres.
    """
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

    # EPSG:4326 axis order for WMS 1.3.0 is latitude, longitude.
    bbox = f"{south:.5f},{west:.5f},{north:.5f},{east:.5f}"
    return (
        "https://view.eumetsat.int/geoserver/wms?"
        "service=WMS&version=1.3.0&request=GetMap&"
        "layers=mtg_fd:ir105_hrfi,backgrounds:ne_10m_coastline,backgrounds:ne_boundary_lines_land&"
        f"bbox={bbox}&width={VISUAL_SIZE_PX}&height={VISUAL_SIZE_PX}&crs=EPSG:4326&"
        "styles=&format=image/jpeg&bgcolor=0xCCCCCC"
    )


def install(core: Any) -> None:
    if getattr(core, "_SATELLITE_UI_PATCH_INSTALLED", False):
        return

    old_document = sat._satellite_document

    def satellite_document(core_arg: Any, options: dict[str, Any]) -> dict[str, Any]:
        document = dict(old_document(core_arg, options))
        document["visual_url"] = _regional_ir_url(options)
        document["visual_radius_km"] = int(VISUAL_RADIUS_KM)
        document["visual_size_px"] = VISUAL_SIZE_PX
        document["visual_center"] = {
            "latitude": round(float(options["latitude"]), 5),
            "longitude": round(float(options["longitude"]), 5),
        }
        return document

    sat._satellite_document = satellite_document

    # v4 is a small wrapper over the proven v3 card. Install both files so a
    # clean Home Assistant installation has the import dependency available.
    core.ASTRO_START_CARD_VERSION = ASTRO_CARD_VERSION
    sat.SATELLITE_CARD_VERSION = SATELLITE_CARD_VERSION

    installs = []
    for source, target in core.DASHBOARD_CARD_INSTALLS:
        if target.startswith("astro-satellite-card-v"):
            continue
        installs.append((source, target))
    if not any(target == f"astro-start-card-v{ASTRO_CARD_VERSION}.js" for _, target in installs):
        installs.append((f"astro-start-card-v{ASTRO_CARD_VERSION}.js", f"astro-start-card-v{ASTRO_CARD_VERSION}.js"))
    installs.append(("astro-satellite-card.js", "astro-satellite-card-v3.js"))
    installs.append((f"astro-satellite-card-v{SATELLITE_CARD_VERSION}.js", f"astro-satellite-card-v{SATELLITE_CARD_VERSION}.js"))
    core.DASHBOARD_CARD_INSTALLS = tuple(installs)

    sat.RELEASE_VERSION = RELEASE_VERSION
    clm_map.RELEASE_VERSION = RELEASE_VERSION
    lowload.RELEASE_VERSION = RELEASE_VERSION
    index_sampler.RELEASE_VERSION = RELEASE_VERSION
    storage.RELEASE_VERSION = RELEASE_VERSION
    core.APP_VERSION = RELEASE_VERSION
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._SATELLITE_UI_PATCH_INSTALLED = True
