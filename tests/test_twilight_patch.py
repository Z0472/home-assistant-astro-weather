"""Regression tests for morning/evening twilight display flags in 12.3.2."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))

import astro_weather_backend as core
import twilight_patch


class TwilightPatchTests(unittest.TestCase):
    def test_evening_and_morning_boundary_hours_are_twilight(self):
        result = {
            "darkStart": "2026-09-12T19:13:51Z",
            "darkEnd": "2026-09-13T02:45:06Z",
            "displayHours": [
                {"start": "2026-09-12T17:23:27Z", "end": "2026-09-12T18:00:00Z"},
                {"start": "2026-09-12T20:00:00Z", "end": "2026-09-12T21:00:00Z"},
                {"start": "2026-09-13T02:00:00Z", "end": "2026-09-13T03:00:00Z"},
                {"start": "2026-09-13T03:00:00Z", "end": "2026-09-13T04:00:00Z"},
            ],
        }

        twilight_patch.normalize_display_twilight(core, result)
        rows = result["displayHours"]

        self.assertTrue(rows[0]["twilight"])
        self.assertEqual(rows[0]["twilightPhase"], "evening")
        self.assertFalse(rows[1]["twilight"])
        self.assertTrue(rows[1]["isAstronomicalDark"])
        self.assertTrue(rows[2]["twilight"])
        self.assertEqual(rows[2]["twilightPhase"], "morning")
        self.assertTrue(rows[3]["twilight"])
        self.assertEqual(rows[3]["twilightPhase"], "morning")

    def test_twilight_patch_does_not_change_decision_hours(self):
        result = {
            "darkStart": "2026-09-12T19:13:51Z",
            "darkEnd": "2026-09-13T02:45:06Z",
            "hours": [{"start": "2026-09-12T20:00:00Z", "status": "good"}],
            "displayHours": [
                {"start": "2026-09-13T03:00:00Z", "end": "2026-09-13T04:00:00Z"},
            ],
        }
        original_hours = [dict(row) for row in result["hours"]]
        twilight_patch.normalize_display_twilight(core, result)
        self.assertEqual(result["hours"], original_hours)
        self.assertTrue(result["displayHours"][0]["twilight"])


if __name__ == "__main__":
    unittest.main()
