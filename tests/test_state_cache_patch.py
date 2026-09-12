"""Regression tests for 12.3.1 last-good state restore."""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))

import astro_weather_backend as core
import state_cache_patch as cache


class StateCachePatchTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
        self.options = {
            "latitude": 48.9311,
            "longitude": 14.3553,
            "altitude": 500,
            "publish_homeassistant_entities": True,
        }

    def _seed(self, generated):
        with core.STATE_LOCK:
            core.STATE.clear()
            core.STATE.update({
                "state": "ok",
                "generated_at": core.iso_z(generated),
                "backend_version": "12.3.0",
                "location": {
                    "latitude": 48.9311,
                    "longitude": 14.3553,
                    "altitude": 500,
                    "timezone": "Europe/Prague",
                },
                "forecast": [{"datetime": core.iso_z(generated)}],
            })
            core.DECISION_STATE.clear()
            core.DECISION_STATE.update({
                "state": "NEJISTÉ",
                "machine_state": "uncertain",
                "generated_at": core.iso_z(generated),
                "backend_version": "12.3.0",
                "daily": [{"decision": "uncertain", "label": "NEJISTÉ"}],
            })
            core.MOON_STATE.clear()
            core.MOON_STATE.update({
                "state": "7.5 h",
                "attributes": {"daily": [{"date": "2026-09-12"}]},
            })

    def test_fresh_cache_is_published_immediately_after_restart(self):
        generated = self.now - timedelta(minutes=20)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(core, "CACHE_DIR", Path(tmp)), patch.object(
                core, "utc_now", return_value=self.now
            ):
                self._seed(generated)
                cache.save_last_good_state(core)

                with core.STATE_LOCK:
                    core.STATE.clear()
                    core.DECISION_STATE.clear()
                    core.MOON_STATE.clear()

                with patch.object(core, "APP_VERSION", "12.3.1"), patch.object(
                    core, "publish_homeassistant_entities"
                ) as publish:
                    restored = cache.restore_last_good_state(core, self.options)

        self.assertTrue(restored)
        self.assertEqual(core.DECISION_STATE["state"], "NEJISTÉ")
        self.assertTrue(core.DECISION_STATE["refreshing"])
        self.assertTrue(core.DECISION_STATE["restored_from_cache"])
        self.assertEqual(core.DECISION_STATE["backend_version"], "12.3.1")
        publish.assert_called_once()

    def test_cache_older_than_twelve_hours_is_not_restored(self):
        generated = self.now - timedelta(hours=13)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(core, "CACHE_DIR", Path(tmp)), patch.object(
                core, "utc_now", return_value=self.now
            ):
                self._seed(generated)
                cache.save_last_good_state(core)
                with core.STATE_LOCK:
                    core.STATE.clear()
                    core.DECISION_STATE.clear()
                    core.MOON_STATE.clear()
                with patch.object(core, "publish_homeassistant_entities") as publish:
                    restored = cache.restore_last_good_state(core, self.options)

        self.assertFalse(restored)
        publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
