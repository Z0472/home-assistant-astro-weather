"""Astro Weather 12.2.1 confidence display and boundary consistency patch."""
from __future__ import annotations

from typing import Any

import cloud_consensus as cc

RELEASE_VERSION = "12.2.1"
ASTRO_CARD_VERSION = 24
MOON_CARD_VERSION = 24


def install(core: Any) -> None:
    if getattr(core, "_CONFIDENCE_PATCH_INSTALLED", False):
        return

    old_load_options = core.load_options
    old_analyze_night = core.analyze_night
    old_consensus = cc.cloud_consensus

    def fixed_consensus(values: dict[str, Any], warn: float = 35.0, bad: float = 55.0) -> dict[str, Any]:
        result = old_consensus(values, warn, bad)
        spread = result.get("spread")
        # In 12.2.0 exactly spread == warn could be marked both good and outlier.
        # Outlier classification must win on the warning boundary.
        if (
            result.get("model_count", 0) >= 3
            and result.get("outlier")
            and isinstance(spread, (int, float))
            and spread >= warn
            and result.get("agreement") == "good"
        ):
            result["agreement"] = "outlier"
            result["confidence"] = max(50.0, min(75.0, 75.0 - 0.35 * float(spread)))
        return result

    def load_options() -> dict[str, Any]:
        options = old_load_options()
        agent = str(options.get("met_user_agent", "")).strip()
        if not agent or agent.startswith("AstroWeatherBackend/"):
            options["met_user_agent"] = (
                f"AstroWeatherBackend/{RELEASE_VERSION} "
                "https://github.com/Z0472/home-assistant-astro-weather"
            )
        return options

    def analyze_night(night: dict[str, Any], forecast: list[dict[str, Any]],
                      moon_rows: list[dict[str, Any]], options: dict[str, Any]) -> dict[str, Any] | None:
        result = old_analyze_night(night, forecast, moon_rows, options)
        if result is None:
            return None
        hours = result.get("hours") if isinstance(result.get("hours"), list) else []

        def weighted(field: str) -> float | None:
            total = 0.0
            weight = 0.0
            for hour in hours:
                value = core.safe_float(hour.get(field))
                duration = core.safe_float(hour.get("duration"))
                if value is None or duration is None or duration <= 0:
                    continue
                total += value * duration
                weight += duration
            return total / weight if weight else None

        result["scoreAvg"] = core.round_or_none(weighted("score"), 1)
        result["confidenceAvg"] = core.round_or_none(weighted("confidence"), 1)
        return result

    cc.cloud_consensus = fixed_consensus
    core.cloud_consensus = fixed_consensus
    core.load_options = load_options
    core.analyze_night = analyze_night

    core.APP_VERSION = RELEASE_VERSION
    core.ASTRO_START_CARD_VERSION = ASTRO_CARD_VERSION
    core.MOON_FORECAST_CARD_VERSION = MOON_CARD_VERSION
    core.DASHBOARD_CARD_INSTALLS = (
        ("astro-start-card.js", "astro-start-card-base-v22.js"),
        ("astro-start-card-v23.js", "astro-start-card-v23.js"),
        ("astro-start-card-v24.js", f"astro-start-card-v{ASTRO_CARD_VERSION}.js"),
        ("moon-forecast-card.js", "moon-forecast-card-v23.js"),
        ("moon-forecast-card-v24.js", f"moon-forecast-card-v{MOON_CARD_VERSION}.js"),
    )
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._CONFIDENCE_PATCH_INSTALLED = True
