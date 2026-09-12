"""Normalize sunset-to-sunrise twilight flags for Astro Weather Backend 12.3.2."""
from __future__ import annotations

from typing import Any

RELEASE_VERSION = "12.3.2"


def normalize_display_twilight(core: Any, result: dict[str, Any]) -> None:
    """Mark every displayed hour that is not fully inside astronomical darkness as twilight.

    This deliberately treats a boundary hour that partly overlaps astronomical darkness and
    partly overlaps dusk/dawn as twilight in the UI. The operational decision itself remains
    based on the original astronomical-night rows and is not changed here.
    """
    rows = result.get("displayHours")
    if not isinstance(rows, list) or not rows:
        return

    dark_start = core.parse_iso_utc(str(result.get("darkStart") or ""))
    dark_end = core.parse_iso_utc(str(result.get("darkEnd") or ""))
    if dark_start is None or dark_end is None or dark_end <= dark_start:
        return

    for row in rows:
        if not isinstance(row, dict):
            continue
        start = core.parse_iso_utc(str(row.get("start") or ""))
        end = core.parse_iso_utc(str(row.get("end") or ""))
        if start is None or end is None or end <= start:
            continue

        fully_dark = start >= dark_start and end <= dark_end
        row["isAstronomicalDark"] = fully_dark
        row["twilight"] = not fully_dark

        if fully_dark:
            row["twilightPhase"] = None
        elif end <= dark_start or start < dark_start:
            row["twilightPhase"] = "evening"
        elif start >= dark_end or end > dark_end:
            row["twilightPhase"] = "morning"
        else:
            row["twilightPhase"] = "transition"


def install(core: Any) -> None:
    if getattr(core, "_TWILIGHT_PATCH_INSTALLED", False):
        return

    old_analyze_night = core.analyze_night

    def analyze_night(
        night: dict[str, Any],
        forecast: list[dict[str, Any]],
        moon_rows: list[dict[str, Any]],
        options: dict[str, Any],
    ) -> dict[str, Any] | None:
        result = old_analyze_night(night, forecast, moon_rows, options)
        if result is not None:
            normalize_display_twilight(core, result)
        return result

    core.analyze_night = analyze_night
    core.APP_VERSION = RELEASE_VERSION
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._TWILIGHT_PATCH_INSTALLED = True
