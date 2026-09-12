"""Regression tests for 12.3.4 temporal cloud-edge consistency."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))

import astro_weather_backend as core
import edge_consistency_patch as edge_guard
import spatial_timeline_patch as timeline


class EdgeConsistencyPatchTests(unittest.TestCase):
    def setUp(self):
        self.options = {
            "latitude": 48.9311,
            "longitude": 14.3553,
            "altitude": 500,
            "timezone": "Europe/Prague",
            "spatial_radius_km": 30,
            "spatial_cloud_analysis": True,
        }
        self.base = datetime(2026, 9, 12, 21, 0, tzinfo=timezone.utc)

    def _snap(self, when, cloud, bearing, distance, edge_type="cloud"):
        directions = {
            0: "S", 45: "SV", 90: "V", 135: "JV",
            180: "J", 225: "JZ", 270: "Z", 315: "SZ",
        }
        return {
            "time": core.iso_z(when),
            "centerCloud": float(cloud),
            "minCloud": max(0.0, float(cloud) - 25),
            "maxCloud": min(100.0, float(cloud) + 25),
            "spatialStability": 50.0,
            "boundary": True,
            "edge": {
                "type": edge_type,
                "bearing_deg": float(bearing),
                "direction": directions[int(bearing)],
                "distance_km": float(distance),
            },
            "sources": ["ICON", "ALADIN"],
            "iconTime": core.iso_z(when),
            "aladinTime": core.iso_z(when),
        }

    def test_adjacent_western_bearings_form_one_stable_edge_track(self):
        records = [
            (self.base, self._snap(self.base, 30, 270, 12)),
            (self.base + timedelta(hours=1), self._snap(self.base + timedelta(hours=1), 40, 315, 9)),
            (self.base + timedelta(hours=2), self._snap(self.base + timedelta(hours=2), 55, 270, 6)),
        ]
        track = edge_guard._edge_track(records)
        self.assertIsNotNone(track)
        self.assertEqual(track["direction"], "Z")
        self.assertTrue(track["approaching"])
        self.assertEqual(track["points"], 3)

    def test_rotating_nearest_edges_are_rejected_as_one_track(self):
        records = [
            (self.base, self._snap(self.base, 30, 270, 12)),
            (self.base + timedelta(hours=1), self._snap(self.base + timedelta(hours=1), 40, 90, 9)),
            (self.base + timedelta(hours=2), self._snap(self.base + timedelta(hours=2), 55, 0, 6)),
        ]
        self.assertIsNone(edge_guard._edge_track(records))
        self.assertIsNone(edge_guard._edge_motion(records))

    def test_hour_tooltip_describes_its_exact_interval_and_hides_unstable_direction(self):
        snaps = [
            self._snap(self.base, 20, 270, 12),
            self._snap(self.base + timedelta(hours=1), 45, 90, 9),
            self._snap(self.base + timedelta(hours=2), 50, 0, 7),
        ]
        records = []
        for index, snap in enumerate(snaps):
            when = self.base + timedelta(hours=index)
            hour = {
                "start": core.iso_z(when),
                "end": core.iso_z(when + timedelta(hours=1)),
            }
            records.append((when, hour, snap))

        edge_guard._enrich_hour_trends(records)
        result = {"displayHours": [row for _, row, _ in records], "hours": []}
        edge_guard._rewrite_hour_labels(core, self.options, result)

        first = result["displayHours"][0]
        self.assertEqual(first["spatialTrend"], "incoming")
        self.assertEqual(first["spatialArrow"], "↗")
        self.assertFalse(first["spatialEdgeDirectionStable"])
        self.assertIsNone(first["spatialEdgeDirection"])
        self.assertIn("23:00 → 00:00: ↗ oblačnosti přibývá", first["spatialTrendLabel"])
        self.assertIn("směr hrany nejistý", first["spatialTrendLabel"])

    def test_current_trend_keeps_eta_but_suppresses_spurious_direction(self):
        records = [
            (self.base, self._snap(self.base, 20, 270, 12)),
            (self.base + timedelta(hours=1), self._snap(self.base + timedelta(hours=1), 70, 90, 8)),
            (self.base + timedelta(hours=2), self._snap(self.base + timedelta(hours=2), 80, 0, 5)),
        ]
        with patch.object(timeline, "_current_records", return_value=records):
            current = edge_guard._current_spatial(core, self.options)

        self.assertIsNotNone(current)
        self.assertEqual(current["state"], "incoming")
        self.assertIsNotNone(current["etaMinutes"])
        self.assertIsNone(current["edgeDirection"])
        self.assertFalse(current["edgeDirectionStable"])
        self.assertIn("směr hrany nejistý", current["shortText"])
        self.assertNotIn(" od Z", current["shortText"])


if __name__ == "__main__":
    unittest.main()
