"""Time-aware decision policy for Astro Weather Backend 12.4.18.

The numerical forecast remains authoritative when the observing start is still
far away. Spatial cloud geometry and the live EUMETSAT CLM become progressively
more important only as the planned start approaches:

* > 6 h: satellite is informational only;
* 3-6 h: satellite is a confidence check, but cannot change the verdict;
* 1-3 h: a sufficiently confident satellite nowcast may soften SPUSTIT to
  NEJISTE when it is materially cloudier than the model consensus at start;
* <= 1 h: current CLM has strong weight; widespread/current cloud without a
  convincing clearing trend may soften SPUSTIT to NEJISTE.

The model-derived spatial edge is likewise informational more than three hours
before start. This prevents a modelled evening boundary seen at noon from
prematurely changing the daily verdict.

Missing or stale satellite data always fail open: they never create NEJISTE by
themselves and any earlier satellite-only adjustment is removed on the next
publication.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any

import cloud_consensus as cc
import satellite_nowcast_patch as sat
import spatial_cloud_patch as spatial

RELEASE_VERSION = "12.4.18"

SPATIAL_DECISION_HORIZON_HOURS = 3.0
SATELLITE_INFORMATIONAL_HOURS = 6.0
SATELLITE_NOWCAST_HOURS = 3.0
SATELLITE_STRONG_HOURS = 1.0
SATELLITE_MIN_NOWCAST_CONFIDENCE = 50.0
SATELLITE_STRONG_CLEARING_CONFIDENCE = 60.0

_BASELINE_GENERATED_AT: str | None = None
_BASELINE_DECISION: dict[str, Any] | None = None
_LAST_OPTIONS: dict[str, Any] = {}


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _safe(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _parse(core: Any, value: Any) -> datetime | None:
    if value is None:
        return None
    return core.parse_iso_utc(str(value))


def _first_night(decision: dict[str, Any]) -> dict[str, Any] | None:
    daily = decision.get("daily")
    if not isinstance(daily, list) or not daily or not isinstance(daily[0], dict):
        return None
    return daily[0]


def _night_start(core: Any, night: dict[str, Any] | None) -> datetime | None:
    if not isinstance(night, dict):
        return None
    for key in ("launchBlock", "bestBlock"):
        block = night.get(key)
        if isinstance(block, dict):
            start = _parse(core, block.get("start"))
            if start is not None:
                return start
    return _parse(core, night.get("darkStart"))


def _hours_to_start(core: Any, night: dict[str, Any] | None) -> float | None:
    start = _night_start(core, night)
    if start is None:
        return None
    return (start - core.utc_now()).total_seconds() / 3600.0


def _spatial_policy_wrapper(original: Any):
    def apply(
        core_arg: Any,
        options: dict[str, Any],
        result: dict[str, Any],
        spatial_info: dict[str, Any],
    ) -> None:
        hours = _hours_to_start(core_arg, result)
        role = "active"
        if hours is not None and hours > SPATIAL_DECISION_HORIZON_HOURS:
            role = "informational"

        result["spatialDecisionRole"] = role
        result["spatialDecisionHorizonHours"] = SPATIAL_DECISION_HORIZON_HOURS
        result["spatialHoursToStart"] = None if hours is None else round(hours, 2)

        if role == "informational":
            result["spatialDecisionNote"] = (
                f"Prostorová předpověď okolí je {hours:.1f} h před startem pouze informativní; "
                "verdikt zatím nemění."
            )
            return

        original(core_arg, options, result, spatial_info)

    return apply


def _model_cloud_at(core: Any, options: dict[str, Any], target: datetime | None) -> float | None:
    if target is None:
        return None
    values, row = sat._current_model_values(core, target)
    if row is None:
        return None
    consensus = cc.cloud_consensus(
        values,
        float(options.get("disagreement_warn", 35)),
        float(options.get("disagreement_bad", 55)),
    )
    return _safe(consensus.get("effective"))


def _projected_satellite_cloud(satellite: dict[str, Any], hours: float) -> float | None:
    cloud = _safe(satellite.get("cloud_pct"))
    if cloud is None:
        return None
    slope = _safe(satellite.get("trend_slope_pph"))
    if slope is None:
        return cloud
    return _clamp(cloud + slope * max(0.0, hours))


def _baseline_for(decision: dict[str, Any], *, fresh: bool = False) -> dict[str, Any]:
    global _BASELINE_GENERATED_AT, _BASELINE_DECISION

    generated = str(decision.get("generated_at") or "")
    if fresh or _BASELINE_DECISION is None or generated != _BASELINE_GENERATED_AT:
        base = _copy(decision)
        base.pop("satelliteNowcast", None)
        base.pop("satelliteComparison", None)
        base.pop("satelliteDecisionPolicy", None)
        daily = base.get("daily")
        if isinstance(daily, list):
            for night in daily:
                if isinstance(night, dict):
                    night.pop("satelliteDecisionPolicy", None)
                    night.pop("satelliteAdjusted", None)
        _BASELINE_GENERATED_AT = generated
        _BASELINE_DECISION = base
    return _copy(_BASELINE_DECISION)


def _policy_note(role: str, hours: float | None, comparison: dict[str, Any]) -> str:
    if hours is None:
        return "Čas do startu nelze spolehlivě určit; satelit zůstává pouze informativní."
    if role == "informational":
        return f"Do startu zbývá {hours:.1f} h; satelit je zatím pouze aktuální kontrola a verdikt nemění."
    if role == "confidence":
        agreement = _safe(comparison.get("agreement_pct"))
        if agreement is None:
            return f"Do startu zbývá {hours:.1f} h; satelit slouží jen jako kontrola důvěry a verdikt nemění."
        return (
            f"Do startu zbývá {hours:.1f} h; aktuální shoda satelit–modely je {agreement:.0f} %, "
            "ale satelit v tomto horizontu verdikt nemění."
        )
    if role == "nowcast":
        return f"Do startu zbývá {hours:.1f} h; krátký satelitní nowcast už může znejistit SPUSTIT."
    return f"Do startu zbývá {max(0.0, hours):.1f} h; aktuální satelit má vysokou rozhodovací váhu."


def _apply_satellite_policy(
    core: Any,
    options: dict[str, Any],
    decision: dict[str, Any],
    satellite: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    out = _copy(decision)
    out["satelliteNowcast"] = _copy(satellite)
    out["satelliteComparison"] = _copy(comparison)

    night = _first_night(out)
    start = _night_start(core, night)
    hours = None if start is None else (start - core.utc_now()).total_seconds() / 3600.0
    effective_hours = None if hours is None else max(0.0, hours)

    if not satellite.get("available"):
        role = "unavailable"
    elif effective_hours is None or effective_hours > SATELLITE_INFORMATIONAL_HOURS:
        role = "informational"
    elif effective_hours > SATELLITE_NOWCAST_HOURS:
        role = "confidence"
    elif effective_hours > SATELLITE_STRONG_HOURS:
        role = "nowcast"
    else:
        role = "strong"

    policy: dict[str, Any] = {
        "role": role,
        "changed": False,
        "hours_to_start": None if hours is None else round(hours, 2),
        "target_start": None if start is None else core.iso_z(start),
        "informational_over_hours": SATELLITE_INFORMATIONAL_HOURS,
        "nowcast_from_hours": SATELLITE_NOWCAST_HOURS,
        "strong_from_hours": SATELLITE_STRONG_HOURS,
        "note": None,
        "projected_cloud_pct": None,
        "model_cloud_pct": None,
        "difference_pp": None,
        "nowcast_confidence_pct": _safe(satellite.get("nowcast_confidence_pct")),
    }

    if role == "unavailable":
        policy["note"] = (
            "Satelitní CLM není čerstvě dostupné; chybějící satelitní data verdikt nemění."
        )
        out["satelliteDecisionPolicy"] = policy
        if night is not None:
            night["satelliteDecisionPolicy"] = _copy(policy)
        return out

    policy["note"] = _policy_note(role, effective_hours, comparison)

    if night is None or night.get("decision") != "good" or effective_hours is None:
        out["satelliteDecisionPolicy"] = policy
        if night is not None:
            night["satelliteDecisionPolicy"] = _copy(policy)
        return out

    projected = _projected_satellite_cloud(satellite, effective_hours)
    model_cloud = _model_cloud_at(core, options, start)
    confidence = _safe(satellite.get("nowcast_confidence_pct"))
    area = _safe(satellite.get("cloud_pct"))
    center = _safe(satellite.get("center_cloud_pct"))
    trend = str(satellite.get("trend") or "unknown")

    policy["projected_cloud_pct"] = None if projected is None else round(projected, 1)
    policy["model_cloud_pct"] = None if model_cloud is None else round(model_cloud, 1)
    if projected is not None and model_cloud is not None:
        policy["difference_pp"] = round(projected - model_cloud, 1)

    risky = False
    reason = None

    if role == "nowcast":
        warn = float(options.get("disagreement_warn", 35))
        if (
            confidence is not None
            and confidence >= SATELLITE_MIN_NOWCAST_CONFIDENCE
            and projected is not None
            and model_cloud is not None
            and projected >= spatial.EDGE_THRESHOLD
            and projected - model_cloud >= warn
        ):
            risky = True
            reason = (
                f"Satelitní nowcast pro dobu startu odhaduje asi {projected:.0f} % oblačnosti, "
                f"zatímco modelový konsensus {model_cloud:.0f} %. Do startu zbývá {effective_hours:.1f} h; "
                "před chlazením zkontroluj aktuální satelit a kamery."
            )

    elif role == "strong":
        cloudy_now = bool(
            (center is not None and center >= 50.0)
            or (area is not None and area >= spatial.CLOUDY_THRESHOLD)
        )
        cloudy_at_start = bool(projected is not None and projected >= spatial.CLOUDY_THRESHOLD)
        convincing_clearing = bool(
            trend == "clearing"
            and confidence is not None
            and confidence >= SATELLITE_STRONG_CLEARING_CONFIDENCE
            and projected is not None
            and projected <= spatial.CLEAR_THRESHOLD
        )
        risky = (cloudy_now or cloudy_at_start) and not convincing_clearing
        if risky:
            local_text = "mrak" if center is not None and center >= 50.0 else "jasno/nejisté"
            area_text = "—" if area is None else f"{area:.0f} %"
            reason = (
                f"Do startu zbývá jen {effective_hours:.1f} h. Satelit nyní ukazuje nad observatoří {local_text} "
                f"a v okolí {area_text} oblačných vzorků; není vidět dost přesvědčivé vyjasňování. "
                "Před chlazením nebo otevřením střechy zkontroluj kamery."
            )

    if risky:
        night.update(
            decision="uncertain",
            label="NEJISTÉ",
            reason=reason,
            satelliteAdjusted=True,
        )
        out.update(
            state="NEJISTÉ",
            machine_state="uncertain",
            reason=reason,
        )
        policy["changed"] = True
        policy["note"] = reason

    out["satelliteDecisionPolicy"] = policy
    night["satelliteDecisionPolicy"] = _copy(policy)
    return out


def _sync_core_decision(core: Any, decision: dict[str, Any]) -> None:
    with core.STATE_LOCK:
        core.DECISION_STATE.clear()
        core.DECISION_STATE.update(_copy(decision))
        summary = core.STATE.get("decision_summary")
        if isinstance(summary, dict):
            summary.update({
                "state": decision.get("state"),
                "machine_state": decision.get("machine_state"),
                "reason": decision.get("reason"),
            })


def install(core: Any) -> None:
    global _LAST_OPTIONS
    if getattr(core, "_DECISION_POLICY_PATCH_INSTALLED", False):
        return

    old_load_options = core.load_options
    old_publish = core.publish_homeassistant_entities
    old_inject = sat._inject_states
    old_spatial_apply = spatial._apply_to_decision

    spatial._apply_to_decision = _spatial_policy_wrapper(old_spatial_apply)

    def load_options() -> dict[str, Any]:
        global _LAST_OPTIONS
        options = old_load_options()
        _LAST_OPTIONS = _copy(options)
        agent = str(options.get("met_user_agent", "")).strip()
        if not agent or agent.startswith("AstroWeatherBackend/"):
            options["met_user_agent"] = (
                f"AstroWeatherBackend/{RELEASE_VERSION} "
                "https://github.com/Z0472/home-assistant-astro-weather"
            )
            _LAST_OPTIONS = _copy(options)
        return options

    def publish(options: dict[str, Any], weather: dict[str, Any],
                decision: dict[str, Any], moon: dict[str, Any]) -> None:
        global _LAST_OPTIONS
        _LAST_OPTIONS = _copy(options)
        fresh = "satelliteDecisionPolicy" not in decision
        base = _baseline_for(decision, fresh=fresh)
        decorated = _apply_satellite_policy(
            core, options, base, sat.SATELLITE_STATE, sat.COMPARISON_STATE
        )
        weather_out = _copy(weather)
        summary = weather_out.get("decision_summary")
        if isinstance(summary, dict):
            summary.update({
                "state": decorated.get("state"),
                "machine_state": decorated.get("machine_state"),
                "reason": decorated.get("reason"),
            })
        _sync_core_decision(core, decorated)
        old_publish(options, weather_out, decorated, moon)

    def inject_states(core_arg: Any, satellite: dict[str, Any], comparison: dict[str, Any]) -> None:
        old_inject(core_arg, satellite, comparison)
        with core_arg.STATE_LOCK:
            current = _copy(core_arg.DECISION_STATE)
        options = _LAST_OPTIONS or {
            "disagreement_warn": 35,
            "disagreement_bad": 55,
        }
        base = _baseline_for(current, fresh=False)
        decorated = _apply_satellite_policy(core_arg, options, base, satellite, comparison)
        _sync_core_decision(core_arg, decorated)

    core.load_options = load_options
    core.publish_homeassistant_entities = publish
    sat._inject_states = inject_states

    sat.RELEASE_VERSION = RELEASE_VERSION
    core.APP_VERSION = RELEASE_VERSION
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._DECISION_POLICY_PATCH_INSTALLED = True
