"""Regression tests for the 12.4.1 low-load satellite bootstrap guard."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))

import astro_weather_backend as core
import satellite_nowcast_patch as sat
import satellite_lowload_patch as lowload


class SatelliteLowloadPatchTests(unittest.TestCase):
    def test_selects_all_cached_but_only_one_uncached_product(self):
        rows = [
            {"product_id": "newest"},
            {"product_id": "cached2"},
            {"product_id": "uncached-old"},
            {"product_id": "cached1"},
        ]
        cache = [
            {"product_id": "cached1", "time": "2026-09-12T17:00:00Z"},
            {"product_id": "cached2", "time": "2026-09-12T17:10:00Z"},
        ]
        with patch.object(sat, "_load_sample_cache", return_value=cache):
            selected = lowload._select_cached_plus_one(core, rows)
        self.assertEqual(
            [row["product_id"] for row in selected],
            ["newest", "cached2", "cached1"],
        )

    def test_empty_cache_admits_only_latest_product(self):
        rows = [
            {"product_id": "newest"},
            {"product_id": "older"},
            {"product_id": "oldest"},
        ]
        with patch.object(sat, "_load_sample_cache", return_value=[]):
            selected = lowload._select_cached_plus_one(core, rows)
        self.assertEqual(selected, [{"product_id": "newest"}])

    def test_release_version_and_delay_are_safe_defaults(self):
        self.assertEqual(lowload.RELEASE_VERSION, "12.4.1")
        self.assertGreaterEqual(lowload.INITIAL_SATELLITE_DELAY_SECONDS, 60)


if __name__ == "__main__":
    unittest.main()
