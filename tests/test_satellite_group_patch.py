"""Regression tests for the 12.4.17 operational template-50002 fixes."""
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


def _pack_values(values, width):
    acc = 0
    total_bits = 0
    for value in values:
        acc = (acc << width) | int(value)
        total_bits += width
    pad = (-total_bits) % 8
    acc <<= pad
    return acc.to_bytes((total_bits + pad) // 8, "big")


def _section5_50002(order=2, width=8, spd=(10, 12, -1)):
    encoded = []
    for index, value in enumerate(spd):
        value = int(value)
        if index == len(spd) - 1 and value < 0:
            encoded.append((1 << (width - 1)) | (-value))
        else:
            encoded.append(value)
    spd_blob = _pack_values(encoded, width)
    length = 34 + len(spd_blob)
    section = bytearray(length)
    section[0:4] = length.to_bytes(4, "big")
    section[4] = 5
    section[5:9] = (9).to_bytes(4, "big")
    section[9:11] = (50002).to_bytes(2, "big")
    section[32] = order
    section[33] = width
    section[34:] = spd_blob
    return bytes(section)


def _minimal_grib2(section5):
    section7 = (5).to_bytes(4, "big") + b"\x07"
    total = 16 + len(section5) + len(section7) + 4
    header = b"GRIB" + b"\x00\x00\x00\x02" + total.to_bytes(8, "big")
    return header + section5 + section7 + b"7777"


class SatelliteGroupPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        group_patch.install(core)

    def test_spd_array_is_read_directly_from_section5(self):
        with tempfile.TemporaryDirectory() as tmp:
            grib = Path(tmp) / "sample.grib2"
            grib.write_bytes(_minimal_grib2(_section5_50002()))
            width, spd = group_patch._read_spd_from_section5(grib, 2)
        self.assertEqual(width, 8)
        self.assertEqual(spd, [10, 12, -1])

    def test_operational_436159_groups_are_accepted_without_spd_grib_get(self):
        calls = []

        def run_cmd(argv, timeout=0):
            calls.append(list(argv))
            key = argv[argv.index("-p") + 1]
            if key == lowmem._METADATA_KEYS:
                return "space_view 5568 5568 0 1 0 0 0 0 50002 grid_second_order 0 0 0 0 0\n"
            if key == lowmem._SECOND_ORDER_KEYS:
                return "2 436159 31002622 4 8 2 0 31002624\n"
            raise AssertionError(key)

        with tempfile.TemporaryDirectory() as tmp:
            grib = Path(tmp) / "sample.grib2"
            grib.write_bytes(b"GRIB")
            with patch.object(core, "run_cmd", side_effect=run_cmd), \
                    patch.object(group_patch, "_read_spd_from_section5", return_value=(8, [0, 0, 0])):
                meta = lowmem._metadata(core, grib)

        self.assertEqual(meta["number_of_groups"], 436159)
        self.assertEqual(meta["number_of_points"], 31002624)
        self.assertEqual(meta["lowmem_mode"], "second_order_50002")
        self.assertLess(meta["descriptor_vector_bytes"], 11 * 1024 * 1024)
        self.assertLess(
            meta["descriptor_vector_bytes"] + meta["descriptor_packed_bytes"],
            group_patch.MAX_DESCRIPTOR_WORKING_SET_BYTES,
        )
        requested = [call[call.index("-p") + 1] for call in calls]
        self.assertNotIn("SPD", requested)
        self.assertNotIn("widthOfSPD", requested)

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
