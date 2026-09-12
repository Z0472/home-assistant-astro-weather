"""Expose the exact MTG/FCI CLM samples used by the backend to the HA satellite card.

The visualisation intentionally reuses the existing 17 sampled CLM values instead
of decoding a second, larger satellite region.  This keeps Raspberry Pi CPU/RAM
load flat and makes the map auditable: every dot shown on the card is one of the
values that contributes to the published satellite cloud percentage.
"""
from __future__ import annotations

from typing import Any

import satellite_nowcast_patch as sat

RELEASE_VERSION = "12.4.0"
SATELLITE_CARD_VERSION = 2


def _augment_document(core: Any, document: dict[str, Any]) -> dict[str, Any]:
    result = dict(document)
    if not result.get("available"):
        return result

    try:
        frames = sat._load_sample_cache(core)
    except Exception:
        frames = []
    if not frames:
        return result

    as_of = str(result.get("as_of") or "")
    selected = None
    for frame in reversed(frames):
        if as_of and str(frame.get("time") or "") == as_of:
            selected = frame
            break
    if selected is None:
        selected = sorted(frames, key=lambda row: row.get("time") or "")[-1]

    points = selected.get("points") if isinstance(selected, dict) else None
    if isinstance(points, dict):
        # 0 = clear, 1 = cloud, null = no data.  These are the exact 17 samples
        # used for cloud_pct; the card must not present them as an interpolated
        # full-resolution satellite image.
        result["clm_points"] = dict(points)
        result["clm_map_basis"] = "17 přesných CLM vzorků: střed + 8 směrů v R/2 + 8 směrů v R"
        result["clm_map_radius_km"] = int(result.get("radius_km") or 30)
        result["clm_map_time"] = selected.get("time")
        result["clm_processing_storage"] = selected.get("processing_storage")
    return result


def install(core: Any) -> None:
    if getattr(core, "_SATELLITE_CARD_MAP_PATCH_INSTALLED", False):
        return

    old_document = sat._satellite_document

    def satellite_document(core_arg: Any, options: dict[str, Any]) -> dict[str, Any]:
        return _augment_document(core_arg, old_document(core_arg, options))

    sat._satellite_document = satellite_document

    # Bump only the satellite resource so Home Assistant browsers do not keep
    # the old card in cache. _augment_manifest reads this module global at call
    # time, so the manifest will point to v2 during the next card installation.
    sat.SATELLITE_CARD_VERSION = SATELLITE_CARD_VERSION
    installs = [
        (source, target)
        for source, target in core.DASHBOARD_CARD_INSTALLS
        if not target.startswith("astro-satellite-card-v")
    ]
    installs.append(("astro-satellite-card.js", f"astro-satellite-card-v{SATELLITE_CARD_VERSION}.js"))
    core.DASHBOARD_CARD_INSTALLS = tuple(installs)

    core._SATELLITE_CARD_MAP_PATCH_INSTALLED = True
