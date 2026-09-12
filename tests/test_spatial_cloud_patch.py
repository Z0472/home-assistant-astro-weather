"""Regression tests for 12.3 spatial cloud-neighbourhood analysis."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))

import astro_weather_backend as core
import model_runtime
import confidence_patch
import night_forecast_patch
import spatial_cloud_patch as spatial


class SpatialCloudPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        model_runtime.install(core)
        confidence_patch.install(core)
        night_forecast_patch.install(core)
        spatial.install(core)

    def setUp(self):
        self.options = {
            "latitude": 48.9247,
            "longitude": 14.4319,
            "timezone": "Europe/Prague",
            "horizon_hours": 72,
            "spatial_cloud_analysis": True,
            "spatial_radius_km": 30,
            "wind_bad_ms": 12.0,
            "aod_bad": 0.40,
            "seeing_bad_arcsec": 2.5,
        }

    def test_sampling_grid_has_center_and_two_eight_point_rings(self):
        points = spatial.build_spatial_points(48.9247, 14.4319, 30)
        self.assertEqual(len(points), 17)
        self.assertEqual(points[0]["id"], "C")
        inner = [p for p in points if p["ring"] == "inner"]
        outer = [p for p in points if p["ring"] == "outer"]
        self.assertEqual(len(inner), 8)
        self.assertEqual(len(outer), 8)
        self.assertTrue(all(abs(p["distance_km"] - 15.0) < 0.01 for p in inner))
        self.assertTrue(all(abs(p["distance_km"] - 30.0) < 0.01 for p in outer))

    def test_radius_is_clamped_to_supported_10_50_km_range(self):
        self.assertEqual(spatial.build_spatial_points(48.9, 14.4, 1)[-1]["distance_km"], 10.0)
        self.assertEqual(spatial.build_spatial_points(48.9, 14.4, 99)[-1]["distance_km"], 50.0)

    def test_cloud_edge_is_found_west_of_clear_center(self):
        points = spatial.build_spatial_points(48.9247, 14.4319, 30)
        values = {"C": 10.0}
        for point in points:
            if point["id"] == "C":
                continue
            if point["direction"] == "Z":
                values[point["id"]] = 40.0 if point["ring"] == "inner" else 90.0
            else:
                values[point["id"]] = 10.0
        edge = spatial._edge_for_values(points, values)
        self.assertIsNotNone(edge)
        self.assertEqual(edge["type"], "cloud")
        self.assertEqual(edge["direction"], "Z")
        self.assertAlmostEqual(edge["distance_km"], 18.0, places=1)

    def test_snapshot_reports_low_spatial_stability_at_cloud_boundary(self):
        points = spatial.build_spatial_points(48.9247, 14.4319, 30)
        stamp = "2026-09-12T20:00:00Z"
        spatial.ICON_SPATIAL_ROWS = {stamp: {"points": {}}}
        spatial.ALADIN_SPATIAL_ROWS = {}
        for point in points:
            total = 10.0 if point["direction"] not in {"Z", "SZ", "JZ"} else 90.0
            if point["id"] == "C":
                total = 10.0
            spatial.ICON_SPATIAL_ROWS[stamp]["points"][point["id"]] = {
                "total": total, "low": total, "mid": 0.0, "high": 0.0,
            }
        spatial.ICON_WIND_ROWS = {stamp: {"850": {"speed_ms": 8.0, "direction_deg": 270.0}}}
        snap = spatial._snapshot(core, self.options, datetime(2026, 9, 12, 20, tzinfo=timezone.utc))
        self.assertIsNotNone(snap)
        self.assertTrue(snap["boundary"])
        self.assertLess(snap["spatialStability"], 30)
        self.assertIn(snap["edge"]["direction"], {"JZ", "Z", "SZ"})
        self.assertTrue(snap["windSupportsEdgeMotion"])

    def test_incoming_clouds_can_soften_good_decision_to_uncertain(self):
        result = {
            "decision": "good",
            "label": "SPUSTIT",
            "reason": "dobrý blok",
            "hours": [{
                "precip": 0.0, "fog": 0.0, "wind": 2.0,
                "moonInterferes": False, "aerosolApplied": False,
                "seeingApplied": False,
            }],
        }
        spatial_info = {
            "state": "incoming",
            "etaMinutes": 75,
            "shortText": "☁ Oblačnost přichází ~1 h 15 min od Z",
            "edgeDistanceKm": 12.0,
            "spatialStability": 25.0,
        }
        spatial._apply_to_decision(core, self.options, result, spatial_info)
        self.assertEqual(result["decision"], "uncertain")
        self.assertEqual(result["label"], "NEJISTÉ")
        self.assertTrue(result["spatialAdjusted"])

    def test_hard_veto_is_never_softened_by_spatial_clearing(self):
        result = {
            "decision": "bad",
            "label": "NESPOUŠTĚT",
            "reason": "srážky",
            "hours": [{
                "precip": 0.3, "fog": 0.0, "wind": 2.0,
                "moonInterferes": False, "aerosolApplied": False,
                "seeingApplied": False,
            }],
        }
        spatial_info = {
            "state": "clearing",
            "etaMinutes": 30,
            "shortText": "🌙 Vyjasnění ~30 min",
            "spatialStability": 20.0,
        }
        spatial._apply_to_decision(core, self.options, result, spatial_info)
        self.assertEqual(result["decision"], "bad")
        self.assertEqual(result["label"], "NESPOUŠTĚT")


if __name__ == "__main__":
    unittest.main()
