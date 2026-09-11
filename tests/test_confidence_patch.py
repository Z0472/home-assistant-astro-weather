"""Regression tests for Astro Weather 12.2.1 confidence presentation patch."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))
import astro_weather_backend as core
import cloud_consensus as cc
import model_runtime
import confidence_patch


class ConfidencePatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        model_runtime.install(core)
        confidence_patch.install(core)

    def setUp(self):
        with patch.object(core, "OPTIONS_FILE", Path("/nonexistent/astro_test_options.json")):
            self.options = core.load_options()
        self.options["use_aerosols"] = False
        self.options["use_seeing"] = False
        self.start = datetime(2026, 9, 11, 19, tzinfo=timezone.utc)
        self.night = {
            "date": "2026-09-11",
            "status": "nerusi",
            "astronomical_dark_start": core.iso_z(self.start),
            "astronomical_dark_end": core.iso_z(self.start + timedelta(hours=4)),
        }

    def row(self, hour, met=5, aladin=10, icon=15):
        return {
            "datetime": core.iso_z(self.start + timedelta(hours=hour)),
            "met": {
                "cloud_total": met, "cloud_high": met,
                "temperature": 12, "dew_point": 5, "fog": 0,
                "precipitation_1h": 0, "wind_speed_ms": 2,
            },
            "aladin": {"cloud_total": aladin, "cloud_high": aladin},
            "icon": {"cloud_total": icon, "cloud_high": icon},
            "aerosols": None,
            "seeing": None,
        }

    def test_release_version_and_user_agent(self):
        self.assertEqual(core.APP_VERSION, "12.2.1")
        self.assertEqual(core.ASTRO_START_CARD_VERSION, 24)
        self.assertEqual(core.MOON_FORECAST_CARD_VERSION, 24)
        self.assertIn("12.2.1", self.options["met_user_agent"])

    def test_warn_boundary_cannot_be_good_and_outlier_at_once(self):
        result = cc.cloud_consensus({"ALADIN": 0, "MET": 10.2, "ICON": 35}, 35, 55)
        self.assertTrue(result["outlier"])
        self.assertEqual(result["outlier_name"], "ICON")
        self.assertEqual(result["agreement"], "outlier")
        self.assertLess(result["confidence"], 65)

    def test_night_publishes_average_score_and_confidence(self):
        rows = [self.row(i) for i in range(4)]
        analysis = core.analyze_night(self.night, rows, [], self.options)
        self.assertIsNotNone(analysis)
        self.assertAlmostEqual(analysis["scoreAvg"], 88.0, places=1)
        self.assertAlmostEqual(analysis["confidenceAvg"], 90.0, places=1)

    def test_v24_cards_contain_confidence_presentation(self):
        astro = (ROOT / "astro_weather_backend/cards/astro-start-card-v24.js").read_text(encoding="utf-8")
        moon = (ROOT / "astro_weather_backend/cards/moon-forecast-card-v24.js").read_text(encoding="utf-8")
        self.assertIn("Průměrná důvěra", astro)
        self.assertIn("Důvěra", astro)
        self.assertIn("Průměrná důvěra", moon)
        self.assertIn("ICON", moon)


if __name__ == "__main__":
    unittest.main()
