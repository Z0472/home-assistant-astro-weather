"""Regression tests for Astro Weather 12.4.3 satellite UI refinements."""
import math
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))

import satellite_ui_patch as ui


class SatelliteUiPatchTests(unittest.TestCase):
    def test_regional_ir_url_is_centered_and_about_150km_radius(self):
        lat = 48.9311
        lon = 14.3553
        url = ui._regional_ir_url({"latitude": lat, "longitude": lon})
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.netloc, "view.eumetsat.int")
        self.assertEqual(query["service"], ["WMS"])
        self.assertEqual(query["version"], ["1.3.0"])
        self.assertEqual(query["crs"], ["EPSG:4326"])
        self.assertEqual(query["width"], ["900"])
        self.assertEqual(query["height"], ["600"])
        self.assertIn("mtg_fd:ir105_hrfi", query["layers"][0])

        south, west, north, east = [float(x) for x in query["bbox"][0].split(",")]
        self.assertAlmostEqual((south + north) / 2.0, lat, places=4)
        self.assertAlmostEqual((west + east) / 2.0, lon, places=4)

        ns_radius_km = (north - south) * 111.32 / 2.0
        ew_radius_km = (east - west) * 111.32 * math.cos(math.radians(lat)) / 2.0
        self.assertGreater(ns_radius_km, 145.0)
        self.assertLess(ns_radius_km, 155.0)
        self.assertGreater(ew_radius_km, 145.0)
        self.assertLess(ew_radius_km, 155.0)

    def test_main_card_moves_live_satellite_line_to_today_only(self):
        source = (ROOT / "astro_weather_backend/cards/astro-start-card-v30.js").read_text(encoding="utf-8")
        self.assertIn('import "/local/astro-start-card-v29.js";', source)
        self.assertIn("idx !== 0", source)
        self.assertIn("night-satellite-v30", source)
        self.assertIn("Satelit vs modely", source)
        self.assertIn("satellite-agreement-v29", source)
        self.assertIn("_detailHtml", source)

    def test_release_constants(self):
        self.assertEqual(ui.RELEASE_VERSION, "12.4.3")
        self.assertEqual(ui.ASTRO_CARD_VERSION, 30)
        self.assertEqual(ui.SATELLITE_CARD_VERSION, 2)
        self.assertEqual(ui.VISUAL_RADIUS_KM, 150.0)


if __name__ == "__main__":
    unittest.main()
