#!/usr/bin/env python3
"""
Astro Weather Backend for Home Assistant.

Sources:
  - MET Norway Locationforecast 2.0 complete: detailed cloud layers, fog,
    dew point, humidity, temperature, wind and precipitation.
  - CHMI ALADIN open data (CZ_1km GRIB): low/mid/high/total cloud cover.
  - CAMS through Open-Meteo Air Quality API: aerosol optical depth at 550 nm.
  - 7Timer ASTRO: astronomical seeing scale converted to arcsec.

The process runs as a small Home Assistant local App (formerly add-on) and
serves JSON on internal HTTP endpoints. In addition to the raw forecast it
creates one authoritative SPUSTIT / NEJISTE / NESPOUSTET decision by combining
MET, ALADIN and an internal Moon/astronomical-night calculation.
"""

from __future__ import annotations

import bz2
import html.parser
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

APP_VERSION = "12.1.8"
HTTP_PORT = 8099
OPTIONS_FILE = Path("/data/options.json")
CACHE_DIR = Path("/data/cache")
HA_CONFIG_DIR = Path("/ha_config")
DASHBOARD_CARDS_DIR = Path("/app/cards")
DASHBOARD_CARD_FILES = ("astro-start-card.js", "moon-forecast-card.js")
DASHBOARD_CARD_INSTALLS = (
    ("astro-start-card.js", "astro-start-card.js"),
    ("astro-start-card.js", "astro-start-card-v20.js"),
    ("moon-forecast-card.js", "moon-forecast-card.js"),
    ("moon-forecast-card.js", "moon-forecast-card-v22.js"),
)
DASHBOARD_CARD_RESOURCE_URLS = ("/local/astro-start-card-v20.js", "/local/moon-forecast-card-v22.js")
RAD = math.pi / 180.0
DEG = 180.0 / math.pi
J2000 = 2451545.0
J1970 = 2440588.0
OBLIQUITY = RAD * 23.4397
ASTRONOMICAL_DARK_ALTITUDE_DEG = -18.0

MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
OPEN_METEO_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
SEVEN_TIMER_URL = "https://www.7timer.info/bin/api.pl"
SEVEN_TIMER_MAX_NEAREST_MINUTES = 100
SEEING_ARCSEC_BY_INDEX = {
    1: 0.5,
    2: 0.75,
    3: 1.0,
    4: 1.25,
    5: 1.5,
    6: 2.0,
    7: 2.5,
    8: 3.0,
}
SEEING_DISPLAY_BY_INDEX = {
    1: "0.5",
    2: "0.75",
    3: "1",
    4: "1.25",
    5: "1.5",
    6: "2",
    7: "2.5",
    8: ">2.5",
}
ALADIN_ROOT = "https://opendata.chmi.cz/meteorology/weather/nwp_aladin/CZ_1km"
ALADIN_CYCLES = ("00", "06", "12", "18")
ALADIN_PRODUCTS = {
    "cloud_low": "SURFNEBUL_BASSE",
    "cloud_medium": "SURFNEBUL_MOYENN",
    "cloud_high": "SURFNEBUL_HAUTE",
    "cloud_total": "SURFNEBUL_TOTALE",
}

STATE_LOCK = threading.Lock()
STATE: dict[str, Any] = {
    "state": "starting",
    "generated_at": None,
    "location": {},
    "sources": {},
    "errors": {},
    "forecast": [],
    "decision_summary": {},
}
DECISION_STATE: dict[str, Any] = {
    "state": "BEZ DAT",
    "machine_state": "unavailable",
    "generated_at": None,
    "backend_version": APP_VERSION,
    "reason": "Backend se spousti.",
    "daily": [],
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def log(message: str) -> None:
    print(f"[{iso_z(utc_now())}] {message}", flush=True)


def load_options() -> dict[str, Any]:
    defaults = {
        "latitude": 50.0755,
        "longitude": 14.4378,
        "altitude": 250,
        "timezone": "Europe/Prague",
        "refresh_minutes": 30,
        "horizon_hours": 72,
        "met_user_agent": "AstroWeatherBackend/12.1.8 https://github.com/Z0472/home-assistant-astro-weather",
        "moon_entity": "sensor.mesic_foceni_predpoved",
        "moon_horizon_days": 45,
        "moon_interference_illumination_pct": 15.0,
        "moon_interference_altitude_deg": 0.0,
        "publish_homeassistant_entities": True,
        "weather_entity": "sensor.astro_weather_detail",
        "decision_entity": "sensor.astro_vhodnost_foceni",
        "decision_nights": 3,
        "min_good_block_hours": 4.0,
        "max_start_delay_minutes": 90,
        "prep_minutes": 45,
        "good_score": 70,
        "marginal_score": 50,
        "disagreement_warn": 35,
        "disagreement_bad": 55,
        "wind_warn_ms": 8.0,
        "wind_bad_ms": 12.0,
        "use_moon": True,
        "use_aerosols": True,
        "aerosol_refresh_minutes": 180,
        "aod_warn": 0.30,
        "aod_bad": 0.40,
        "use_seeing": True,
        "seeing_warn_arcsec": 1.8,
        "seeing_bad_arcsec": 2.5,
        "install_dashboard_cards": True,
        "install_lovelace_resources": True,
        "debug": False,
    }
    try:
        if OPTIONS_FILE.exists():
            with OPTIONS_FILE.open("r", encoding="utf-8") as f:
                user = json.load(f)
            if isinstance(user, dict):
                defaults.update(user)
    except Exception as exc:
        log(f"VAROVANI: nelze nacist {OPTIONS_FILE}: {exc}")

    defaults["latitude"] = float(defaults["latitude"])
    defaults["longitude"] = float(defaults["longitude"])
    defaults["altitude"] = int(defaults["altitude"])
    defaults["timezone"] = str(defaults["timezone"]).strip() or "Europe/Prague"
    defaults["refresh_minutes"] = max(10, int(defaults["refresh_minutes"]))
    defaults["horizon_hours"] = max(24, min(120, int(defaults["horizon_hours"])))
    defaults["met_user_agent"] = str(defaults["met_user_agent"]).strip()
    defaults["moon_entity"] = str(defaults["moon_entity"]).strip()
    defaults["moon_horizon_days"] = max(3, min(60, int(defaults["moon_horizon_days"])))
    defaults["moon_interference_illumination_pct"] = max(
        0.0, min(100.0, float(defaults["moon_interference_illumination_pct"]))
    )
    defaults["moon_interference_altitude_deg"] = max(
        -5.0, min(30.0, float(defaults["moon_interference_altitude_deg"]))
    )
    defaults["publish_homeassistant_entities"] = bool(defaults["publish_homeassistant_entities"])
    defaults["weather_entity"] = str(defaults["weather_entity"]).strip()
    defaults["decision_entity"] = str(defaults["decision_entity"]).strip()
    defaults["decision_nights"] = max(1, min(5, int(defaults["decision_nights"])))
    defaults["min_good_block_hours"] = max(1.0, min(12.0, float(defaults["min_good_block_hours"])))
    defaults["max_start_delay_minutes"] = max(0, min(360, int(defaults["max_start_delay_minutes"])))
    defaults["prep_minutes"] = max(0, min(240, int(defaults["prep_minutes"])))
    defaults["good_score"] = max(0, min(100, int(defaults["good_score"])))
    defaults["marginal_score"] = max(0, min(100, int(defaults["marginal_score"])))
    defaults["disagreement_warn"] = max(0, min(100, int(defaults["disagreement_warn"])))
    defaults["disagreement_bad"] = max(0, min(100, int(defaults["disagreement_bad"])))
    defaults["wind_warn_ms"] = max(0.0, float(defaults["wind_warn_ms"]))
    defaults["wind_bad_ms"] = max(defaults["wind_warn_ms"], float(defaults["wind_bad_ms"]))
    defaults["use_moon"] = bool(defaults["use_moon"])
    defaults["use_aerosols"] = bool(defaults["use_aerosols"])
    defaults["use_seeing"] = bool(defaults["use_seeing"])
    defaults["aerosol_refresh_minutes"] = max(60, min(360, int(defaults["aerosol_refresh_minutes"])))
    aod_warn, aod_bad = safe_float(defaults["aod_warn"]), safe_float(defaults["aod_bad"])
    if aod_warn is None or aod_bad is None or not 0.10 < aod_warn < aod_bad <= 5:
        raise ValueError("Prahy musí splňovat 0.10 < aod_warn < aod_bad <= 5")
    defaults["aod_warn"], defaults["aod_bad"] = aod_warn, aod_bad
    seeing_warn = safe_float(defaults["seeing_warn_arcsec"])
    seeing_bad = safe_float(defaults["seeing_bad_arcsec"])
    if seeing_warn is None or seeing_bad is None or not 1.0 <= seeing_warn < seeing_bad <= 8.0:
        raise ValueError("Prahy musí splňovat 1.0 <= seeing_warn_arcsec < seeing_bad_arcsec <= 8.0")
    defaults["seeing_warn_arcsec"], defaults["seeing_bad_arcsec"] = seeing_warn, seeing_bad
    defaults["install_dashboard_cards"] = bool(defaults["install_dashboard_cards"])
    defaults["install_lovelace_resources"] = bool(defaults.get("install_lovelace_resources", True))
    defaults["debug"] = bool(defaults["debug"])
    return defaults


def install_dashboard_cards(options: dict[str, Any]) -> None:
    if not options.get("install_dashboard_cards", True):
        log("KARTY: automaticke kopirovani je vypnute.")
        return

    if not HA_CONFIG_DIR.exists():
        log("KARTY VAROVANI: /ha_config neni pripojene, karty nelze zapsat do /config/www.")
        return

    if not DASHBOARD_CARDS_DIR.exists():
        log("KARTY VAROVANI: /app/cards neexistuje, v image chybi dashboard karty.")
        return

    target_dir = HA_CONFIG_DIR / "www"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        for source_filename, target_filename in DASHBOARD_CARD_INSTALLS:
            source = DASHBOARD_CARDS_DIR / source_filename
            target = target_dir / target_filename
            if not source.exists():
                log(f"KARTY VAROVANI: zdrojova karta {source} chybi.")
                continue

            source_bytes = source.read_bytes()
            target.write_bytes(source_bytes)
            first_line = ""
            try:
                first_line = source_bytes.splitlines()[0].decode("utf-8", "replace")[:120]
            except Exception:
                first_line = "verzi se nepodarilo precist"
            copied.append(f"{target_filename} [{first_line}]")

        if copied:
            log(f"KARTY: prepsano v /config/www: {' | '.join(copied)}")
        else:
            log("KARTY VAROVANI: zadna dashboard karta nebyla zapsana.")
    except Exception as exc:
        log(f"KARTY CHYBA: nelze zapsat dashboard karty do /config/www: {exc}")


def home_assistant_api_request(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 20,
) -> Any:
    token = os.environ.get("SUPERVISOR_TOKEN", "").strip()
    if not token:
        raise RuntimeError("SUPERVISOR_TOKEN neni dostupny; zkontroluj homeassistant_api: true")

    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        "http://supervisor/core/api" + path,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:250]
        raise RuntimeError(f"HA API {method} {path} -> HTTP {exc.code}: {detail}") from exc

    if not raw:
        return None
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def lovelace_resource_key(url: str) -> str:
    base = str(url or "").split("?", 1)[0].strip()
    filename = base.rsplit("/", 1)[-1]
    if filename.startswith("astro-start-card"):
        return "astro-start-card"
    if filename.startswith("moon-forecast-card"):
        return "moon-forecast-card"
    return base


def ensure_lovelace_resources(options: dict[str, Any]) -> None:
    if not options.get("install_lovelace_resources", True):
        log("KARTY RESOURCE: automaticka registrace Lovelace resources je vypnuta.")
        return

    desired = {
        "astro-start-card": "/local/astro-start-card-v20.js",
        "moon-forecast-card": "/local/moon-forecast-card-v22.js",
    }

    try:
        resources = home_assistant_api_request("/config/lovelace/resources")
        if isinstance(resources, dict):
            rows = resources.get("resources") or resources.get("data") or []
        elif isinstance(resources, list):
            rows = resources
        else:
            rows = []

        rows = [row for row in rows if isinstance(row, dict)]
        changed: list[str] = []
        present: list[str] = []
        warnings: list[str] = []

        for resource_key, wanted_url in desired.items():
            matches = [
                row for row in rows
                if lovelace_resource_key(str(row.get("url", ""))) == resource_key
            ]

            exact = [row for row in matches if str(row.get("url", "")) == wanted_url]
            if exact:
                present.append(wanted_url)
                duplicates = [row for row in matches if row not in exact]
            else:
                duplicates = matches[1:]
                row_to_update = matches[0] if matches else None
                resource_id = str(row_to_update.get("id", "")).strip() if row_to_update else ""
                if resource_id:
                    try:
                        home_assistant_api_request(
                            f"/config/lovelace/resources/{urllib.parse.quote(resource_id, safe='')}",
                            method="PUT",
                            payload={"res_type": "module", "url": wanted_url},
                        )
                        changed.append(wanted_url)
                    except Exception as exc:
                        warnings.append(f"{resource_key}: nelze prepsat resource {resource_id}: {exc}")
                else:
                    try:
                        home_assistant_api_request(
                            "/config/lovelace/resources",
                            method="POST",
                            payload={"res_type": "module", "url": wanted_url},
                        )
                        changed.append(wanted_url)
                    except Exception as exc:
                        warnings.append(f"{resource_key}: nelze pridat resource: {exc}")

            for duplicate in duplicates:
                resource_id = str(duplicate.get("id", "")).strip()
                old_url = str(duplicate.get("url", ""))
                if not resource_id:
                    warnings.append(f"{old_url}: duplicitni resource nema id, smaz rucne")
                    continue
                try:
                    home_assistant_api_request(
                        f"/config/lovelace/resources/{urllib.parse.quote(resource_id, safe='')}",
                        method="DELETE",
                    )
                    changed.append(f"smazano {old_url}")
                except Exception as exc:
                    warnings.append(f"{old_url}: nelze smazat duplicitni resource {resource_id}: {exc}")

        if changed:
            log(f"KARTY RESOURCE: aktualizovano v Lovelace resources: {', '.join(changed)}")
        elif present:
            log("KARTY RESOURCE: Lovelace resources uz obsahuji aktualni dashboard karty.")
        for warning in warnings:
            log(f"KARTY RESOURCE VAROVANI: {warning}")
    except Exception as exc:
        log(f"KARTY RESOURCE VAROVANI: automaticka registrace selhala: {exc}")


def http_get(url: str, *, user_agent: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json,text/html,*/*",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def publish_home_assistant_state(entity_id: str, state: str, attributes: dict[str, Any]) -> None:
    token = os.environ.get("SUPERVISOR_TOKEN", "").strip()
    if not token:
        raise RuntimeError("SUPERVISOR_TOKEN neni dostupny; zkontroluj homeassistant_api: true")
    if not entity_id:
        raise RuntimeError("entity_id neni nastaven")

    quoted = urllib.parse.quote(entity_id, safe="")
    url = f"http://supervisor/core/api/states/{quoted}"
    body = json.dumps({"state": state, "attributes": attributes}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()


def publish_homeassistant_entities(
    options: dict[str, Any],
    weather_state: dict[str, Any],
    decision_state: dict[str, Any],
    moon_doc: dict[str, Any],
) -> None:
    if not options["publish_homeassistant_entities"]:
        return

    weather_entity = options["weather_entity"]
    if weather_entity:
        weather_attrs = {key: value for key, value in weather_state.items() if key != "state"}
        weather_attrs.update({
            "friendly_name": "Astro Weather Detail",
            "icon": "mdi:weather-night",
        })
        publish_home_assistant_state(weather_entity, str(weather_state.get("state", "unknown")), weather_attrs)

    decision_entity = options["decision_entity"]
    if decision_entity:
        decision_attrs = {key: value for key, value in decision_state.items() if key != "state"}
        decision_attrs.update({
            "friendly_name": "Astro vhodnost foceni",
            "icon": "mdi:telescope",
        })
        publish_home_assistant_state(decision_entity, str(decision_state.get("state", "BEZ DAT")), decision_attrs)

    moon_entity = options["moon_entity"]
    if moon_entity:
        attrs = moon_doc.get("attributes") if isinstance(moon_doc.get("attributes"), dict) else {}
        moon_attrs = dict(attrs)
        moon_attrs.update({
            "friendly_name": "Měsíc focení předpověď",
            "icon": "mdi:moon-waning-crescent",
        })
        publish_home_assistant_state(moon_entity, str(moon_doc.get("state", "BEZ DAT")), moon_attrs)


def safe_float(value: Any) -> float | None:
    try:
        f = float(value)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def round_or_none(value: Any, digits: int = 1) -> float | None:
    f = safe_float(value)
    return None if f is None else round(f, digits)


# ---------------------------------------------------------------------------
# MET Norway Locationforecast
# ---------------------------------------------------------------------------

def fetch_met(options: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    params = {
        "lat": f"{options['latitude']:.4f}",
        "lon": f"{options['longitude']:.4f}",
        "altitude": str(options["altitude"]),
    }
    url = MET_URL + "?" + urllib.parse.urlencode(params)
    raw = http_get(url, user_agent=options["met_user_agent"], timeout=45)
    doc = json.loads(raw.decode("utf-8"))

    props = doc.get("properties") or {}
    meta = props.get("meta") or {}
    timeseries = props.get("timeseries") or []
    result: dict[str, dict[str, Any]] = {}

    for row in timeseries:
        stamp = row.get("time")
        data = row.get("data") or {}
        details = ((data.get("instant") or {}).get("details") or {})
        next1 = ((data.get("next_1_hours") or {}).get("details") or {})

        if not stamp:
            continue

        result[stamp] = {
            "cloud_total": round_or_none(details.get("cloud_area_fraction")),
            "cloud_low": round_or_none(details.get("cloud_area_fraction_low")),
            "cloud_medium": round_or_none(details.get("cloud_area_fraction_medium")),
            "cloud_high": round_or_none(details.get("cloud_area_fraction_high")),
            "fog": round_or_none(details.get("fog_area_fraction")),
            "temperature": round_or_none(details.get("air_temperature")),
            "dew_point": round_or_none(details.get("dew_point_temperature")),
            "humidity": round_or_none(details.get("relative_humidity")),
            "wind_speed_ms": round_or_none(details.get("wind_speed")),
            "wind_from_direction": round_or_none(details.get("wind_from_direction")),
            "precipitation_1h": round_or_none(next1.get("precipitation_amount")),
        }

    source = {
        "available": bool(result),
        "provider": "MET Norway Locationforecast 2.0",
        "endpoint": "complete",
        "model_updated_at": meta.get("updated_at"),
        "hours": len(result),
    }
    return result, source


# ---------------------------------------------------------------------------
# CHMI ALADIN discovery/download/GRIB point extraction
# ---------------------------------------------------------------------------

class HrefCollector(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def discover_latest_aladin_run(options: dict[str, Any]) -> str:
    # The directory listing contains several recent runs. Choose the newest
    # YYYYMMDDHH prefix across 00/06/12/18.
    pattern = re.compile(r"ALADCZ1K4opendata_(\d{10})_SURFNEBUL_TOTALE\.grb\.bz2$")
    runs: set[str] = set()
    errors: list[str] = []

    for cycle in ALADIN_CYCLES:
        url = f"{ALADIN_ROOT}/{cycle}/"
        try:
            body = http_get(url, user_agent=options["met_user_agent"], timeout=30)
            parser = HrefCollector()
            parser.feed(body.decode("utf-8", errors="replace"))
            for href in parser.hrefs:
                name = urllib.parse.unquote(href.rsplit("/", 1)[-1])
                match = pattern.match(name)
                if match:
                    runs.add(match.group(1))
        except Exception as exc:
            errors.append(f"{cycle}: {exc}")

    if not runs:
        raise RuntimeError("Nenalezen zadny beh ALADIN. " + "; ".join(errors))
    return max(runs)


def aladin_cycle_from_run(run: str) -> str:
    if len(run) != 10 or run[-2:] not in ALADIN_CYCLES:
        raise ValueError(f"Neplatny ALADIN run: {run}")
    return run[-2:]


def download_aladin_product(run: str, product: str, options: dict[str, Any]) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cycle = aladin_cycle_from_run(run)
    filename = f"ALADCZ1K4opendata_{run}_{product}.grb.bz2"
    url = f"{ALADIN_ROOT}/{cycle}/{filename}"
    bz_path = CACHE_DIR / filename

    if bz_path.exists() and bz_path.stat().st_size > 1000:
        return bz_path

    tmp = bz_path.with_suffix(bz_path.suffix + ".part")
    log(f"ALADIN download: {filename}")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": options["met_user_agent"],
            "Accept": "application/octet-stream,*/*",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as out:
        shutil.copyfileobj(response, out, length=1024 * 1024)
    tmp.replace(bz_path)
    return bz_path


def run_cmd(args: list[str], timeout: int = 120) -> str:
    proc = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Prikaz selhal ({proc.returncode}): {' '.join(args)}; stderr={proc.stderr.strip()}"
        )
    return proc.stdout


def parse_number_lines(text: str) -> list[float]:
    values: list[float] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # -l mode=1 returns one nearest value per GRIB message.
        token = line.split()[0]
        values.append(float(token))
    return values


def grib_message_times(grib_path: Path) -> list[str]:
    out = run_cmd([
        "grib_get",
        "-p", "validityDate:i,validityTime:i",
        str(grib_path),
    ])
    stamps: list[str] = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        date_s = str(int(parts[0])).zfill(8)
        time_i = int(parts[1])
        time_s = f"{time_i:04d}"
        dt = datetime.strptime(date_s + time_s, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        stamps.append(iso_z(dt))
    return stamps


def grib_unit_and_global_max(grib_path: Path) -> tuple[str, float | None]:
    unit = ""
    try:
        unit = run_cmd(["grib_get", "-w", "count=1", "-p", "units:s", str(grib_path)]).strip()
    except Exception:
        pass

    max_value: float | None = None
    try:
        max_out = run_cmd(["grib_get", "-p", "max:d", str(grib_path)])
        vals = [float(x.strip()) for x in max_out.splitlines() if x.strip()]
        if vals:
            max_value = max(vals)
    except Exception:
        pass
    return unit, max_value


def cloud_to_percent(raw: float, unit: str, global_max: float | None) -> float:
    u = unit.strip().lower().replace(" ", "")
    factor = 1.0

    if "%" in u or "percent" in u:
        factor = 1.0
    elif "octa" in u or "okta" in u:
        factor = 12.5
    elif "fraction" in u or u in {"1", "(0-1)", "0-1"}:
        factor = 100.0
    elif global_max is not None and global_max <= 1.05:
        # Typical GRIB representation of cloud fraction.
        factor = 100.0

    pct = raw * factor
    return round(max(0.0, min(100.0, pct)), 1)


def extract_grib_point_series(bz_path: Path, lat: float, lon: float) -> dict[str, float]:
    grib_path = bz_path.with_suffix("")  # removes .bz2 -> .grb
    try:
        with bz2.open(bz_path, "rb") as src, grib_path.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)

        times = grib_message_times(grib_path)
        values_out = run_cmd([
            "grib_get",
            "-F", "%.8f",
            "-l", f"{lat:.6f},{lon:.6f},1",
            str(grib_path),
        ], timeout=180)
        values = parse_number_lines(values_out)

        if len(times) != len(values):
            raise RuntimeError(
                f"GRIB pocet casu {len(times)} != pocet hodnot {len(values)} ({bz_path.name})"
            )

        unit, global_max = grib_unit_and_global_max(grib_path)
        return {
            stamp: cloud_to_percent(raw, unit, global_max)
            for stamp, raw in zip(times, values)
        }
    finally:
        try:
            grib_path.unlink(missing_ok=True)
        except Exception:
            pass


def cleanup_old_aladin_cache(current_run: str) -> None:
    if not CACHE_DIR.exists():
        return
    for path in CACHE_DIR.glob("ALADCZ1K4opendata_*_SURFNEBUL_*.grb.bz2"):
        match = re.search(r"opendata_(\d{10})_", path.name)
        if match and match.group(1) != current_run:
            try:
                path.unlink()
            except Exception:
                pass


def fetch_aladin(options: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if shutil.which("grib_get") is None:
        raise RuntimeError("ecCodes/grib_get neni v kontejneru k dispozici")

    run = discover_latest_aladin_run(options)
    lat = float(options["latitude"])
    lon = float(options["longitude"])

    product_series: dict[str, dict[str, float]] = {}
    for field_name, product_name in ALADIN_PRODUCTS.items():
        bz_path = download_aladin_product(run, product_name, options)
        product_series[field_name] = extract_grib_point_series(bz_path, lat, lon)

    cleanup_old_aladin_cache(run)

    all_stamps: set[str] = set()
    for series in product_series.values():
        all_stamps.update(series.keys())

    result: dict[str, dict[str, Any]] = {}
    for stamp in sorted(all_stamps):
        result[stamp] = {
            field: series.get(stamp)
            for field, series in product_series.items()
        }

    run_dt = datetime.strptime(run, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    source = {
        "available": bool(result),
        "provider": "CHMI ALADIN open data",
        "dataset": "CZ_1km",
        "native_model_grid_km": 2.3,
        "run": run,
        "run_time": iso_z(run_dt),
        "hours": len(result),
        "products": list(ALADIN_PRODUCTS.values()),
    }
    return result, source


# ---------------------------------------------------------------------------
# Merge and refresh
# ---------------------------------------------------------------------------

def parse_iso_utc(value: str) -> datetime | None:
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Internal Sun/Moon forecast.
# Low-precision formulas are enough for operational night planning and avoid
# numpy, skyfield and external ephemeris files in Home Assistant.
# ---------------------------------------------------------------------------

def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def to_julian(dt: datetime) -> float:
    return dt.astimezone(timezone.utc).timestamp() / 86400.0 - 0.5 + J1970


def to_days(dt: datetime) -> float:
    return to_julian(dt) - J2000


def right_ascension(lon: float, lat: float) -> float:
    return math.atan2(
        math.sin(lon) * math.cos(OBLIQUITY) - math.tan(lat) * math.sin(OBLIQUITY),
        math.cos(lon),
    )


def declination(lon: float, lat: float) -> float:
    return math.asin(
        math.sin(lat) * math.cos(OBLIQUITY)
        + math.cos(lat) * math.sin(OBLIQUITY) * math.sin(lon)
    )


def sidereal_time(days: float, longitude: float) -> float:
    lw = RAD * -longitude
    return RAD * (280.16 + 360.9856235 * days) - lw


def astro_altitude(dt: datetime, latitude: float, longitude: float, ra: float, dec: float) -> float:
    phi = RAD * latitude
    h = sidereal_time(to_days(dt), longitude) - ra
    return math.asin(math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(h))


def solar_mean_anomaly(days: float) -> float:
    return RAD * (357.5291 + 0.98560028 * days)


def ecliptic_longitude(mean_anomaly: float) -> float:
    center = RAD * (
        1.9148 * math.sin(mean_anomaly)
        + 0.0200 * math.sin(2 * mean_anomaly)
        + 0.0003 * math.sin(3 * mean_anomaly)
    )
    perihelion = RAD * 102.9372
    return mean_anomaly + center + perihelion + math.pi


def sun_coords(dt: datetime) -> dict[str, float]:
    mean_anomaly = solar_mean_anomaly(to_days(dt))
    lon = ecliptic_longitude(mean_anomaly)
    return {"ra": right_ascension(lon, 0.0), "dec": declination(lon, 0.0)}


def sun_altitude(dt: datetime, latitude: float, longitude: float) -> float:
    coords = sun_coords(dt)
    return astro_altitude(dt, latitude, longitude, coords["ra"], coords["dec"])


def moon_coords(dt: datetime) -> dict[str, float]:
    days = to_days(dt)
    lon = RAD * (218.316 + 13.176396 * days)
    mean_anomaly = RAD * (134.963 + 13.064993 * days)
    argument_latitude = RAD * (93.272 + 13.229350 * days)

    ecliptic_lon = lon + RAD * 6.289 * math.sin(mean_anomaly)
    ecliptic_lat = RAD * 5.128 * math.sin(argument_latitude)
    distance_km = 385001.0 - 20905.0 * math.cos(mean_anomaly)
    return {
        "ra": right_ascension(ecliptic_lon, ecliptic_lat),
        "dec": declination(ecliptic_lon, ecliptic_lat),
        "distance_km": distance_km,
    }


def astro_refraction(altitude: float) -> float:
    # Approximation used by common Sun/Moon calculators, returned in radians.
    h = max(altitude, 0.0)
    return 0.0002967 / math.tan(h + 0.00312536 / (h + 0.08901179))


def moon_altitude(dt: datetime, latitude: float, longitude: float) -> float:
    coords = moon_coords(dt)
    altitude = astro_altitude(dt, latitude, longitude, coords["ra"], coords["dec"])
    return altitude + astro_refraction(altitude)


def moon_illumination(dt: datetime) -> dict[str, float | str]:
    sun = sun_coords(dt)
    moon = moon_coords(dt)
    sun_distance_km = 149598000.0

    phase_angle = math.acos(clamp(
        math.sin(sun["dec"]) * math.sin(moon["dec"])
        + math.cos(sun["dec"]) * math.cos(moon["dec"]) * math.cos(sun["ra"] - moon["ra"]),
        -1.0,
        1.0,
    ))
    incidence = math.atan2(
        sun_distance_km * math.sin(phase_angle),
        moon["distance_km"] - sun_distance_km * math.cos(phase_angle),
    )
    angle = math.atan2(
        math.cos(sun["dec"]) * math.sin(sun["ra"] - moon["ra"]),
        math.sin(sun["dec"]) * math.cos(moon["dec"])
        - math.cos(sun["dec"]) * math.sin(moon["dec"]) * math.cos(sun["ra"] - moon["ra"]),
    )

    fraction = (1.0 + math.cos(incidence)) / 2.0
    phase = 0.5 + 0.5 * incidence * (-1 if angle < 0 else 1) / math.pi
    phase = phase % 1.0
    return {
        "fraction": clamp(fraction, 0.0, 1.0),
        "percent": clamp(fraction * 100.0, 0.0, 100.0),
        "phase_value": phase,
        "phase": moon_phase_label(phase),
    }


def moon_phase_label(phase: float) -> str:
    if phase < 0.03 or phase >= 0.97:
        return "nov"
    if phase < 0.22:
        return "dorůstající srpek"
    if phase < 0.28:
        return "první čtvrť"
    if phase < 0.47:
        return "dorůstající Měsíc"
    if phase < 0.53:
        return "úplněk"
    if phase < 0.72:
        return "couvající Měsíc"
    if phase < 0.78:
        return "poslední čtvrť"
    return "couvající srpek"


def local_day_label(day: date) -> str:
    weekdays = ["po", "út", "st", "čt", "pá", "so", "ne"]
    return f"{weekdays[day.weekday()]} {day.day}. {day.month}."


def find_altitude_crossing(
    altitude_func: Any,
    start: datetime,
    end: datetime,
    threshold: float,
    direction: str,
    step_minutes: int = 10,
) -> datetime | None:
    if end <= start:
        return None

    previous_time = start
    previous_value = altitude_func(previous_time) - threshold
    step = timedelta(minutes=step_minutes)
    current_time = start + step

    while current_time <= end + timedelta(seconds=1):
        current_time = min(current_time, end)
        current_value = altitude_func(current_time) - threshold
        crossed_down = direction == "down" and previous_value >= 0 and current_value < 0
        crossed_up = direction == "up" and previous_value <= 0 and current_value > 0
        if crossed_down or crossed_up:
            lo, hi = previous_time, current_time
            for _ in range(32):
                mid = lo + (hi - lo) / 2
                mid_value = altitude_func(mid) - threshold
                if direction == "down":
                    if mid_value >= 0:
                        lo = mid
                    else:
                        hi = mid
                else:
                    if mid_value <= 0:
                        lo = mid
                    else:
                        hi = mid
            return hi
        if current_time >= end:
            break
        previous_time, previous_value = current_time, current_value
        current_time += step
    return None


def astronomical_night(day: date, tz: ZoneInfo, options: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    latitude = options["latitude"]
    longitude = options["longitude"]
    local_noon = datetime(day.year, day.month, day.day, 12, 0, tzinfo=tz)
    local_midnight = local_noon + timedelta(hours=12)
    next_noon = local_noon + timedelta(days=1)

    def sun_alt(dt: datetime) -> float:
        return sun_altitude(dt, latitude, longitude)

    threshold = RAD * ASTRONOMICAL_DARK_ALTITUDE_DEG
    start = find_altitude_crossing(
        sun_alt,
        local_noon.astimezone(timezone.utc),
        local_midnight.astimezone(timezone.utc),
        threshold,
        "down",
    )
    end = find_altitude_crossing(
        sun_alt,
        local_midnight.astimezone(timezone.utc),
        next_noon.astimezone(timezone.utc),
        threshold,
        "up",
    )
    return start, end


def moon_events_between(start: datetime, end: datetime, options: dict[str, Any]) -> list[dict[str, Any]]:
    latitude = options["latitude"]
    longitude = options["longitude"]
    events: list[dict[str, Any]] = []

    def altitude(dt: datetime) -> float:
        return moon_altitude(dt, latitude, longitude)

    threshold = 0.0
    previous_time = start
    previous_above = altitude(previous_time) >= threshold
    step = timedelta(minutes=10)
    current_time = start + step

    while current_time <= end + timedelta(seconds=1):
        current_time = min(current_time, end)
        current_above = altitude(current_time) >= threshold
        if current_above != previous_above:
            direction = "up" if current_above else "down"
            event_time = find_altitude_crossing(
                altitude,
                previous_time,
                current_time,
                threshold,
                direction,
                step_minutes=2,
            )
            if event_time is not None:
                events.append({"event": "RISE" if current_above else "SET", "time": event_time})
        if current_time >= end:
            break
        previous_time, previous_above = current_time, current_above
        current_time += step
    return events


def nearest_event(events: list[dict[str, Any]], event_type: str, center: datetime) -> datetime | None:
    matches = [
        e["time"] for e in events
        if e.get("event") == event_type and isinstance(e.get("time"), datetime)
    ]
    if not matches:
        return None
    return min(matches, key=lambda dt: abs((dt - center).total_seconds()))


def moon_interferes_at(dt: datetime, options: dict[str, Any]) -> tuple[bool, float, float, str]:
    altitude_deg = moon_altitude(dt, options["latitude"], options["longitude"]) * DEG
    illumination = moon_illumination(dt)
    illumination_pct = float(illumination["percent"])
    phase = str(illumination["phase"])
    interferes = (
        illumination_pct >= options["moon_interference_illumination_pct"]
        and altitude_deg >= options["moon_interference_altitude_deg"]
    )
    return interferes, altitude_deg, illumination_pct, phase


def integrate_moon_for_night(
    dark_start: datetime,
    dark_end: datetime,
    options: dict[str, Any],
) -> dict[str, float]:
    clean_hours = 0.0
    interference_hours = 0.0
    max_altitude: float | None = None
    step = timedelta(minutes=5)
    cursor = dark_start

    while cursor < dark_end:
        segment_end = min(cursor + step, dark_end)
        midpoint = cursor + (segment_end - cursor) / 2
        duration = (segment_end - cursor).total_seconds() / 3600.0
        interferes, altitude_deg, _, _ = moon_interferes_at(midpoint, options)
        max_altitude = altitude_deg if max_altitude is None else max(max_altitude, altitude_deg)
        if options["use_moon"] and interferes:
            interference_hours += duration
        else:
            clean_hours += duration
        cursor = segment_end

    dark_hours = (dark_end - dark_start).total_seconds() / 3600.0
    return {
        "dark_hours": dark_hours,
        "clean_hours": clean_hours,
        "interference_hours": interference_hours,
        "moon_max_altitude": max_altitude if max_altitude is not None else 0.0,
    }


def build_internal_moon_document(options: dict[str, Any]) -> dict[str, Any]:
    tz = ZoneInfo(options["timezone"])
    now = utc_now()
    today = now.astimezone(tz).date()
    first_day = today - timedelta(days=1)
    days_to_generate = max(options["moon_horizon_days"], options["decision_nights"] + 2)
    daily: list[dict[str, Any]] = []
    night_ranges: list[tuple[datetime, datetime]] = []

    for offset in range(days_to_generate + 1):
        day = first_day + timedelta(days=offset)
        dark_start, dark_end = astronomical_night(day, tz, options)
        midpoint_local = datetime(day.year, day.month, day.day, 0, 0, tzinfo=tz) + timedelta(days=1)
        midpoint = midpoint_local.astimezone(timezone.utc)
        illumination = moon_illumination(midpoint)
        altitude_midnight = moon_altitude(midpoint, options["latitude"], options["longitude"]) * DEG

        if dark_start is None or dark_end is None or dark_end <= dark_start:
            daily.append({
                "date": day.isoformat(),
                "label": local_day_label(day),
                "status": "bez_dat",
                "phase": illumination["phase"],
                "moon_illumination": round(float(illumination["percent"]), 1),
                "moon_altitude_midnight": round(altitude_midnight, 1),
                "astronomical_dark_start": None,
                "astronomical_dark_end": None,
                "dark_hours": 0.0,
                "clean_hours": 0.0,
                "interference_hours": 0.0,
            })
            continue

        night_ranges.append((dark_start, dark_end))
        moon_stats = integrate_moon_for_night(dark_start, dark_end, options)
        dark_hours = moon_stats["dark_hours"]
        clean_hours = moon_stats["clean_hours"]
        interference_hours = moon_stats["interference_hours"]

        if not options["use_moon"] or interference_hours <= 0.05:
            status = "nerusi"
        elif clean_hours <= 0.05:
            status = "rusi"
        else:
            status = "castecne"

        events_start = datetime(day.year, day.month, day.day, 0, 0, tzinfo=tz).astimezone(timezone.utc)
        events_end = events_start + timedelta(days=2)
        events = moon_events_between(events_start, events_end, options)
        center = dark_start + (dark_end - dark_start) / 2
        moonrise = nearest_event(events, "RISE", center)
        moonset = nearest_event(events, "SET", center)

        daily.append({
            "date": day.isoformat(),
            "label": local_day_label(day),
            "status": status,
            "phase": illumination["phase"],
            "moon_illumination": round(float(illumination["percent"]), 1),
            "moon_altitude_midnight": round(altitude_midnight, 1),
            "moonrise": iso_z(moonrise) if moonrise is not None else None,
            "moonset": iso_z(moonset) if moonset is not None else None,
            "astronomical_dark_start": iso_z(dark_start),
            "astronomical_dark_end": iso_z(dark_end),
            "dark_hours": round(dark_hours, 2),
            "clean_hours": round(clean_hours, 2),
            "interference_hours": round(interference_hours, 2),
            "moon_max_altitude": round(moon_stats["moon_max_altitude"], 1),
        })

    hourly: list[dict[str, Any]] = []
    if night_ranges:
        start = min(r[0] for r in night_ranges) - timedelta(hours=2)
        end = max(r[1] for r in night_ranges) + timedelta(hours=2)
        start = start.replace(minute=0, second=0, microsecond=0)
        cursor = start
        while cursor <= end:
            midpoint = cursor + timedelta(minutes=30)
            interferes, altitude_deg, illumination_pct, phase = moon_interferes_at(midpoint, options)
            hourly.append({
                "time": iso_z(cursor),
                "interferes": bool(options["use_moon"] and interferes),
                "moon_altitude": round(altitude_deg, 1),
                "moon_illumination": round(illumination_pct, 1),
                "phase": phase,
            })
            cursor += timedelta(hours=1)

    first_future = next(
        (
            item for item in daily
            if parse_iso_utc(str(item.get("astronomical_dark_end", ""))) is not None
            and parse_iso_utc(str(item.get("astronomical_dark_end", ""))) > now
        ),
        None,
    )
    state = "BEZ DAT"
    if first_future is not None and safe_float(first_future.get("clean_hours")) is not None:
        state = f"{float(first_future['clean_hours']):.1f} h"

    return {
        "state": state,
        "last_updated": iso_z(now),
        "attributes": {
            "daily": daily,
            "hourly": hourly,
            "generated_at": iso_z(now),
            "backend_version": APP_VERSION,
            "provider": "Astro Weather Backend internal Moon",
            "latitude": options["latitude"],
            "longitude": options["longitude"],
            "timezone": options["timezone"],
            "moon_horizon_days": days_to_generate,
            "moon_interference_illumination_pct": options["moon_interference_illumination_pct"],
            "moon_interference_altitude_deg": options["moon_interference_altitude_deg"],
        },
    }


# ---------------------------------------------------------------------------
# Sky quality forecast without SkyAccuracy.
# AOD comes from CAMS data exposed by Open-Meteo Air Quality API. Seeing comes
# from the public 7Timer ASTRO JSON API. Both are optional; outage means fallback
# to the MET + ALADIN + internal Moon decision.
# ---------------------------------------------------------------------------

def value_at(values: Any, index: int) -> Any:
    return values[index] if isinstance(values, list) and index < len(values) else None


def nonnegative_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    f = safe_float(value)
    return f if f is not None and f >= 0 else None


def write_json_cache(path: Path, fetched_at: datetime, payload: dict[str, Any]) -> None:
    try:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            json.dumps({"fetched_at": iso_z(fetched_at), "payload": payload}, ensure_ascii=False),
            encoding="utf-8",
        )
        temp.replace(path)
    except OSError as exc:
        log(f"KVALITA OBLOHY: cache nelze zapsat: {exc}")


def cache_age(now: datetime, fetched_at: datetime | None) -> timedelta | None:
    if fetched_at is None:
        return None
    age = now - fetched_at
    return age if age >= timedelta(0) else None


def open_meteo_air_quality_url(options: dict[str, Any]) -> str:
    forecast_days = max(1, min(7, math.ceil((options["horizon_hours"] + 24) / 24)))
    params = {
        "latitude": f"{options['latitude']:.5f}",
        "longitude": f"{options['longitude']:.5f}",
        "hourly": "aerosol_optical_depth,dust",
        "timezone": "UTC",
        "forecast_days": str(forecast_days),
    }
    return OPEN_METEO_AIR_QUALITY_URL + "?" + urllib.parse.urlencode(params)


def parse_open_meteo_air_quality(doc: dict[str, Any], options: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(doc, dict):
        raise ValueError("Open-Meteo CAMS vrátil neplatný JSON")

    lat = safe_float(doc.get("latitude"))
    lon = safe_float(doc.get("longitude"))
    if lat is not None and lon is not None:
        if abs(lat - options["latitude"]) > 1.0 or abs(lon - options["longitude"]) > 1.0:
            raise ValueError("Open-Meteo CAMS vrátil jinou lokalitu")

    hourly = doc.get("hourly") if isinstance(doc.get("hourly"), dict) else {}
    times = hourly.get("time")
    if not isinstance(times, list):
        raise ValueError("Open-Meteo CAMS neobsahuje hodinovou osu")

    output: dict[str, dict[str, Any]] = {}
    for idx, raw_time in enumerate(times):
        stamp = parse_iso_utc(str(raw_time))
        if stamp is None or stamp.minute or stamp.second:
            continue
        aod = nonnegative_float(value_at(hourly.get("aerosol_optical_depth"), idx))
        dust = nonnegative_float(value_at(hourly.get("dust"), idx))
        if aod is None:
            continue
        output[iso_z(stamp)] = {
            "aod550": aod,
            "dust_aod550": None,
            "dust_ugm3": dust,
        }

    if not any(row.get("aod550") is not None for row in output.values()):
        raise ValueError("Open-Meteo CAMS neobsahuje platné AOD 550")
    return output


def fetch_cams_aerosols(options: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    now = utc_now()
    ttl = timedelta(minutes=options["aerosol_refresh_minutes"])
    max_age = timedelta(hours=6)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"open_meteo_cams_aod_{options['latitude']:.4f}_{options['longitude']:.4f}.json"
    endpoint = open_meteo_air_quality_url(options)
    errors: dict[str, str] = {}

    cached_rows: dict[str, dict[str, Any]] | None = None
    fetched_at: datetime | None = None
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = parse_iso_utc(str(cache.get("fetched_at", "")))
        cached_rows = parse_open_meteo_air_quality(cache["payload"], options)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError):
        pass

    age = cache_age(now, fetched_at)
    fresh = cached_rows is not None and age is not None and age < ttl
    stale = False
    rows = cached_rows if fresh else None

    if not fresh:
        try:
            doc = json.loads(http_get(endpoint, user_agent=options["met_user_agent"], timeout=30).decode("utf-8"))
            rows = parse_open_meteo_air_quality(doc, options)
            fetched_at = utc_now()
            stale = False
            write_json_cache(path, fetched_at, doc)
        except Exception as exc:
            errors["open_meteo"] = str(exc)[:250]
            if cached_rows is not None and age is not None and age <= max_age:
                rows = cached_rows
                stale = True
            else:
                rows = {}

    result: dict[str, dict[str, Any]] = {}
    retrieved = fetched_at if fetched_at is not None else now
    for stamp, row in (rows or {}).items():
        result[stamp] = {
            **row,
            "stale": stale,
            "fetched_at": iso_z(retrieved),
            "source": "CAMS / Open-Meteo",
        }

    for old in CACHE_DIR.glob("open_meteo_cams_aod_*.json"):
        try:
            if now.timestamp() - old.stat().st_mtime > 7 * 86400:
                old.unlink()
        except OSError:
            pass

    return result, {
        "available": bool(result),
        "enabled": options["use_aerosols"],
        "provider": "CAMS through Open-Meteo Air Quality API",
        "url": "https://open-meteo.com/en/docs/air-quality-api",
        "endpoint": endpoint,
        "hours": len(result),
        "errors": errors,
        "model_updated_at": None,
        "oldest_fetched_at": iso_z(retrieved) if result else None,
        "refresh_minutes": options["aerosol_refresh_minutes"],
        "stale_hours": sum(bool(row.get("stale")) for row in result.values()),
        "units": {
            "aod550": "dimensionless",
            "dust_ugm3": "ug/m3",
            "dust_aod550": None,
        },
        "note": "dust_ugm3 je povrchová koncentrace prachu, ne prachová složka AOD.",
    }


def seven_timer_url(options: dict[str, Any]) -> str:
    params = {
        "lon": f"{options['longitude']:.5f}",
        "lat": f"{options['latitude']:.5f}",
        "product": "astro",
        "output": "json",
    }
    return SEVEN_TIMER_URL + "?" + urllib.parse.urlencode(params)


def parse_7timer_init(value: Any) -> datetime:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{10}", text):
        raise ValueError("7Timer neobsahuje platný init čas")
    return datetime.strptime(text, "%Y%m%d%H").replace(tzinfo=timezone.utc)


def parse_7timer_astro(doc: dict[str, Any], options: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(doc, dict):
        raise ValueError("7Timer vrátil neplatný JSON")
    init = parse_7timer_init(doc.get("init"))
    rows = doc.get("dataseries")
    if not isinstance(rows, list):
        raise ValueError("7Timer neobsahuje dataseries")

    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        timepoint = safe_float(row.get("timepoint"))
        raw_seeing = nonnegative_float(row.get("seeing"))
        if timepoint is None or raw_seeing is None:
            continue
        if abs(timepoint - round(timepoint)) > 0.001:
            continue
        seeing_index = int(round(raw_seeing))
        if seeing_index not in SEEING_ARCSEC_BY_INDEX:
            continue
        raw_transparency = nonnegative_float(row.get("transparency"))
        transparency_index = int(round(raw_transparency)) if raw_transparency is not None else None
        if transparency_index not in range(1, 9):
            transparency_index = None
        stamp = init + timedelta(hours=int(round(timepoint)))
        output[iso_z(stamp)] = {
            "seeingIndex": seeing_index,
            "seeingArcsec": SEEING_ARCSEC_BY_INDEX[seeing_index],
            "seeingDisplay": SEEING_DISPLAY_BY_INDEX[seeing_index],
            "transparencyIndex": transparency_index,
            "source_time": iso_z(stamp),
        }

    if not output:
        raise ValueError("7Timer neobsahuje platný seeing")
    return output


def expand_sparse_seeing(samples: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    parsed_samples: list[tuple[datetime, dict[str, Any]]] = []
    for stamp, row in samples.items():
        dt = parse_iso_utc(stamp)
        if dt is not None:
            parsed_samples.append((dt, row))
    parsed_samples.sort(key=lambda item: item[0])
    if not parsed_samples:
        return {}

    start = parsed_samples[0][0].replace(minute=0, second=0, microsecond=0)
    end = parsed_samples[-1][0].replace(minute=0, second=0, microsecond=0)
    cursor = start
    output: dict[str, dict[str, Any]] = {}
    while cursor <= end:
        best_dt, best_row = min(parsed_samples, key=lambda item: abs((item[0] - cursor).total_seconds()))
        diff_minutes = abs((best_dt - cursor).total_seconds()) / 60.0
        if diff_minutes <= SEVEN_TIMER_MAX_NEAREST_MINUTES:
            output[iso_z(cursor)] = {
                **best_row,
                "nearest_diff_minutes": round(diff_minutes, 1),
            }
        cursor += timedelta(hours=1)
    return output


def fetch_7timer_seeing(options: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    now = utc_now()
    ttl = timedelta(minutes=options["aerosol_refresh_minutes"])
    max_age = timedelta(hours=6)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"seven_timer_astro_{options['latitude']:.4f}_{options['longitude']:.4f}.json"
    endpoint = seven_timer_url(options)
    errors: dict[str, str] = {}

    cached_rows: dict[str, dict[str, Any]] | None = None
    fetched_at: datetime | None = None
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = parse_iso_utc(str(cache.get("fetched_at", "")))
        cached_rows = expand_sparse_seeing(parse_7timer_astro(cache["payload"], options))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError):
        pass

    age = cache_age(now, fetched_at)
    fresh = cached_rows is not None and age is not None and age < ttl
    stale = False
    rows = cached_rows if fresh else None

    if not fresh:
        try:
            doc = json.loads(http_get(endpoint, user_agent=options["met_user_agent"], timeout=30).decode("utf-8"))
            rows = expand_sparse_seeing(parse_7timer_astro(doc, options))
            fetched_at = utc_now()
            stale = False
            write_json_cache(path, fetched_at, doc)
        except Exception as exc:
            errors["7timer"] = str(exc)[:250]
            if cached_rows is not None and age is not None and age <= max_age:
                rows = cached_rows
                stale = True
            else:
                rows = {}

    result: dict[str, dict[str, Any]] = {}
    retrieved = fetched_at if fetched_at is not None else now
    for stamp, row in (rows or {}).items():
        result[stamp] = {
            **row,
            "stale": stale,
            "fetched_at": iso_z(retrieved),
            "source": "7Timer ASTRO",
        }

    for old in CACHE_DIR.glob("seven_timer_astro_*.json"):
        try:
            if now.timestamp() - old.stat().st_mtime > 7 * 86400:
                old.unlink()
        except OSError:
            pass

    return result, {
        "available": bool(result),
        "enabled": options["use_seeing"],
        "provider": "7Timer ASTRO direct",
        "url": "https://www.7timer.info/doc.php?lang=en",
        "endpoint": endpoint,
        "source_code": "astro",
        "hours": len(result),
        "errors": errors,
        "model_updated_at": None,
        "oldest_fetched_at": iso_z(retrieved) if result else None,
        "refresh_minutes": options["aerosol_refresh_minutes"],
        "stale_hours": sum(bool(row.get("stale")) for row in result.values()),
        "units": {"seeing_arcsec": "arcsec", "seeing_index": "1..8"},
        "native_resolution": "3h expanded to nearest hourly value",
    }


def fetch_sky_quality(options: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    sources: dict[str, dict[str, Any]] = {}

    if options["use_aerosols"]:
        try:
            aerosol_rows, aerosol_source = fetch_cams_aerosols(options)
        except Exception as exc:
            aerosol_rows = {}
            aerosol_source = {
                "available": False,
                "enabled": True,
                "provider": "CAMS through Open-Meteo Air Quality API",
                "errors": {"open_meteo": str(exc)[:250]},
            }
        for stamp, row in aerosol_rows.items():
            combined.setdefault(stamp, {})["aerosols"] = row
        sources["aerosols"] = aerosol_source
    else:
        sources["aerosols"] = {"available": False, "enabled": False}

    if options["use_seeing"]:
        try:
            seeing_rows, seeing_source = fetch_7timer_seeing(options)
        except Exception as exc:
            seeing_rows = {}
            seeing_source = {
                "available": False,
                "enabled": True,
                "provider": "7Timer ASTRO direct",
                "errors": {"7timer": str(exc)[:250]},
            }
        for stamp, row in seeing_rows.items():
            combined.setdefault(stamp, {})["seeing"] = row
        sources["seeing"] = seeing_source
    else:
        sources["seeing"] = {"available": False, "enabled": False}

    return combined, sources


def fetch_aerosols(options: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    local_options = dict(options)
    local_options["use_seeing"] = False
    return fetch_cams_aerosols(local_options)


def aerosol_quality(row: dict[str, Any] | None, options: dict[str, Any]) -> dict[str, Any]:
    row = row if isinstance(row, dict) else {}
    aod, dust = safe_float(row.get("aod550")), safe_float(row.get("dust_aod550"))
    aod = aod if aod is not None and aod >= 0 else None
    dust = dust if dust is not None and dust >= 0 else None
    dust_ugm3 = nonnegative_float(row.get("dust_ugm3"))
    enabled = options["use_aerosols"]
    stale = bool(row.get("stale"))
    applied = enabled and aod is not None and not stale
    fallback = enabled and not applied
    quality = "unknown"
    penalty = 0.0
    if not enabled:
        quality = "disabled"
    elif stale:
        quality = "stale"
    elif applied:
        warn, bad = options["aod_warn"], options["aod_bad"]
        quality = ("bad" if aod >= bad else "poor" if aod >= warn
                   else "excellent" if aod <= 0.10 else "good" if aod <= 0.20 else "reduced")
        if aod > 0.10:
            penalty = (25.0 * (aod - 0.10) / (warn - 0.10) if aod < warn
                       else min(70.0, 25.0 + 25.0 * (aod - warn) / (bad - warn)))
    return {"aod550": aod, "dustAod550": dust, "dustUgm3": dust_ugm3, "aerosolStatus": quality,
            "aerosolPenalty": penalty, "aerosolsAvailable": aod is not None,
            "aerosolsStale": stale, "aerosolsFetchedAt": row.get("fetched_at"),
            "aerosolApplied": applied, "aerosolFallback": fallback,
            "aerosolUncertain": applied and aod >= options["aod_warn"],
            "aerosolBad": applied and aod >= options["aod_bad"]}


def seeing_quality(row: dict[str, Any] | None, options: dict[str, Any]) -> dict[str, Any]:
    row = row if isinstance(row, dict) else {}
    seeing = safe_float(row.get("seeingArcsec"))
    index = row.get("seeingIndex")
    display = row.get("seeingDisplay")
    seeing = seeing if seeing is not None and seeing > 0 else None
    enabled = options["use_seeing"]
    stale = bool(row.get("stale"))
    applied = enabled and seeing is not None and not stale
    fallback = enabled and not applied
    quality = "unknown"
    penalty = 0.0
    if not enabled:
        quality = "disabled"
    elif stale:
        quality = "stale"
    elif applied:
        warn, bad = options["seeing_warn_arcsec"], options["seeing_bad_arcsec"]
        quality = "excellent" if seeing <= 1.0 else "good" if seeing < warn else "poor" if seeing < bad else "bad"
        if seeing > warn:
            penalty = min(45.0, 15.0 + 30.0 * (seeing - warn) / (bad - warn))
    return {
        "seeingArcsec": seeing,
        "seeingIndex": index if isinstance(index, int) else None,
        "seeingDisplay": str(display) if display not in (None, "") else None,
        "transparencyIndex": row.get("transparencyIndex") if isinstance(row.get("transparencyIndex"), int) else None,
        "seeingStatus": quality,
        "seeingPenalty": penalty,
        "seeingAvailable": seeing is not None,
        "seeingStale": stale,
        "seeingFetchedAt": row.get("fetched_at"),
        "seeingApplied": applied,
        "seeingFallback": fallback,
        "seeingUncertain": applied and seeing >= options["seeing_warn_arcsec"],
        "seeingBad": applied and seeing >= options["seeing_bad_arcsec"],
    }


# ---------------------------------------------------------------------------
# Observatory start decision (MET + ALADIN + internal Moon forecast)
# ---------------------------------------------------------------------------

def format_local_time(dt: datetime, options: dict[str, Any]) -> str:
    try:
        return dt.astimezone(ZoneInfo(options["timezone"])).strftime("%H:%M")
    except Exception:
        return dt.astimezone(timezone.utc).strftime("%H:%M")


def decision_settings(options: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "decision_nights",
        "min_good_block_hours",
        "max_start_delay_minutes",
        "prep_minutes",
        "good_score",
        "marginal_score",
        "disagreement_warn",
        "disagreement_bad",
        "wind_warn_ms",
        "wind_bad_ms",
        "use_moon",
        "moon_horizon_days",
        "moon_interference_illumination_pct",
        "moon_interference_altitude_deg",
        "use_aerosols",
        "use_seeing",
        "aerosol_refresh_minutes",
        "aod_warn",
        "aod_bad",
        "seeing_warn_arcsec",
        "seeing_bad_arcsec",
    )
    return {key: options[key] for key in keys}


def dew_penalty(margin: float | None) -> float:
    if margin is None:
        return 0.0
    if margin >= 5:
        return 0.0
    if margin >= 3:
        return (5 - margin) * 5
    if margin >= 2:
        return 10 + (3 - margin) * 10
    if margin >= 1:
        return 20 + (2 - margin) * 20
    return 50.0


def nearest_moon_hour(target: datetime, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_diff = float("inf")
    for row in rows:
        dt = parse_iso_utc(str(row.get("time", "")))
        if dt is None:
            continue
        diff = abs((dt - target).total_seconds())
        if diff < best_diff:
            best_diff = diff
            best = row
    return best if best_diff <= 45 * 60 else None


def score_hour(
    row: dict[str, Any],
    moon_hour: dict[str, Any] | None,
    night: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    met = row.get("met") if isinstance(row.get("met"), dict) else None
    aladin = row.get("aladin") if isinstance(row.get("aladin"), dict) else None

    mt = safe_float(met.get("cloud_total")) if met else None
    at = safe_float(aladin.get("cloud_total")) if aladin else None
    mh = safe_float(met.get("cloud_high")) if met else None
    ah = safe_float(aladin.get("cloud_high")) if aladin else None

    effective_cloud: float | None = None
    disagreement: float | None = None
    confidence = 0.0

    if mt is not None and at is not None:
        worst = max(mt, at)
        mean = (mt + at) / 2.0
        effective_cloud = 0.70 * worst + 0.30 * mean
        disagreement = abs(mt - at)
        confidence = max(25.0, min(100.0, 100.0 - disagreement * 1.05))
    elif mt is not None or at is not None:
        effective_cloud = mt if mt is not None else at
        confidence = 45.0

    high_values = [v for v in (mh, ah) if v is not None]
    if high_values and effective_cloud is not None:
        effective_cloud = max(effective_cloud, max(high_values) * 0.85)

    temp = safe_float(met.get("temperature")) if met else None
    dew = safe_float(met.get("dew_point")) if met else None
    dew_margin = temp - dew if temp is not None and dew is not None else None
    dew_p = dew_penalty(dew_margin)

    fog = safe_float(met.get("fog")) if met else None
    fog_p = 0.0 if fog is None else min(70.0, fog * 1.5)
    precip = safe_float(met.get("precipitation_1h")) if met else None
    wind = safe_float(met.get("wind_speed_ms")) if met else None
    wind_p = 0.0
    if wind is not None and wind > options["wind_warn_ms"]:
        wind_p = min(40.0, (wind - options["wind_warn_ms"]) * 10.0)

    cloud_score = 0.0 if effective_cloud is None else 100.0 - effective_cloud
    score = max(0.0, min(100.0, cloud_score - dew_p - fog_p - wind_p))
    aerosol = aerosol_quality(row.get("aerosols"), options)
    seeing = seeing_quality(row.get("seeing"), options)
    score = max(0.0, score - aerosol["aerosolPenalty"])
    score = max(0.0, score - seeing["seeingPenalty"])

    reasons: list[str] = []
    hard_bad = False
    moon_uncertain = False

    # Missing/stale aerosols are advisory only. For these hours the weather
    # score, confidence and all vetoes remain exactly as in version 7.
    if aerosol["aerosolApplied"]:
        if aerosol["aod550"] >= options["aod_warn"]:
            reasons.append(f"zákal: AOD 550 {aerosol['aod550']:.2f}")
        elif aerosol["aod550"] > 0.10:
            reasons.append(f"aerosoly: AOD 550 {aerosol['aod550']:.2f}")
        if aerosol["aerosolBad"]:
            hard_bad = True
            score = min(score, 20.0)

    # Missing/stale seeing is advisory only. With no fresh 7Timer
    # value, the hour keeps the v7/v9 weather decision.
    if seeing["seeingApplied"]:
        seeing_label = seeing["seeingDisplay"] or f"{seeing['seeingArcsec']:.2f}"
        if seeing["seeingArcsec"] >= options["seeing_warn_arcsec"]:
            reasons.append(f"seeing {seeing_label}\"")
        if seeing["seeingBad"]:
            hard_bad = True
            score = min(score, 35.0)

    if precip is not None and precip > 0:
        hard_bad = True
        score = 0.0
        reasons.append(f"srážky {precip:.1f} mm")
    if fog is not None and fog >= 20:
        hard_bad = True
        score = min(score, 15.0)
        reasons.append(f"mlha {fog:.0f} %")
    if wind is not None and wind >= options["wind_bad_ms"]:
        hard_bad = True
        score = min(score, 20.0)
        reasons.append(f"vítr {wind:.1f} m/s")

    moon_interferes = False
    if options["use_moon"]:
        if moon_hour is not None and isinstance(moon_hour.get("interferes"), bool):
            moon_interferes = bool(moon_hour["interferes"])
        elif night.get("status") == "nerusi":
            moon_interferes = False
        elif night.get("status") in {"rusi", "castecne"}:
            moon_uncertain = True

    if moon_interferes:
        hard_bad = True
        score = 0.0
        reasons.append("Měsíc")
    elif moon_uncertain:
        confidence = min(confidence, 45.0)
        reasons.append("Měsíc – chybí hodinový detail")

    if dew_margin is not None and dew_margin <= 3:
        reasons.append(f"opar/rosa ΔT {dew_margin:.1f} °C")
    if effective_cloud is not None and effective_cloud > 20:
        reasons.append(f"oblačnost {effective_cloud:.0f} %")

    strong_disagreement = (
        disagreement is not None
        and disagreement >= options["disagreement_bad"]
        and mt is not None
        and at is not None
        and min(mt, at) <= 30
        and max(mt, at) >= 60
    )
    if strong_disagreement:
        reasons.append(f"MET/ALADIN rozdíl {disagreement:.0f} p.b.")
    elif disagreement is not None and disagreement >= options["disagreement_warn"]:
        reasons.append(f"nejistota modelů {disagreement:.0f} p.b.")

    if hard_bad:
        status = "bad"
    elif (
        strong_disagreement
        or moon_uncertain
        or (aerosol["aerosolUncertain"] and score >= options["marginal_score"])
        or (seeing["seeingUncertain"] and score >= options["marginal_score"])
    ):
        status = "uncertain"
    elif score >= options["good_score"] and confidence >= 50:
        status = "good"
    elif score >= options["marginal_score"]:
        status = "partial"
    else:
        status = "bad"

    return {
        "status": status,
        "score": round(score, 1),
        "confidence": round(confidence, 1),
        "reasons": reasons,
        "metTotal": round_or_none(mt),
        "aladinTotal": round_or_none(at),
        "disagreement": round_or_none(disagreement),
        "effectiveCloud": round_or_none(effective_cloud),
        "dewMargin": round_or_none(dew_margin),
        "fog": round_or_none(fog),
        "precip": round_or_none(precip),
        "wind": round_or_none(wind),
        "moonInterferes": moon_interferes,
        "metAvailable": met is not None,
        "aladinAvailable": aladin is not None,
        **{key: value for key, value in aerosol.items() if key not in {"aerosolUncertain", "aerosolBad"}},
        **{key: value for key, value in seeing.items() if key not in {"seeingUncertain", "seeingBad"}},
    }


def public_block(block: dict[str, Any] | None) -> dict[str, Any] | None:
    if block is None:
        return None
    return {
        "start": iso_z(block["start"]),
        "end": iso_z(block["end"]),
        "hours": round(block["hours"], 2),
        "avgScore": round(block["avgScore"], 1),
        "avgConfidence": round(block["avgConfidence"], 1),
        "aodAvg": round_or_none(block.get("aodAvg"), 3),
        "aodMax": round_or_none(block.get("aodMax"), 3),
        "aerosolCoverage": round(block.get("aerosolCoverage", 0.0), 3),
        "seeingAvg": round_or_none(block.get("seeingAvg"), 2),
        "seeingMax": round_or_none(block.get("seeingMax"), 2),
        "seeingCoverage": round(block.get("seeingCoverage", 0.0), 3),
    }


def analyze_night(
    night: dict[str, Any],
    forecast: list[dict[str, Any]],
    moon_rows: list[dict[str, Any]],
    options: dict[str, Any],
) -> dict[str, Any] | None:
    dark_start = parse_iso_utc(str(night.get("astronomical_dark_start", "")))
    dark_end = parse_iso_utc(str(night.get("astronomical_dark_end", "")))
    if dark_start is None or dark_end is None or dark_end <= dark_start:
        return None

    hours: list[dict[str, Any]] = []
    for row in forecast:
        source_start = parse_iso_utc(str(row.get("datetime", "")))
        if source_start is None:
            continue
        source_end = source_start + timedelta(hours=1)
        overlap_start = max(source_start, dark_start)
        overlap_end = min(source_end, dark_end)
        if overlap_end <= overlap_start:
            continue

        moon_hour = nearest_moon_hour(source_start, moon_rows)
        q = score_hour(row, moon_hour, night, options)
        hours.append({
            "_start": overlap_start,
            "_end": overlap_end,
            "start": iso_z(overlap_start),
            "end": iso_z(overlap_end),
            "duration": round((overlap_end - overlap_start).total_seconds() / 3600.0, 3),
            "sourceStart": iso_z(source_start),
            **q,
        })

    if not hours:
        return {
            "night": night,
            "darkStart": iso_z(dark_start),
            "darkEnd": iso_z(dark_end),
            "hours": [],
            "blocks": [],
            "bestBlock": None,
            "launchBlock": None,
            "deadline": iso_z(dark_start + timedelta(minutes=options["max_start_delay_minutes"])),
            "decision": "unavailable",
            "label": "BEZ DAT",
            "reason": "Pro tuto noc není hodinová meteorologická předpověď.",
            "usableHours": 0.0,
            "uncertainHours": 0.0,
            "metAvg": None,
            "aladinAvg": None,
            "modelCoverage": 0.0,
            "aodAvg": None,
            "aodMax": None,
            "dustAodAvg": None,
            "dustAodMax": None,
            "dustUgm3Avg": None,
            "dustUgm3Max": None,
            "aerosolStatus": "disabled" if not options["use_aerosols"] else "unknown",
            "aerosolCoverage": 0.0,
            "aerosolMode": "disabled" if not options["use_aerosols"] else "fallback",
            "aerosolFallbackHours": 0.0,
            "aerosolWarning": None,
            "seeingAvg": None,
            "seeingMax": None,
            "seeingStatus": "disabled" if not options["use_seeing"] else "unknown",
            "seeingCoverage": 0.0,
            "seeingMode": "disabled" if not options["use_seeing"] else "fallback",
            "seeingFallbackHours": 0.0,
            "seeingWarning": None,
            "prepTime": None,
        }

    hours.sort(key=lambda h: h["_start"])

    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for h in hours:
        if h["status"] == "good":
            if current is None or h["_start"] > current["end"] + timedelta(minutes=5):
                current = {"start": h["_start"], "end": h["_end"], "rows": [h]}
                blocks.append(current)
            else:
                current["end"] = h["_end"]
                current["rows"].append(h)
        else:
            current = None

    for block in blocks:
        block["hours"] = (block["end"] - block["start"]).total_seconds() / 3600.0
        duration = sum(h["duration"] for h in block["rows"])
        aod_rows = [h for h in block["rows"] if h["aerosolApplied"]]
        aod_weight = sum(h["duration"] for h in aod_rows)
        seeing_rows = [h for h in block["rows"] if h["seeingApplied"]]
        seeing_weight = sum(h["duration"] for h in seeing_rows)
        block["aerosolCoverage"] = aod_weight / duration if duration else 0.0
        block["aodAvg"] = sum(h["aod550"] * h["duration"] for h in aod_rows) / aod_weight if aod_weight else None
        block["aodMax"] = max((h["aod550"] for h in aod_rows), default=None)
        block["seeingCoverage"] = seeing_weight / duration if duration else 0.0
        block["seeingAvg"] = sum(h["seeingArcsec"] * h["duration"] for h in seeing_rows) / seeing_weight if seeing_weight else None
        block["seeingMax"] = max((h["seeingArcsec"] for h in seeing_rows), default=None)
        if duration > 0:
            block["avgScore"] = sum(h["score"] * h["duration"] for h in block["rows"]) / duration
            block["avgConfidence"] = sum(h["confidence"] * h["duration"] for h in block["rows"]) / duration
        else:
            block["avgScore"] = 0.0
            block["avgConfidence"] = 0.0

    best_block = max(blocks, key=lambda b: b["hours"], default=None)
    deadline = dark_start + timedelta(minutes=options["max_start_delay_minutes"])
    early_blocks = [b for b in blocks if b["start"] <= deadline]
    launch_block = max(early_blocks, key=lambda b: b["hours"], default=None)

    usable_hours = sum(h["duration"] for h in hours if h["status"] in {"good", "partial"})
    uncertain_hours = sum(h["duration"] for h in hours if h["status"] == "uncertain")

    # Zobrazovane nocni prumery pocitame casove vazene podle skutecneho prekryvu
    # hodinove predpovedi s astronomickou noci. Prvni/posledni castecna hodina tak
    # nema stejnou vahu jako cela hodina.
    def weighted_hour_average(field: str) -> float | None:
        weighted_sum = 0.0
        weight_sum = 0.0
        for hour in hours:
            if field in {"aod550", "dustAod550", "dustUgm3"} and not hour["aerosolApplied"]:
                continue
            if field == "seeingArcsec" and not hour["seeingApplied"]:
                continue
            value = safe_float(hour.get(field))
            duration = safe_float(hour.get("duration"))
            if value is None or duration is None or duration <= 0:
                continue
            weighted_sum += value * duration
            weight_sum += duration
        return weighted_sum / weight_sum if weight_sum > 0 else None

    met_avg = weighted_hour_average("metTotal")
    aladin_avg = weighted_hour_average("aladinTotal")
    effective_cloud_avg = weighted_hour_average("effectiveCloud")

    both_model_hours = sum(
        h["duration"] for h in hours if h["metAvailable"] and h["aladinAvailable"]
    )
    covered_hours = sum(h["duration"] for h in hours)
    model_coverage = both_model_hours / covered_hours if covered_hours > 0 else 0.0
    aod_avg = weighted_hour_average("aod550")
    dust_avg = weighted_hour_average("dustAod550")
    dust_ugm3_avg = weighted_hour_average("dustUgm3")
    aod_max = max((h["aod550"] for h in hours if h["aerosolApplied"]), default=None)
    dust_max = max((h["dustAod550"] for h in hours if h["aerosolApplied"] and h["dustAod550"] is not None), default=None)
    dust_ugm3_max = max((h["dustUgm3"] for h in hours if h["aerosolApplied"] and h["dustUgm3"] is not None), default=None)
    fresh_aerosol_hours = sum(h["duration"] for h in hours if h["aerosolApplied"])
    aerosol_coverage = fresh_aerosol_hours / covered_hours if covered_hours else 0.0
    aerosol_summary = aerosol_quality({"aod550": aod_max}, options)["aerosolStatus"]
    aerosol_fallback_hours = sum(h["duration"] for h in hours if h["aerosolFallback"])
    aerosol_mode = ("disabled" if not options["use_aerosols"] else "fallback" if fresh_aerosol_hours == 0
                    else "partial" if aerosol_fallback_hours > 0 else "full")
    aerosol_warning = None
    if aerosol_mode == "fallback":
        aerosol_warning = "Aerosoly nedostupné nebo neobnovené – rozhodnutí podle MET, ALADINu a nastavení Měsíce jako ve v7; průzračnost neověřena."
    elif aerosol_mode == "partial":
        aerosol_warning = f"Pro {aerosol_fallback_hours:.1f} h chybí obnovená data aerosolů – tyto hodiny jsou hodnocené jako ve v7, bez ověření průzračnosti."

    seeing_avg = weighted_hour_average("seeingArcsec")
    seeing_max = max((h["seeingArcsec"] for h in hours if h["seeingApplied"]), default=None)
    fresh_seeing_hours = sum(h["duration"] for h in hours if h["seeingApplied"])
    seeing_coverage = fresh_seeing_hours / covered_hours if covered_hours else 0.0
    seeing_summary = seeing_quality({"seeingArcsec": seeing_max}, options)["seeingStatus"]
    seeing_fallback_hours = sum(h["duration"] for h in hours if h["seeingFallback"])
    seeing_mode = ("disabled" if not options["use_seeing"] else "fallback" if fresh_seeing_hours == 0
                   else "partial" if seeing_fallback_hours > 0 else "full")
    seeing_warning = None
    if seeing_mode == "fallback":
        seeing_warning = "Seeing nedostupný nebo neobnovený – rozhodnutí zůstává podle MET, ALADINu, Měsíce a AOD; seeing se nezapočítal."
    elif seeing_mode == "partial":
        seeing_warning = f"Pro {seeing_fallback_hours:.1f} h chybí obnovený seeing – tyto hodiny jsou hodnocené bez korekce seeingu."

    decision = "bad"
    label = "NESPOUŠTĚT"
    reason = "Není dostatečně dlouhé kvalitní okno na začátku noci."
    min_block = options["min_good_block_hours"]

    if launch_block is not None and launch_block["hours"] >= min_block:
        if launch_block["avgConfidence"] >= 60 and model_coverage >= 0.5:
            decision = "good"
            label = "SPUSTIT"
            reason = f"Kvalitní blok začíná včas a má {launch_block['hours']:.1f} h."
        else:
            decision = "uncertain"
            label = "NEJISTÉ"
            reason = "Okno je dost dlouhé, ale jistota modelů nebo datové pokrytí není dostatečné."
    elif best_block is not None and best_block["hours"] >= min_block and best_block["start"] > deadline:
        decision = "bad"
        label = "NESPOUŠTĚT"
        reason = f"Dobré podmínky mají přijít až od {format_local_time(best_block['start'], options)}."
    elif (
        (launch_block is not None and launch_block["hours"] >= min_block * 0.70)
        or usable_hours >= min_block
        or uncertain_hours >= 1.5
    ):
        decision = "uncertain"
        label = "NEJISTÉ"
        reason = "Část noci může být použitelná, ale podmínky nejsou dost stabilní pro jisté spuštění."

    if options["use_aerosols"] and decision != "good":
        bad_aod_hours = sum(h["duration"] for h in hours if h["aerosolApplied"] and h["aod550"] >= options["aod_bad"])
        warn_aod_hours = sum(h["duration"] for h in hours if h["aerosolApplied"] and h["aod550"] >= options["aod_warn"])
        if bad_aod_hours > 0:
            reason += f" Silný zákal (AOD ≥ {options['aod_bad']:.2f}) vyřazuje {bad_aod_hours:.1f} h."
        elif warn_aod_hours > 0:
            reason += f" Zvýšený zákal (AOD ≥ {options['aod_warn']:.2f}) znejisťuje {warn_aod_hours:.1f} h."
    if options["use_seeing"] and decision != "good":
        bad_seeing_hours = sum(h["duration"] for h in hours if h["seeingApplied"] and h["seeingArcsec"] >= options["seeing_bad_arcsec"])
        warn_seeing_hours = sum(h["duration"] for h in hours if h["seeingApplied"] and h["seeingArcsec"] >= options["seeing_warn_arcsec"])
        if bad_seeing_hours > 0:
            reason += f" Špatný seeing (≥ {options['seeing_bad_arcsec']:.1f}\") vyřazuje {bad_seeing_hours:.1f} h."
        elif warn_seeing_hours > 0:
            reason += f" Horší seeing (≥ {options['seeing_warn_arcsec']:.1f}\") znejisťuje {warn_seeing_hours:.1f} h."
    if aerosol_warning:
        reason += " " + aerosol_warning
    if seeing_warning:
        reason += " " + seeing_warning

    selected_block = launch_block or best_block
    prep_time = (
        selected_block["start"] - timedelta(minutes=options["prep_minutes"])
        if selected_block is not None
        else None
    )

    public_hours = [
        {key: value for key, value in h.items() if not key.startswith("_")}
        for h in hours
    ]
    public_blocks = [public_block(block) for block in blocks]

    return {
        "night": night,
        "darkStart": iso_z(dark_start),
        "darkEnd": iso_z(dark_end),
        "hours": public_hours,
        "blocks": public_blocks,
        "bestBlock": public_block(best_block),
        "launchBlock": public_block(launch_block),
        "deadline": iso_z(deadline),
        "usableHours": round(usable_hours, 2),
        "uncertainHours": round(uncertain_hours, 2),
        "decision": decision,
        "label": label,
        "reason": reason,
        "prepTime": iso_z(prep_time) if prep_time is not None else None,
        "metAvg": round_or_none(met_avg),
        "aladinAvg": round_or_none(aladin_avg),
        "effectiveCloudAvg": round_or_none(effective_cloud_avg),
        "modelCoverage": round(model_coverage, 3),
        "aodAvg": round_or_none(aod_avg, 3),
        "aodMax": round_or_none(aod_max, 3),
        "dustAodAvg": round_or_none(dust_avg, 3),
        "dustAodMax": round_or_none(dust_max, 3),
        "dustUgm3Avg": round_or_none(dust_ugm3_avg, 1),
        "dustUgm3Max": round_or_none(dust_ugm3_max, 1),
        "aerosolStatus": aerosol_summary,
        "aerosolCoverage": round(aerosol_coverage, 3),
        "aerosolMode": aerosol_mode,
        "aerosolFallbackHours": round(aerosol_fallback_hours, 2),
        "aerosolWarning": aerosol_warning,
        "seeingAvg": round_or_none(seeing_avg, 2),
        "seeingMax": round_or_none(seeing_max, 2),
        "seeingStatus": seeing_summary,
        "seeingCoverage": round(seeing_coverage, 3),
        "seeingMode": seeing_mode,
        "seeingFallbackHours": round(seeing_fallback_hours, 2),
        "seeingWarning": seeing_warning,
    }


def unavailable_decision(
    reason: str,
    options: dict[str, Any],
    weather_state: str,
) -> dict[str, Any]:
    return {
        "state": "BEZ DAT",
        "machine_state": "unavailable",
        "generated_at": iso_z(utc_now()),
        "backend_version": APP_VERSION,
        "reason": reason,
        "weather_state": weather_state,
        "moon_entity": options["moon_entity"],
        "settings": decision_settings(options),
        "daily": [],
        "error": reason,
    }


def build_decision(
    forecast: list[dict[str, Any]],
    moon_doc: dict[str, Any],
    options: dict[str, Any],
    weather_state: str,
) -> dict[str, Any]:
    attrs = moon_doc.get("attributes") if isinstance(moon_doc.get("attributes"), dict) else {}
    daily = attrs.get("daily") if isinstance(attrs.get("daily"), list) else []
    hourly = attrs.get("hourly") if isinstance(attrs.get("hourly"), list) else []

    now = utc_now()
    upcoming: list[dict[str, Any]] = []
    for night in daily:
        if not isinstance(night, dict):
            continue
        end = parse_iso_utc(str(night.get("astronomical_dark_end", "")))
        if end is not None and end > now:
            upcoming.append(night)
        if len(upcoming) >= options["decision_nights"]:
            break

    if not upcoming:
        return unavailable_decision(
            "Interní měsíční data neobsahují žádnou budoucí astronomickou noc.",
            options,
            weather_state,
        )

    analyses: list[dict[str, Any]] = []
    for night in upcoming:
        result = analyze_night(night, forecast, hourly, options)
        if result is not None:
            analyses.append(result)

    if not analyses:
        return unavailable_decision(
            "Budoucí noci nelze vyhodnotit kvůli chybějícím nebo neplatným datumům.",
            options,
            weather_state,
        )

    first = analyses[0]
    return {
        "state": first["label"],
        "machine_state": first["decision"],
        "generated_at": iso_z(utc_now()),
        "backend_version": APP_VERSION,
        "reason": first["reason"],
        "weather_state": weather_state,
        "moon_entity": options["moon_entity"],
        "moon_state": moon_doc.get("state"),
        "moon_last_updated": moon_doc.get("last_updated"),
        "settings": decision_settings(options),
        "daily": analyses,
        "error": None,
    }


def merge_sources(
    met: dict[str, dict[str, Any]],
    aladin: dict[str, dict[str, Any]],
    horizon_hours: int,
    sky_quality: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    now = utc_now()
    start = now - timedelta(hours=1)
    end = now + timedelta(hours=horizon_hours)
    stamps = sorted(set(met) | set(aladin))
    output: list[dict[str, Any]] = []

    for stamp in stamps:
        dt = parse_iso_utc(stamp)
        if dt is None or dt < start or dt > end:
            continue
        quality = (sky_quality or {}).get(iso_z(dt))
        quality = quality if isinstance(quality, dict) else {}
        output.append({
            "datetime": iso_z(dt),
            "met": met.get(stamp),
            "aladin": aladin.get(stamp),
            "aerosols": quality.get("aerosols"),
            "seeing": quality.get("seeing"),
        })
    return output


def refresh_once(options: dict[str, Any]) -> None:
    log("Obnovuji astro meteo data...")
    met_data: dict[str, dict[str, Any]] = {}
    aladin_data: dict[str, dict[str, Any]] = {}
    sky_quality_data: dict[str, dict[str, Any]] = {}
    sources: dict[str, Any] = {}
    errors: dict[str, Any] = {"met": None, "aladin": None, "moon": None, "aerosols": None, "seeing": None}

    try:
        met_data, sources["met"] = fetch_met(options)
        log(f"MET: {len(met_data)} hodin")
    except Exception as exc:
        errors["met"] = str(exc)
        sources["met"] = {"available": False}
        log(f"MET CHYBA: {exc}")
        if options["debug"]:
            traceback.print_exc()

    try:
        aladin_data, sources["aladin"] = fetch_aladin(options)
        log(f"ALADIN: {len(aladin_data)} hodin, run {sources['aladin'].get('run')}")
    except Exception as exc:
        errors["aladin"] = str(exc)
        sources["aladin"] = {"available": False}
        log(f"ALADIN CHYBA: {exc}")
        if options["debug"]:
            traceback.print_exc()

    if options["use_aerosols"] or options["use_seeing"]:
        try:
            sky_quality_data, sky_sources = fetch_sky_quality(options)
            sources["aerosols"] = sky_sources["aerosols"]
            sources["seeing"] = sky_sources["seeing"]
            errors["aerosols"] = sources["aerosols"].get("errors") or None
            errors["seeing"] = sources["seeing"].get("errors") or None
            aerosol_hours = sum(1 for row in sky_quality_data.values() if isinstance(row.get("aerosols"), dict))
            seeing_hours = sum(1 for row in sky_quality_data.values() if isinstance(row.get("seeing"), dict))
            log(f"KVALITA OBLOHY: {aerosol_hours} hodin CAMS/Open-Meteo AOD, {seeing_hours} hodin 7Timer seeing")
            if errors["aerosols"]:
                log(f"AEROSOLY VAROVANI: {errors['aerosols']}")
            if errors["seeing"]:
                log(f"SEEING VAROVANI: {errors['seeing']}")
        except Exception as exc:
            if options["use_aerosols"]:
                errors["aerosols"] = str(exc)
                sources["aerosols"] = {"available": False, "enabled": True, "provider": "CAMS through Open-Meteo Air Quality API"}
            else:
                sources["aerosols"] = {"available": False, "enabled": False}
            if options["use_seeing"]:
                errors["seeing"] = str(exc)
                sources["seeing"] = {"available": False, "enabled": True, "provider": "7Timer ASTRO direct"}
            else:
                sources["seeing"] = {"available": False, "enabled": False}
            log(f"KVALITA OBLOHY CHYBA: {exc}")
    else:
        sources["aerosols"] = {"available": False, "enabled": False}
        sources["seeing"] = {"available": False, "enabled": False}

    if not options["use_aerosols"]:
        sources["aerosols"] = {"available": False, "enabled": False}
        errors["aerosols"] = None
    if not options["use_seeing"]:
        sources["seeing"] = {"available": False, "enabled": False}
        errors["seeing"] = None

    available_count = int(bool(met_data)) + int(bool(aladin_data))
    state = "ok" if available_count == 2 else "partial" if available_count == 1 else "error"
    forecast = merge_sources(met_data, aladin_data, options["horizon_hours"], sky_quality_data)

    moon_doc: dict[str, Any] | None = None
    try:
        moon_doc = build_internal_moon_document(options)
        attrs = moon_doc.get("attributes") if isinstance(moon_doc.get("attributes"), dict) else {}
        sources["moon"] = {
            "available": True,
            "provider": "Astro Weather Backend internal Moon",
            "entity_id": options["moon_entity"],
            "state": moon_doc.get("state"),
            "last_updated": moon_doc.get("last_updated"),
            "daily": len(attrs.get("daily") or []) if isinstance(attrs.get("daily"), list) else 0,
            "hourly": len(attrs.get("hourly") or []) if isinstance(attrs.get("hourly"), list) else 0,
            "illumination_threshold_pct": options["moon_interference_illumination_pct"],
            "altitude_threshold_deg": options["moon_interference_altitude_deg"],
        }
        log(
            f"MESIC INTERNI: {sources['moon']['daily']} noci, "
            f"{sources['moon']['hourly']} hodin, publikuji {options['moon_entity']}"
        )
    except Exception as exc:
        errors["moon"] = str(exc)
        sources["moon"] = {
            "available": False,
            "provider": "Astro Weather Backend internal Moon",
            "entity_id": options["moon_entity"],
        }
        log(f"MESIC CHYBA: {exc}")
        if options["debug"]:
            traceback.print_exc()

    if moon_doc is not None:
        try:
            decision = build_decision(forecast, moon_doc, options, state)
        except Exception as exc:
            log(f"ROZHODNUTI CHYBA: {exc}")
            if options["debug"]:
                traceback.print_exc()
            decision = unavailable_decision(f"Chyba vypoctu rozhodnuti: {exc}", options, state)
    else:
        decision = unavailable_decision(
            f"Nelze vypocitat interni Mesic: {errors['moon']}",
            options,
            state,
        )

    new_state = {
        "state": state,
        "generated_at": iso_z(utc_now()),
        "backend_version": APP_VERSION,
        "location": {
            "latitude": options["latitude"],
            "longitude": options["longitude"],
            "altitude": options["altitude"],
            "timezone": options["timezone"],
        },
        "sources": sources,
        "errors": errors,
        "forecast": forecast,
        "decision_summary": {
            "state": decision.get("state"),
            "machine_state": decision.get("machine_state"),
            "reason": decision.get("reason"),
        },
    }

    with STATE_LOCK:
        STATE.clear()
        STATE.update(new_state)
        DECISION_STATE.clear()
        DECISION_STATE.update(decision)

    if moon_doc is not None:
        try:
            publish_homeassistant_entities(options, new_state, decision, moon_doc)
            if options["publish_homeassistant_entities"]:
                log(
                    "HA ENTITY: publikovano "
                    f"{options['weather_entity']}, {options['decision_entity']}, {options['moon_entity']}"
                )
        except Exception as exc:
            log(f"HA ENTITY CHYBA: {exc}")
            if options["debug"]:
                traceback.print_exc()

    log(
        f"Hotovo: state={state}, forecast={len(forecast)} hodin, "
        f"rozhodnuti={decision.get('state')}"
    )


def refresh_worker(options: dict[str, Any]) -> None:
    while True:
        started = time.monotonic()
        try:
            refresh_once(options)
        except Exception as exc:
            log(f"NEOCEKAVANA CHYBA refresh: {exc}")
            traceback.print_exc()
        elapsed = time.monotonic() - started
        sleep_for = max(30.0, options["refresh_minutes"] * 60.0 - elapsed)
        time.sleep(sleep_for)


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------

def filtered_state(hours: int | None = None) -> dict[str, Any]:
    with STATE_LOCK:
        payload = json.loads(json.dumps(STATE, ensure_ascii=False))

    if hours is not None and isinstance(payload.get("forecast"), list):
        now = utc_now()
        end = now + timedelta(hours=max(1, min(120, hours)))
        payload["forecast"] = [
            row for row in payload["forecast"]
            if (dt := parse_iso_utc(str(row.get("datetime", "")))) is not None and dt <= end
        ]
    return payload


def filtered_decision() -> dict[str, Any]:
    with STATE_LOCK:
        return json.loads(json.dumps(DECISION_STATE, ensure_ascii=False))


class Handler(BaseHTTPRequestHandler):
    server_version = f"AstroWeatherBackend/{APP_VERSION}"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep normal request logging quiet; backend refresh logs are enough.
        return

    def send_json(self, obj: Any, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/health":
            with STATE_LOCK:
                self.send_json({
                    "state": STATE.get("state"),
                    "generated_at": STATE.get("generated_at"),
                    "backend_version": APP_VERSION,
                    "decision": DECISION_STATE.get("state"),
                    "decision_machine_state": DECISION_STATE.get("machine_state"),
                })
            return

        if parsed.path == "/forecast":
            hours: int | None = None
            try:
                if "hours" in query:
                    hours = int(query["hours"][0])
            except Exception:
                hours = None
            self.send_json(filtered_state(hours))
            return

        if parsed.path == "/decision":
            self.send_json(filtered_decision())
            return

        self.send_json({"error": "not_found"}, status=404)


def main() -> None:
    options = load_options()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    log(f"Astro Weather Backend {APP_VERSION}")
    install_dashboard_cards(options)
    ensure_lovelace_resources(options)
    log(
        f"Lokalita {options['latitude']:.4f}, {options['longitude']:.4f}, "
        f"{options['altitude']} m; refresh {options['refresh_minutes']} min"
    )
    log(
        f"Rozhodovani: min blok {options['min_good_block_hours']:.1f} h, "
        f"start do {options['max_start_delay_minutes']} min od astronomicke tmy, "
        f"priprava {options['prep_minutes']} min, Mesic={'ano' if options['use_moon'] else 'ne'}"
    )

    worker = threading.Thread(target=refresh_worker, args=(options,), daemon=True)
    worker.start()

    server = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), Handler)
    log(f"HTTP API posloucha na 0.0.0.0:{HTTP_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
