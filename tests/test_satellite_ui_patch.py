"""Regression tests for Astro Weather 12.4.6 satellite/main-card UI refinements."""
import math
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))

import satellite_ui_patch as ui


class SatelliteUiPatchTests(unittest.TestCase):
    def test_regional_ir_url_is_centered_square_and_about_150km_radius(self):
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
        self.assertEqual(query["height"], ["900"])
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

    def test_main_card_v31_removes_duplicate_astronomical_night_rows(self):
        source = (ROOT / "astro_weather_backend/cards/astro-start-card-v31.js").read_text(encoding="utf-8")
        self.assertIn('import "/local/astro-start-card-v30.js";', source)
        self.assertIn('class="night-astro"', source)
        self.assertIn('class="detail-sub">Astronomická noc', source)
        self.assertIn("_nightSummaryHtml", source)
        self.assertIn("_detailHtml", source)
        self.assertIn("_compactNightRowsV31", source)

        base = (ROOT / "astro_weather_backend/cards/astro-start-card.js").read_text(encoding="utf-8")
        self.assertIn('<div class="k">Astronomická noc</div>', base)

    def test_satellite_card_v5_separates_live_clm_age_and_ir_refresh(self):
        v4 = (ROOT / "astro_weather_backend/cards/astro-satellite-card-v4.js").read_text(encoding="utf-8")
        v5 = (ROOT / "astro_weather_backend/cards/astro-satellite-card-v5.js").read_text(encoding="utf-8")

        self.assertIn('import "/local/astro-satellite-card-v4.js";', v5)
        self.assertIn("_liveClmAgeV5", v5)
        self.assertIn("Date.now()", v5)
        self.assertIn("CLM ${this._time(asOf)} · před ${age} min", v5)
        self.assertIn("setInterval", v5)
        self.assertIn("30000", v5)
        self.assertIn("age >= 45", v5)
        self.assertIn("age >= 30", v5)
        self.assertIn("IR obnoveno ${refreshed}", v5)
        self.assertIn("_logicalTimeLabelsV5", v5)

        # v5 must preserve the fine v4 overlay rather than replacing it.
        self.assertIn("_fineOverlayV4", v4)
        self.assertIn("sample-clear-v4", v4)
        self.assertIn("sample-cloud-v4", v4)

    def test_release_constants(self):
        self.assertEqual(ui.RELEASE_VERSION, "12.4.6")
        self.assertEqual(ui.ASTRO_CARD_VERSION, 31)
        self.assertEqual(ui.SATELLITE_CARD_VERSION, 5)
        self.assertEqual(ui.VISUAL_RADIUS_KM, 150.0)
        self.assertEqual(ui.VISUAL_SIZE_PX, 900)


if __name__ == "__main__":
    unittest.main()
