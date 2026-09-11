"""Runtime integration of ICON and generic model consensus into the stable backend."""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import cloud_consensus as cc
import weather_models as wm

RELEASE_VERSION = "12.2.0"
ASTRO_CARD_VERSION = 23


def merge_sources_wrapped(core: Any, original: Any, met: dict[str, Any], aladin: dict[str, Any],
                          horizon_hours: int, sky_quality: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows = original(met, aladin, horizon_hours, sky_quality)
    by_stamp = {str(row.get("datetime")): row for row in rows}
    now = core.utc_now()
    start, end = now - timedelta(hours=1), now + timedelta(hours=horizon_hours)
    for stamp, icon_row in wm.ICON_ROWS.items():
        dt = core.parse_iso_utc(stamp)
        if dt is None or dt < start or dt > end:
            continue
        canonical = core.iso_z(dt)
        row = by_stamp.get(canonical)
        if row is None:
            quality = (sky_quality or {}).get(canonical)
            quality = quality if isinstance(quality, dict) else {}
            row = {
                "datetime": canonical,
                "met": met.get(stamp),
                "aladin": aladin.get(stamp),
                "aerosols": quality.get("aerosols"),
                "seeing": quality.get("seeing"),
            }
            rows.append(row)
            by_stamp[canonical] = row
        row["icon"] = icon_row
    for row in rows:
        row.setdefault("icon", wm.ICON_ROWS.get(str(row.get("datetime"))))
    rows.sort(key=lambda row: str(row.get("datetime", "")))
    return rows


def _generic_conflict_reason(core: Any, analysis: dict[str, Any]) -> str | None:
    rows = [h for h in analysis.get("hours", []) if h.get("strongDisagreement")]
    if not rows:
        return None
    worst = max(rows, key=lambda h: core.safe_float(h.get("modelSpread")) or 0)
    bits = []
    for key, label in (("metTotal", "MET"), ("aladinTotal", "ALADIN"), ("iconTotal", "ICON")):
        value = core.safe_float(worst.get(key))
        if value is not None:
            bits.append(f"{label} {value:.0f} %")
    duration = sum(float(h.get("duration") or 0) for h in rows)
    spread = core.safe_float(worst.get("modelSpread")) or 0
    return (
        f"Meteorologické modely se během {duration:.1f} h výrazně rozcházejí; "
        f"největší rozptyl je {spread:.0f} p. b. ({', '.join(bits)}). "
        "Proto je verdikt NEJISTÉ a před spuštěním je vhodné zkontrolovat aktuální satelit nebo kamery."
    )


def analyze_night_wrapped(core: Any, original: Any, night: dict[str, Any], forecast: list[dict[str, Any]],
                          moon_rows: list[dict[str, Any]], options: dict[str, Any]) -> dict[str, Any] | None:
    result = original(night, forecast, moon_rows, options)
    if result is None:
        return None
    hours = result.get("hours") if isinstance(result.get("hours"), list) else []
    covered = sum(float(h.get("duration") or 0) for h in hours)

    def weighted(field: str) -> float | None:
        pairs = [(core.safe_float(h.get(field)), core.safe_float(h.get("duration"))) for h in hours]
        pairs = [(v, d) for v, d in pairs if v is not None and d is not None and d > 0]
        weight = sum(d for _, d in pairs)
        return sum(v * d for v, d in pairs) / weight if weight else None

    coverage2 = sum(float(h.get("duration") or 0) for h in hours if int(h.get("modelCount") or 0) >= 2)
    coverage3 = sum(float(h.get("duration") or 0) for h in hours if int(h.get("modelCount") or 0) >= 3)
    result["modelCoverage"] = round(coverage2 / covered, 3) if covered else 0.0
    result["threeModelCoverage"] = round(coverage3 / covered, 3) if covered else 0.0
    result["iconAvg"] = core.round_or_none(weighted("iconTotal"))
    result["modelCountAvg"] = core.round_or_none(weighted("modelCount"), 2)

    # The 12.1.12 analyzer gates SPUSTIT on specifically MET+ALADIN coverage.
    # Re-evaluate only that gate using any two independent available models.
    launch = result.get("launchBlock") if isinstance(result.get("launchBlock"), dict) else None
    if launch and float(launch.get("hours") or 0) >= float(options["min_good_block_hours"]):
        if float(launch.get("avgConfidence") or 0) >= 60 and result["modelCoverage"] >= 0.5:
            result.update(
                decision="good",
                label="SPUSTIT",
                reason=f"Kvalitní blok začíná včas a má {float(launch['hours']):.1f} h.",
            )
        else:
            result.update(
                decision="uncertain",
                label="NEJISTÉ",
                reason=_generic_conflict_reason(core, result)
                or "Okno je dost dlouhé, ale jistota modelů nebo datové pokrytí není dostatečné.",
            )
    generic = _generic_conflict_reason(core, result)
    if generic and result.get("decision") == "uncertain":
        result["reason"] = generic
    result["reason"] = str(result.get("reason") or "").replace(
        "MET, ALADINu a nastavení Měsíce",
        "dostupných meteorologických modelů a nastavení Měsíce",
    ).replace(
        "MET, ALADINu, Měsíce a AOD",
        "meteorologických modelů, Měsíce a AOD",
    )
    return result


def install(core: Any) -> None:
    """Install 12.2 wrappers. The base 12.1.12 module itself is not modified."""
    if getattr(core, "_MODEL_CONSENSUS_INSTALLED", False):
        return
    old_load, old_settings = core.load_options, core.decision_settings
    old_met, old_aladin = core.fetch_met, core.fetch_aladin
    old_score, old_merge = core.score_hour, core.merge_sources
    old_analyze, old_refresh = core.analyze_night, core.refresh_once

    core.APP_VERSION = RELEASE_VERSION
    core.ASTRO_START_CARD_VERSION = ASTRO_CARD_VERSION
    core.DASHBOARD_CARD_INSTALLS = (
        ("astro-start-card.js", f"astro-start-card-v{ASTRO_CARD_VERSION}.js"),
        ("moon-forecast-card.js", f"moon-forecast-card-v{core.MOON_FORECAST_CARD_VERSION}.js"),
    )
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"

    def load_options() -> dict[str, Any]:
        options = old_load()
        options["use_icon"] = bool(options.get("use_icon", True))
        agent = str(options.get("met_user_agent", "")).strip()
        if not agent or agent.startswith("AstroWeatherBackend/"):
            options["met_user_agent"] = (
                f"AstroWeatherBackend/{RELEASE_VERSION} "
                "https://github.com/Z0472/home-assistant-astro-weather"
            )
        return options

    def settings(options: dict[str, Any]) -> dict[str, Any]:
        value = old_settings(options)
        value["use_icon"] = bool(options.get("use_icon", True))
        return value

    def fetch_met(options: dict[str, Any]):
        wm.refresh_icon(options, core)
        rows, source = old_met(options)
        source.setdefault("model_family", "MET Norway Locationforecast")
        return rows, source

    def refresh(options: dict[str, Any]):
        old_refresh(options)
        # Base refresh knows only two models. Add ICON diagnostics and correct
        # generic weather state, then republish the completed entity snapshot.
        with core.STATE_LOCK:
            core.STATE.setdefault("sources", {})["icon"] = dict(wm.ICON_SOURCE)
            core.STATE.setdefault("errors", {})["icon"] = wm.ICON_ERROR
            max_models = max(
                (int(h.get("modelCount") or 0)
                 for d in core.DECISION_STATE.get("daily", []) if isinstance(d, dict)
                 for h in d.get("hours", []) if isinstance(h, dict)),
                default=0,
            )
            if max_models >= 2:
                core.STATE["state"] = "ok"
                core.DECISION_STATE["weather_state"] = "ok"
            snapshot = json.loads(json.dumps(core.STATE, ensure_ascii=False))
            decision = json.loads(json.dumps(core.DECISION_STATE, ensure_ascii=False))
            moon = json.loads(json.dumps(core.MOON_STATE, ensure_ascii=False))
        if moon and options.get("publish_homeassistant_entities"):
            core.publish_homeassistant_entities(options, snapshot, decision, moon)

    core.load_options = load_options
    core.decision_settings = settings
    core.fetch_icon = lambda options: wm.fetch_icon(options, core)
    core.fetch_met = fetch_met
    core.fetch_aladin = lambda options: wm.fetch_aladin_wrapped(core, old_aladin, options)
    core.cloud_consensus = cc.cloud_consensus
    core.score_hour = lambda row, moon, night, options: cc.score_hour_wrapped(
        core, old_score, row, moon, night, options
    )
    core.merge_sources = lambda met, aladin, horizon, sky=None: merge_sources_wrapped(
        core, old_merge, met, aladin, horizon, sky
    )
    core.analyze_night = lambda night, forecast, moon_rows, options: analyze_night_wrapped(
        core, old_analyze, night, forecast, moon_rows, options
    )
    core.refresh_once = refresh
    core._MODEL_CONSENSUS_INSTALLED = True
