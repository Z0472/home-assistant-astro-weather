#!/usr/bin/env python3
"""Astro Weather Backend 12.2 entrypoint."""
import astro_weather_backend as core
import model_runtime

model_runtime.install(core)

if __name__ == "__main__":
    core.main()
