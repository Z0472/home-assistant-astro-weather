"""Release-level wiring checks for Home Assistant Astro Weather 12.3.3."""
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

    def test_release_config_and_docker_entrypoint(self):
        config = (ROOT / "astro_weather_backend/config.yaml").read_text(encoding="utf-8")
        docker = (ROOT / "astro_weather_backend/Dockerfile").read_text(encoding="utf-8")
        app = (ROOT / "astro_weather_backend/app.py").read_text(encoding="utf-8")
        self.assertIn('version: "12.3.3"', config)
        self.assertIn("use_icon: true", config)
        self.assertIn("spatial_cloud_analysis: true", config)
        self.assertIn("spatial_radius_km: 30", config)
        self.assertIn('spatial_radius_km: "int(10,50)"', config)
        self.assertIn("COPY weather_models.py", docker)
        self.assertIn("COPY cloud_consensus.py", docker)
        self.assertIn("COPY model_runtime.py", docker)
        self.assertIn("COPY confidence_patch.py", docker)
        self.assertIn("COPY night_forecast_patch.py", docker)
        self.assertIn("COPY spatial_cloud_patch.py", docker)
        self.assertIn("COPY spatial_timeline_patch.py", docker)
        self.assertIn("COPY twilight_patch.py", docker)
        self.assertIn("COPY state_cache_patch.py", docker)
        self.assertIn("spatial_timeline_patch.install(core)", app)
        self.assertIn("twilight_patch.install(core)", app)
        self.assertIn("state_cache_patch.install(core)", app)
        self.assertIn('CMD ["python3", "-u", "/app/app.py"]', docker)

    def test_v28_decision_card_install_is_self_contained(self):
        source = ROOT / "astro_weather_backend/cards"
        with tempfile.TemporaryDirectory() as config_dir:
            target = Path(config_dir) / "www"
            target.mkdir()
            target.joinpath("astro-start-card-v27.js").write_text("old v27", encoding="utf-8")
            target.joinpath("moon-forecast-card-v25.js").write_text("old moon v25", encoding="utf-8")
            with patch.object(core, "OPTIONS_FILE", Path("/nonexistent/astro_test_options.json")), \
                    patch.object(core, "DASHBOARD_CARDS_DIR", source), \
                    patch.object(core, "HA_CONFIG_DIR", Path(config_dir)), \
                    patch.object(core, "log"):
                options = core.load_options()
                ok = core.install_dashboard_cards(options)

            self.assertTrue(ok)
            self.assertTrue(target.joinpath("astro-start-card-base-v22.js").exists())
            self.assertTrue(target.joinpath("astro-start-card-v23.js").exists())
            self.assertTrue(target.joinpath("astro-start-card-v24.js").exists())
            self.assertTrue(target.joinpath("astro-start-card-v25.js").exists())
            self.assertTrue(target.joinpath("astro-start-card-v26.js").exists())
            self.assertTrue(target.joinpath("astro-start-card-v27.js").exists())
            self.assertTrue(target.joinpath("astro-start-card-v28.js").exists())
            self.assertTrue(target.joinpath("moon-forecast-card-v23.js").exists())
            self.assertTrue(target.joinpath("moon-forecast-card-v24.js").exists())
            self.assertTrue(target.joinpath("moon-forecast-card-v25.js").exists())
            self.assertTrue(target.joinpath("astro-weather-cards-loader.js").exists())

            astro = target.joinpath("astro-start-card-v28.js").read_text(encoding="utf-8")
            moon = target.joinpath("moon-forecast-card-v25.js").read_text(encoding="utf-8")
            self.assertIn('import "/local/astro-start-card-v27.js";', astro)
            self.assertIn('label: "svítání"', astro)
            self.assertIn('label: "soumrak"', astro)
            self.assertIn('import "/local/moon-forecast-card-v24.js";', moon)
            self.assertIn("Průměrná shoda modelů", moon)

            manifest = json.loads(target.joinpath("astro-weather-cards-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["backend_version"], "12.3.3")
            self.assertEqual(manifest["cards"][0]["version"], 28)
            self.assertEqual(manifest["cards"][0]["url"], "/local/astro-start-card-v28.js")
            self.assertEqual(manifest["cards"][1]["version"], 25)
            self.assertEqual(manifest["cards"][1]["url"], "/local/moon-forecast-card-v25.js")


if __name__ == "__main__":
    unittest.main()
