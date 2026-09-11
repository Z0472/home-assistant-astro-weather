"""Release-level wiring checks for Home Assistant Astro Weather 12.2.1."""
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


class ReleaseWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        model_runtime.install(core)
        confidence_patch.install(core)

    def test_release_config_and_docker_entrypoint(self):
        config = (ROOT / "astro_weather_backend/config.yaml").read_text(encoding="utf-8")
        docker = (ROOT / "astro_weather_backend/Dockerfile").read_text(encoding="utf-8")
        self.assertIn('version: "12.2.1"', config)
        self.assertIn("use_icon: true", config)
        self.assertIn("use_icon: bool", config)
        self.assertIn("COPY weather_models.py", docker)
        self.assertIn("COPY cloud_consensus.py", docker)
        self.assertIn("COPY model_runtime.py", docker)
        self.assertIn("COPY confidence_patch.py", docker)
        self.assertIn('CMD ["python3", "-u", "/app/app.py"]', docker)

    def test_v24_cards_install_is_self_contained(self):
        source = ROOT / "astro_weather_backend/cards"
        with tempfile.TemporaryDirectory() as config_dir:
            target = Path(config_dir) / "www"
            target.mkdir()
            target.joinpath("astro-start-card-v23.js").write_text("old v23", encoding="utf-8")
            target.joinpath("moon-forecast-card-v23.js").write_text("old moon v23", encoding="utf-8")
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
            self.assertTrue(target.joinpath("moon-forecast-card-v23.js").exists())
            self.assertTrue(target.joinpath("moon-forecast-card-v24.js").exists())
            self.assertTrue(target.joinpath("astro-weather-cards-loader.js").exists())

            astro = target.joinpath("astro-start-card-v24.js").read_text(encoding="utf-8")
            moon = target.joinpath("moon-forecast-card-v24.js").read_text(encoding="utf-8")
            self.assertIn('import "/local/astro-start-card-v23.js";', astro)
            self.assertIn("Důvěra", astro)
            self.assertIn('import "/local/moon-forecast-card-v23.js";', moon)
            self.assertIn("Průměrná důvěra", moon)

            manifest = json.loads(target.joinpath("astro-weather-cards-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["backend_version"], "12.2.1")
            self.assertEqual(manifest["cards"][0]["version"], 24)
            self.assertEqual(manifest["cards"][0]["url"], "/local/astro-start-card-v24.js")
            self.assertEqual(manifest["cards"][1]["version"], 24)
            self.assertEqual(manifest["cards"][1]["url"], "/local/moon-forecast-card-v24.js")


if __name__ == "__main__":
    unittest.main()
