"""Persistent last-good Home Assistant state cache for Astro Weather Backend 12.3.1."""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

CACHE_FILENAME = "last_good_homeassistant_state.json"
MAX_CACHE_AGE = timedelta(hours=12)


def _cache_path(core: Any):
    return core.CACHE_DIR / CACHE_FILENAME


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _location_matches(options: dict[str, Any], weather: dict[str, Any]) -> bool:
    location = weather.get("location") if isinstance(weather.get("location"), dict) else {}
    try:
        return (
            abs(float(location.get("latitude")) - float(options["latitude"])) <= 0.01
            and abs(float(location.get("longitude")) - float(options["longitude"])) <= 0.01
            and abs(float(location.get("altitude")) - float(options["altitude"])) <= 100
        )
    except (TypeError, ValueError):
        return False


def save_last_good_state(core: Any) -> None:
    with core.STATE_LOCK:
        weather = _copy_json(core.STATE)
        decision = _copy_json(core.DECISION_STATE)
        moon = _copy_json(core.MOON_STATE)

    if not isinstance(decision.get("daily"), list) or not decision.get("daily"):
        return
    generated_at = core.parse_iso_utc(str(decision.get("generated_at") or weather.get("generated_at") or ""))
    if generated_at is None:
        return

    payload = {
        "saved_at": core.iso_z(core.utc_now()),
        "weather": weather,
        "decision": decision,
        "moon": moon,
    }
    path = _cache_path(core)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temp.replace(path)
    except OSError as exc:
        core.log(f"STAV CACHE VAROVANI: nelze ulozit posledni platny stav: {exc}")


def restore_last_good_state(core: Any, options: dict[str, Any]) -> bool:
    path = _cache_path(core)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False

    weather = payload.get("weather")
    decision = payload.get("decision")
    moon = payload.get("moon")
    if not isinstance(weather, dict) or not isinstance(decision, dict) or not isinstance(moon, dict):
        return False
    if not _location_matches(options, weather):
        core.log("STAV CACHE: ulozena lokalita se lisi, cache nepouzivam.")
        return False

    generated_at = core.parse_iso_utc(
        str(decision.get("generated_at") or weather.get("generated_at") or "")
    )
    if generated_at is None:
        return False
    age = core.utc_now() - generated_at
    if age < timedelta(0) or age > MAX_CACHE_AGE:
        core.log(
            "STAV CACHE: posledni stav je prilis stary "
            f"({age.total_seconds() / 3600.0:.1f} h), cache nepouzivam."
        )
        return False

    source_version = decision.get("backend_version") or weather.get("backend_version")
    weather = _copy_json(weather)
    decision = _copy_json(decision)
    moon = _copy_json(moon)

    weather["backend_version"] = core.APP_VERSION
    weather["restored_from_cache"] = True
    weather["refreshing"] = True
    weather["cache_source_version"] = source_version
    weather["cache_age_minutes"] = round(age.total_seconds() / 60.0, 1)

    decision["backend_version"] = core.APP_VERSION
    decision["restored_from_cache"] = True
    decision["refreshing"] = True
    decision["cache_source_version"] = source_version
    decision["cache_age_minutes"] = round(age.total_seconds() / 60.0, 1)

    attrs = moon.get("attributes") if isinstance(moon.get("attributes"), dict) else None
    if attrs is not None:
        attrs["backend_version"] = core.APP_VERSION
        attrs["restored_from_cache"] = True
        attrs["refreshing"] = True

    with core.STATE_LOCK:
        core.STATE.clear()
        core.STATE.update(weather)
        core.DECISION_STATE.clear()
        core.DECISION_STATE.update(decision)
        core.MOON_STATE.clear()
        core.MOON_STATE.update(moon)

    if options.get("publish_homeassistant_entities", True):
        try:
            core.publish_homeassistant_entities(options, weather, decision, moon)
            core.log(
                "STAV CACHE: okamzite obnoven posledni platny stav "
                f"({age.total_seconds() / 60.0:.0f} min stary); probiha cerstvy prepocet."
            )
        except Exception as exc:
            core.log(f"STAV CACHE VAROVANI: stav obnoven v backendu, ale HA publikace selhala: {exc}")
    return True


def install(core: Any) -> None:
    if getattr(core, "_STATE_CACHE_PATCH_INSTALLED", False):
        return

    old_refresh_once = core.refresh_once
    old_main = core.main

    def refresh_once(options: dict[str, Any]) -> None:
        old_refresh_once(options)
        save_last_good_state(core)

    def main() -> None:
        options = core.load_options()
        core.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        restore_last_good_state(core, options)
        old_main()

    core.refresh_once = refresh_once
    core.main = main
    core._STATE_CACHE_PATCH_INSTALLED = True
