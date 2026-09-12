"""Regression tests for the satellite-card CLM sample map patch."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))

import astro_weather_backend as core
import satellite_nowcast_patch as sat
import satellite_card_map_patch as clm_map


class SatelliteCardMapPatchTests(unittest.TestCase):
    def test_augment_document_exposes_exact_latest_samples(self):
        frame = {
            "product_id": "sample",
            "time": "2026-09-12T17:20:00Z",
            "points": {
                "C": 0,
                "inner_000": 0,
                "outer_000": 1,
                "inner_090": 1,
                "outer_090": None,
            },
            "processing_storage": "ram:/dev/shm",
        }
        document = {
            "available": True,
            "as_of": "2026-09-12T17:20:00Z",
            "radius_km": 30,
        }
        with patch.object(sat, "_load_sample_cache", return_value=[frame]):
            result = clm_map._augment_document(core, document)

        self.assertEqual(result["clm_points"], frame["points"])
        self.assertEqual(result["clm_map_radius_km"], 30)
        self.assertEqual(result["clm_map_time"], frame["time"])
        self.assertEqual(result["clm_processing_storage"], "ram:/dev/shm")
        self.assertIn("17 přesných CLM vzorků", result["clm_map_basis"])

    def test_unavailable_document_is_left_without_map(self):
        document = {"available": False, "state": "unavailable"}
        result = clm_map._augment_document(core, document)
        self.assertNotIn("clm_points", result)

    def test_install_bumps_satellite_card_to_v2(self):
        original_version = sat.SATELLITE_CARD_VERSION
        original_installs = core.DASHBOARD_CARD_INSTALLS
        original_flag = getattr(core, "_SATELLITE_CARD_MAP_PATCH_INSTALLED", False)
        try:
            if original_flag:
                delattr(core, "_SATELLITE_CARD_MAP_PATCH_INSTALLED")
            core.DASHBOARD_CARD_INSTALLS = tuple(
                (source, target)
                for source, target in original_installs
                if not target.startswith("astro-satellite-card-v")
            ) + (("astro-satellite-card.js", "astro-satellite-card-v1.js"),)
            clm_map.install(core)
            self.assertEqual(sat.SATELLITE_CARD_VERSION, 2)
            targets = [target for _, target in core.DASHBOARD_CARD_INSTALLS]
            self.assertIn("astro-satellite-card-v2.js", targets)
            self.assertNotIn("astro-satellite-card-v1.js", targets)
        finally:
            sat.SATELLITE_CARD_VERSION = original_version
            core.DASHBOARD_CARD_INSTALLS = original_installs
            if original_flag:
                core._SATELLITE_CARD_MAP_PATCH_INSTALLED = True
            elif hasattr(core, "_SATELLITE_CARD_MAP_PATCH_INSTALLED"):
                delattr(core, "_SATELLITE_CARD_MAP_PATCH_INSTALLED")


if __name__ == "__main__":
    unittest.main()
