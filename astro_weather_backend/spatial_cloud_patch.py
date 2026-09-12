"""Spatial cloud-neighbourhood analysis for Astro Weather Backend 12.3."""
from __future__ import annotations

import bz2
import json
import math
import shutil
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import night_forecast_patch as night_patch
import weather_models as wm

RELEASE_VERSION = "12.3.0"
ASTRO_CARD_VERSION = 26
DEFAULT_RADIUS_KM = 30
MIN_RADIUS_KM = 10
MAX_RADIUS_KM = 50
EDGE_THRESHOLD = 50.0
CLEAR_THRESHOLD = 25.0
CLOUDY_THRESHOLD = 60.0
NEAREST_TIME_MINUTES = 55
DECISION_ETA_MINUTES = 180
EARTH_RADIUS_KM = 6371.0088

BEARINGS = (
    (0.0, "S"),
    (45.0, "SV"),
    (90.0, "V"),
    (135.0, "JV"),
    (180.0, "J"),
    (225.0, "JZ"),
    (270.0, "Z"),
    (315.0, "SZ"),
)

ICON_SPATIAL_ROWS: dict[str, dict[str, Any]] = {}
ICON_WIND_ROWS: dict[str, dict[str, Any]] = {}
ALADIN_SPATIAL_ROWS: dict[str, dict[str, Any]] = {}
ICON_SPATIAL_SOURCE: dict[str, Any] = {}
ALADIN_SPATIAL_SOURCE: dict[str, Any] = {}


def _safe(core: Any, value: Any) -> float | None:
    return core.safe_float(value)


def _destination(latitude: float, longitude: float, distance_km: float, bearing_deg: float) -> tuple[float, float]:
    """Destination point on a sphere, accurate enough for 10-50 km sampling."""
    lat1 = math.radians(latitude)
    lon1 = math.radians(longitude)
    bearing = math.radians(bearing_deg)
    angular = distance_km / EARTH_RADIUS_KM
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular)
        + math.cos(lat1) * math.sin(angular) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), ((math.degrees(lon2) + 540.0) % 360.0) - 180.0


def build_spatial_points(latitude: float, longitude: float, radius_km: int) -> list[dict[str, Any]]:
    radius = max(MIN_RADIUS_KM, min(MAX_RADIUS_KM, int(radius_km)))
    points: list[dict[str, Any]] = [{
        "id": "C",
        "ring": "center",
        "bearing": None,
        "direction": "STŘED",
        "distance_km": 0.0,
        "latitude": float(latitude),
        "longitude": float(longitude),
    }]
    for ring, distance in (("inner", radius / 2.0), ("outer", float(radius))):
        for bearing, direction in BEARINGS:
            lat, lon = _destination(float(latitude), float(longitude), distance, bearing)
            points.append({
                "id": f"{ring}_{int(bearing):03d}",
                "ring": ring,
                "bearing": bearing,
                "direction": direction,
                "distance_km": round(distance, 3),
                "latitude": lat,
                "longitude": lon,
            })
    return points


def _forecast_days(options: dict[str, Any]) -> int:
    return max(1, min(8, math.ceil((int(options["horizon_hours"]) + 24) / 24)))


def _icon_spatial_url(options: dict[str, Any], points: list[dict[str, Any]]) -> str:
    return wm.ICON_URL + "?" + urllib.parse.urlencode({
        "latitude": ",".join(f"{p['latitude']:.5f}" for p in points),
        "longitude": ",".join(f"{p['longitude']:.5f}" for p in points),
        "hourly": "cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high",
        "timezone": "UTC",
        "forecast_days": str(_forecast_days(options)),
        "models": wm.ICON_MODEL,
    })


def _icon_wind_url(options: dict[str, Any]) -> str:
    variables = []
    for level in (850, 700, 500, 300):
        variables += [f"wind_speed_{level}hPa", f"wind_direction_{level}hPa"]
    return wm.ICON_URL + "?" + urllib.parse.urlencode({
        "latitude": f"{float(options['latitude']):.5f}",
        "longitude": f"{float(options['longitude']):.5f}",
        "hourly": ",".join(variables),
        "timezone": "UTC",
        "forecast_days": str(_forecast_days(options)),
        "models": wm.ICON_MODEL,
        "wind_speed_unit": "ms",
    })


def _parse_icon_locations(doc: Any, points: list[dict[str, Any]], core: Any) -> dict[str, dict[str, Any]]:
    locations = doc if isinstance(doc, list) else [doc]
    if len(locations) != len(points):
        raise ValueError(f"ICON spatial vrátil {len(locations)} lokalit, očekáváno {len(points)}")

    rows: dict[str, dict[str, Any]] = {}
    field_map = {
        "total": "cloud_cover",
        "low": "cloud_cover_low",
        "mid": "cloud_cover_mid",
        "high": "cloud_cover_high",
    }
    for point, location in zip(points, locations):
        if not isinstance(location, dict) or location.get("error"):
            raise ValueError(str(location.get("reason") if isinstance(location, dict) else "neplatný JSON"))
        hourly = location.get("hourly") if isinstance(location.get("hourly"), dict) else {}
        times = hourly.get("time")
        if not isinstance(times, list):
            raise ValueError("ICON spatial neobsahuje hodinovou osu")
        for index, raw_time in enumerate(times):
            dt = core.parse_iso_utc(str(raw_time))
            if dt is None:
                continue
            stamp = core.iso_z(dt)
            values: dict[str, float | None] = {}
            for name, api_name in field_map.items():
                series = hourly.get(api_name)
                raw = series[index] if isinstance(series, list) and index < len(series) else None
                values[name] = wm.cloud(raw)
            if values["total"] is None:
                continue
            rows.setdefault(stamp, {"points": {}})["points"][point["id"]] = values
    return rows


def _parse_icon_wind(doc: Any, core: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(doc, dict) or doc.get("error"):
        return {}
    hourly = doc.get("hourly") if isinstance(doc.get("hourly"), dict) else {}
    times = hourly.get("time")
    if not isinstance(times, list):
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for index, raw_time in enumerate(times):
        dt = core.parse_iso_utc(str(raw_time))
        if dt is None:
            continue
        stamp = core.iso_z(dt)
        levels: dict[str, Any] = {}
        for level in (850, 700, 500, 300):
            speeds = hourly.get(f"wind_speed_{level}hPa")
            directions = hourly.get(f"wind_direction_{level}hPa")
            speed = core.safe_float(speeds[index] if isinstance(speeds, list) and index < len(speeds) else None)
            direction = core.safe_float(directions[index] if isinstance(directions, list) and index < len(directions) else None)
            if speed is not None or direction is not None:
                levels[str(level)] = {
                    "speed_ms": None if speed is None else round(speed, 1),
                    "direction_deg": None if direction is None else round(direction % 360.0, 1),
                }
        if levels:
            rows[stamp] = levels
    return rows


def fetch_icon_spatial(options: dict[str, Any], core: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    points = build_spatial_points(options["latitude"], options["longitude"], options["spatial_radius_km"])
    endpoint = _icon_spatial_url(options, points)
    doc = json.loads(core.http_get(endpoint, user_agent=options["met_user_agent"], timeout=60).decode("utf-8"))
    rows = _parse_icon_locations(doc, points, core)

    wind_rows: dict[str, Any] = {}
    wind_error = None
    try:
        wind_doc = json.loads(core.http_get(
            _icon_wind_url(options), user_agent=options["met_user_agent"], timeout=45
        ).decode("utf-8"))
        wind_rows = _parse_icon_wind(wind_doc, core)
    except Exception as exc:
        wind_error = str(exc)

    source = {
        "available": bool(rows),
        "provider": "Open-Meteo DWD ICON API",
        "model": "DWD ICON Seamless",
        "points": len(points),
        "radius_km": int(options["spatial_radius_km"]),
        "wind_available": bool(wind_rows),
        "wind_error": wind_error,
    }
    return rows, wind_rows, source


def fetch_aladin_spatial(options: dict[str, Any], core: Any, run: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if shutil.which("grib_get") is None:
        raise RuntimeError("ecCodes/grib_get neni v kontejneru k dispozici")
    points = build_spatial_points(options["latitude"], options["longitude"], options["spatial_radius_km"])
    product = core.ALADIN_PRODUCTS["cloud_total"]
    bz_path = core.download_aladin_product(run, product, options)
    grib_path = Path(str(bz_path) + ".spatial.grb")
    try:
        with bz2.open(bz_path, "rb") as src, grib_path.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        times = core.grib_message_times(grib_path)
        unit, global_max = core.grib_unit_and_global_max(grib_path)
        rows: dict[str, dict[str, Any]] = {stamp: {"points": {}} for stamp in times}
        for point in points:
            out = core.run_cmd([
                "grib_get",
                "-F", "%.8f",
                "-l", f"{point['latitude']:.6f},{point['longitude']:.6f},1",
                str(grib_path),
            ], timeout=180)
            values = core.parse_number_lines(out)
            if len(values) != len(times):
                raise RuntimeError(
                    f"ALADIN spatial {point['id']}: {len(values)} hodnot, očekáváno {len(times)}"
                )
            for stamp, raw in zip(times, values):
                rows[stamp]["points"][point["id"]] = core.cloud_to_percent(raw, unit, global_max)
        return rows, {
            "available": bool(rows),
            "provider": "CHMI ALADIN CZ_1km",
            "run": run,
            "points": len(points),
            "radius_km": int(options["spatial_radius_km"]),
        }
    finally:
        try:
            grib_path.unlink(missing_ok=True)
        except Exception:
            pass


def _nearest_row(core: Any, rows: dict[str, Any], target: datetime) -> tuple[str | None, Any]:
    best_stamp = None
    best = None
    best_diff = float("inf")
    for stamp, value in rows.items():
        dt = core.parse_iso_utc(str(stamp))
        if dt is None:
            continue
        diff = abs((dt - target).total_seconds())
        if diff < best_diff:
            best_diff, best_stamp, best = diff, stamp, value
    if best_diff > NEAREST_TIME_MINUTES * 60:
        return None, None
    return best_stamp, best


def _angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _edge_for_values(points: list[dict[str, Any]], values: dict[str, float], threshold: float = EDGE_THRESHOLD) -> dict[str, Any] | None:
    center = values.get("C")
    if center is None:
        return None
    target_type = "cloud" if center < threshold else "clear"
    candidates: list[dict[str, Any]] = []

    by_bearing: dict[float, list[tuple[float, float]]] = {}
    for point in points:
        if point["id"] == "C" or point["id"] not in values or point["bearing"] is None:
            continue
        by_bearing.setdefault(float(point["bearing"]), []).append(
            (float(point["distance_km"]), float(values[point["id"]]))
        )

    for bearing, radial in by_bearing.items():
        samples = [(0.0, float(center))] + sorted(radial)
        for (d0, v0), (d1, v1) in zip(samples, samples[1:]):
            crosses = (v0 < threshold <= v1) if target_type == "cloud" else (v0 >= threshold > v1)
            if not crosses:
                continue
            if abs(v1 - v0) < 1e-9:
                distance = d1
            else:
                fraction = (threshold - v0) / (v1 - v0)
                distance = d0 + max(0.0, min(1.0, fraction)) * (d1 - d0)
            direction = min(BEARINGS, key=lambda item: _angle_diff(item[0], bearing))[1]
            candidates.append({
                "type": target_type,
                "bearing_deg": round(bearing, 1),
                "direction": direction,
                "distance_km": round(distance, 1),
                "threshold": threshold,
            })
            break
    return min(candidates, key=lambda item: item["distance_km"], default=None)


def _dominant_layer(icon_row: dict[str, Any] | None) -> tuple[str | None, int | None]:
    if not isinstance(icon_row, dict):
        return None, None
    center = icon_row.get("points", {}).get("C", {})
    layers = {
        "nízká": wm.cloud(center.get("low")),
        "střední": wm.cloud(center.get("mid")),
        "vysoká": wm.cloud(center.get("high")),
    }
    valid = [(name, value) for name, value in layers.items() if value is not None]
    if not valid:
        return None, None
    name, value = max(valid, key=lambda item: item[1])
    if value < 20:
        return None, None
    return name, {"nízká": 850, "střední": 700, "vysoká": 300}[name]


def _snapshot(core: Any, options: dict[str, Any], target: datetime) -> dict[str, Any] | None:
    points = build_spatial_points(options["latitude"], options["longitude"], options["spatial_radius_km"])
    icon_stamp, icon = _nearest_row(core, ICON_SPATIAL_ROWS, target)
    aladin_stamp, aladin = _nearest_row(core, ALADIN_SPATIAL_ROWS, target)
    if icon is None and aladin is None:
        return None

    values: dict[str, float] = {}
    coverage: dict[str, int] = {"ICON": 0, "ALADIN": 0}
    for point in points:
        samples: list[float] = []
        if isinstance(icon, dict):
            value = wm.cloud(icon.get("points", {}).get(point["id"], {}).get("total"))
            if value is not None:
                samples.append(value)
                coverage["ICON"] += 1
        if isinstance(aladin, dict):
            value = wm.cloud(aladin.get("points", {}).get(point["id"]))
            if value is not None:
                samples.append(value)
                coverage["ALADIN"] += 1
        if samples:
            values[point["id"]] = sum(samples) / len(samples)

    if "C" not in values or len(values) < 3:
        return None
    all_values = list(values.values())
    edge = _edge_for_values(points, values)
    layer, pressure = _dominant_layer(icon)
    _, wind_row = _nearest_row(core, ICON_WIND_ROWS, target)
    wind = wind_row.get(str(pressure)) if pressure is not None and isinstance(wind_row, dict) else None
    wind_from = _safe(core, wind.get("direction_deg")) if isinstance(wind, dict) else None
    wind_speed = _safe(core, wind.get("speed_ms")) if isinstance(wind, dict) else None
    wind_support = None
    if edge is not None and wind_from is not None:
        wind_support = _angle_diff(float(edge["bearing_deg"]), wind_from) <= 67.5

    return {
        "time": core.iso_z(target),
        "centerCloud": round(values["C"], 1),
        "minCloud": round(min(all_values), 1),
        "maxCloud": round(max(all_values), 1),
        "meanCloud": round(sum(all_values) / len(all_values), 1),
        "spatialStability": round(max(0.0, 100.0 - (max(all_values) - min(all_values))), 1),
        "boundary": bool(min(all_values) <= CLEAR_THRESHOLD and max(all_values) >= CLOUDY_THRESHOLD),
        "edge": edge,
        "dominantLayer": layer,
        "windLevelHpa": pressure,
        "windFromDeg": None if wind_from is None else round(wind_from % 360.0, 1),
        "windSpeedMs": None if wind_speed is None else round(wind_speed, 1),
        "windSupportsEdgeMotion": wind_support,
        "sources": [name for name, count in coverage.items() if count >= max(3, len(points) // 2)],
        "iconTime": icon_stamp,
        "aladinTime": aladin_stamp,
    }


def _format_eta(minutes: int | None) -> str:
    if minutes is None:
        return ""
    rounded = max(0, int(round(minutes / 15.0) * 15))
    if rounded < 60:
        return f"~{rounded} min"
    hours, mins = divmod(rounded, 60)
    if mins == 0:
        return f"~{hours} h"
    return f"~{hours} h {mins} min"


def _series_trend(core: Any, options: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:
    hours = result.get("displayHours") if isinstance(result.get("displayHours"), list) else result.get("hours")
    if not isinstance(hours, list) or not hours:
        return None

    records: list[tuple[datetime, dict[str, Any]]] = []
    for hour in hours:
        dt = core.parse_iso_utc(str(hour.get("start", ""))) if isinstance(hour, dict) else None
        if dt is None:
            continue
        snap = _snapshot(core, options, dt)
        if snap is not None:
            records.append((dt, snap))
    if not records:
        return None

    now = core.utc_now()
    index = 0
    for i, (dt, _) in enumerate(records):
        end = dt + timedelta(hours=1)
        if dt <= now < end:
            index = i
            break
        if dt >= now:
            index = i
            break
    current_time, current = records[index]
    future = records[index + 1:]
    center = float(current["centerCloud"])
    state = "boundary"
    eta_minutes: int | None = None

    def first_cross(predicate):
        for when, snap in future:
            if predicate(float(snap["centerCloud"])):
                return when, snap
        return None

    if center <= CLEAR_THRESHOLD:
        state = "stable_clear"
        crossing = first_cross(lambda value: value >= CLOUDY_THRESHOLD)
        if crossing is not None:
            state = "incoming"
            eta_minutes = max(0, round((crossing[0] - current_time).total_seconds() / 60))
        elif current.get("boundary"):
            state = "boundary"
    elif center >= CLOUDY_THRESHOLD:
        state = "stable_cloudy"
        crossing = first_cross(lambda value: value <= CLEAR_THRESHOLD)
        if crossing is not None:
            state = "clearing"
            eta_minutes = max(0, round((crossing[0] - current_time).total_seconds() / 60))
        elif current.get("boundary"):
            state = "boundary"
    else:
        current["boundary"] = True
        to_clear = first_cross(lambda value: value <= CLEAR_THRESHOLD)
        to_cloud = first_cross(lambda value: value >= CLOUDY_THRESHOLD)
        choices = []
        if to_clear is not None:
            choices.append(("clearing", to_clear[0]))
        if to_cloud is not None:
            choices.append(("incoming", to_cloud[0]))
        if choices:
            state, when = min(choices, key=lambda item: item[1])
            eta_minutes = max(0, round((when - current_time).total_seconds() / 60))

    edge = current.get("edge")
    if state in {"boundary", "stable_clear", "stable_cloudy"} and isinstance(edge, dict):
        edge_type = edge.get("type")
        samples = [(current_time, float(edge["distance_km"]))]
        for when, snap in future[:3]:
            candidate = snap.get("edge")
            if isinstance(candidate, dict) and candidate.get("type") == edge_type:
                samples.append((when, float(candidate["distance_km"])))
        if len(samples) >= 2:
            hours_delta = (samples[-1][0] - samples[0][0]).total_seconds() / 3600.0
            distance_delta = samples[-1][1] - samples[0][1]
            if hours_delta > 0 and distance_delta <= -2.0:
                speed = -distance_delta / hours_delta
                estimate = round(samples[0][1] / speed * 60) if speed >= 1.0 else None
                if estimate is not None and 0 <= estimate <= 360:
                    if edge_type == "cloud" and center < EDGE_THRESHOLD:
                        state, eta_minutes = "incoming", estimate
                    elif edge_type == "clear" and center >= EDGE_THRESHOLD:
                        state, eta_minutes = "clearing", estimate

    radius = int(options["spatial_radius_km"])
    edge_distance = edge.get("distance_km") if isinstance(edge, dict) else None
    edge_direction = edge.get("direction") if isinstance(edge, dict) else None
    eta_text = _format_eta(eta_minutes)

    if state == "incoming":
        short = f"☁ Oblačnost přichází {eta_text}".strip()
        if edge_direction:
            short += f" od {edge_direction}"
    elif state == "clearing":
        short = f"🌙 Vyjasnění {eta_text}".strip()
        if edge_direction:
            short += f" od {edge_direction}"
    elif state == "stable_clear":
        short = "✓ Okolí stabilně jasné"
    elif state == "stable_cloudy":
        short = "☁ Okolí stabilně zatažené"
    else:
        short = "⚠ Hrana oblačnosti v okolí"
        if edge_distance is not None and edge_direction:
            short += f" · ~{float(edge_distance):.0f} km {edge_direction}"

    return {
        "state": state,
        "shortText": short,
        "radiusKm": radius,
        "etaMinutes": eta_minutes,
        "edgeDistanceKm": edge_distance,
        "edgeDirection": edge_direction,
        "centerCloud": current.get("centerCloud"),
        "minCloud": current.get("minCloud"),
        "maxCloud": current.get("maxCloud"),
        "spatialStability": current.get("spatialStability"),
        "dominantLayer": current.get("dominantLayer"),
        "windLevelHpa": current.get("windLevelHpa"),
        "windFromDeg": current.get("windFromDeg"),
        "windSpeedMs": current.get("windSpeedMs"),
        "windSupportsEdgeMotion": current.get("windSupportsEdgeMotion"),
        "sources": current.get("sources", []),
        "sampleTime": current.get("time"),
    }


def _apply_to_decision(core: Any, options: dict[str, Any], result: dict[str, Any], spatial: dict[str, Any]) -> None:
    if night_patch._has_hard_veto(core, result, options):
        return
    state = spatial.get("state")
    eta = _safe(core, spatial.get("etaMinutes"))
    edge = _safe(core, spatial.get("edgeDistanceKm"))
    radius = float(options["spatial_radius_km"])

    if result.get("decision") == "good":
        risky = state == "incoming" and (eta is None or eta <= DECISION_ETA_MINUTES)
        risky = risky or (state == "boundary" and edge is not None and edge <= max(10.0, radius * 0.6))
        if risky:
            result.update(
                decision="uncertain",
                label="NEJISTÉ",
                reason=(
                    f"{spatial.get('shortText', 'Hrana oblačnosti je poblíž')}. "
                    "Bodová předpověď proto není prostorově stabilní; před otevřením zkontroluj aktuální oblohu."
                ),
                spatialAdjusted=True,
            )
    elif result.get("decision") == "bad":
        hopeful = state == "clearing" and eta is not None and eta <= DECISION_ETA_MINUTES
        hopeful = hopeful or (
            state == "boundary"
            and _safe(core, spatial.get("spatialStability")) is not None
            and float(spatial["spatialStability"]) < 50.0
        )
        if hopeful:
            result.update(
                decision="uncertain",
                label="NEJISTÉ",
                reason=(
                    f"{spatial.get('shortText', 'Prostorová situace je proměnlivá')}. "
                    "Bez tvrdého veto důvodu proto není vhodné vydat jisté NESPOUŠTĚT."
                ),
                spatialAdjusted=True,
            )


def install(core: Any) -> None:
    if getattr(core, "_SPATIAL_CLOUD_PATCH_INSTALLED", False):
        return

    old_load_options = core.load_options
    old_settings = core.decision_settings
    old_fetch_met = core.fetch_met
    old_fetch_aladin = core.fetch_aladin
    old_analyze_night = core.analyze_night

    def load_options() -> dict[str, Any]:
        options = old_load_options()
        options["spatial_cloud_analysis"] = bool(options.get("spatial_cloud_analysis", True))
        try:
            radius = int(options.get("spatial_radius_km", DEFAULT_RADIUS_KM))
        except (TypeError, ValueError):
            radius = DEFAULT_RADIUS_KM
        options["spatial_radius_km"] = max(MIN_RADIUS_KM, min(MAX_RADIUS_KM, radius))
        agent = str(options.get("met_user_agent", "")).strip()
        if not agent or agent.startswith("AstroWeatherBackend/"):
            options["met_user_agent"] = (
                f"AstroWeatherBackend/{RELEASE_VERSION} "
                "https://github.com/Z0472/home-assistant-astro-weather"
            )
        return options

    def settings(options: dict[str, Any]) -> dict[str, Any]:
        value = old_settings(options)
        value["spatial_cloud_analysis"] = bool(options.get("spatial_cloud_analysis", True))
        value["spatial_radius_km"] = int(options.get("spatial_radius_km", DEFAULT_RADIUS_KM))
        return value

    def fetch_met(options: dict[str, Any]):
        global ICON_SPATIAL_ROWS, ICON_WIND_ROWS, ICON_SPATIAL_SOURCE
        rows, source = old_fetch_met(options)
        ICON_SPATIAL_ROWS, ICON_WIND_ROWS, ICON_SPATIAL_SOURCE = {}, {}, {}
        if options.get("spatial_cloud_analysis", True) and options.get("use_icon", True):
            try:
                ICON_SPATIAL_ROWS, ICON_WIND_ROWS, ICON_SPATIAL_SOURCE = fetch_icon_spatial(options, core)
                core.log(
                    f"PROSTOR ICON: {ICON_SPATIAL_SOURCE.get('points', 0)} bodů, "
                    f"radius {options['spatial_radius_km']} km"
                )
            except Exception as exc:
                ICON_SPATIAL_SOURCE = {"available": False, "error": str(exc)}
                core.log(f"PROSTOR ICON VAROVANI: {exc}")
        return rows, source

    def fetch_aladin(options: dict[str, Any]):
        global ALADIN_SPATIAL_ROWS, ALADIN_SPATIAL_SOURCE
        ALADIN_SPATIAL_ROWS, ALADIN_SPATIAL_SOURCE = {}, {}
        rows, source = old_fetch_aladin(options)
        if options.get("spatial_cloud_analysis", True):
            run = str(source.get("run") or "")
            if run:
                try:
                    ALADIN_SPATIAL_ROWS, ALADIN_SPATIAL_SOURCE = fetch_aladin_spatial(options, core, run)
                    core.log(
                        f"PROSTOR ALADIN: {ALADIN_SPATIAL_SOURCE.get('points', 0)} bodů, "
                        f"radius {options['spatial_radius_km']} km"
                    )
                except Exception as exc:
                    ALADIN_SPATIAL_SOURCE = {"available": False, "error": str(exc)}
                    core.log(f"PROSTOR ALADIN VAROVANI: {exc}")
        return rows, source

    def analyze_night(night: dict[str, Any], forecast: list[dict[str, Any]],
                      moon_rows: list[dict[str, Any]], options: dict[str, Any]) -> dict[str, Any] | None:
        result = old_analyze_night(night, forecast, moon_rows, options)
        if result is None or not options.get("spatial_cloud_analysis", True):
            return result
        spatial = _series_trend(core, options, result)
        if spatial is not None:
            result["spatialCloud"] = spatial
            _apply_to_decision(core, options, result, spatial)
        return result

    core.load_options = load_options
    core.decision_settings = settings
    core.fetch_met = fetch_met
    core.fetch_aladin = fetch_aladin
    core.analyze_night = analyze_night

    core.APP_VERSION = RELEASE_VERSION
    core.ASTRO_START_CARD_VERSION = ASTRO_CARD_VERSION
    current_installs = list(core.DASHBOARD_CARD_INSTALLS)
    target = f"astro-start-card-v{ASTRO_CARD_VERSION}.js"
    if not any(dst == target for _, dst in current_installs):
        current_installs.append(("astro-start-card-v26.js", target))
    core.DASHBOARD_CARD_INSTALLS = tuple(current_installs)
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._SPATIAL_CLOUD_PATCH_INSTALLED = True
