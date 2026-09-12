"""Regression tests for 12.3.1 current/night spatial timeline semantics."""
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
import spatial_cloud_patch as spatial
import spatial_timeline_patch as timeline


class SpatialTimelinePatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        model_runtime.install(core)
        confidence_patch.install(core)
        night_forecast_patch.install(core)
        spatial.install(core)
        timeline.install(core)

    def setUp(self):
        self.options = {
            "latitude": 48.9311,
            "longitude": 14.3553,
            "altitude": 500,
            "timezone": "Europe/Prague",
            "horizon_hours": 72,
            "spatial_cloud_analysis": True,
            "spatial_radius_km": 30,
            "met_user_agent": "test",
        }

    def _snap(self, target, cloud, edge_type="cloud", edge_distance=12.0):
        return {
            "time": core.iso_z(target),
            "centerCloud": float(cloud),
            "minCloud": max(0.0, float(cloud) - 20),
            "maxCloud": min(100.0, float(cloud) + 20),
            "spatialStability": 60.0,
            "boundary": 25 <= cloud <= 75,
            "edge": {
                "type": edge_type,
                "bearing_deg": 270.0,
                "direction": "Z",
                "distance_km": edge_distance,
            },
            "dominantLayer": "střední",
            "windLevelHpa": 700,
            "windFromDeg": 290.0,
            "windSpeedMs": 8.0,
            "windSupportsEdgeMotion": True,
            "sources": ["ICON", "ALADIN"],
            "iconTime": core.iso_z(target.replace(minute=0, second=0, microsecond=0)),
            "aladinTime": core.iso_z(target.replace(minute=0, second=0, microsecond=0)),
        }

    def test_current_trend_uses_relative_eta_from_now(self):
        now = datetime(2026, 9, 12, 9, 30, tzinfo=timezone.utc)

        def fake_snapshot(_core, _options, target):
            delta_h = round((target - now).total_seconds() / 3600.0)
            cloud = {0: 10, 1: 35, 2: 75}.get(delta_h, 80)
            return self._snap(target, cloud, edge_distance=max(2.0, 12.0 - delta_h * 3))

        with patch.object(core, "utc_now", return_value=now), patch.object(
            spatial, "_snapshot", side_effect=fake_snapshot
        ):
            current = timeline._current_spatial(core, self.options)

        self.assertIsNotNone(current)
        self.assertEqual(current["state"], "incoming")
        self.assertEqual(current["arrow"], "↗")
        self.assertIn("Zatahování", current["shortText"])
        self.assertIn("za ", current["shortText"])
        self.assertEqual(current["edgeDirection"], "Z")

    def test_night_summary_uses_absolute_clock_time_not_relative_eta(self):
        start = datetime(2026, 9, 12, 18, 0, tzinfo=timezone.utc)
        clouds = [85, 55, 15, 10]
        records = []
        for index, cloud in enumerate(clouds):
            when = start + timedelta(hours=index)
            hour = {"start": core.iso_z(when)}
            records.append((when, hour, self._snap(when, cloud, edge_type="clear")))

        timeline._enrich_hour_trends(records)
        summary = timeline._night_summary(core, self.options, records)

        self.assertIsNotNone(summary)
        self.assertIn("vyjasnění kolem", summary["shortText"])
        self.assertNotIn("za ", summary["shortText"])
        self.assertEqual(records[0][1]["spatialArrow"], "↘")
        self.assertEqual(records[-1][1]["spatialArrow"], "→")

    def test_three_hour_arrows_mean_clouding_clearing_steady(self):
        base = self._snap(datetime.now(timezone.utc), 20)
        cloudier = {**base, "centerCloud": 45}
        clearer = {**base, "centerCloud": 5}

        self.assertEqual(timeline._trend_between(base, cloudier), "incoming")
        self.assertEqual(timeline._arrow("incoming"), "↗")
        self.assertEqual(timeline._trend_between(base, clearer), "clearing")
        self.assertEqual(timeline._arrow("clearing"), "↘")
        self.assertEqual(timeline._trend_between(base, {**base, "centerCloud": 24}), "steady")
        self.assertEqual(timeline._arrow("steady"), "→")

    def test_release_layer_sets_12_3_1_and_card_v27(self):
        self.assertEqual(core.APP_VERSION, "12.3.1")
        self.assertEqual(core.ASTRO_START_CARD_VERSION, 27)
        self.assertTrue(
            any(dst == "astro-start-card-v27.js" for _, dst in core.DASHBOARD_CARD_INSTALLS)
        )


if __name__ == "__main__":
    unittest.main()
