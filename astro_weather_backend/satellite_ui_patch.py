"""Satellite UI refinements for Astro Weather Backend 12.4.7.

Keeps nightly model averages and instantaneous satellite/model comparison
separate and unambiguous. Main card v32 shows nightly cloud averages only in
the top night cards and removes their duplicate detail-row presentation.
Satellite card v6 labels its model percentage explicitly as the current model
consensus at the CLM observation time.
"""
from __future__ import annotations

import math
from typing import Any

import satellite_nowcast_patch as sat
import satellite_card_map_patch as clm_map
import satellite_lowload_patch as lowload
import satellite_index_sampler_patch as index_sampler
import storage_protection_patch as storage

RELEASE_VERSION = "12.4.7"
ASTRO_CARD_VERSION = 32
SATELLITE_CARD_VERSION = 6
VISUAL_RADIUS_KM = 150.0
VISUAL_SIZE_PX = 900


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

    # v32 imports v31 -> v30. v6 imports v5 -> v4 -> v3. Install the whole
    # dependency chain so clean Home Assistant installs are self-contained.
    core.ASTRO_START_CARD_VERSION = ASTRO_CARD_VERSION
    sat.SATELLITE_CARD_VERSION = SATELLITE_CARD_VERSION

    installs = []
    for source, target in core.DASHBOARD_CARD_INSTALLS:
        if target.startswith("astro-satellite-card-v"):
            continue
        if target.startswith("astro-start-card-v31") or target.startswith("astro-start-card-v32"):
            continue
        installs.append((source, target))

    if not any(target == "astro-start-card-v30.js" for _, target in installs):
        installs.append(("astro-start-card-v30.js", "astro-start-card-v30.js"))
    installs.append(("astro-start-card-v31.js", "astro-start-card-v31.js"))
    installs.append(("astro-start-card-v32.js", "astro-start-card-v32.js"))

    installs.append(("astro-satellite-card.js", "astro-satellite-card-v3.js"))
    installs.append(("astro-satellite-card-v4.js", "astro-satellite-card-v4.js"))
    installs.append(("astro-satellite-card-v5.js", "astro-satellite-card-v5.js"))
    installs.append(("astro-satellite-card-v6.js", "astro-satellite-card-v6.js"))
    core.DASHBOARD_CARD_INSTALLS = tuple(installs)

    sat.RELEASE_VERSION = RELEASE_VERSION
    clm_map.RELEASE_VERSION = RELEASE_VERSION
    lowload.RELEASE_VERSION = RELEASE_VERSION
    index_sampler.RELEASE_VERSION = RELEASE_VERSION
    storage.RELEASE_VERSION = RELEASE_VERSION
    core.APP_VERSION = RELEASE_VERSION
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._SATELLITE_UI_PATCH_INSTALLED = True
