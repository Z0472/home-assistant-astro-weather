"""Regression tests for 12.2.2 night display and decision confidence behavior."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))

import astro_weather_backend as core
import model_runtime
import confidence_patch
import night_forecast_patch as patch


class NightForecastPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        model_runtime.install(core)
        confidence_patch.install(core)
        patch.install(core)

    def setUp(self):
        self.options = {
            "latitude": 48.9247,
            "longitude": 14.4319,
            "timezone": "Europe/Prague",
            "disagreement_warn": 35,
            "disagreement_bad": 55,
            "wind_bad_ms": 12.0,
            "aod_bad": 0.40,
            "seeing_bad_arcsec": 2.5,
        }

    def test_low_model_agreement_softens_cloud_only_stop(self):
        result = {
            "decision": "bad",
            "label": "NESPOUŠTĚT",
            "reason": "Není dostatečně dlouhé kvalitní okno na začátku noci.",
            "modelAgreementAvg": 56.0,
            "hours": [
                {
                    "duration": 1.0,
                    "precip": 0.0,
                    "fog": 0.0,
                    "wind": 2.0,
                    "moonInterferes": False,
                    "aerosolApplied": False,
                    "seeingApplied": False,
                }
            ],
        }
        patch._soften_low_agreement_bad(core, result, self.options)
        self.assertEqual(result["decision"], "uncertain")
        self.assertEqual(result["label"], "NEJISTÉ")
        self.assertIn("56", result["reason"])

    def test_hard_veto_keeps_stop_even_with_low_agreement(self):
        result = {
            "decision": "bad",
            "label": "NESPOUŠTĚT",
            "reason": "Srážky.",
            "modelAgreementAvg": 40.0,
            "hours": [
                {
                    "duration": 1.0,
                    "precip": 0.2,
                    "fog": 0.0,
                    "wind": 2.0,
                    "moonInterferes": False,
                    "aerosolApplied": False,
                    "seeingApplied": False,
                }
            ],
        }
        patch._soften_low_agreement_bad(core, result, self.options)
        self.assertEqual(result["decision"], "bad")
        self.assertEqual(result["label"], "NESPOUŠTĚT")

    def test_solar_window_runs_from_sunset_to_next_sunrise(self):
        sunset, sunrise = patch._solar_window(core, {"date": "2026-09-12"}, self.options)
        self.assertIsNotNone(sunset)
        self.assertIsNotNone(sunrise)
        self.assertLess(sunset, sunrise)
        duration = (sunrise - sunset).total_seconds() / 3600.0
        self.assertGreater(duration, 8.0)
        self.assertLess(duration, 16.0)


if __name__ == "__main__":
    unittest.main()
