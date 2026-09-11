"""Regression tests for the 12.2 universal DWD ICON / multi-model layer."""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "astro_weather_backend"))
import astro_weather_backend as core
import cloud_consensus as cc
import model_runtime as runtime
import weather_models as wm


class ModelConsensusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runtime.install(core)

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
            "astronomical_dark_end": core.iso_z(self.start + timedelta(hours=8)),
        }

    def weather_row(self, met=0, aladin=0, icon=0, hour=0):
        stamp = core.iso_z(self.start + timedelta(hours=hour))
        return {
            "datetime": stamp,
            "met": None if met is None else {
                "cloud_total": met,
                "cloud_high": met,
                "temperature": 12,
                "dew_point": 5,
                "fog": 0,
                "precipitation_1h": 0,
                "wind_speed_ms": 2,
            },
            "aladin": None if aladin is None else {"cloud_total": aladin, "cloud_high": aladin},
            "icon": None if icon is None else {"cloud_total": icon, "cloud_high": icon},
            "aerosols": None,
            "seeing": None,
        }

    def test_release_layer_sets_version_and_icon_default(self):
        self.assertEqual(core.APP_VERSION, "12.2.0")
        self.assertEqual(core.ASTRO_START_CARD_VERSION, 23)
        self.assertTrue(self.options["use_icon"])
        self.assertIn("12.2.0", self.options["met_user_agent"])
        self.assertTrue(core.decision_settings(self.options)["use_icon"])

    def test_icon_url_explicitly_selects_dwd_seamless(self):
        url = wm.icon_forecast_url(self.options)
        self.assertIn("models=dwd_icon_seamless", url)
        self.assertIn("cloud_cover_low", url)
        self.assertIn("cloud_cover_mid", url)
        self.assertIn("cloud_cover_high", url)
        self.assertIn("timezone=UTC", url)

    def test_parse_icon_forecast(self):
        doc = {
            "latitude": self.options["latitude"],
            "longitude": self.options["longitude"],
            "hourly": {
                "time": ["2026-09-11T19:00", "2026-09-11T20:00"],
                "cloud_cover": [12, 88],
                "cloud_cover_low": [5, 80],
                "cloud_cover_mid": [3, 20],
                "cloud_cover_high": [7, 50],
            },
        }
        parsed = wm.parse_icon_forecast(doc, self.options, core)
        first = parsed[core.iso_z(self.start)]
        self.assertEqual(first["cloud_total"], 12)
        self.assertEqual(first["cloud_low"], 5)
        self.assertEqual(first["cloud_medium"], 3)
        self.assertEqual(first["cloud_high"], 7)

    def test_parse_icon_rejects_wrong_location_and_missing_total(self):
        wrong = {
            "latitude": self.options["latitude"] + 2,
            "longitude": self.options["longitude"],
            "hourly": {"time": ["2026-09-11T19:00"], "cloud_cover": [5]},
        }
        with self.assertRaises(ValueError):
            wm.parse_icon_forecast(wrong, self.options, core)
        missing = {
            "latitude": self.options["latitude"],
            "longitude": self.options["longitude"],
            "hourly": {"time": ["2026-09-11T19:00"], "cloud_cover": [None]},
        }
        with self.assertRaises(ValueError):
            wm.parse_icon_forecast(missing, self.options, core)

    def test_fetch_icon_has_explicit_model_family_metadata(self):
        doc = {
            "latitude": self.options["latitude"],
            "longitude": self.options["longitude"],
            "hourly": {
                "time": ["2026-09-11T19:00"],
                "cloud_cover": [10], "cloud_cover_low": [2],
                "cloud_cover_mid": [3], "cloud_cover_high": [4],
            },
        }
        with patch.object(core, "http_get", return_value=json.dumps(doc).encode()):
            rows, source = core.fetch_icon(self.options)
        self.assertTrue(rows)
        self.assertEqual(source["model_family"], "DWD ICON")
        self.assertEqual(source["dataset"], "dwd_icon_seamless")

    def test_two_model_consensus_is_identical_to_12_1_12_formula(self):
        result = cc.cloud_consensus({"MET": 0, "ALADIN": 100}, 35, 55)
        self.assertEqual(result["model_count"], 2)
        self.assertAlmostEqual(result["effective"], 85.0)
        self.assertAlmostEqual(result["confidence"], 25.0)
        self.assertTrue(result["strong_disagreement"])

        result = cc.cloud_consensus({"MET": 10, "ALADIN": 20}, 35, 55)
        expected = 0.70 * 20 + 0.30 * 15
        self.assertAlmostEqual(result["effective"], expected)
        self.assertAlmostEqual(result["confidence"], 100 - 10 * 1.05)

    def test_three_model_tight_pair_resists_one_cloudy_outlier(self):
        result = cc.cloud_consensus({"MET": 80, "ALADIN": 10, "ICON": 15}, 35, 55)
        self.assertEqual(result["model_count"], 3)
        self.assertAlmostEqual(result["median"], 15)
        self.assertAlmostEqual(result["spread"], 70)
        self.assertAlmostEqual(result["effective"], 29)
        self.assertTrue(result["outlier"])
        self.assertEqual(result["outlier_name"], "MET")
        self.assertFalse(result["strong_disagreement"])
        self.assertAlmostEqual(result["confidence"], 50.5)

    def test_three_model_clear_conflict_is_not_averaged_away(self):
        result = cc.cloud_consensus({"MET": 10, "ALADIN": 45, "ICON": 80}, 35, 55)
        self.assertAlmostEqual(result["effective"], 59)
        self.assertEqual(result["agreement"], "conflict")
        self.assertFalse(result["outlier"])
        self.assertTrue(result["strong_disagreement"])
        self.assertEqual(result["confidence"], 25)

    def test_three_model_agreement_has_high_confidence(self):
        result = cc.cloud_consensus({"MET": 5, "ALADIN": 10, "ICON": 15}, 35, 55)
        self.assertAlmostEqual(result["effective"], 12)
        self.assertEqual(result["agreement"], "good")
        self.assertEqual(result["confidence"], 90)

    def test_score_hour_outlier_is_visible_but_does_not_hard_break_hour(self):
        row = self.weather_row(met=80, aladin=10, icon=15)
        scored = core.score_hour(row, None, self.night, self.options)
        self.assertEqual(scored["modelCount"], 3)
        self.assertEqual(scored["modelOutlierName"], "MET")
        self.assertTrue(scored["modelOutlier"])
        self.assertFalse(scored["strongDisagreement"])
        self.assertEqual(scored["effectiveCloud"], 29)
        self.assertEqual(scored["score"], 71)
        self.assertEqual(scored["status"], "good")
        self.assertIn("MET mimo shodu", " ".join(scored["reasons"]))

    def test_score_hour_three_way_conflict_is_uncertain(self):
        row = self.weather_row(met=10, aladin=45, icon=80)
        scored = core.score_hour(row, None, self.night, self.options)
        self.assertTrue(scored["strongDisagreement"])
        self.assertEqual(scored["status"], "uncertain")
        self.assertEqual(scored["modelAgreement"], "conflict")
        self.assertEqual(scored["effectiveCloud"], 59)

    def test_missing_icon_preserves_two_model_score(self):
        row = self.weather_row(met=10, aladin=20, icon=None)
        scored = core.score_hour(row, None, self.night, self.options)
        expected_cloud = 0.70 * 20 + 0.30 * 15
        self.assertAlmostEqual(scored["effectiveCloud"], expected_cloud)
        self.assertAlmostEqual(scored["confidence"], 89.5)
        self.assertEqual(scored["modelCount"], 2)
        self.assertFalse(scored["iconAvailable"])

    def test_one_model_can_never_form_good_block(self):
        row = self.weather_row(met=0, aladin=None, icon=None)
        scored = core.score_hour(row, None, self.night, self.options)
        self.assertEqual(scored["confidence"], 45)
        self.assertEqual(scored["status"], "partial")
        self.assertEqual(scored["modelCount"], 1)

    def test_no_cloud_models_keeps_zero_score(self):
        row = self.weather_row(met=None, aladin=None, icon=None)
        scored = core.score_hour(row, None, self.night, self.options)
        self.assertEqual(scored["score"], 0)
        self.assertEqual(scored["status"], "bad")
        self.assertIsNone(scored["dominantPenalty"])

    def test_met_plus_icon_is_full_two_model_coverage_without_aladin(self):
        rows = [self.weather_row(met=0, aladin=None, icon=0, hour=i) for i in range(8)]
        analysis = core.analyze_night(self.night, rows, [], self.options)
        self.assertEqual(analysis["decision"], "good")
        self.assertEqual(analysis["modelCoverage"], 1.0)
        self.assertEqual(analysis["threeModelCoverage"], 0.0)
        self.assertEqual(analysis["iconAvg"], 0)
        self.assertEqual(analysis["launchBlock"]["hours"], 8)

    def test_three_model_night_reports_icon_average_and_three_model_coverage(self):
        rows = [self.weather_row(met=5, aladin=10, icon=15, hour=i) for i in range(8)]
        analysis = core.analyze_night(self.night, rows, [], self.options)
        self.assertEqual(analysis["decision"], "good")
        self.assertEqual(analysis["modelCoverage"], 1.0)
        self.assertEqual(analysis["threeModelCoverage"], 1.0)
        self.assertEqual(analysis["iconAvg"], 15)
        self.assertEqual(analysis["modelCountAvg"], 3)

    def test_generic_conflict_reason_lists_all_available_models(self):
        rows = [self.weather_row(met=10, aladin=45, icon=80, hour=i) for i in range(8)]
        analysis = core.analyze_night(self.night, rows, [], self.options)
        self.assertEqual(analysis["decision"], "uncertain")
        self.assertIn("Meteorologické modely", analysis["reason"])
        self.assertIn("MET 10 %", analysis["reason"])
        self.assertIn("ALADIN 45 %", analysis["reason"])
        self.assertIn("ICON 80 %", analysis["reason"])

    def test_merge_sources_keeps_icon_only_timestamps(self):
        now = self.start - timedelta(hours=1)
        stamp = core.iso_z(self.start)
        with patch.object(core, "utc_now", return_value=now), \
                patch.object(wm, "ICON_ROWS", {stamp: {"cloud_total": 12}}):
            merged = core.merge_sources({}, {}, 24, {})
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["icon"]["cloud_total"], 12)

    def test_aladin_coverage_validation_rejects_far_grid(self):
        with patch.object(core, "discover_latest_aladin_run", return_value="2026091112"), \
                patch.object(wm, "aladin_nearest_grid_distance_km", return_value=600.0), \
                patch.object(wm, "_ALADIN_COVERAGE_CACHE", {}):
            original = Mock()
            with self.assertRaises(RuntimeError):
                wm.fetch_aladin_wrapped(core, original, self.options)
            original.assert_not_called()

    def test_aladin_coverage_validation_accepts_near_grid(self):
        rows = {core.iso_z(self.start): {"cloud_total": 10}}
        source = {"available": True, "run": "2026091112"}
        original = Mock(return_value=(rows, source))
        with patch.object(core, "discover_latest_aladin_run", return_value="2026091112"), \
                patch.object(wm, "aladin_nearest_grid_distance_km", return_value=1.2):
            got_rows, got_source = wm.fetch_aladin_wrapped(core, original, self.options)
        self.assertEqual(got_rows, rows)
        self.assertTrue(got_source["coverage_validated"])
        self.assertEqual(got_source["nearest_grid_distance_km"], 1.2)

    def test_icon_failure_is_fail_open_and_reported(self):
        with patch.object(wm, "fetch_icon", side_effect=TimeoutError("ICON outage")), \
                patch.object(core, "log"):
            wm.refresh_icon(self.options, core)
        self.assertEqual(wm.ICON_ROWS, {})
        self.assertEqual(wm.ICON_ERROR, "ICON outage")
        self.assertFalse(wm.ICON_SOURCE["available"])

        rows = [self.weather_row(met=0, aladin=0, icon=None, hour=i) for i in range(8)]
        analysis = core.analyze_night(self.night, rows, [], self.options)
        self.assertEqual(analysis["decision"], "good")
        self.assertEqual(analysis["modelCoverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
