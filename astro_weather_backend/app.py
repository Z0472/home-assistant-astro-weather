#!/usr/bin/env python3
"""Astro Weather Backend 12.3.2 entrypoint."""
import astro_weather_backend as core
import model_runtime
import confidence_patch
import night_forecast_patch
import spatial_cloud_patch
import spatial_timeline_patch
import twilight_patch
import state_cache_patch

model_runtime.install(core)
confidence_patch.install(core)
night_forecast_patch.install(core)
spatial_cloud_patch.install(core)
spatial_timeline_patch.install(core)
twilight_patch.install(core)
state_cache_patch.install(core)

if __name__ == "__main__":
    core.main()
