#!/usr/bin/env python3
"""Astro Weather Backend 12.2.2 entrypoint."""
import astro_weather_backend as core
import model_runtime
import confidence_patch
import night_forecast_patch

model_runtime.install(core)
confidence_patch.install(core)
night_forecast_patch.install(core)

if __name__ == "__main__":
    core.main()
