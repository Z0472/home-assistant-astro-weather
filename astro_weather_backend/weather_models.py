"""Weather-model adapters for Astro Weather Backend 12.2."""
from __future__ import annotations

import bz2
import json
import math
import re
import shutil
import urllib.parse
from typing import Any

ICON_URL = "https://api.open-meteo.com/v1/forecast"
ICON_MODEL = "dwd_icon_seamless"
ICON_MODEL_FAMILY = "DWD ICON"
ALADIN_MAX_NEAREST_GRID_KM = 25.0

ICON_ROWS: dict[str, dict[str, Any]] = {}
ICON_SOURCE: dict[str, Any] = {"available": False, "enabled": True}
ICON_ERROR: str | None = None
_ALADIN_COVERAGE_CACHE: dict[tuple[str, float, float], float] = {}


def cloud(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not 0 <= number <= 100:
        return None
    return number


def icon_forecast_url(options: dict[str, Any]) -> str:
    days = max(1, min(8, math.ceil((int(options["horizon_hours"]) + 24) / 24)))
    return ICON_URL + "?" + urllib.parse.urlencode({
        "latitude": f"{float(options['latitude']):.5f}",
        "longitude": f"{float(options['longitude']):.5f}",
        "elevation": str(int(options["altitude"])),
        "hourly": "cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high",
        "timezone": "UTC",
        "forecast_days": str(days),
        # Explicit DWD family: never Open-Meteo Best Match.
        "models": ICON_MODEL,
    })


def parse_icon_forecast(doc: dict[str, Any], options: dict[str, Any], core: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(doc, dict) or doc.get("error"):
        raise ValueError(str(doc.get("reason") if isinstance(doc, dict) else "neplatný JSON"))
    lat, lon = core.safe_float(doc.get("latitude")), core.safe_float(doc.get("longitude"))
    if lat is not None and lon is not None and (
        abs(lat - float(options["latitude"])) > 1.0
        or abs(lon - float(options["longitude"])) > 1.0
    ):
        raise ValueError("Open-Meteo DWD ICON vrátil jinou lokalitu")
    hourly = doc.get("hourly") if isinstance(doc.get("hourly"), dict) else {}
    times = hourly.get("time")
    if not isinstance(times, list):
        raise ValueError("Open-Meteo DWD ICON neobsahuje hodinovou osu")
    fields = {
        "cloud_total": "cloud_cover",
        "cloud_low": "cloud_cover_low",
        "cloud_medium": "cloud_cover_mid",
        "cloud_high": "cloud_cover_high",
    }
    result: dict[str, dict[str, Any]] = {}
    for i, raw_time in enumerate(times):
        dt = core.parse_iso_utc(str(raw_time))
        if dt is None or dt.minute or dt.second:
            continue
        row = {}
        for out_name, api_name in fields.items():
            values = hourly.get(api_name)
            value = cloud(values[i] if isinstance(values, list) and i < len(values) else None)
            row[out_name] = None if value is None else round(value, 1)
        if row["cloud_total"] is not None:
            result[core.iso_z(dt)] = row
    if not result:
        raise ValueError("Open-Meteo DWD ICON neobsahuje platnou oblačnost")
    return result


def fetch_icon(options: dict[str, Any], core: Any) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    endpoint = icon_forecast_url(options)
    doc = json.loads(core.http_get(
        endpoint, user_agent=options["met_user_agent"], timeout=45
    ).decode("utf-8"))
    rows = parse_icon_forecast(doc, options, core)
    return rows, {
        "available": True,
        "enabled": True,
        "provider": "Open-Meteo DWD ICON API",
        "model": "DWD ICON Seamless",
        "model_family": ICON_MODEL_FAMILY,
        "dataset": ICON_MODEL,
        "endpoint": endpoint,
        "hours": len(rows),
        "note": "DWD ICON family: ICON-D2 / ICON-EU / ICON Global podle pokrytí a horizontu.",
    }


def refresh_icon(options: dict[str, Any], core: Any) -> None:
    global ICON_ROWS, ICON_SOURCE, ICON_ERROR
    ICON_ROWS, ICON_ERROR = {}, None
    if not options.get("use_icon", True):
        ICON_SOURCE = {
            "available": False, "enabled": False,
            "model": "DWD ICON Seamless", "model_family": ICON_MODEL_FAMILY,
        }
        return
    try:
        ICON_ROWS, ICON_SOURCE = fetch_icon(options, core)
        core.log(f"ICON: {len(ICON_ROWS)} hodin, DWD ICON Seamless")
    except Exception as exc:
        ICON_ERROR = str(exc)
        ICON_SOURCE = {
            "available": False, "enabled": True,
            "provider": "Open-Meteo DWD ICON API",
            "model": "DWD ICON Seamless", "model_family": ICON_MODEL_FAMILY,
        }
        core.log(f"ICON CHYBA: {exc}")


def aladin_nearest_grid_distance_km(core: Any, run: str, options: dict[str, Any]) -> float:
    """Validate ALADIN coverage by actual nearest-grid distance, not a country bbox."""
    key = (run, round(float(options["latitude"]), 4), round(float(options["longitude"]), 4))
    if key in _ALADIN_COVERAGE_CACHE:
        return _ALADIN_COVERAGE_CACHE[key]
    if shutil.which("grib_ls") is None:
        raise RuntimeError("ecCodes/grib_ls neni v kontejneru k dispozici")
    bz_path = core.download_aladin_product(run, core.ALADIN_PRODUCTS["cloud_total"], options)
    path = bz_path.with_name(bz_path.name + ".coverage.grb")
    try:
        with bz2.open(bz_path, "rb") as src, path.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        output = core.run_cmd([
            "grib_ls", "-w", "count=1", "-F", "%.3f",
            "-l", f"{float(options['latitude']):.6f},{float(options['longitude']):.6f},1",
            "-p", "shortName", str(path),
        ], timeout=90)
        found = re.findall(r"distance=([0-9]+(?:\.[0-9]+)?)\s*\(Km\)", output, re.IGNORECASE)
        if not found:
            raise RuntimeError("ecCodes nevratil vzdalenost k nejblizsimu bodu ALADIN")
        distance = min(float(v) for v in found)
        _ALADIN_COVERAGE_CACHE[key] = distance
        return distance
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def fetch_aladin_wrapped(core: Any, original: Any, options: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    run = core.discover_latest_aladin_run(options)
    distance = aladin_nearest_grid_distance_km(core, run, options)
    if distance > ALADIN_MAX_NEAREST_GRID_KM:
        raise RuntimeError(
            f"Lokalita je mimo domenu ALADIN CZ_1km: nejblizsi bod site je {distance:.1f} km daleko"
        )
    rows, source = original(options)
    source.update(
        nearest_grid_distance_km=round(distance, 2),
        coverage_validated=True,
        model_family="CHMI ALADIN",
    )
    return rows, source
