"""Temporal consistency guard for spatial cloud edges in Astro Weather Backend 12.3.4."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

import spatial_cloud_patch as spatial
import spatial_timeline_patch as timeline

RELEASE_VERSION = "12.3.4"
EDGE_TRACK_POINTS = 3
EDGE_DIRECTION_TOLERANCE_DEG = 67.5
EDGE_DISTANCE_JITTER_KM = 2.0
EDGE_MIN_APPROACH_KM = 2.0
EDGE_MIN_SPEED_KMH = 1.0


def _safe(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _circular_mean_deg(values: list[float]) -> float | None:
    if not values:
        return None
    x = sum(math.cos(math.radians(value)) for value in values)
    y = sum(math.sin(math.radians(value)) for value in values)
    if math.hypot(x, y) < 1e-6:
        return None
    return math.degrees(math.atan2(y, x)) % 360.0


def _nearest_direction(bearing: float) -> str:
    return min(spatial.BEARINGS, key=lambda item: _angle_diff(item[0], bearing))[1]


def _edge_track(
    records: list[tuple[datetime, dict[str, Any]]],
) -> dict[str, Any] | None:
    """Track one edge only when three consecutive model times describe the same geometry.

    The old code selected the nearest 50 % crossing independently at every hour. In a patchy
    cloud field that can jump between unrelated edges around the observatory and make the
    direction appear to rotate. A publishable direction now requires three consecutive points
    with the same edge type and bearings clustered within one neighbouring compass sector.
    """
    if len(records) < EDGE_TRACK_POINTS:
        return None

    samples: list[dict[str, Any]] = []
    edge_type: str | None = None
    for when, snap in records[:EDGE_TRACK_POINTS]:
        edge = snap.get("edge") if isinstance(snap.get("edge"), dict) else None
        if edge is None:
            return None
        candidate_type = str(edge.get("type") or "")
        bearing = _safe(edge.get("bearing_deg"))
        distance = _safe(edge.get("distance_km"))
        if not candidate_type or bearing is None or distance is None or distance < 0:
            return None
        if edge_type is None:
            edge_type = candidate_type
        elif candidate_type != edge_type:
            return None
        samples.append({
            "time": when,
            "bearing": bearing % 360.0,
            "distance": distance,
        })

    bearings = [sample["bearing"] for sample in samples]
    mean_bearing = _circular_mean_deg(bearings)
    if mean_bearing is None:
        return None
    if any(_angle_diff(mean_bearing, bearing) > EDGE_DIRECTION_TOLERANCE_DEG for bearing in bearings):
        return None

    distances = [sample["distance"] for sample in samples]
    distance_consistent = all(
        later <= earlier + EDGE_DISTANCE_JITTER_KM
        for earlier, later in zip(distances, distances[1:])
    )
    approach_km = distances[0] - distances[-1]
    elapsed_h = (samples[-1]["time"] - samples[0]["time"]).total_seconds() / 3600.0
    speed_kmh = approach_km / elapsed_h if elapsed_h > 0 else 0.0
    approaching = (
        distance_consistent
        and approach_km >= EDGE_MIN_APPROACH_KM
        and speed_kmh >= EDGE_MIN_SPEED_KMH
    )

    eta_time = None
    eta_minutes = None
    if approaching:
        eta_h = distances[0] / speed_kmh
        eta_minutes = round(eta_h * 60.0)
        if 0 <= eta_minutes <= timeline.MAX_CURRENT_ETA_MINUTES:
            eta_time = samples[0]["time"] + timedelta(hours=eta_h)
        else:
            eta_minutes = None

    return {
        "type": edge_type,
        "bearing_deg": round(mean_bearing, 1),
        "direction": _nearest_direction(mean_bearing),
        "distance_km": distances[0],
        "points": len(samples),
        "approaching": approaching,
        "approach_km": round(approach_km, 1),
        "speed_kmh": round(speed_kmh, 1) if approaching else None,
        "eta_time": eta_time,
        "eta_minutes": eta_minutes,
    }


def _edge_motion(
    records: list[tuple[datetime, dict[str, Any]]],
) -> tuple[str, datetime] | None:
    track = _edge_track(records)
    if track is None or not track["approaching"] or track["eta_time"] is None:
        return None
    state = "incoming" if track["type"] == "cloud" else "clearing"
    return state, track["eta_time"]


def _trend_between(current: dict[str, Any], following: dict[str, Any] | None) -> str:
    """Local hourly trend from centre cloud only; edge motion needs three-point consistency."""
    if following is None:
        return "steady"
    current_cloud = _safe(current.get("centerCloud"))
    next_cloud = _safe(following.get("centerCloud"))
    if current_cloud is None or next_cloud is None:
        return "steady"
    delta = next_cloud - current_cloud
    if delta >= timeline.TREND_DELTA_PCT:
        return "incoming"
    if delta <= -timeline.TREND_DELTA_PCT:
        return "clearing"
    return "steady"


def _enrich_hour_trends(
    records: list[tuple[datetime, dict[str, Any], dict[str, Any]]],
) -> None:
    for index, (_, hour, snap) in enumerate(records):
        next_snap = records[index + 1][2] if index + 1 < len(records) else None
        trend = _trend_between(snap, next_snap)

        track_input = [
            (record[0], record[2])
            for record in records[index:index + EDGE_TRACK_POINTS]
        ]
        track = _edge_track(track_input)
        if trend == "steady" and track is not None and track["approaching"]:
            trend = "incoming" if track["type"] == "cloud" else "clearing"

        edge = snap.get("edge") if isinstance(snap.get("edge"), dict) else {}
        raw_direction = edge.get("direction")
        raw_distance = _safe(edge.get("distance_km"))

        hour["spatialTrend"] = trend
        hour["spatialArrow"] = timeline._arrow(trend)
        hour["spatialTrendLabel"] = timeline._trend_label(trend)
        hour["spatialCenterCloud"] = snap.get("centerCloud")
        hour["spatialEdgeRawDirection"] = raw_direction
        hour["spatialEdgeDirectionStable"] = track is not None
        hour["spatialEdgeTrackPoints"] = 0 if track is None else track["points"]
        hour["spatialEdgeMovingToward"] = bool(track and track["approaching"])
        hour["spatialEdgeDistanceKm"] = raw_distance
        hour["spatialEdgeDirection"] = track["direction"] if track is not None else None


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
        "spatialEdgeRawDirection",
        "spatialEdgeDirectionStable",
        "spatialEdgeTrackPoints",
        "spatialEdgeMovingToward",
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


def _current_spatial(core: Any, options: dict[str, Any]) -> dict[str, Any] | None:
    records = timeline._current_records(core, options)
    if not records:
        return None

    now, current = records[0]
    transition = timeline._significant_transition(records)
    track = _edge_track(records)
    state: str
    change_time: datetime | None = None

    if transition is not None:
        state, change_time, _ = transition
    else:
        motion = _edge_motion(records)
        if motion is not None:
            state, change_time = motion
        elif current.get("boundary"):
            state = "boundary"
        else:
            center = _safe(current.get("centerCloud"))
            if center is not None and center <= spatial.CLEAR_THRESHOLD:
                state = "stable_clear"
            elif center is not None and center >= spatial.CLOUDY_THRESHOLD:
                state = "stable_cloudy"
            else:
                state = "steady"

    eta_minutes = None
    if change_time is not None:
        eta_minutes = max(0, round((change_time - now).total_seconds() / 60.0))

    raw_edge = current.get("edge") if isinstance(current.get("edge"), dict) else {}
    raw_distance = _safe(raw_edge.get("distance_km"))
    raw_direction = raw_edge.get("direction")
    stable_direction = track["direction"] if track is not None else None
    motion_direction = stable_direction if track is not None and track["approaching"] else None
    arrow = timeline._arrow(state)

    if state == "incoming":
        short = f"{arrow} Zatahování"
        if motion_direction:
            short += f" od {motion_direction}"
        elif raw_direction:
            short += " · směr hrany nejistý"
        if eta_minutes is not None:
            short += f" · změna asi za {timeline._format_eta(eta_minutes)}"
    elif state == "clearing":
        short = f"{arrow} Vyjasňování"
        if motion_direction:
            short += f" od {motion_direction}"
        elif raw_direction:
            short += " · směr hrany nejistý"
        if eta_minutes is not None:
            short += f" · změna asi za {timeline._format_eta(eta_minutes)}"
    elif state == "stable_clear":
        short = f"{arrow} Okolí stabilně jasné"
    elif state == "stable_cloudy":
        short = f"{arrow} Okolí stabilně zatažené"
    elif state == "boundary":
        short = f"{arrow} Hrana oblačnosti v okolí"
        if stable_direction and raw_distance is not None:
            short += f" · ~{raw_distance:.0f} km {stable_direction}"
        elif raw_direction:
            short += " · směr nejistý"
        short += " · bez výrazné změny"
    else:
        short = f"{arrow} Bez výrazné změny"

    return {
        "state": state,
        "arrow": arrow,
        "trendLabel": timeline._trend_label(state),
        "shortText": short,
        "asOf": core.iso_z(now),
        "etaMinutes": eta_minutes,
        "changeTime": core.iso_z(change_time) if change_time is not None else None,
        "radiusKm": int(options["spatial_radius_km"]),
        "edgeDistanceKm": raw_distance,
        "edgeDirection": stable_direction,
        "edgeRawDirection": raw_direction,
        "edgeDirectionStable": track is not None,
        "edgeMovingToward": bool(track and track["approaching"]),
        "edgeTrackPoints": 0 if track is None else track["points"],
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


def _rewrite_hour_labels(core: Any, options: dict[str, Any], result: dict[str, Any]) -> None:
    rows = result.get("displayHours")
    if not isinstance(rows, list) or not rows:
        rows = result.get("hours")
    if not isinstance(rows, list):
        return

    phrase = {
        "incoming": "↗ oblačnosti přibývá",
        "clearing": "↘ oblačnosti ubývá",
        "steady": "→ setrvalý stav",
    }
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not row.get("spatialArrow"):
            continue
        start = core.parse_iso_utc(str(row.get("start") or ""))
        next_start = None
        if index + 1 < len(rows) and isinstance(rows[index + 1], dict):
            next_start = core.parse_iso_utc(str(rows[index + 1].get("start") or ""))
        end = next_start or core.parse_iso_utc(str(row.get("end") or ""))
        trend = str(row.get("spatialTrend") or "steady")
        text = phrase.get(trend, "→ setrvalý stav")
        if start is not None and end is not None:
            label = (
                f"{core.format_local_time(start, options)} → "
                f"{core.format_local_time(end, options)}: {text}"
            )
        else:
            label = text
        if row.get("spatialEdgeRawDirection") and not row.get("spatialEdgeDirectionStable"):
            label += " · směr hrany nejistý"
        row["spatialTrendLabel"] = label

    display = result.get("displayHours")
    hours = result.get("hours")
    if isinstance(display, list) and isinstance(hours, list):
        labels = {
            row.get("start"): row.get("spatialTrendLabel")
            for row in display
            if isinstance(row, dict) and row.get("start") and row.get("spatialTrendLabel")
        }
        for row in hours:
            if isinstance(row, dict) and row.get("start") in labels:
                row["spatialTrendLabel"] = labels[row["start"]]


def install(core: Any) -> None:
    if getattr(core, "_EDGE_CONSISTENCY_PATCH_INSTALLED", False):
        return

    old_analyze_night = core.analyze_night
    old_load_options = core.load_options

    timeline._edge_motion = _edge_motion
    timeline._trend_between = _trend_between
    timeline._enrich_hour_trends = _enrich_hour_trends
    timeline._mirror_to_astronomical_hours = _mirror_to_astronomical_hours
    timeline._current_spatial = _current_spatial

    def load_options() -> dict[str, Any]:
        options = old_load_options()
        agent = str(options.get("met_user_agent", "")).strip()
        if not agent or agent.startswith("AstroWeatherBackend/"):
            options["met_user_agent"] = (
                f"AstroWeatherBackend/{RELEASE_VERSION} "
                "https://github.com/Z0472/home-assistant-astro-weather"
            )
        return options

    def analyze_night(
        night: dict[str, Any],
        forecast: list[dict[str, Any]],
        moon_rows: list[dict[str, Any]],
        options: dict[str, Any],
    ) -> dict[str, Any] | None:
        result = old_analyze_night(night, forecast, moon_rows, options)
        if result is not None and options.get("spatial_cloud_analysis", True):
            _rewrite_hour_labels(core, options, result)
        return result

    core.load_options = load_options
    core.analyze_night = analyze_night
    core.APP_VERSION = RELEASE_VERSION
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._EDGE_CONSISTENCY_PATCH_INSTALLED = True
