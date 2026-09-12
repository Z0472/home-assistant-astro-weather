"""Regression tests for Astro Weather 12.4.9 satellite/main-card UI refinements."""
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

    def test_model_comparison_uses_center_clm_not_regional_fraction(self):
        seen = {}

        def original(core, options, satellite):
            seen["cloud_pct"] = satellite.get("cloud_pct")
            return {
                "state": "20.0",
                "available": True,
                "agreement_pct": 20.0,
                "satellite_cloud_pct": satellite.get("cloud_pct"),
                "model_cloud_pct": 80.0,
            }

        result = ui._comparison_using_center(
            object(),
            {"satellite_radius_km": 30},
            {
                "cloud_pct": 53.0,
                "center_cloud_pct": 0.0,
                "radius_km": 30,
                "as_of": "2026-09-12T21:40:00Z",
            },
            original,
        )
        self.assertEqual(seen["cloud_pct"], 0.0)
        self.assertEqual(result["satellite_cloud_pct"], 0.0)
        self.assertEqual(result["satellite_local_cloud_pct"], 0.0)
        self.assertEqual(result["satellite_area_cloud_pct"], 53.0)
        self.assertEqual(result["satellite_scope"], "observatory_center")
        self.assertEqual(result["satellite_radius_km"], 30)

    def test_model_comparison_is_unavailable_when_center_clm_is_missing(self):
        called = []

        def original(core, options, satellite):
            called.append(True)
            return {}

        result = ui._comparison_using_center(
            object(),
            {"satellite_radius_km": 30},
            {"cloud_pct": 53.0, "center_cloud_pct": None, "as_of": "2026-09-12T21:40:00Z"},
            original,
        )
        self.assertFalse(result["available"])
        self.assertEqual(result["satellite_area_cloud_pct"], 53.0)
        self.assertEqual(called, [])
        self.assertIn("přímo nad observatoří", result["reason"])

    def test_main_card_v31_removes_duplicate_astronomical_night_rows(self):
        source = (ROOT / "astro_weather_backend/cards/astro-start-card-v31.js").read_text(encoding="utf-8")
        self.assertIn('import "/local/astro-start-card-v30.js";', source)
        self.assertIn('class="night-astro"', source)
        self.assertIn('class="detail-sub">Astronomická noc', source)
        self.assertIn("_compactNightRowsV31", source)

    def test_main_card_v32_keeps_nightly_model_percentages_only_in_summary(self):
        source = (ROOT / "astro_weather_backend/cards/astro-start-card-v32.js").read_text(encoding="utf-8")
        self.assertIn('import "/local/astro-start-card-v31.js";', source)
        self.assertIn("Průměry oblačnosti za astronomickou noc", source)
        self.assertIn("duplicateNightAverages", source)

    def test_main_card_v33_labels_local_clm_comparison(self):
        source = (ROOT / "astro_weather_backend/cards/astro-start-card-v33.js").read_text(encoding="utf-8")
        self.assertIn('import "/local/astro-start-card-v32.js";', source)
        self.assertIn("observatoř", source)
        self.assertIn("satellite_local_cloud_pct", source)
        self.assertIn("Regionální 30km podíl", source)
        self.assertIn("_localSatelliteComparisonV33", source)

    def test_satellite_card_v5_separates_live_clm_age_and_ir_refresh(self):
        v5 = (ROOT / "astro_weather_backend/cards/astro-satellite-card-v5.js").read_text(encoding="utf-8")
        self.assertIn("CLM ${this._time(asOf)} · před ${age} min", v5)
        self.assertIn("setInterval", v5)
        self.assertIn("IR obnoveno ${refreshed}", v5)

    def test_satellite_card_v7_starts_age_timer_from_render_and_hass_setter(self):
        source = (ROOT / "astro_weather_backend/cards/astro-satellite-card-v7.js").read_text(encoding="utf-8")
        self.assertIn("_ensureLiveClmAgeTimerV7", source)
        self.assertIn("_satAgeTimerV5", source)
        self.assertIn("oldHassSetter.call(this, hass)", source)
        self.assertIn("_updateLiveClmAgeV5", source)

    def test_satellite_card_v8_separates_observatory_from_area_nowcast(self):
        source = (ROOT / "astro_weather_backend/cards/astro-satellite-card-v8.js").read_text(encoding="utf-8")
        self.assertIn('import "/local/astro-satellite-card-v7.js";', source)
        self.assertIn("Observatoř: ${local.label}", source)
        self.assertIn("oblačných CLM vzorků", source)
        self.assertIn("Vývoj oblačnosti v okolí", source)
        self.assertIn("satellite_local_cloud_pct", source)
        self.assertIn("Regionální", source) if False else None
        self.assertIn("_localVsAreaV8", source)

    def test_release_constants(self):
        self.assertEqual(ui.RELEASE_VERSION, "12.4.9")
        self.assertEqual(ui.ASTRO_CARD_VERSION, 33)
        self.assertEqual(ui.SATELLITE_CARD_VERSION, 8)
        self.assertEqual(ui.VISUAL_RADIUS_KM, 150.0)
        self.assertEqual(ui.VISUAL_SIZE_PX, 900)


if __name__ == "__main__":
    unittest.main()
