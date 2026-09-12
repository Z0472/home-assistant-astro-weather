"""Regression tests for EUMETSAT satellite-nowcast integration 12.4.0."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
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
import edge_consistency_patch
import satellite_nowcast_patch as sat


class SatelliteNowcastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        model_runtime.install(core)
        confidence_patch.install(core)
        night_forecast_patch.install(core)
        spatial_cloud_patch.install(core)
        spatial_timeline_patch.install(core)
        twilight_patch.install(core)
        state_cache_patch.install(core)
        edge_consistency_patch.install(core)
        sat.install(core)

    def test_release_and_options_fail_open_without_credentials(self):
        with patch.object(core, "OPTIONS_FILE", Path("/nonexistent/astro_satellite_test.json")):
            options = core.load_options()
        self.assertEqual(core.APP_VERSION, "12.4.0")
        self.assertTrue(options["use_satellite"])
        self.assertEqual(options["satellite_radius_km"], 30)
        self.assertEqual(options["satellite_refresh_minutes"], 10)
        doc = sat._satellite_document(core, options)
        self.assertFalse(doc["available"])
        self.assertEqual(doc["credential_status"], "required")
        self.assertIn("EUMETView", doc["reason"])

    def test_linear_nowcast_uses_recent_observations(self):
        base = datetime(2026, 9, 12, 18, 0, tzinfo=timezone.utc)
        frames = []
        for index, cloud in enumerate((10.0, 20.0, 30.0, 40.0)):
            frames.append({
                "time": (base + timedelta(minutes=10 * index)).isoformat().replace("+00:00", "Z"),
                "cloud_pct": cloud,
            })
        out = sat._linear_nowcast(frames)
        self.assertEqual(out["trend"], "incoming")
        self.assertEqual(out["arrow"], "↗")
        self.assertGreater(out["slope_pph"], 0)
        self.assertEqual(len(out["points"]), 4)
        self.assertEqual(out["points"][0]["cloud_pct"], 40.0)
        self.assertTrue(out["points"][1]["estimated"])

    def test_edge_direction_requires_three_consistent_frames(self):
        base = datetime(2026, 9, 12, 18, 0, tzinfo=timezone.utc)

        def frame(minutes, inner_cloud):
            points = {"C": 0}
            for bearing, _ in spatial_cloud_patch.BEARINGS:
                points[f"inner_{int(bearing):03d}"] = 0
                points[f"outer_{int(bearing):03d}"] = 0
            points["outer_270"] = 1
            if inner_cloud:
                points["inner_270"] = 1
            return {
                "time": (base + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z"),
                "points": points,
            }

        edge = sat._stable_edge([frame(0, False), frame(10, False), frame(20, True)], 30)
        self.assertIsNotNone(edge)
        self.assertEqual(edge["type"], "cloud")
        self.assertEqual(edge["direction"], "Z")
        self.assertTrue(edge["stable"])
        self.assertTrue(edge["approaching"])
        self.assertIsNotNone(edge["eta_minutes"])

        self.assertIsNone(sat._stable_edge([frame(0, False), frame(10, True)], 30))

    def test_model_satellite_comparison_keeps_per_model_errors(self):
        stamp = datetime(2026, 9, 12, 18, 0, tzinfo=timezone.utc)
        with core.STATE_LOCK:
            core.STATE["forecast"] = [{
                "datetime": core.iso_z(stamp),
                "met": {"cloud_total": 10.0},
                "aladin": {"cloud_total": 20.0},
                "icon": {"cloud_total": 30.0},
            }]
        options = {
            "disagreement_warn": 35,
            "disagreement_bad": 55,
        }
        result = sat._comparison(core, options, {
            "cloud_pct": 25.0,
            "as_of": core.iso_z(stamp),
        })
        self.assertTrue(result["available"])
        self.assertEqual(result["model_count"], 3)
        self.assertGreater(result["agreement_pct"], 90)
        self.assertEqual(set(result["models"]), {"MET", "ALADIN", "ICON"})
        self.assertEqual(result["models"]["MET"]["absolute_error_pp"], 15.0)

    def test_operational_grib_product_id_uses_validity_interval_end(self):
        product_id = (
            "W_XX-EUMETSAT-Darmstadt,IMG+SAT,MTI1+FCI-2-CLM--FD------GRIB2_"
            "C_EUMT_20260912172557_L2PF_OPE_20260912171000_20260912172000_N__O_0104_0000"
        )
        parsed = sat._product_time(product_id, {})
        self.assertEqual(
            parsed,
            datetime(2026, 9, 12, 17, 20, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
