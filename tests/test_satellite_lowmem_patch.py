"""Regression tests for the 12.4.15 bounded-memory FCI CLM sampler."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))

import astro_weather_backend as core
import satellite_nowcast_patch as sat
import satellite_index_sampler_patch as index_sampler
import satellite_lowmem_patch as lowmem
import storage_protection_patch as storage


def _pack_values(values, bits_per_value):
    if bits_per_value == 0:
        return b""
    acc = 0
    total_bits = 0
    for value in values:
        acc = (acc << bits_per_value) | int(value)
        total_bits += bits_per_value
    pad = (-total_bits) % 8
    acc <<= pad
    return acc.to_bytes((total_bits + pad) // 8, "big")


def _minimal_grib2_payload(payload):
    section7 = (5 + len(payload)).to_bytes(4, "big") + b"\x07" + payload
    total = 16 + len(section7) + 4
    section0 = b"GRIB" + b"\x00\x00\x00\x02" + total.to_bytes(8, "big")
    return section0 + section7 + b"7777"


def _minimal_grib2_section7(values, bits_per_value=2):
    return _minimal_grib2_payload(_pack_values(values, bits_per_value))


def _second_order_payload(group_widths, group_lengths, first_orders, residual_groups,
                          width_of_widths, width_of_lengths, width_of_first_orders):
    payload = b"".join((
        _pack_values(group_widths, width_of_widths),
        _pack_values(group_lengths, width_of_lengths),
        _pack_values(first_orders, width_of_first_orders),
    ))

    acc = 0
    total_bits = 0
    for width, values in zip(group_widths, residual_groups):
        for value in values:
            if width:
                acc = (acc << width) | int(value)
                total_bits += width
    if total_bits:
        pad = (-total_bits) % 8
        acc <<= pad
        payload += acc.to_bytes((total_bits + pad) // 8, "big")
    return payload


class SatelliteLowMemoryTests(unittest.TestCase):
    def test_packed_reader_extracts_two_bit_categories(self):
        values = [0, 1, 2, 3, 2, 1, 0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.grib2"
            path.write_bytes(_minimal_grib2_section7(values))
            offset, length = lowmem._section7_range(path)
            with path.open("rb") as handle:
                decoded = [
                    lowmem._read_packed_uint(handle, offset, length, i, 2)
                    for i in range(len(values))
                ]
        self.assertEqual(decoded, values)

    def test_simple_packing_formula(self):
        meta = {
            "reference_value": 1.0,
            "binary_scale_factor": 1,
            "decimal_scale_factor": 1,
        }
        self.assertAlmostEqual(lowmem._decode_simple(2, meta), 0.5)

    def test_second_order_template_50002_stream_decoder(self):
        payload = _second_order_payload(
            group_widths=[0, 2],
            group_lengths=[3, 4],
            first_orders=[1, 2],
            residual_groups=[[0, 0, 0], [0, 1, 2, 3]],
            width_of_widths=2,
            width_of_lengths=3,
            width_of_first_orders=2,
        )
        meta = {
            "number_of_groups": 2,
            "number_of_second_order_values": 7,
            "number_of_points": 9,
            "width_of_widths": 2,
            "width_of_lengths": 3,
            "width_of_first_order_values": 2,
            "order_of_spd": 2,
            "spd": [10, 12, -1],
        }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.grib2"
            path.write_bytes(_minimal_grib2_payload(payload))
            offset, length = lowmem._section7_range(path)
            with path.open("rb") as handle:
                decoded = lowmem._decode_second_order_targets(
                    handle, offset, length, meta, [0, 1, 4, 8]
                )

        self.assertEqual(decoded, {0: 10, 1: 12, 4: 18, 8: 46})

    def test_second_order_metadata_accepts_operational_template(self):
        def run_cmd(argv, timeout=0):
            key = argv[argv.index("-p") + 1]
            if key == lowmem._METADATA_KEYS:
                return "space_view 5568 5568 0 1 0 0 0 0 50002 grid_second_order 0 0 0 0 0\n"
            if key == lowmem._SECOND_ORDER_KEYS:
                return "1 1 7 1 3 2 0 9\n"
            if key == "widthOfSPD":
                return "8\n"
            if key == "SPD":
                return "2 2 0\n"
            raise AssertionError(key)

        with tempfile.TemporaryDirectory() as tmp:
            grib = Path(tmp) / "sample.grib2"
            grib.write_bytes(_minimal_grib2_payload(b"\x00\xe0\x00"))
            with patch.object(core, "run_cmd", side_effect=run_cmd):
                meta = lowmem._metadata(core, grib)

        self.assertEqual(meta["lowmem_mode"], "second_order_50002")
        self.assertEqual(meta["packing_type"], "grid_second_order")
        self.assertEqual(meta["order_of_spd"], 2)
        self.assertEqual(meta["spd"], [2, 2, 0])

    def test_sampler_never_uses_eccodes_value_decode(self):
        options = {
            "latitude": 48.9311,
            "longitude": 14.3553,
            "satellite_radius_km": 30,
        }
        product = {"product_id": "test-product", "time": "2026-09-14T04:40:00Z"}
        calls = []

        def run_cmd(argv, timeout=0):
            calls.append(list(argv))
            self.assertIn("-p", argv)
            self.assertNotIn("-i", argv)
            self.assertNotIn("-l", argv)
            return "space_view 5568 5568 0 1 0 0 0 0 0 grid_simple 2 0 0 0 0\n"

        with tempfile.TemporaryDirectory() as tmp:
            grib = Path(tmp) / "sample.grib2"
            grib.write_bytes(_minimal_grib2_section7([2]))
            with patch.object(lowmem.shutil, "which", return_value="/usr/bin/grib_get"), \
                    patch.object(lowmem, "_ensure_memory_headroom"), \
                    patch.object(sat, "_download_product", return_value=b"payload"), \
                    patch.object(storage, "_write_satellite_grib_to_ram", return_value=grib), \
                    patch.object(index_sampler, "_reference_pixel", return_value=(0, 0)), \
                    patch.object(core, "run_cmd", side_effect=run_cmd):
                result = lowmem._sample_product(core, options, product, "token")

        self.assertEqual(result["sampler"], "python-grib2-simple-packed")
        self.assertEqual(result["cloud_pct"], 100.0)
        self.assertEqual(result["valid_samples"], 17)
        self.assertEqual(result["sample_count"], 17)
        self.assertEqual(result["packing_type"], "grid_simple")
        self.assertEqual(len(calls), 1)
        self.assertFalse(any("-i" in call or "-l" in call for call in calls))

    def test_second_order_sampler_never_uses_full_field_decode(self):
        options = {
            "latitude": 48.9311,
            "longitude": 14.3553,
            "satellite_radius_km": 30,
        }
        product = {"product_id": "test-product", "time": "2026-09-14T05:30:00Z"}
        calls = []

        payload = _second_order_payload(
            group_widths=[0],
            group_lengths=[7],
            first_orders=[0],
            residual_groups=[[0] * 7],
            width_of_widths=1,
            width_of_lengths=3,
            width_of_first_orders=1,
        )

        def run_cmd(argv, timeout=0):
            calls.append(list(argv))
            self.assertIn("-p", argv)
            self.assertNotIn("-i", argv)
            self.assertNotIn("-l", argv)
            key = argv[argv.index("-p") + 1]
            if key == lowmem._METADATA_KEYS:
                return "space_view 5568 5568 0 1 0 0 0 0 50002 grid_second_order 0 0 0 0 0\n"
            if key == lowmem._SECOND_ORDER_KEYS:
                return "1 1 7 1 3 2 0 9\n"
            if key == "widthOfSPD":
                return "8\n"
            if key == "SPD":
                return "2 2 0\n"
            raise AssertionError(key)

        with tempfile.TemporaryDirectory() as tmp:
            grib = Path(tmp) / "sample.grib2"
            grib.write_bytes(_minimal_grib2_payload(payload))
            with patch.object(lowmem.shutil, "which", return_value="/usr/bin/grib_get"), \
                    patch.object(lowmem, "_ensure_memory_headroom"), \
                    patch.object(sat, "_download_product", return_value=b"payload"), \
                    patch.object(storage, "_write_satellite_grib_to_ram", return_value=grib), \
                    patch.object(index_sampler, "_reference_pixel", return_value=(0, 8)), \
                    patch.object(core, "run_cmd", side_effect=run_cmd):
                result = lowmem._sample_product(core, options, product, "token")

        self.assertEqual(result["sampler"], "python-grib2-second-order-stream")
        self.assertEqual(result["cloud_pct"], 100.0)
        self.assertEqual(result["center_cloud_pct"], 100.0)
        self.assertEqual(result["packing_template"], 50002)
        self.assertEqual(result["order_of_spd"], 2)
        self.assertFalse(any("-i" in call or "-l" in call for call in calls))

    def test_unsupported_packing_fails_before_data_decode(self):
        with tempfile.TemporaryDirectory() as tmp:
            grib = Path(tmp) / "sample.grib2"
            grib.write_bytes(_minimal_grib2_section7([2]))
            with patch.object(
                core,
                "run_cmd",
                return_value="space_view 5568 5568 0 1 0 0 0 0 40 grid_jpeg 8 0 0 0 0\n",
            ):
                with self.assertRaisesRegex(RuntimeError, "nepodporovane GRIB2 baleni"):
                    lowmem._metadata(core, grib)


if __name__ == "__main__":
    unittest.main()
