"""Astro Weather 12.2.2 night-display and decision-confidence patch."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo
import math

RELEASE_VERSION = "12.2.2"
ASTRO_CARD_VERSION = 25
MOON_CARD_VERSION = 25
SUNSET_ALTITUDE_DEG = -0.833
BAD_WEATHER_MIN_MODEL_AGREEMENT = 60.0


def _solar_window(core: Any, night: dict[str, Any], options: dict[str, Any]):
    """Return apparent sunset and sunrise around the night date."""
    try:
        y, m, d = (int(part) for part in str(night.get("date", "")).split("-"))
        tz = ZoneInfo(str(options.get("timezone") or "Europe/Prague"))
        latitude = float(options["latitude"])
        longitude = float(options["longitude"])
    except Exception:
        return None, None

    local_noon = datetime(y, m, d, 12, 0, tzinfo=tz)
    local_midnight = local_noon + timedelta(hours=12)
    next_noon = local_noon + timedelta(days=1)
    threshold = math.radians(SUNSET_ALTITUDE_DEG)

    def altitude(dt: datetime) -> float:
        return core.sun_altitude(dt, latitude, longitude)

    sunset = core.find_altitude_crossing(
        altitude,
        local_noon.astimezone(timezone.utc),
        local_midnight.astimezone(timezone.utc),
        threshold,
        "down",
    )
    sunrise = core.find_altitude_crossing(
        altitude,
        local_midnight.astimezone(timezone.utc),
        next_noon.astimezone(timezone.utc),
        threshold,
        "up",
    )
    return sunset, sunrise


def _display_hours(core: Any, night: dict[str, Any], forecast: list[dict[str, Any]],
                   moon_rows: list[dict[str, Any]], options: dict[str, Any],
                   sunset: datetime | None, sunrise: datetime | None) -> list[dict[str, Any]]:
    """Score rows for display from sunset to sunrise without changing the decision window."""
    if sunset is None or sunrise is None or sunrise <= sunset:
        return []

    dark_start = core.parse_iso_utc(str(night.get("astronomical_dark_start", "")))
    dark_end = core.parse_iso_utc(str(night.get("astronomical_dark_end", "")))
    rows: list[dict[str, Any]] = []

    for row in forecast:
        source_start = core.parse_iso_utc(str(row.get("datetime", "")))
        if source_start is None:
            continue
        source_end = source_start + timedelta(hours=1)
        overlap_start = max(source_start, sunset)
        overlap_end = min(source_end, sunrise)
        if overlap_end <= overlap_start:
            continue

        moon_hour = core.nearest_moon_hour(source_start, moon_rows)
        scored = dict(core.score_hour(row, moon_hour, night, options))
        duration = (overlap_end - overlap_start).total_seconds() / 3600.0

        dark_overlap = 0.0
        if dark_start is not None and dark_end is not None:
            ds = max(overlap_start, dark_start)
            de = min(overlap_end, dark_end)
            if de > ds:
                dark_overlap = (de - ds).total_seconds() / 3600.0

        scored.update({
            "start": core.iso_z(overlap_start),
            "end": core.iso_z(overlap_end),
            "duration": round(duration, 3),
            "isAstronomicalDark": dark_overlap >= max(0.001, duration - 0.01),
            "twilight": dark_overlap < max(0.001, duration - 0.01),
        })
        rows.append(scored)

    return rows


def _model_agreement_average(core: Any, result: dict[str, Any], options: dict[str, Any]) -> float | None:
    total = 0.0
    weight = 0.0
    for hour in result.get("hours", []):
        if not isinstance(hour, dict):
            continue
        duration = core.safe_float(hour.get("duration"))
        if duration is None or duration <= 0:
            continue
        consensus = core.cloud_consensus(
            {
                "MET": hour.get("metTotal"),
                "ALADIN": hour.get("aladinTotal"),
                "ICON": hour.get("iconTotal"),
            },
            float(options["disagreement_warn"]),
            float(options["disagreement_bad"]),
        )
        confidence = core.safe_float(consensus.get("confidence"))
        if confidence is None:
            continue
        total += confidence * duration
        weight += duration
    return total / weight if weight else None


def _has_hard_veto(core: Any, result: dict[str, Any], options: dict[str, Any]) -> bool:
    """True for physical vetoes that must keep NESPOUSTET independent of model agreement."""
    for hour in result.get("hours", []):
        if not isinstance(hour, dict):
            continue
        precip = core.safe_float(hour.get("precip"))
        fog = core.safe_float(hour.get("fog"))
        wind = core.safe_float(hour.get("wind"))
        aod = core.safe_float(hour.get("aod550"))
        seeing = core.safe_float(hour.get("seeingArcsec"))
        if precip is not None and precip > 0:
            return True
        if fog is not None and fog >= 20:
            return True
        if wind is not None and wind >= float(options["wind_bad_ms"]):
            return True
        if bool(hour.get("moonInterferes")):
            return True
        if bool(hour.get("aerosolApplied")) and aod is not None and aod >= float(options["aod_bad"]):
            return True
        if bool(hour.get("seeingApplied")) and seeing is not None and seeing >= float(options["seeing_bad_arcsec"]):
            return True
    return False


def _soften_low_agreement_bad(core: Any, result: dict[str, Any], options: dict[str, Any]) -> None:
    """Do not claim a confident weather stop when the cloud models agree only weakly."""
    if result.get("decision") != "bad" or _has_hard_veto(core, result, options):
        return

    agreement = core.safe_float(result.get("modelAgreementAvg"))
    if agreement is None or agreement >= BAD_WEATHER_MIN_MODEL_AGREEMENT:
        return

    result.update(
        decision="uncertain",
        label="NEJISTÉ",
        reason=(
            f"Modely předpovídají nepříznivé podmínky, ale jejich shoda je jen {agreement:.0f} %. "
            "Bez tvrdého veto důvodu proto není bezpečné vydat jisté NESPOUŠTĚT; "
            "zkontroluj aktuální oblohu, satelit nebo kameru."
        ),
    )


def install(core: Any) -> None:
    if getattr(core, "_NIGHT_FORECAST_PATCH_INSTALLED", False):
        return

    old_load_options = core.load_options
    old_analyze_night = core.analyze_night

    def load_options() -> dict[str, Any]:
        options = old_load_options()
        agent = str(options.get("met_user_agent", "")).strip()
        if not agent or agent.startswith("AstroWeatherBackend/"):
            options["met_user_agent"] = (
                f"AstroWeatherBackend/{RELEASE_VERSION} "
                "https://github.com/Z0472/home-assistant-astro-weather"
            )
        return options

    def analyze_night(night: dict[str, Any], forecast: list[dict[str, Any]],
                      moon_rows: list[dict[str, Any]], options: dict[str, Any]) -> dict[str, Any] | None:
        result = old_analyze_night(night, forecast, moon_rows, options)
        if result is None:
            return None

        agreement = _model_agreement_average(core, result, options)
        result["modelAgreementAvg"] = core.round_or_none(agreement, 1)
        _soften_low_agreement_bad(core, result, options)

        sunset, sunrise = _solar_window(core, night, options)
        if sunset is not None and sunrise is not None and sunrise > sunset:
            result["sunset"] = core.iso_z(sunset)
            result["sunrise"] = core.iso_z(sunrise)
            display = _display_hours(core, night, forecast, moon_rows, options, sunset, sunrise)
            if display:
                result["displayHours"] = display

        return result

    core.load_options = load_options
    core.analyze_night = analyze_night
    core.APP_VERSION = RELEASE_VERSION
    core.ASTRO_START_CARD_VERSION = ASTRO_CARD_VERSION
    core.MOON_FORECAST_CARD_VERSION = MOON_CARD_VERSION
    core.DASHBOARD_CARD_INSTALLS = (
        ("astro-start-card.js", "astro-start-card-base-v22.js"),
        ("astro-start-card-v23.js", "astro-start-card-v23.js"),
        ("astro-start-card-v24.js", "astro-start-card-v24.js"),
        ("astro-start-card-v25.js", f"astro-start-card-v{ASTRO_CARD_VERSION}.js"),
        ("moon-forecast-card.js", "moon-forecast-card-v23.js"),
        ("moon-forecast-card-v24.js", "moon-forecast-card-v24.js"),
        ("moon-forecast-card-v25.js", f"moon-forecast-card-v{MOON_CARD_VERSION}.js"),
    )
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._NIGHT_FORECAST_PATCH_INSTALLED = True
