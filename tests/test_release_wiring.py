"""Release-level wiring checks for Home Assistant Astro Weather 12.2."""
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


class ReleaseWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        model_runtime.install(core)

    def test_release_config_and_docker_entrypoint(self):
        config = (ROOT / "astro_weather_backend/config.yaml").read_text(encoding="utf-8")
        docker = (ROOT / "astro_weather_backend/Dockerfile").read_text(encoding="utf-8")
        self.assertIn('version: "12.2.0"', config)
        self.assertIn("use_icon: true", config)
        self.assertIn("use_icon: bool", config)
        self.assertIn("COPY weather_models.py", docker)
        self.assertIn("COPY cloud_consensus.py", docker)
        self.assertIn("COPY model_runtime.py", docker)
        self.assertIn('CMD ["python3", "-u", "/app/app.py"]', docker)

    def test_v23_card_install_is_self_contained(self):
        source = ROOT / "astro_weather_backend/cards"
        with tempfile.TemporaryDirectory() as config_dir:
            target = Path(config_dir) / "www"
            target.mkdir()
            # Simulate a real upgrade with the previous physical card present.
            target.joinpath("astro-start-card-v22.js").write_text("old v22", encoding="utf-8")
            with patch.object(core, "OPTIONS_FILE", Path("/nonexistent/astro_test_options.json")), \
                    patch.object(core, "DASHBOARD_CARDS_DIR", source), \
                    patch.object(core, "HA_CONFIG_DIR", Path(config_dir)), \
                    patch.object(core, "log"):
                options = core.load_options()
                ok = core.install_dashboard_cards(options)

            self.assertTrue(ok)
            self.assertTrue(target.joinpath("astro-start-card-base-v22.js").exists())
            self.assertTrue(target.joinpath("astro-start-card-v23.js").exists())
            self.assertTrue(target.joinpath("moon-forecast-card-v23.js").exists())
            self.assertTrue(target.joinpath("astro-weather-cards-loader.js").exists())

            enhancer = target.joinpath("astro-start-card-v23.js").read_text(encoding="utf-8")
            self.assertIn('import "/local/astro-start-card-base-v22.js";', enhancer)
            self.assertIn("ICON", enhancer)
            self.assertIn("Astro Start Decision Card v23", enhancer)

            manifest = json.loads(target.joinpath("astro-weather-cards-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["backend_version"], "12.2.0")
            self.assertEqual(manifest["cards"][0]["version"], 23)
            self.assertEqual(manifest["cards"][0]["url"], "/local/astro-start-card-v23.js")

            compatibility = target.joinpath("astro-start-card-v22.js").read_text(encoding="utf-8")
            self.assertIn('/local/astro-weather-cards-loader.js', compatibility)


if __name__ == "__main__":
    unittest.main()
