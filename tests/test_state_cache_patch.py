"""Regression tests for 12.3.2 last-good state guard."""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

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
                "backend_version": "12.3.1",
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
                "backend_version": "12.3.1",
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

                with patch.object(core, "APP_VERSION", "12.3.2"), patch.object(
                    core, "publish_homeassistant_entities"
                ) as publish:
                    restored = cache.restore_last_good_state(core, self.options)

        self.assertTrue(restored)
        self.assertEqual(core.DECISION_STATE["state"], "NEJISTÉ")
        self.assertTrue(core.DECISION_STATE["refreshing"])
        self.assertTrue(core.DECISION_STATE["restored_from_cache"])
        self.assertEqual(core.DECISION_STATE["backend_version"], "12.3.2")
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

    def test_periodic_refresh_never_publishes_transient_unavailable_over_valid_state(self):
        generated = self.now - timedelta(minutes=10)
        self._seed(generated)

        original_refresh = core.refresh_once
        original_publish = core.publish_homeassistant_entities
        original_load_options = core.load_options
        original_main = core.main
        original_version = core.APP_VERSION
        original_server_version = core.Handler.server_version
        publisher = Mock()

        def invalid_refresh(options):
            weather = {
                "state": "error",
                "generated_at": core.iso_z(self.now),
                "location": {
                    "latitude": 48.9311,
                    "longitude": 14.3553,
                    "altitude": 500,
                },
                "forecast": [],
            }
            decision = {
                "state": "BEZ DAT",
                "machine_state": "unavailable",
                "generated_at": core.iso_z(self.now),
                "reason": "docasny vypadek modelu",
                "daily": [],
            }
            moon = {
                "state": "7.5 h",
                "attributes": {"daily": [{"date": "2026-09-12"}]},
            }
            with core.STATE_LOCK:
                core.STATE.clear()
                core.STATE.update(weather)
                core.DECISION_STATE.clear()
                core.DECISION_STATE.update(decision)
                core.MOON_STATE.clear()
                core.MOON_STATE.update(moon)
            core.publish_homeassistant_entities(options, weather, decision, moon)

        try:
            core.refresh_once = invalid_refresh
            core.publish_homeassistant_entities = publisher
            if hasattr(core, "_STATE_CACHE_PATCH_INSTALLED"):
                delattr(core, "_STATE_CACHE_PATCH_INSTALLED")

            with tempfile.TemporaryDirectory() as tmp, patch.object(
                core, "CACHE_DIR", Path(tmp)
            ), patch.object(core, "utc_now", return_value=self.now):
                cache.install(core)
                core.refresh_once(self.options)

            self.assertEqual(core.DECISION_STATE["state"], "NEJISTÉ")
            self.assertEqual(core.DECISION_STATE["machine_state"], "uncertain")
            self.assertTrue(core.DECISION_STATE["daily"])
            self.assertIn("last_refresh_error", core.DECISION_STATE)
            self.assertGreaterEqual(publisher.call_count, 2)
            for call in publisher.call_args_list:
                published_decision = call.args[2]
                self.assertNotEqual(published_decision.get("machine_state"), "unavailable")
                self.assertTrue(published_decision.get("daily"))
        finally:
            core.refresh_once = original_refresh
            core.publish_homeassistant_entities = original_publish
            core.load_options = original_load_options
            core.main = original_main
            core.APP_VERSION = original_version
            core.Handler.server_version = original_server_version
            if hasattr(core, "_STATE_CACHE_PATCH_INSTALLED"):
                delattr(core, "_STATE_CACHE_PATCH_INSTALLED")
            cache._REFRESH_FALLBACK = None


if __name__ == "__main__":
    unittest.main()
