"""Persistent last-good Home Assistant state guard for Astro Weather Backend 12.3.3."""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

RELEASE_VERSION = "12.3.3"
CACHE_FILENAME = "last_good_homeassistant_state.json"
MAX_CACHE_AGE = timedelta(hours=12)

_REFRESH_FALLBACK: tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None = None


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


def _decision_is_valid(decision: dict[str, Any]) -> bool:
    daily = decision.get("daily")
    machine = str(decision.get("machine_state") or "").lower()
    state = str(decision.get("state") or "").lower()
    return (
        isinstance(daily, list)
        and bool(daily)
        and machine not in {"unavailable", "unknown", "none", ""}
        and state not in {"unavailable", "unknown", "bez dat", ""}
    )


def _snapshot_last_good(core: Any):
    with core.STATE_LOCK:
        weather = _copy_json(core.STATE)
        decision = _copy_json(core.DECISION_STATE)
        moon = _copy_json(core.MOON_STATE)
    if not _decision_is_valid(decision) or not moon:
        return None
    return weather, decision, moon


def _decorate_snapshot(
    core: Any,
    snapshot: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
    *,
    refreshing: bool,
    refresh_error: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    weather, decision, moon = (_copy_json(item) for item in snapshot)
    now = core.iso_z(core.utc_now())

    weather["backend_version"] = core.APP_VERSION
    weather["refreshing"] = refreshing
    weather["last_good_state"] = True
    decision["backend_version"] = core.APP_VERSION
    decision["refreshing"] = refreshing
    decision["last_good_state"] = True

    if refreshing:
        weather["refresh_started_at"] = now
        decision["refresh_started_at"] = now
    else:
        weather.pop("refresh_started_at", None)
        decision.pop("refresh_started_at", None)

    if refresh_error:
        weather["last_refresh_error"] = refresh_error[:300]
        weather["last_refresh_failed_at"] = now
        decision["last_refresh_error"] = refresh_error[:300]
        decision["last_refresh_failed_at"] = now
    else:
        weather.pop("last_refresh_error", None)
        decision.pop("last_refresh_error", None)

    attrs = moon.get("attributes") if isinstance(moon.get("attributes"), dict) else None
    if attrs is not None:
        attrs["backend_version"] = core.APP_VERSION
        attrs["refreshing"] = refreshing
        attrs["last_good_state"] = True
        if refresh_error:
            attrs["last_refresh_error"] = refresh_error[:300]
        else:
            attrs.pop("last_refresh_error", None)

    return weather, decision, moon


def _apply_snapshot(core: Any, snapshot) -> None:
    weather, decision, moon = snapshot
    with core.STATE_LOCK:
        core.STATE.clear()
        core.STATE.update(_copy_json(weather))
        core.DECISION_STATE.clear()
        core.DECISION_STATE.update(_copy_json(decision))
        core.MOON_STATE.clear()
        core.MOON_STATE.update(_copy_json(moon))


def save_last_good_state(core: Any) -> None:
    snapshot = _snapshot_last_good(core)
    if snapshot is None:
        return
    weather, decision, moon = snapshot

    generated_at = core.parse_iso_utc(
        str(decision.get("generated_at") or weather.get("generated_at") or "")
    )
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
    if not _decision_is_valid(decision):
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
    snapshot = _decorate_snapshot(
        core,
        (_copy_json(weather), _copy_json(decision), _copy_json(moon)),
        refreshing=True,
    )
    weather, decision, moon = snapshot
    weather["restored_from_cache"] = True
    weather["cache_source_version"] = source_version
    weather["cache_age_minutes"] = round(age.total_seconds() / 60.0, 1)
    decision["restored_from_cache"] = True
    decision["cache_source_version"] = source_version
    decision["cache_age_minutes"] = round(age.total_seconds() / 60.0, 1)

    attrs = moon.get("attributes") if isinstance(moon.get("attributes"), dict) else None
    if attrs is not None:
        attrs["restored_from_cache"] = True

    _apply_snapshot(core, (weather, decision, moon))

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
    global _REFRESH_FALLBACK
    if getattr(core, "_STATE_CACHE_PATCH_INSTALLED", False):
        return

    old_refresh_once = core.refresh_once
    old_main = core.main
    old_publish = core.publish_homeassistant_entities
    old_load_options = core.load_options

    def load_options() -> dict[str, Any]:
        options = old_load_options()
        agent = str(options.get("met_user_agent", "")).strip()
        if not agent or agent.startswith("AstroWeatherBackend/"):
            options["met_user_agent"] = (
                f"AstroWeatherBackend/{RELEASE_VERSION} "
                "https://github.com/Z0472/home-assistant-astro-weather"
            )
        return options

    def publish_homeassistant_entities(
        options: dict[str, Any],
        weather_state: dict[str, Any],
        decision_state: dict[str, Any],
        moon_doc: dict[str, Any],
    ) -> None:
        fallback = _REFRESH_FALLBACK
        if fallback is not None and not _decision_is_valid(decision_state):
            reason = str(decision_state.get("reason") or "refresh vratil neplatny stav")
            guarded = _decorate_snapshot(core, fallback, refreshing=True, refresh_error=reason)
            core.log(
                "STAV GUARD: potlacuji docasny unavailable/BEZ DAT; "
                "v Home Assistantu zustava posledni platny stav."
            )
            return old_publish(options, *guarded)
        return old_publish(options, weather_state, decision_state, moon_doc)

    def refresh_once(options: dict[str, Any]) -> None:
        global _REFRESH_FALLBACK
        fallback = _snapshot_last_good(core)
        _REFRESH_FALLBACK = fallback

        if fallback is not None and options.get("publish_homeassistant_entities", True):
            try:
                old_publish(options, *_decorate_snapshot(core, fallback, refreshing=True))
            except Exception as exc:
                core.log(f"STAV GUARD VAROVANI: nelze potvrdit posledni platny stav pred refreshem: {exc}")

        try:
            old_refresh_once(options)
        except Exception as exc:
            if fallback is not None:
                restored = _decorate_snapshot(core, fallback, refreshing=False, refresh_error=str(exc))
                _apply_snapshot(core, restored)
                if options.get("publish_homeassistant_entities", True):
                    try:
                        old_publish(options, *restored)
                    except Exception as publish_exc:
                        core.log(f"STAV GUARD VAROVANI: obnova po chybe publikace selhala: {publish_exc}")
            raise
        finally:
            _REFRESH_FALLBACK = None

        current = _snapshot_last_good(core)
        if current is None and fallback is not None:
            with core.STATE_LOCK:
                failed_reason = str(core.DECISION_STATE.get("reason") or "refresh vratil neplatny stav")
            restored = _decorate_snapshot(core, fallback, refreshing=False, refresh_error=failed_reason)
            _apply_snapshot(core, restored)
            if options.get("publish_homeassistant_entities", True):
                try:
                    old_publish(options, *restored)
                except Exception as exc:
                    core.log(f"STAV GUARD VAROVANI: obnova posledniho platneho stavu selhala: {exc}")
            core.log("STAV GUARD: refresh nedal platny vysledek; ponechavam predchozi senzor bez vypadku.")
            return

        save_last_good_state(core)

    def main() -> None:
        options = core.load_options()
        core.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        restore_last_good_state(core, options)
        old_main()

    core.load_options = load_options
    core.publish_homeassistant_entities = publish_homeassistant_entities
    core.refresh_once = refresh_once
    core.main = main
    core.APP_VERSION = RELEASE_VERSION
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._STATE_CACHE_PATCH_INSTALLED = True
