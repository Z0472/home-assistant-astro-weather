"""Regression tests for the 12.4.2 MTG/FCI direct-index sampler."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))

import astro_weather_backend as core
import satellite_nowcast_patch as sat
import satellite_index_sampler_patch as idx


class SatelliteIndexSamplerTests(unittest.TestCase):
    def test_homole_reference_pixel_is_stable(self):
        row, col = idx._reference_pixel(48.9311, 14.3553, 0.0)
        self.assertEqual((row, col), (5019, 3272))
        self.assertEqual(idx._grid_index(row, col), row * 5568 + col)

    def test_grid_validation_accepts_operational_fci_order(self):
        idx._validate_grid({
            "grid_type": "space_view",
            "nx": 5568,
            "ny": 5568,
            "i_negative": 0,
            "j_positive": 1,
            "j_consecutive": 0,
            "alternate_rows": 0,
            "sub_satellite_lat": 0.0,
            "sub_satellite_lon": 0.0,
        })

    def test_grid_validation_rejects_unknown_scanning_order(self):
        with self.assertRaises(RuntimeError):
            idx._validate_grid({
                "grid_type": "space_view",
                "nx": 5568,
                "ny": 5568,
                "i_negative": 0,
                "j_positive": 0,
                "j_consecutive": 0,
                "alternate_rows": 0,
                "sub_satellite_lat": 0.0,
                "sub_satellite_lon": 0.0,
            })

    def test_sampler_uses_index_not_nearest_latlon(self):
        options = {
            "latitude": 48.9311,
            "longitude": 14.3553,
            "satellite_radius_km": 30,
        }
        product = {"product_id": "test-product", "time": "2026-09-12T18:20:00Z"}
        calls = []

        def run_cmd(argv, timeout=0):
            calls.append(list(argv))
            if "-p" in argv:
                return "space_view 5568 5568 0 1 0 0 0 0\n"
            self.assertIn("-i", argv)
            self.assertNotIn("-l", argv)
            return "2\n"

        with tempfile.TemporaryDirectory() as tmp:
            grib = Path(tmp) / "sample.grib2"
            grib.write_bytes(b"GRIB-test")
            with patch.object(idx.shutil, "which", return_value="/usr/bin/grib_get"), \
                    patch.object(sat, "_download_product", return_value=b"payload"), \
                    patch.object(sat, "_write_grib_from_download", return_value=grib), \
                    patch.object(core, "run_cmd", side_effect=run_cmd):
                result = idx._sample_product(core, options, product, "token")

        self.assertEqual(result["sampler"], "eccodes-direct-index")
        self.assertEqual(result["cloud_pct"], 100.0)
        self.assertEqual(result["valid_samples"], 17)
        self.assertEqual(len(result["point_indexes"]), 17)
        self.assertEqual(sum(1 for call in calls if "-i" in call), 17)
        self.assertFalse(any("-l" in call for call in calls))


if __name__ == "__main__":
    unittest.main()
