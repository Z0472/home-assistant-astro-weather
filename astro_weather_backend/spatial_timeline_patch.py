"""Spatial cloud timeline/UI semantics for Astro Weather Backend 12.3.1."""
from __future__ import annotations

import bz2
import math
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import spatial_cloud_patch as spatial

RELEASE_VERSION = "12.3.1"
ASTRO_CARD_VERSION = 27
TREND_DELTA_PCT = 10.0
CURRENT_HORIZON_HOURS = 6
MAX_CURRENT_ETA_MINUTES = CURRENT_HORIZON_HOURS * 60


def _safe(core: Any, value: Any) -> float | None:
    return core.safe_float(value)


def _band(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value <= spatial.CLEAR_THRESHOLD:
        return "clear"
    if value >= spatial.CLOUDY_THRESHOLD:
        return "cloudy"
    return "mixed"


def _arrow(state: str) -> str:
    return {
        "incoming": "↗",
        "clearing": "↘",
        "steady": "→",
        "boundary": "→",
        "stable_clear": "→",
        "stable_cloudy": "→",
    }.get(state, "→")


def _trend_label(state: str) -> str:
    return {
        "incoming": "zatahování",
        "clearing": "vyjasňování",
        "steady": "setrvalý stav",
        "boundary": "hrana oblačnosti",
        "stable_clear": "stabilně jasno",
        "stable_cloudy": "stabilně zataženo",
    }.get(state, "setrvalý stav")


def _format_eta(minutes: int | None) -> str:
    if minutes is None:
        return ""
    rounded = max(0, int(round(minutes / 5.0) * 5))
    if rounded < 60:
        return f"{rounded} min"
    hours, mins = divmod(rounded, 60)
    if mins == 0:
        return f"{hours} h"
    return f"{hours} h {mins} min"


def _format_clock(core: Any, options: dict[str, Any], when: datetime | None) -> str:
    return core.format_local_time(when, options) if when is not None else "—"


def _interpolate_crossing(
    t0: datetime,
    v0: float,
    t1: datetime,
    v1: float,
    threshold: float,
) -> datetime:
    if abs(v1 - v0) < 1e-9:
        return t1
    ratio = (threshold - v0) / (v1 - v0)
    ratio = max(0.0, min(1.0, ratio))
    return t0 + (t1 - t0) * ratio


def _significant_transition(
    records: list[tuple[datetime, dict[str, Any]]],
) -> tuple[str, datetime, int] | None:
    """Return first clear/cloudy threshold transition in a time series."""
    if len(records) < 2:
        return None

    for index, ((t0, s0), (t1, s1)) in enumerate(zip(records, records[1:])):
        v0 = float(s0["centerCloud"])
        v1 = float(s1["centerCloud"])
        if v0 < spatial.CLOUDY_THRESHOLD <= v1:
            return "incoming", _interpolate_crossing(
                t0, v0, t1, v1, spatial.CLOUDY_THRESHOLD
            ), index + 1
        if v0 > spatial.CLEAR_THRESHOLD >= v1:
            return "clearing", _interpolate_crossing(
                t0, v0, t1, v1, spatial.CLEAR_THRESHOLD
            ), index + 1
    return None


def _edge_motion(
    records: list[tuple[datetime, dict[str, Any]]],
) -> tuple[str, datetime] | None:
    """Estimate ETA from a cloud/clear edge moving toward the site."""
    if len(records) < 2:
        return None
    first_time, first = records[0]
    edge = first.get("edge")
    if not isinstance(edge, dict):
        return None
    edge_type = edge.get("type")
    d0 = _safe_value(edge.get("distance_km"))
    if d0 is None or d0 <= 0:
        return None

    for when, snap in records[1:4]:
        candidate = snap.get("edge")
        if not isinstance(candidate, dict) or candidate.get("type") != edge_type:
            continue
        d1 = _safe_value(candidate.get("distance_km"))
        if d1 is None:
            continue
        elapsed_h = (when - first_time).total_seconds() / 3600.0
        if elapsed_h <= 0:
            continue
        approach_km = d0 - d1
        if approach_km < 2.0:
            continue
        speed_kmh = approach_km / elapsed_h
        if speed_kmh < 1.0:
            continue
        eta_h = d0 / speed_kmh
        if eta_h * 60 > MAX_CURRENT_ETA_MINUTES:
            return None
        state = "incoming" if edge_type == "cloud" else "clearing"
        return state, first_time + timedelta(hours=eta_h)
    return None


def _safe_value(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _trend_between(current: dict[str, Any], following: dict[str, Any] | None) -> str:
    if following is None:
        return "steady"
    current_cloud = _safe_value(current.get("centerCloud"))
    next_cloud = _safe_value(following.get("centerCloud"))
    if current_cloud is not None and next_cloud is not None:
        delta = next_cloud - current_cloud
        if delta >= TREND_DELTA_PCT:
            return "incoming"
        if delta <= -TREND_DELTA_PCT:
            return "clearing"

    edge0 = current.get("edge")
    edge1 = following.get("edge")
    if isinstance(edge0, dict) and isinstance(edge1, dict):
        if edge0.get("type") == edge1.get("type"):
            d0 = _safe_value(edge0.get("distance_km"))
            d1 = _safe_value(edge1.get("distance_km"))
            if d0 is not None and d1 is not None and d0 - d1 >= 3.0:
                return "incoming" if edge0.get("type") == "cloud" else "clearing"
    return "steady"


def _current_records(core: Any, options: dict[str, Any]) -> list[tuple[datetime, dict[str, Any]]]:
    now = core.utc_now()
    records: list[tuple[datetime, dict[str, Any]]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for hour in range(CURRENT_HORIZON_HOURS + 1):
        target = now + timedelta(hours=hour)
        snap = spatial._snapshot(core, options, target)
        if snap is None:
            continue
        source_key = (snap.get("iconTime"), snap.get("aladinTime"))
        if source_key in seen and records:
            continue
        seen.add(source_key)
        records.append((target, snap))
    return records


def _current_spatial(core: Any, options: dict[str, Any]) -> dict[str, Any] | None:
    records = _current_records(core, options)
    if not records:
        return None

    now, current = records[0]
    transition = _significant_transition(records)
    state: str
    change_time: datetime | None = None

    if transition is not None:
        state, change_time, _ = transition
    else:
        edge = _edge_motion(records)
        if edge is not None:
            state, change_time = edge
        elif current.get("boundary"):
            state = "boundary"
        else:
            center = _safe_value(current.get("centerCloud"))
            if center is not None and center <= spatial.CLEAR_THRESHOLD:
                state = "stable_clear"
            elif center is not None and center >= spatial.CLOUDY_THRESHOLD:
                state = "stable_cloudy"
            else:
                state = "steady"

    eta_minutes = None
    if change_time is not None:
        eta_minutes = max(0, round((change_time - now).total_seconds() / 60.0))

    edge = current.get("edge") if isinstance(current.get("edge"), dict) else {}
    edge_distance = _safe_value(edge.get("distance_km"))
    edge_direction = edge.get("direction")
    arrow = _arrow(state)

    if state == "incoming":
        short = f"{arrow} Zatahování"
        if edge_direction:
            short += f" od {edge_direction}"
        if eta_minutes is not None:
            short += f" · změna asi za {_format_eta(eta_minutes)}"
    elif state == "clearing":
        short = f"{arrow} Vyjasňování"
        if edge_direction:
            short += f" od {edge_direction}"
        if eta_minutes is not None:
            short += f" · změna asi za {_format_eta(eta_minutes)}"
    elif state == "stable_clear":
        short = f"{arrow} Okolí stabilně jasné"
    elif state == "stable_cloudy":
        short = f"{arrow} Okolí stabilně zatažené"
    elif state == "boundary":
        short = f"{arrow} Hrana oblačnosti"
        if edge_distance is not None and edge_direction:
            short += f" ~{edge_distance:.0f} km {edge_direction}"
        short += " · bez výrazné změny"
    else:
        short = f"{arrow} Bez výrazné změny"

    return {
        "state": state,
        "arrow": arrow,
        "trendLabel": _trend_label(state),
        "shortText": short,
        "asOf": core.iso_z(now),
        "etaMinutes": eta_minutes,
        "changeTime": core.iso_z(change_time) if change_time is not None else None,
        "radiusKm": int(options["spatial_radius_km"]),
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
        "iconTime": current.get("iconTime"),
        "aladinTime": current.get("aladinTime"),
    }


def _night_records(
    core: Any,
    options: dict[str, Any],
    result: dict[str, Any],
) -> list[tuple[datetime, dict[str, Any], dict[str, Any]]]:
    hours = result.get("displayHours")
    if not isinstance(hours, list) or not hours:
        hours = result.get("hours")
    if not isinstance(hours, list):
        return []

    records: list[tuple[datetime, dict[str, Any], dict[str, Any]]] = []
    for hour in hours:
        if not isinstance(hour, dict):
            continue
        dt = core.parse_iso_utc(str(hour.get("start", "")))
        if dt is None:
            continue
        snap = spatial._snapshot(core, options, dt)
        if snap is not None:
            records.append((dt, hour, snap))
    return records


def _night_summary(
    core: Any,
    options: dict[str, Any],
    records: list[tuple[datetime, dict[str, Any], dict[str, Any]]],
) -> dict[str, Any] | None:
    if not records:
        return None

    simple = [(dt, snap) for dt, _, snap in records]
    transitions: list[dict[str, Any]] = []
    work = simple

    for _ in range(2):
        found = _significant_transition(work)
        if found is None:
            break
        state, when, local_index = found
        transitions.append({
            "state": state,
            "time": core.iso_z(when),
            "localTime": _format_clock(core, options, when),
            "arrow": _arrow(state),
        })
        next_start = local_index
        if next_start >= len(work):
            break
        work = work[next_start:]

    first = simple[0][1]
    last = simple[-1][1]
    first_center = _safe_value(first.get("centerCloud"))
    last_center = _safe_value(last.get("centerCloud"))

    if transitions:
        parts = []
        for event in transitions:
            if event["state"] == "clearing":
                parts.append(f"↘ vyjasnění kolem {event['localTime']}")
            else:
                parts.append(f"↗ zatahování kolem {event['localTime']}")
        short = " · ".join(parts)
        state = transitions[0]["state"]
    else:
        values = [
            _safe_value(snap.get("centerCloud"))
            for _, snap in simple
        ]
        values = [value for value in values if value is not None]
        if values and max(values) <= spatial.CLEAR_THRESHOLD:
            state, short = "stable_clear", "→ stabilně jasno"
        elif values and min(values) >= spatial.CLOUDY_THRESHOLD:
            state, short = "stable_cloudy", "→ stabilně zataženo"
        elif first_center is not None and last_center is not None and last_center - first_center >= TREND_DELTA_PCT:
            state, short = "incoming", "↗ postupné zatahování"
        elif first_center is not None and last_center is not None and first_center - last_center >= TREND_DELTA_PCT:
            state, short = "clearing", "↘ postupné vyjasňování"
        else:
            state, short = "boundary", "→ proměnlivá oblačnost"

    edge = first.get("edge") if isinstance(first.get("edge"), dict) else {}
    return {
        "state": state,
        "arrow": _arrow(state),
        "shortText": short,
        "radiusKm": int(options["spatial_radius_km"]),
        "transitions": transitions,
        "edgeDistanceKm": _safe_value(edge.get("distance_km")),
        "edgeDirection": edge.get("direction"),
        "centerCloud": first.get("centerCloud"),
        "minCloud": first.get("minCloud"),
        "maxCloud": first.get("maxCloud"),
        "spatialStability": first.get("spatialStability"),
        "dominantLayer": first.get("dominantLayer"),
        "windLevelHpa": first.get("windLevelHpa"),
        "windFromDeg": first.get("windFromDeg"),
        "windSpeedMs": first.get("windSpeedMs"),
        "windSupportsEdgeMotion": first.get("windSupportsEdgeMotion"),
        "sources": first.get("sources", []),
        "sampleTime": first.get("time"),
    }


def _enrich_hour_trends(
    records: list[tuple[datetime, dict[str, Any], dict[str, Any]]],
) -> None:
    for index, (_, hour, snap) in enumerate(records):
        next_snap = records[index + 1][2] if index + 1 < len(records) else None
        trend = _trend_between(snap, next_snap)
        hour["spatialTrend"] = trend
        hour["spatialArrow"] = _arrow(trend)
        hour["spatialTrendLabel"] = _trend_label(trend)
        hour["spatialCenterCloud"] = snap.get("centerCloud")
        edge = snap.get("edge") if isinstance(snap.get("edge"), dict) else {}
        hour["spatialEdgeDistanceKm"] = edge.get("distance_km")
        hour["spatialEdgeDirection"] = edge.get("direction")


def _mirror_to_astronomical_hours(result: dict[str, Any]) -> None:
    display = result.get("displayHours")
    hours = result.get("hours")
    if not isinstance(display, list) or not isinstance(hours, list):
        return
    trend_by_start = {
        row.get("start"): row
        for row in display
        if isinstance(row, dict) and isinstance(row.get("start"), str)
    }
    fields = (
        "spatialTrend",
        "spatialArrow",
        "spatialTrendLabel",
        "spatialCenterCloud",
        "spatialEdgeDistanceKm",
        "spatialEdgeDirection",
    )
    for row in hours:
        if not isinstance(row, dict):
            continue
        source = trend_by_start.get(row.get("start"))
        if not isinstance(source, dict):
            continue
        for field in fields:
            if field in source:
                row[field] = source[field]


def fetch_aladin_spatial_parallel(
    options: dict[str, Any],
    core: Any,
    run: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Same ALADIN sampling as 12.3.0, but with four point queries in parallel."""
    if shutil.which("grib_get") is None:
        raise RuntimeError("ecCodes/grib_get neni v kontejneru k dispozici")

    points = spatial.build_spatial_points(
        options["latitude"], options["longitude"], options["spatial_radius_km"]
    )
    product = core.ALADIN_PRODUCTS["cloud_total"]
    bz_path = core.download_aladin_product(run, product, options)
    grib_path = Path(str(bz_path) + ".spatial.grb")

    try:
        with bz2.open(bz_path, "rb") as src, grib_path.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        times = core.grib_message_times(grib_path)
        unit, global_max = core.grib_unit_and_global_max(grib_path)
        rows: dict[str, dict[str, Any]] = {
            stamp: {"points": {}} for stamp in times
        }

        def sample(point: dict[str, Any]) -> tuple[str, list[float]]:
            out = core.run_cmd([
                "grib_get",
                "-F", "%.8f",
                "-l", f"{point['latitude']:.6f},{point['longitude']:.6f},1",
                str(grib_path),
            ], timeout=180)
            values = core.parse_number_lines(out)
            if len(values) != len(times):
                raise RuntimeError(
                    f"ALADIN spatial {point['id']}: {len(values)} hodnot, "
                    f"očekáváno {len(times)}"
                )
            return point["id"], values

        sampled: dict[str, list[float]] = {}
        with ThreadPoolExecutor(max_workers=min(4, len(points))) as executor:
            futures = [executor.submit(sample, point) for point in points]
            for future in as_completed(futures):
                point_id, values = future.result()
                sampled[point_id] = values

        for point in points:
            values = sampled[point["id"]]
            for stamp, raw in zip(times, values):
                rows[stamp]["points"][point["id"]] = core.cloud_to_percent(
                    raw, unit, global_max
                )

        return rows, {
            "available": bool(rows),
            "provider": "CHMI ALADIN CZ_1km",
            "run": run,
            "points": len(points),
            "radius_km": int(options["spatial_radius_km"]),
            "parallel_workers": min(4, len(points)),
        }
    finally:
        try:
            grib_path.unlink(missing_ok=True)
        except Exception:
            pass


def install(core: Any) -> None:
    if getattr(core, "_SPATIAL_TIMELINE_PATCH_INSTALLED", False):
        return

    old_analyze_night = core.analyze_night

    spatial.fetch_aladin_spatial = fetch_aladin_spatial_parallel

    def analyze_night(
        night: dict[str, Any],
        forecast: list[dict[str, Any]],
        moon_rows: list[dict[str, Any]],
        options: dict[str, Any],
    ) -> dict[str, Any] | None:
        result = old_analyze_night(night, forecast, moon_rows, options)
        if result is None or not options.get("spatial_cloud_analysis", True):
            return result

        previous_spatial = result.get("spatialCloud")
        records = _night_records(core, options, result)
        if records:
            _enrich_hour_trends(records)
            _mirror_to_astronomical_hours(result)
            night_summary = _night_summary(core, options, records)
            if night_summary is not None:
                result["spatialCloud"] = night_summary
                if (
                    result.get("spatialAdjusted")
                    and isinstance(previous_spatial, dict)
                    and previous_spatial.get("shortText")
                    and isinstance(result.get("reason"), str)
                ):
                    result["reason"] = result["reason"].replace(
                        str(previous_spatial["shortText"]),
                        str(night_summary["shortText"]),
                        1,
                    )

        current = _current_spatial(core, options)
        if current is not None:
            result["currentSpatialCloud"] = current

        return result

    core.analyze_night = analyze_night
    core.APP_VERSION = RELEASE_VERSION
    core.ASTRO_START_CARD_VERSION = ASTRO_CARD_VERSION

    current_installs = list(core.DASHBOARD_CARD_INSTALLS)
    target = f"astro-start-card-v{ASTRO_CARD_VERSION}.js"
    if not any(dst == target for _, dst in current_installs):
        current_installs.append((target, target))
    core.DASHBOARD_CARD_INSTALLS = tuple(current_installs)

    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._SPATIAL_TIMELINE_PATCH_INSTALLED = True
