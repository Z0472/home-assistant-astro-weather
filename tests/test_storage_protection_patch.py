"""Regression tests for SD-card protection in Astro Weather Backend 12.4.0."""
import bz2
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))

import astro_weather_backend as core
import storage_protection_patch as storage


class StorageProtectionTests(unittest.TestCase):
    def test_satellite_zip_is_extracted_only_into_ram_tmpfs(self):
        payload = io.BytesIO()
        grib = b"GRIB" + bytes([0xFF, 0xFF, 0x03, 0x02]) + b"test-payload"
        with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("operational_clm.bin", grib)

        with tempfile.TemporaryDirectory() as ram_dir, patch.object(
            storage, "RAM_TMP_DIR", Path(ram_dir)
        ), patch.object(storage, "RAM_RESERVE_BYTES", 0):
            path = storage._write_satellite_grib_to_ram(payload.getvalue())
            try:
                self.assertEqual(path.parent, Path(ram_dir))
                self.assertEqual(path.read_bytes(), grib)
                self.assertFalse(any(Path(ram_dir).glob("*.zip")))
            finally:
                path.unlink(missing_ok=True)

    def test_aladin_uncompressed_grib_uses_ram_not_sd_cache_directory(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            sd_dir = root / "sd-cache"
            ram_dir = root / "ram"
            sd_dir.mkdir()
            ram_dir.mkdir()

            bz_path = sd_dir / "ALADCZ1K4opendata_test_SURFNEBUL_TOTALE.grb.bz2"
            bz_path.write_bytes(bz2.compress(b"temporary uncompressed GRIB bytes"))
            seen_paths = []

            def fake_run_cmd(args, timeout=120):
                seen_paths.append(Path(args[-1]))
                return "42.0\n"

            with patch.object(storage, "RAM_TMP_DIR", ram_dir), patch.object(
                storage, "RAM_RESERVE_BYTES", 0
            ), patch.object(storage, "ALADIN_START_HEADROOM_BYTES", 0), patch.object(
                core, "grib_message_times", return_value=["2026-09-12T18:00:00Z"]
            ), patch.object(core, "run_cmd", side_effect=fake_run_cmd), patch.object(
                core, "grib_unit_and_global_max", return_value=("%", 100.0)
            ):
                result = storage._extract_aladin_point_series_ram(core, bz_path, 48.9, 14.3)

            self.assertEqual(result, {"2026-09-12T18:00:00Z": 42.0})
            self.assertTrue(seen_paths)
            self.assertTrue(all(path.parent == ram_dir for path in seen_paths))
            self.assertFalse(any(sd_dir.glob("*.grb")))
            self.assertFalse(any(ram_dir.iterdir()))

    def test_missing_ram_tmpfs_refuses_sd_fallback(self):
        with tempfile.TemporaryDirectory() as base:
            missing = Path(base) / "does-not-exist"
            with patch.object(storage, "RAM_TMP_DIR", missing):
                with self.assertRaisesRegex(RuntimeError, "odmitam zapisovat velky GRIB na SD kartu"):
                    storage._new_ram_file("astro_test_", ".grib")


if __name__ == "__main__":
    unittest.main()
