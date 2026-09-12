#!/usr/bin/env python3
"""Astro Weather Backend 12.4.0 entrypoint."""
import astro_weather_backend as core
import model_runtime
import confidence_patch
import night_forecast_patch
import spatial_cloud_patch
import spatial_timeline_patch
import twilight_patch
import state_cache_patch
import entity_watchdog_patch
import edge_consistency_patch
import satellite_nowcast_patch
import storage_protection_patch
import satellite_card_map_patch

model_runtime.install(core)
confidence_patch.install(core)
night_forecast_patch.install(core)
spatial_cloud_patch.install(core)
spatial_timeline_patch.install(core)
twilight_patch.install(core)
state_cache_patch.install(core)
entity_watchdog_patch.install(core)
edge_consistency_patch.install(core)
satellite_nowcast_patch.install(core)
storage_protection_patch.install(core)
satellite_card_map_patch.install(core)

if __name__ == "__main__":
    core.main()
