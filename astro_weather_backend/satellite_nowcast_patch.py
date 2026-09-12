"""EUMETSAT MTG/FCI satellite reality and short nowcast for Astro Weather Backend 12.4.0.

Quantitative cloud data use the operational FCI Cloud Mask GRIB-2 product
(EO:EUM:DAT:0800). EUMETSAT Data Store discovery is anonymous, but downloads
require a registered account and an API consumer key/secret. Without credentials
this patch fails open: all existing weather decisions remain untouched and the
satellite card still exposes the public EUMETView IR visualisation.
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import cloud_consensus as cc
import spatial_cloud_patch as spatial

RELEASE_VERSION = "12.4.0"
ASTRO_CARD_VERSION = 29
SATELLITE_CARD_VERSION = 1

EUMETSAT_CLM_GRIB_COLLECTION = "EO:EUM:DAT:0800"
EUMETSAT_SEARCH_URL = "https://api.eumetsat.int/data/search-products/1.0.0/os"
EUMETSAT_DOWNLOAD_BASE = "https://api.eumetsat.int/data/download/1.0.0"
EUMETSAT_TOKEN_URL = "https://api.eumetsat.int/token"
EUMETVIEW_IR_EUROPE_URL = (
    "https://view.eumetsat.int/geoserver/wms?"
    "service=WMS&version=1.3.0&request=GetMap&"
    "layers=mtg_fd:ir105_hrfi,backgrounds:ne_10m_coastline,backgrounds:ne_boundary_lines_land&"
    "bbox=-2500000,3050000,3750000,5450000&width=1200&height=633&"
    "srs=AUTO:97004,9001,0,0&styles=&format=image/jpeg&bgcolor=0xCCCCCC"
)

SAMPLE_CACHE_FILENAME = "satellite_clm_samples.json"
SEARCH_LOOKBACK_MINUTES = 90
MAX_FRAMES = 7
MAX_SAMPLE_AGE_MINUTES = 45
TREND_MIN_SLOPE_PPH = 5.0
EDGE_DIRECTION_TOLERANCE_DEG = 67.5
EDGE_MIN_APPROACH_KM = 2.0
EDGE_MIN_SPEED_KMH = 1.0

SATELLITE_STATE: dict[str, Any] = {
    "state": "unavailable",
    "backend_version": RELEASE_VERSION,
    "available": False,
}
COMPARISON_STATE: dict[str, Any] = {
    "state": "unavailable",
    "backend_version": RELEASE_VERSION,
    "available": False,
}


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


def _credentials(options: dict[str, Any]) -> tuple[str, str]:
    key = str(options.get("eumetsat_consumer_key") or os.environ.get("EUMETSAT_CONSUMER_KEY", "")).strip()
    secret = str(options.get("eumetsat_consumer_secret") or os.environ.get("EUMETSAT_CONSUMER_SECRET", "")).strip()
    return key, secret


def _cache_path(core: Any) -> Path:
    return core.CACHE_DIR / SAMPLE_CACHE_FILENAME


def _load_sample_cache(core: Any) -> list[dict[str, Any]]:
    try:
        raw = json.loads(_cache_path(core).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return []
    rows = raw.get("frames") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and row.get("product_id") and row.get("time")]


def _save_sample_cache(core: Any, frames: list[dict[str, Any]]) -> None:
    path = _cache_path(core)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "saved_at": core.iso_z(core.utc_now()),
        "collection": EUMETSAT_CLM_GRIB_COLLECTION,
        "frames": frames[-MAX_FRAMES:],
    }
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp.replace(path)


def _request_json(url: str, *, headers: dict[str, str] | None = None, data: bytes | None = None,
                  timeout: int = 45) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Accept": "application/json", "User-Agent": f"AstroWeatherBackend/{RELEASE_VERSION}", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        document = json.loads(response.read().decode("utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError("EUMETSAT API nevratilo JSON objekt")
    return document


def _access_token(key: str, secret: str) -> str:
    basic = base64.b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "validity_period": "3600",
    }).encode("ascii")
    doc = _request_json(
        EUMETSAT_TOKEN_URL,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=body,
        timeout=30,
    )
    token = str(doc.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("EUMETSAT token endpoint nevratil access_token")
    return token


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _product_time(product_id: str, properties: dict[str, Any]) -> datetime | None:
    for key in (
        "start", "startTime", "sensingStart", "sensing_start", "beginPosition",
        "date", "datetime", "timeStart", "time_start",
    ):
        dt = _parse_iso(properties.get(key))
        if dt is not None:
            return dt
    matches = re.findall(r"(?<!\d)(20\d{12})(?!\d)", product_id)
    for item in reversed(matches):
        try:
            return datetime.strptime(item, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _extract_search_products(doc: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = []
    for key in ("features", "products", "items"):
        value = doc.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    if not candidates:
        feed = doc.get("feed")
        if isinstance(feed, dict):
            for key in ("entry", "entries"):
                value = feed.get(key)
                if isinstance(value, list):
                    candidates.extend(value)

    output: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        props = item.get("properties") if isinstance(item.get("properties"), dict) else item
        product_id = str(
            item.get("id")
            or props.get("id")
            or props.get("identifier")
            or props.get("productIdentifier")
            or props.get("title")
            or ""
        ).strip()
        if not product_id:
            continue
        when = _product_time(product_id, props)
        output.append({
            "product_id": product_id,
            "time": when.isoformat().replace("+00:00", "Z") if when else None,
        })
    dedup: dict[str, dict[str, Any]] = {row["product_id"]: row for row in output}
    return sorted(dedup.values(), key=lambda row: row.get("time") or "", reverse=True)


def _search_recent_products(core: Any) -> list[dict[str, Any]]:
    end = core.utc_now() + timedelta(minutes=5)
    start = end - timedelta(minutes=SEARCH_LOOKBACK_MINUTES)
    params = {
        "pi": EUMETSAT_CLM_GRIB_COLLECTION,
        "dtstart": core.iso_z(start),
        "dtend": core.iso_z(end),
        "sort": "start,time,0",
        "format": "json",
        "c": str(MAX_FRAMES),
    }
    doc = _request_json(EUMETSAT_SEARCH_URL + "?" + urllib.parse.urlencode(params), timeout=45)
    return _extract_search_products(doc)[:MAX_FRAMES]


def _download_product(product_id: str, token: str) -> bytes:
    collection = urllib.parse.quote(EUMETSAT_CLM_GRIB_COLLECTION, safe="")
    product = urllib.parse.quote(product_id, safe="")
    url = f"{EUMETSAT_DOWNLOAD_BASE}/collections/{collection}/products/{product}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/octet-stream,application/zip,*/*",
            "User-Agent": f"AstroWeatherBackend/{RELEASE_VERSION}",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def _write_grib_from_download(core: Any, product_id: str, payload: bytes) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", product_id)[-120:]
    target = core.CACHE_DIR / f"satellite_{safe_id}.grib2"
    if payload[:4] == b"GRIB":
        target.write_bytes(payload)
        return target

    archive = core.CACHE_DIR / f"satellite_{safe_id}.zip"
    archive.write_bytes(payload)
    try:
        with zipfile.ZipFile(archive) as zf:
            names = [
                name for name in zf.namelist()
                if name.lower().endswith((".bin", ".grb", ".grib", ".grib2"))
            ]
            if not names:
                raise RuntimeError("EUMETSAT CLM balíček neobsahuje GRIB-2 soubor")
            with zf.open(names[0]) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    finally:
        archive.unlink(missing_ok=True)
    return target


def _cloud_category(value: Any) -> int | None:
    number = _safe(value)
    if number is None:
        return None
    category = int(round(number))
    if category in (0, 1):
        return 0
    if category == 2:
        return 1
    return None


def _sample_product(core: Any, options: dict[str, Any], product: dict[str, Any], token: str) -> dict[str, Any]:
    if shutil.which("grib_get") is None:
        raise RuntimeError("ecCodes/grib_get neni v kontejneru k dispozici")
    payload = _download_product(str(product["product_id"]), token)
    grib_path = _write_grib_from_download(core, str(product["product_id"]), payload)
    points = spatial.build_spatial_points(
        float(options["latitude"]),
        float(options["longitude"]),
        int(options["satellite_radius_km"]),
    )
    sampled: dict[str, int | None] = {}
    try:
        for point in points:
            out = core.run_cmd([
                "grib_get",
                "-F", "%.8f",
                "-l", f"{point['latitude']:.6f},{point['longitude']:.6f},1",
                str(grib_path),
            ], timeout=60)
            values = core.parse_number_lines(out)
            sampled[point["id"]] = _cloud_category(values[-1] if values else None)
    finally:
        grib_path.unlink(missing_ok=True)

    valid = [value for value in sampled.values() if value is not None]
    if not valid:
        raise RuntimeError("FCI CLM neposkytl platné vzorky v okolí observatoře")
    cloudy = sum(valid)
    center = sampled.get("C")
    return {
        "product_id": product["product_id"],
        "time": product.get("time") or core.iso_z(core.utc_now()),
        "cloud_pct": round(100.0 * cloudy / len(valid), 1),
        "center_cloud_pct": None if center is None else float(center * 100),
        "valid_samples": len(valid),
        "sample_count": len(sampled),
        "points": sampled,
    }


def _bearing_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _mean_bearing(values: list[float]) -> float | None:
    if not values:
        return None
    x = sum(math.cos(math.radians(value)) for value in values)
    y = sum(math.sin(math.radians(value)) for value in values)
    if math.hypot(x, y) < 1e-6:
        return None
    return math.degrees(math.atan2(y, x)) % 360.0


def _edge_for_frame(frame: dict[str, Any], radius_km: int) -> dict[str, Any] | None:
    points = frame.get("points")
    if not isinstance(points, dict):
        return None
    center = points.get("C")
    if center not in (0, 1):
        return None

    candidates: list[tuple[float, float, str]] = []
    edge_type = "cloud" if center == 0 else "clear"
    target = 1 if center == 0 else 0
    for bearing, direction in spatial.BEARINGS:
        inner = points.get(f"inner_{int(bearing):03d}")
        outer = points.get(f"outer_{int(bearing):03d}")
        distance = None
        if inner == target:
            distance = radius_km / 2.0
        elif outer == target:
            distance = float(radius_km)
        if distance is not None:
            candidates.append((distance, float(bearing), direction))
    if not candidates:
        return None
    distance, bearing, direction = min(candidates, key=lambda item: item[0])
    return {
        "type": edge_type,
        "distance_km": distance,
        "bearing_deg": bearing,
        "direction": direction,
    }


def _stable_edge(frames: list[dict[str, Any]], radius_km: int) -> dict[str, Any] | None:
    recent = sorted(frames, key=lambda row: row.get("time") or "")[-3:]
    if len(recent) < 3:
        return None
    edges = [_edge_for_frame(frame, radius_km) for frame in recent]
    if any(edge is None for edge in edges):
        return None
    edge_type = edges[0]["type"]
    if any(edge["type"] != edge_type for edge in edges):
        return None
    bearings = [float(edge["bearing_deg"]) for edge in edges]
    mean = _mean_bearing(bearings)
    if mean is None or any(_bearing_diff(mean, bearing) > EDGE_DIRECTION_TOLERANCE_DEG for bearing in bearings):
        return None

    direction = min(spatial.BEARINGS, key=lambda item: _bearing_diff(item[0], mean))[1]
    distances = [float(edge["distance_km"]) for edge in edges]
    times = [_parse_iso(frame.get("time")) for frame in recent]
    if any(value is None for value in times):
        return {
            "type": edge_type, "direction": direction, "bearing_deg": round(mean, 1),
            "distance_km": distances[-1], "stable": True, "approaching": False,
        }
    elapsed_h = (times[-1] - times[0]).total_seconds() / 3600.0
    approach = distances[0] - distances[-1]
    speed = approach / elapsed_h if elapsed_h > 0 else 0.0
    approaching = approach >= EDGE_MIN_APPROACH_KM and speed >= EDGE_MIN_SPEED_KMH
    eta = None
    if approaching:
        eta = round(distances[-1] / speed * 60.0)
        if eta < 0 or eta > 180:
            eta = None
    return {
        "type": edge_type,
        "direction": direction,
        "bearing_deg": round(mean, 1),
        "distance_km": distances[-1],
        "stable": True,
        "approaching": approaching,
        "speed_kmh": round(speed, 1) if approaching else None,
        "eta_minutes": eta,
    }


def _linear_nowcast(frames: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[tuple[datetime, float]] = []
    for frame in frames:
        when = _parse_iso(frame.get("time"))
        cloud = _safe(frame.get("cloud_pct"))
        if when is not None and cloud is not None:
            rows.append((when, cloud))
    rows = sorted(rows)[-MAX_FRAMES:]
    if not rows:
        return {"trend": "unknown", "arrow": "?", "slope_pph": None, "points": []}

    latest_time, latest_cloud = rows[-1]
    slope = 0.0
    residual = None
    if len(rows) >= 3:
        origin = rows[0][0]
        xs = [(when - origin).total_seconds() / 3600.0 for when, _ in rows]
        ys = [cloud for _, cloud in rows]
        xbar = sum(xs) / len(xs)
        ybar = sum(ys) / len(ys)
        denom = sum((x - xbar) ** 2 for x in xs)
        if denom > 1e-9:
            slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denom
            intercept = ybar - slope * xbar
            residual = math.sqrt(sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys)) / len(xs))

    if slope >= TREND_MIN_SLOPE_PPH:
        trend, arrow = "incoming", "↗"
    elif slope <= -TREND_MIN_SLOPE_PPH:
        trend, arrow = "clearing", "↘"
    else:
        trend, arrow = "steady", "→"

    points = []
    for offset in (0, 1, 2, 3):
        value = latest_cloud if offset == 0 else _clamp(latest_cloud + slope * offset)
        points.append({
            "offset_hours": offset,
            "label": "TEĎ" if offset == 0 else f"+{offset} h",
            "cloud_pct": round(value, 1),
            "observed": offset == 0,
            "estimated": offset != 0,
        })

    span_minutes = 0.0 if len(rows) < 2 else (rows[-1][0] - rows[0][0]).total_seconds() / 60.0
    confidence = min(100.0, 30.0 + len(rows) * 8.0 + min(25.0, span_minutes / 3.0))
    if residual is not None:
        confidence -= min(35.0, residual * 1.2)
    return {
        "trend": trend,
        "arrow": arrow,
        "slope_pph": round(slope, 1),
        "confidence": round(_clamp(confidence), 1),
        "residual_pp": None if residual is None else round(residual, 1),
        "points": points,
        "as_of": latest_time.isoformat().replace("+00:00", "Z"),
    }


def _current_model_values(core: Any, at: datetime) -> tuple[dict[str, float | None], dict[str, Any] | None]:
    with core.STATE_LOCK:
        forecast = _copy(core.STATE.get("forecast") or [])
    best = None
    best_diff = float("inf")
    for row in forecast:
        if not isinstance(row, dict):
            continue
        when = core.parse_iso_utc(str(row.get("datetime") or ""))
        if when is None:
            continue
        diff = abs((when - at).total_seconds())
        if diff < best_diff:
            best, best_diff = row, diff
    if best is None or best_diff > 90 * 60:
        return {}, None
    met = best.get("met") if isinstance(best.get("met"), dict) else {}
    aladin = best.get("aladin") if isinstance(best.get("aladin"), dict) else {}
    icon = best.get("icon") if isinstance(best.get("icon"), dict) else {}
    return {
        "MET": _safe(met.get("cloud_total")),
        "ALADIN": _safe(aladin.get("cloud_total")),
        "ICON": _safe(icon.get("cloud_total")),
    }, best


def _comparison(core: Any, options: dict[str, Any], satellite: dict[str, Any]) -> dict[str, Any]:
    cloud = _safe(satellite.get("cloud_pct"))
    when = _parse_iso(satellite.get("as_of"))
    if cloud is None or when is None:
        return {
            "state": "unavailable",
            "available": False,
            "backend_version": RELEASE_VERSION,
            "reason": "Satelitní cloud mask není k dispozici.",
        }
    values, forecast = _current_model_values(core, when)
    if forecast is None:
        return {
            "state": "unavailable",
            "available": False,
            "backend_version": RELEASE_VERSION,
            "satellite_cloud_pct": cloud,
            "satellite_as_of": satellite.get("as_of"),
            "reason": "Pro čas satelitního snímku chybí modelová data.",
        }
    consensus = cc.cloud_consensus(
        values,
        float(options["disagreement_warn"]),
        float(options["disagreement_bad"]),
    )
    effective = _safe(consensus.get("effective"))
    if effective is None:
        return {
            "state": "unavailable",
            "available": False,
            "backend_version": RELEASE_VERSION,
            "satellite_cloud_pct": cloud,
            "satellite_as_of": satellite.get("as_of"),
            "reason": "Žádný model nemá pro satelitní čas oblačnost.",
        }
    signed = effective - cloud
    absolute = abs(signed)
    agreement = _clamp(100.0 - absolute)
    per_model = {}
    for name, value in values.items():
        if value is not None:
            per_model[name] = {
                "cloud_pct": round(value, 1),
                "signed_error_pp": round(value - cloud, 1),
                "absolute_error_pp": round(abs(value - cloud), 1),
            }
    label = "výborná" if agreement >= 85 else "dobrá" if agreement >= 70 else "slabší" if agreement >= 50 else "špatná"
    return {
        "state": f"{agreement:.1f}",
        "available": True,
        "backend_version": RELEASE_VERSION,
        "agreement_pct": round(agreement, 1),
        "agreement_label": label,
        "satellite_cloud_pct": round(cloud, 1),
        "model_cloud_pct": round(effective, 1),
        "signed_error_pp": round(signed, 1),
        "absolute_error_pp": round(absolute, 1),
        "model_count": int(consensus.get("model_count") or 0),
        "model_names": consensus.get("model_names") or [],
        "model_spread_pp": None if consensus.get("spread") is None else round(float(consensus["spread"]), 1),
        "models": per_model,
        "satellite_as_of": satellite.get("as_of"),
        "model_time": forecast.get("datetime"),
    }


def _satellite_document(core: Any, options: dict[str, Any]) -> dict[str, Any]:
    key, secret = _credentials(options)
    base = {
        "state": "unavailable",
        "available": False,
        "backend_version": RELEASE_VERSION,
        "provider": "EUMETSAT MTG/FCI Cloud Mask GRIB-2",
        "collection": EUMETSAT_CLM_GRIB_COLLECTION,
        "resolution_km": 2,
        "cadence_minutes": 10,
        "radius_km": int(options["satellite_radius_km"]),
        "visual_url": EUMETVIEW_IR_EUROPE_URL,
        "visual_provider": "EUMETView MTG IR10.5 HRFI",
    }
    if not options.get("use_satellite", True):
        return {**base, "credential_status": "disabled", "reason": "Satelitní integrace je vypnutá."}
    if not key or not secret:
        return {
            **base,
            "credential_status": "required",
            "reason": (
                "Veřejný EUMETView obraz je dostupný bez přihlášení, ale kvantitativní "
                "MTG/FCI Cloud Mask vyžaduje EUMETSAT Data Store consumer key a secret."
            ),
        }

    products = _search_recent_products(core)
    if not products:
        return {**base, "credential_status": "ok", "reason": "EUMETSAT nevrátil žádný čerstvý CLM produkt."}
    token = _access_token(key, secret)
    cache = _load_sample_cache(core)
    cached = {str(row.get("product_id")): row for row in cache}
    frames: list[dict[str, Any]] = []
    errors: list[str] = []
    for product in reversed(products):
        product_id = str(product["product_id"])
        frame = cached.get(product_id)
        if frame is None:
            try:
                frame = _sample_product(core, options, product, token)
            except Exception as exc:
                errors.append(f"{product_id}: {exc}")
                continue
        if isinstance(frame, dict):
            frames.append(frame)

    frames = sorted(frames, key=lambda row: row.get("time") or "")[-MAX_FRAMES:]
    if frames:
        _save_sample_cache(core, frames)
    if not frames:
        return {
            **base,
            "credential_status": "ok",
            "reason": "CLM produkty byly nalezeny, ale nepodařilo se z nich získat lokální vzorky.",
            "errors": errors[-3:],
        }

    latest = frames[-1]
    latest_time = _parse_iso(latest.get("time"))
    age_minutes = None
    if latest_time is not None:
        age_minutes = max(0.0, (core.utc_now() - latest_time).total_seconds() / 60.0)
    if age_minutes is not None and age_minutes > MAX_SAMPLE_AGE_MINUTES:
        return {
            **base,
            "credential_status": "ok",
            "reason": f"Poslední CLM snímek je příliš starý ({age_minutes:.0f} min).",
            "as_of": latest.get("time"),
            "age_minutes": round(age_minutes, 1),
            "errors": errors[-3:],
        }

    nowcast = _linear_nowcast(frames)
    edge = _stable_edge(frames, int(options["satellite_radius_km"]))
    cloud = float(latest["cloud_pct"])
    trend = str(nowcast.get("trend") or "unknown")
    arrow = str(nowcast.get("arrow") or "?")
    if trend == "incoming":
        short = f"{arrow} Satelit: oblačnosti přibývá"
    elif trend == "clearing":
        short = f"{arrow} Satelit: oblačnosti ubývá"
    else:
        short = f"{arrow} Satelit: bez výrazné změny"
    if edge and edge.get("stable"):
        short += f" · hrana od {edge['direction']}"
        if edge.get("approaching") and edge.get("eta_minutes") is not None:
            short += f" · ETA ~{edge['eta_minutes']} min"

    return {
        **base,
        "state": f"{cloud:.1f}",
        "available": True,
        "credential_status": "ok",
        "cloud_pct": round(cloud, 1),
        "center_cloud_pct": latest.get("center_cloud_pct"),
        "as_of": latest.get("time"),
        "age_minutes": None if age_minutes is None else round(age_minutes, 1),
        "short_text": short,
        "trend": trend,
        "arrow": arrow,
        "trend_slope_pph": nowcast.get("slope_pph"),
        "nowcast_confidence_pct": nowcast.get("confidence"),
        "nowcast": nowcast.get("points") or [],
        "edge": edge,
        "frames": len(frames),
        "valid_samples": latest.get("valid_samples"),
        "sample_count": latest.get("sample_count"),
        "errors": errors[-3:],
    }


def _publish_one(core: Any, entity_id: str, state: str, attrs: dict[str, Any]) -> None:
    if entity_id:
        core.publish_home_assistant_state(entity_id, state, attrs)


def _publish_satellite_entities(core: Any, options: dict[str, Any]) -> None:
    if not options.get("publish_homeassistant_entities", True):
        return
    satellite = _copy(SATELLITE_STATE)
    comparison = _copy(COMPARISON_STATE)

    sat_attrs = {key: value for key, value in satellite.items() if key != "state"}
    sat_attrs.update({
        "friendly_name": "Astro satelit – skutečná oblačnost",
        "icon": "mdi:satellite-variant",
        "unit_of_measurement": "%" if satellite.get("available") else None,
        "state_class": "measurement" if satellite.get("available") else None,
    })
    _publish_one(
        core,
        str(options.get("satellite_entity") or ""),
        str(satellite.get("state") or "unavailable"),
        sat_attrs,
    )

    cmp_attrs = {key: value for key, value in comparison.items() if key != "state"}
    cmp_attrs.update({
        "friendly_name": "Astro modely vs satelit – shoda",
        "icon": "mdi:compare-horizontal",
        "unit_of_measurement": "%" if comparison.get("available") else None,
        "state_class": "measurement" if comparison.get("available") else None,
    })
    _publish_one(
        core,
        str(options.get("satellite_comparison_entity") or ""),
        str(comparison.get("state") or "unavailable"),
        cmp_attrs,
    )

    model_ids = {
        "MET": "sensor.astro_met_satelit_chyba",
        "ALADIN": "sensor.astro_aladin_satelit_chyba",
        "ICON": "sensor.astro_icon_satelit_chyba",
    }
    models = comparison.get("models") if isinstance(comparison.get("models"), dict) else {}
    for model, entity_id in model_ids.items():
        row = models.get(model) if isinstance(models.get(model), dict) else {}
        error = _safe(row.get("absolute_error_pp"))
        attrs = {
            "friendly_name": f"Astro {model} vs satelit – absolutní chyba",
            "icon": "mdi:chart-bell-curve",
            "unit_of_measurement": "p. b.",
            "state_class": "measurement",
            "satellite_cloud_pct": comparison.get("satellite_cloud_pct"),
            "model_cloud_pct": row.get("cloud_pct"),
            "signed_error_pp": row.get("signed_error_pp"),
            "satellite_as_of": comparison.get("satellite_as_of"),
            "backend_version": RELEASE_VERSION,
        }
        _publish_one(core, entity_id, "unavailable" if error is None else f"{error:.1f}", attrs)


def _inject_states(core: Any, satellite: dict[str, Any], comparison: dict[str, Any]) -> None:
    with core.STATE_LOCK:
        core.STATE["satellite"] = _copy(satellite)
        core.STATE.setdefault("sources", {})["satellite"] = {
            "available": bool(satellite.get("available")),
            "provider": satellite.get("provider"),
            "collection": satellite.get("collection"),
            "as_of": satellite.get("as_of"),
            "credential_status": satellite.get("credential_status"),
        }
        core.DECISION_STATE["satelliteNowcast"] = _copy(satellite)
        core.DECISION_STATE["satelliteComparison"] = _copy(comparison)


def _update_satellite(core: Any, options: dict[str, Any]) -> None:
    global SATELLITE_STATE, COMPARISON_STATE
    try:
        satellite = _satellite_document(core, options)
    except Exception as exc:
        satellite = {
            "state": "unavailable",
            "available": False,
            "backend_version": RELEASE_VERSION,
            "provider": "EUMETSAT MTG/FCI Cloud Mask GRIB-2",
            "collection": EUMETSAT_CLM_GRIB_COLLECTION,
            "visual_url": EUMETVIEW_IR_EUROPE_URL,
            "credential_status": "error",
            "reason": str(exc)[:300],
        }
        core.log(f"SATELIT VAROVANI: {exc}")
        if options.get("debug"):
            import traceback
            traceback.print_exc()

    comparison = _comparison(core, options, satellite)
    SATELLITE_STATE = satellite
    COMPARISON_STATE = comparison
    _inject_states(core, satellite, comparison)

    if options.get("publish_homeassistant_entities", True):
        _publish_satellite_entities(core, options)
        with core.STATE_LOCK:
            weather = _copy(core.STATE)
            decision = _copy(core.DECISION_STATE)
            moon = _copy(core.MOON_STATE)
        if moon:
            core._SATELLITE_OLD_PUBLISH(options, weather, decision, moon)

    if satellite.get("available"):
        core.log(
            "SATELIT: FCI CLM "
            f"{satellite.get('cloud_pct')} %, trend={satellite.get('trend')}, "
            f"model-shoda={comparison.get('agreement_pct', '—')} %"
        )
    elif satellite.get("credential_status") == "required":
        core.log("SATELIT: EUMETView vizualizace dostupná; CLM porovnání čeká na EUMETSAT API klíč.")
    else:
        core.log(f"SATELIT: bez kvantitativních dat ({satellite.get('reason', 'bez detailu')}).")


def _satellite_worker(core: Any, options: dict[str, Any]) -> None:
    time.sleep(5)
    while True:
        started = time.monotonic()
        try:
            _update_satellite(core, options)
        except Exception as exc:
            core.log(f"SATELIT NEČEKANÁ CHYBA: {exc}")
        elapsed = time.monotonic() - started
        interval = max(600.0, float(options["satellite_refresh_minutes"]) * 60.0)
        time.sleep(max(30.0, interval - elapsed))


def _augment_manifest(core: Any) -> None:
    path = core.HA_CONFIG_DIR / "www" / core.CARD_MANIFEST_FILENAME
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        cards = manifest.get("cards")
        if not isinstance(cards, list):
            cards = []
        cards = [card for card in cards if isinstance(card, dict) and card.get("type") != "astro-satellite-card"]
        cards.append({
            "type": "astro-satellite-card",
            "version": SATELLITE_CARD_VERSION,
            "url": f"/local/astro-satellite-card-v{SATELLITE_CARD_VERSION}.js",
        })
        manifest["cards"] = cards
        manifest["backend_version"] = RELEASE_VERSION
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        core.log(f"SATELIT KARTA VAROVANI: manifest nelze rozšířit: {exc}")


def install(core: Any) -> None:
    if getattr(core, "_SATELLITE_NOWCAST_PATCH_INSTALLED", False):
        return

    old_load_options = core.load_options
    old_settings = core.decision_settings
    old_main = core.main
    old_install_cards = core.install_dashboard_cards
    old_publish = core.publish_homeassistant_entities

    core._SATELLITE_OLD_PUBLISH = old_publish

    def load_options() -> dict[str, Any]:
        options = old_load_options()
        options["use_satellite"] = bool(options.get("use_satellite", True))
        try:
            radius = int(options.get("satellite_radius_km", options.get("spatial_radius_km", 30)))
        except (TypeError, ValueError):
            radius = 30
        options["satellite_radius_km"] = max(10, min(50, radius))
        try:
            refresh = int(options.get("satellite_refresh_minutes", 10))
        except (TypeError, ValueError):
            refresh = 10
        options["satellite_refresh_minutes"] = max(10, min(60, refresh))
        options["satellite_entity"] = str(options.get("satellite_entity") or "sensor.astro_satelit_oblacnost").strip()
        options["satellite_comparison_entity"] = str(
            options.get("satellite_comparison_entity") or "sensor.astro_model_satelit_shoda"
        ).strip()
        options["eumetsat_consumer_key"] = str(options.get("eumetsat_consumer_key") or "").strip()
        options["eumetsat_consumer_secret"] = str(options.get("eumetsat_consumer_secret") or "").strip()
        agent = str(options.get("met_user_agent", "")).strip()
        if not agent or agent.startswith("AstroWeatherBackend/"):
            options["met_user_agent"] = (
                f"AstroWeatherBackend/{RELEASE_VERSION} "
                "https://github.com/Z0472/home-assistant-astro-weather"
            )
        return options

    def settings(options: dict[str, Any]) -> dict[str, Any]:
        result = old_settings(options)
        result.update({
            "use_satellite": bool(options.get("use_satellite", True)),
            "satellite_radius_km": int(options.get("satellite_radius_km", 30)),
            "satellite_refresh_minutes": int(options.get("satellite_refresh_minutes", 10)),
        })
        return result

    def install_cards(options: dict[str, Any]) -> bool:
        ok = old_install_cards(options)
        _augment_manifest(core)
        target = core.HA_CONFIG_DIR / "www" / f"astro-satellite-card-v{SATELLITE_CARD_VERSION}.js"
        return bool(ok and target.exists())

    def publish(options: dict[str, Any], weather: dict[str, Any],
                decision: dict[str, Any], moon: dict[str, Any]) -> None:
        old_publish(options, weather, decision, moon)
        _publish_satellite_entities(core, options)

    def main() -> None:
        options = core.load_options()
        import threading
        thread = threading.Thread(target=_satellite_worker, args=(core, options), daemon=True)
        thread.start()
        old_main()

    core.load_options = load_options
    core.decision_settings = settings
    core.install_dashboard_cards = install_cards
    core.publish_homeassistant_entities = publish
    core.main = main

    core.APP_VERSION = RELEASE_VERSION
    core.ASTRO_START_CARD_VERSION = ASTRO_CARD_VERSION
    current_installs = list(core.DASHBOARD_CARD_INSTALLS)
    for source, target in (
        (f"astro-start-card-v{ASTRO_CARD_VERSION}.js", f"astro-start-card-v{ASTRO_CARD_VERSION}.js"),
        ("astro-satellite-card.js", f"astro-satellite-card-v{SATELLITE_CARD_VERSION}.js"),
    ):
        if not any(dst == target for _, dst in current_installs):
            current_installs.append((source, target))
    core.DASHBOARD_CARD_INSTALLS = tuple(current_installs)
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._SATELLITE_NOWCAST_PATCH_INSTALLED = True
