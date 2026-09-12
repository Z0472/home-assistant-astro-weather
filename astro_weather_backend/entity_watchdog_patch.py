"""Self-healing Home Assistant entity watchdog for Astro Weather Backend 12.4.0.

The core backend publishes REST-created sensor states. Those states are intentionally
lightweight and can disappear when Home Assistant reloads/restarts. The legacy
watchdog only probed the decision entity for HTTP 404. This patch validates every
core entity independently and also detects a stale decision payload by comparing
its generated_at attribute with the backend's current last-good state.
"""
from __future__ import annotations

import json
from typing import Any

RELEASE_VERSION = "12.4.0"
_UNHEALTHY_STATES = {"", "unknown", "unavailable", "none"}


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _decision_is_valid(decision: dict[str, Any]) -> bool:
    daily = decision.get("daily")
    machine = str(decision.get("machine_state") or "").strip().lower()
    state = str(decision.get("state") or "").strip().lower()
    return (
        isinstance(daily, list)
        and bool(daily)
        and machine not in _UNHEALTHY_STATES
        and state not in _UNHEALTHY_STATES | {"bez dat"}
    )


def _snapshot(core: Any):
    with core.STATE_LOCK:
        weather = _copy(core.STATE)
        decision = _copy(core.DECISION_STATE)
        moon = _copy(core.MOON_STATE)
    if not weather.get("generated_at") or not moon or not _decision_is_valid(decision):
        return None
    return weather, decision, moon


def _entity_payloads(options: dict[str, Any], weather: dict[str, Any],
                     decision: dict[str, Any], moon: dict[str, Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []

    weather_entity = str(options.get("weather_entity") or "").strip()
    if weather_entity:
        attrs = {key: value for key, value in weather.items() if key != "state"}
        attrs.update({"friendly_name": "Astro Weather Detail", "icon": "mdi:weather-night"})
        payloads.append({
            "kind": "weather",
            "entity_id": weather_entity,
            "state": str(weather.get("state", "unknown")),
            "attributes": attrs,
        })

    decision_entity = str(options.get("decision_entity") or "").strip()
    if decision_entity:
        attrs = {key: value for key, value in decision.items() if key != "state"}
        attrs.update({"friendly_name": "Astro vhodnost foceni", "icon": "mdi:telescope"})
        payloads.append({
            "kind": "decision",
            "entity_id": decision_entity,
            "state": str(decision.get("state", "BEZ DAT")),
            "attributes": attrs,
        })

    moon_entity = str(options.get("moon_entity") or "").strip()
    if moon_entity:
        moon_attrs = moon.get("attributes") if isinstance(moon.get("attributes"), dict) else {}
        attrs = dict(moon_attrs)
        attrs.update({
            "friendly_name": "Měsíc focení předpověď",
            "icon": "mdi:moon-waning-crescent",
        })
        payloads.append({
            "kind": "moon",
            "entity_id": moon_entity,
            "state": str(moon.get("state", "BEZ DAT")),
            "attributes": attrs,
        })

    return payloads


def _ha_state_document(core: Any, entity_id: str) -> dict[str, Any] | None:
    token = core.os.environ.get("SUPERVISOR_TOKEN", "").strip()
    if not token:
        raise RuntimeError("SUPERVISOR_TOKEN neni dostupny; zkontroluj homeassistant_api: true")

    quoted = core.urllib.parse.quote(entity_id, safe="")
    request = core.urllib.request.Request(
        f"http://supervisor/core/api/states/{quoted}",
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    try:
        with core.urllib.request.urlopen(request, timeout=20) as response:
            document = json.loads(response.read().decode("utf-8"))
        return document if isinstance(document, dict) else {}
    except core.urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def _health_problem(expected: dict[str, Any], actual: dict[str, Any] | None) -> str | None:
    if actual is None:
        return "entita chybi"
    if not isinstance(actual, dict):
        return "HA vratil neplatny stav"

    expected_state = str(expected.get("state") or "").strip()
    actual_state = str(actual.get("state") or "").strip()
    if actual_state.lower() in _UNHEALTHY_STATES and expected_state.lower() not in _UNHEALTHY_STATES:
        return f"stav je {actual_state or 'prazdny'}"
    if actual_state != expected_state:
        return f"stav {actual_state!r} != backend {expected_state!r}"

    kind = expected.get("kind")
    if kind in {"weather", "decision"}:
        expected_attrs = expected.get("attributes") if isinstance(expected.get("attributes"), dict) else {}
        actual_attrs = actual.get("attributes") if isinstance(actual.get("attributes"), dict) else {}
        expected_generated = str(expected_attrs.get("generated_at") or "").strip()
        actual_generated = str(actual_attrs.get("generated_at") or "").strip()
        if expected_generated and actual_generated != expected_generated:
            return (
                "generated_at je zastaraly "
                f"({actual_generated or 'chybi'} != {expected_generated})"
            )

    return None


def republish_missing_homeassistant_entities(core: Any, options: dict[str, Any]) -> bool:
    """Validate each core entity and independently repair missing/stale states."""
    if not options.get("publish_homeassistant_entities", True):
        return False

    snapshot = _snapshot(core)
    if snapshot is None:
        return False
    payloads = _entity_payloads(options, *snapshot)
    if not payloads:
        return False

    unhealthy: list[tuple[dict[str, Any], str]] = []
    for expected in payloads:
        try:
            actual = _ha_state_document(core, expected["entity_id"])
        except Exception as exc:
            core.log(
                f"HA ENTITY KONTROLA: {expected['entity_id']} nelze overit: {exc}"
            )
            continue
        problem = _health_problem(expected, actual)
        if problem:
            unhealthy.append((expected, problem))

    if not unhealthy:
        return False

    repaired: list[str] = []
    failed: list[str] = []
    for expected, problem in unhealthy:
        entity_id = expected["entity_id"]
        try:
            core.publish_home_assistant_state(
                entity_id,
                expected["state"],
                expected["attributes"],
            )
            repaired.append(entity_id)
            core.log(f"HA ENTITY SELF-HEAL: {entity_id}: {problem}; znovu publikovano.")
        except Exception as exc:
            failed.append(entity_id)
            core.log(
                f"HA ENTITY SELF-HEAL CHYBA: {entity_id}: {problem}; publikace selhala: {exc}"
            )

    if repaired:
        core.log("HA ENTITY SELF-HEAL: obnoveno " + ", ".join(repaired))
    if failed:
        core.log("HA ENTITY SELF-HEAL: stale chybi " + ", ".join(failed))
    return bool(repaired)


def install(core: Any) -> None:
    if getattr(core, "_ENTITY_WATCHDOG_PATCH_INSTALLED", False):
        return

    core._ENTITY_WATCHDOG_OLD_REPUBLISH = core.republish_missing_homeassistant_entities

    def patched_republish(options: dict[str, Any]) -> bool:
        return republish_missing_homeassistant_entities(core, options)

    # entity_watchdog_worker resolves this module global dynamically, so replacing
    # the function here upgrades the already existing watchdog thread as well.
    core.republish_missing_homeassistant_entities = patched_republish
    core._ENTITY_WATCHDOG_PATCH_INSTALLED = True
