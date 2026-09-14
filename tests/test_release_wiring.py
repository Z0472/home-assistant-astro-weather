"""Release-level wiring checks for Home Assistant Astro Weather 12.4.17."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))
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
import satellite_lowload_patch
import satellite_index_sampler_patch
import satellite_ui_patch
import satellite_lowmem_patch
import satellite_group_patch


class ReleaseWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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
        satellite_lowload_patch.install(core)
        satellite_index_sampler_patch.install(core)
        satellite_ui_patch.install(core)
        satellite_lowmem_patch.install(core)
        satellite_group_patch.install(core)

    def test_release_config_and_docker_entrypoint(self):
        config = (ROOT / "astro_weather_backend/config.yaml").read_text(encoding="utf-8")
        docker = (ROOT / "astro_weather_backend/Dockerfile").read_text(encoding="utf-8")
        app = (ROOT / "astro_weather_backend/app.py").read_text(encoding="utf-8")
        readme = (ROOT / "astro_weather_backend/README.md").read_text(encoding="utf-8")
        docs = (ROOT / "astro_weather_backend/DOCS.md").read_text(encoding="utf-8")
        self.assertIn('version: "12.4.17"', config)
        self.assertIn("Plánování astrofotografie", config)
        self.assertIn("use_icon: true", config)
        self.assertIn("spatial_cloud_analysis: true", config)
        self.assertIn("use_satellite: true", config)
        self.assertIn("satellite_radius_km: 30", config)
        self.assertIn("satellite_refresh_minutes: 10", config)
        self.assertIn("eumetsat_consumer_secret: password", config)
        self.assertIn("API Key Management", readme)
        self.assertIn("Consumer key", docs)
        self.assertIn("Použijte skutečnou polohu", docs)
        self.assertIn("COPY entity_watchdog_patch.py", docker)
        self.assertIn("COPY satellite_nowcast_patch.py", docker)
        self.assertIn("COPY storage_protection_patch.py", docker)
        self.assertIn("COPY satellite_card_map_patch.py", docker)
        self.assertIn("COPY satellite_lowload_patch.py", docker)
        self.assertIn("COPY satellite_index_sampler_patch.py", docker)
        self.assertIn("COPY satellite_ui_patch.py", docker)
        self.assertIn("COPY satellite_lowmem_patch.py", docker)
        self.assertIn("COPY satellite_group_patch.py", docker)
        self.assertIn("entity_watchdog_patch.install(core)", app)
        self.assertIn("satellite_nowcast_patch.install(core)", app)
        self.assertIn("storage_protection_patch.install(core)", app)
        self.assertIn("satellite_card_map_patch.install(core)", app)
        self.assertIn("satellite_lowload_patch.install(core)", app)
        self.assertIn("satellite_index_sampler_patch.install(core)", app)
        self.assertIn("satellite_ui_patch.install(core)", app)
        self.assertIn("satellite_lowmem_patch.install(core)", app)
        self.assertIn("satellite_group_patch.install(core)", app)
        self.assertIn('CMD ["python3", "-u", "/app/app.py"]', docker)
        self.assertEqual(core.APP_VERSION, "12.4.17")
        self.assertEqual(core.ASTRO_START_CARD_VERSION, 35)
        self.assertEqual(satellite_nowcast_patch.SATELLITE_CARD_VERSION, 9)
        self.assertTrue(getattr(core, "_STORAGE_PROTECTION_PATCH_INSTALLED", False))
        self.assertTrue(getattr(core, "_SATELLITE_CARD_MAP_PATCH_INSTALLED", False))
        self.assertTrue(getattr(core, "_SATELLITE_LOWLOAD_PATCH_INSTALLED", False))
        self.assertTrue(getattr(core, "_SATELLITE_INDEX_SAMPLER_PATCH_INSTALLED", False))
        self.assertTrue(getattr(core, "_SATELLITE_UI_PATCH_INSTALLED", False))
        self.assertTrue(getattr(core, "_SATELLITE_LOWMEM_PATCH_INSTALLED", False))
        self.assertTrue(getattr(core, "_SATELLITE_GROUP_PATCH_INSTALLED", False))
        self.assertIs(satellite_nowcast_patch._sample_product, satellite_lowmem_patch._sample_product)

    def test_v35_and_satellite_card_v9_install_is_self_contained(self):
        source = ROOT / "astro_weather_backend/cards"
        with tempfile.TemporaryDirectory() as config_dir:
            target = Path(config_dir) / "www"
            target.mkdir()
            target.joinpath("astro-start-card-v29.js").write_text("old v29", encoding="utf-8")
            target.joinpath("moon-forecast-card-v25.js").write_text("old moon v25", encoding="utf-8")
            with patch.object(core, "OPTIONS_FILE", Path("/nonexistent/astro_test_options.json")), \
                    patch.object(core, "DASHBOARD_CARDS_DIR", source), \
                    patch.object(core, "HA_CONFIG_DIR", Path(config_dir)), \
                    patch.object(core, "log"):
                options = core.load_options()
                ok = core.install_dashboard_cards(options)

            self.assertTrue(ok)
            for name in (
                "astro-start-card-v30.js", "astro-start-card-v31.js", "astro-start-card-v32.js",
                "astro-start-card-v33.js", "astro-start-card-v34.js", "astro-start-card-v35.js",
                "astro-satellite-card-v3.js", "astro-satellite-card-v4.js",
                "astro-satellite-card-v5.js", "astro-satellite-card-v6.js",
                "astro-satellite-card-v7.js", "astro-satellite-card-v8.js", "astro-satellite-card-v9.js",
                "astro-weather-cards-loader.js",
            ):
                self.assertTrue(target.joinpath(name).exists(), name)

            astro_v35 = target.joinpath("astro-start-card-v35.js").read_text(encoding="utf-8")
            satellite_v9 = target.joinpath("astro-satellite-card-v9.js").read_text(encoding="utf-8")
            self.assertIn('import "/local/astro-start-card-v34.js";', astro_v35)
            self.assertIn("decision-reason-row-v35", astro_v35)
            self.assertIn("detail-title", astro_v35)
            self.assertIn("_compactDecisionReasonV35", astro_v35)
            self.assertIn('import "/local/astro-satellite-card-v8.js";', satellite_v9)
            self.assertIn("history-slider-v9", satellite_v9)
            self.assertIn('searchParams.set("time"', satellite_v9)
            self.assertIn("CLM body jsou skryté", satellite_v9)
            self.assertIn("_irHistoryV9", satellite_v9)

            manifest = json.loads(target.joinpath("astro-weather-cards-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["backend_version"], "12.4.17")
            self.assertEqual(manifest["cards"][0]["version"], 35)
            self.assertEqual(manifest["cards"][0]["url"], "/local/astro-start-card-v35.js")
            self.assertEqual(manifest["cards"][1]["version"], 25)
            sat_cards = [row for row in manifest["cards"] if row.get("type") == "astro-satellite-card"]
            self.assertEqual(len(sat_cards), 1)
            self.assertEqual(sat_cards[0]["version"], 9)
            self.assertEqual(sat_cards[0]["url"], "/local/astro-satellite-card-v9.js")


if __name__ == "__main__":
    unittest.main()
