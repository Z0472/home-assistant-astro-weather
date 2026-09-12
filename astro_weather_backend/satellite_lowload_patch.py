"""Low-load satellite bootstrap guard for Astro Weather Backend 12.4.1.

Prevents the first credentialed EUMETSAT cycle from trying to process every
recent CLM frame at once on small Home Assistant hardware. At most one uncached
satellite product is admitted per refresh cycle; already cached products remain
available for trend/edge calculations. The satellite worker also waits 60 s
after app start so Home Assistant can finish its own startup first.
"""
from __future__ import annotations

import time
from typing import Any

import satellite_nowcast_patch as sat
import storage_protection_patch as storage
import satellite_card_map_patch as clm_map

RELEASE_VERSION = "12.4.1"
INITIAL_SATELLITE_DELAY_SECONDS = 60


def _select_cached_plus_one(core: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        cache = sat._load_sample_cache(core)
    except Exception:
        cache = []
    cached_ids = {
        str(row.get("product_id"))
        for row in cache
        if isinstance(row, dict) and row.get("product_id")
    }

    selected: list[dict[str, Any]] = []
    admitted_uncached = False
    for row in rows:
        product_id = str(row.get("product_id") or "")
        if not product_id:
            continue
        if product_id in cached_ids:
            selected.append(row)
        elif not admitted_uncached:
            selected.append(row)
            admitted_uncached = True
    return selected


def install(core: Any) -> None:
    if getattr(core, "_SATELLITE_LOWLOAD_PATCH_INSTALLED", False):
        return

    old_search = sat._search_recent_products

    def search_recent_products(core_arg: Any) -> list[dict[str, Any]]:
        rows = old_search(core_arg)
        selected = _select_cached_plus_one(core_arg, rows)
        missing = sum(
            1 for row in selected
            if str(row.get("product_id") or "") not in {
                str(item.get("product_id")) for item in sat._load_sample_cache(core_arg)
                if isinstance(item, dict) and item.get("product_id")
            }
        )
        if missing:
            core_arg.log("SATELIT LOW-LOAD: tento cyklus zpracuje maximalne 1 novy CLM snimek.")
        return selected

    def satellite_worker(core_arg: Any, options: dict[str, Any]) -> None:
        core_arg.log(
            f"SATELIT LOW-LOAD: start odlozen o {INITIAL_SATELLITE_DELAY_SECONDS} s kvuli setrnemu startu HA."
        )
        time.sleep(INITIAL_SATELLITE_DELAY_SECONDS)
        while True:
            started = time.monotonic()
            try:
                sat._update_satellite(core_arg, options)
            except Exception as exc:
                core_arg.log(f"SATELIT NECEKANA CHYBA: {exc}")
            elapsed = time.monotonic() - started
            interval = max(600.0, float(options["satellite_refresh_minutes"]) * 60.0)
            time.sleep(max(30.0, interval - elapsed))

    sat._search_recent_products = search_recent_products
    sat._satellite_worker = satellite_worker
    sat.RELEASE_VERSION = RELEASE_VERSION
    storage.RELEASE_VERSION = RELEASE_VERSION
    clm_map.RELEASE_VERSION = RELEASE_VERSION
    core.APP_VERSION = RELEASE_VERSION
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._SATELLITE_LOWLOAD_PATCH_INSTALLED = True
