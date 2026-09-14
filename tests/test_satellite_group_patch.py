"""Regression tests for the 12.4.16 operational second-order group patch."""
from array import array
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))

import astro_weather_backend as core
import satellite_group_patch as group_patch
import satellite_lowmem_patch as lowmem


class SatelliteGroupPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        group_patch.install(core)

    def test_operational_436159_groups_are_accepted(self):
        def run_cmd(argv, timeout=0):
            key = argv[argv.index("-p") + 1]
            if key == lowmem._METADATA_KEYS:
                return "space_view 5568 5568 0 1 0 0 0 0 50002 grid_second_order 0 0 0 0 0\n"
            if key == lowmem._SECOND_ORDER_KEYS:
                return "2 436159 31002622 4 8 2 0 31002624\n"
            if key == "widthOfSPD":
                return "8\n"
            if key == "SPD":
                return "0 0 0\n"
            raise AssertionError(key)

        with tempfile.TemporaryDirectory() as tmp:
            grib = Path(tmp) / "sample.grib2"
            grib.write_bytes(b"GRIB")
            with patch.object(core, "run_cmd", side_effect=run_cmd):
                meta = lowmem._metadata(core, grib)

        self.assertEqual(meta["number_of_groups"], 436159)
        self.assertEqual(meta["number_of_points"], 31002624)
        self.assertEqual(meta["lowmem_mode"], "second_order_50002")
        self.assertLess(meta["descriptor_vector_bytes"], 11 * 1024 * 1024)
        self.assertLess(
            meta["descriptor_vector_bytes"] + meta["descriptor_packed_bytes"],
            group_patch.MAX_DESCRIPTOR_WORKING_SET_BYTES,
        )

    def test_descriptor_reader_uses_compact_array(self):
        count = 100000
        values, offset = group_patch._read_aligned_uint_array(
            io.BytesIO(b""), 0, 0, count, 0
        )
        self.assertIsInstance(values, array)
        self.assertEqual(len(values), count)
        self.assertEqual(offset, 0)
        self.assertLessEqual(values.buffer_info()[1] * values.itemsize, count * 8)

    def test_absurd_group_count_is_rejected_before_allocation(self):
        def run_cmd(argv, timeout=0):
            key = argv[argv.index("-p") + 1]
            if key == lowmem._METADATA_KEYS:
                return "space_view 5568 5568 0 1 0 0 0 0 50002 grid_second_order 0 0 0 0 0\n"
            if key == lowmem._SECOND_ORDER_KEYS:
                return "2 3000000 31002622 4 8 2 0 31002624\n"
            raise AssertionError(key)

        with tempfile.TemporaryDirectory() as tmp:
            grib = Path(tmp) / "sample.grib2"
            grib.write_bytes(b"GRIB")
            with patch.object(core, "run_cmd", side_effect=run_cmd):
                with self.assertRaisesRegex(RuntimeError, "bezpecnostni limit"):
                    lowmem._metadata(core, grib)


if __name__ == "__main__":
    unittest.main()
