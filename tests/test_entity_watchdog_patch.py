"""Regression tests for Home Assistant entity self-healing in 12.4.0."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))

import astro_weather_backend as core
import entity_watchdog_patch as watchdog


class EntityWatchdogPatchTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 12, 17, 0, tzinfo=timezone.utc)
        self.generated = core.iso_z(self.now)
        self.options = {
            "publish_homeassistant_entities": True,
            "weather_entity": "sensor.astro_weather_detail",
            "decision_entity": "sensor.astro_vhodnost_foceni",
            "moon_entity": "sensor.mesic_foceni_predpoved",
        }
        with core.STATE_LOCK:
            core.STATE.clear()
            core.STATE.update({
                "state": "ok",
                "generated_at": self.generated,
                "backend_version": "12.4.0",
                "forecast": [{"datetime": self.generated}],
            })
            core.DECISION_STATE.clear()
            core.DECISION_STATE.update({
                "state": "NEJISTÉ",
                "machine_state": "uncertain",
                "generated_at": self.generated,
                "backend_version": "12.4.0",
                "daily": [{"decision": "uncertain", "label": "NEJISTÉ"}],
            })
            core.MOON_STATE.clear()
            core.MOON_STATE.update({
                "state": "7.5 h",
                "attributes": {"daily": [{"date": "2026-09-12"}]},
            })

    def _healthy_document(self, entity_id):
        snapshot = watchdog._snapshot(core)
        payloads = watchdog._entity_payloads(self.options, *snapshot)
        expected = next(row for row in payloads if row["entity_id"] == entity_id)
        return {
            "entity_id": entity_id,
            "state": expected["state"],
            "attributes": expected["attributes"],
        }

    def test_missing_decision_is_republished_independently(self):
        def ha_state(_core, entity_id):
            if entity_id == self.options["decision_entity"]:
                return None
            return self._healthy_document(entity_id)

        with patch.object(watchdog, "_ha_state_document", side_effect=ha_state), patch.object(
            core, "publish_home_assistant_state"
        ) as publish:
            repaired = watchdog.republish_missing_homeassistant_entities(core, self.options)

        self.assertTrue(repaired)
        publish.assert_called_once()
        self.assertEqual(publish.call_args.args[0], self.options["decision_entity"])
        self.assertEqual(publish.call_args.args[1], "NEJISTÉ")

    def test_stale_decision_is_republished_even_when_entity_exists(self):
        def ha_state(_core, entity_id):
            document = self._healthy_document(entity_id)
            if entity_id == self.options["decision_entity"]:
                document["attributes"] = dict(document["attributes"])
                document["attributes"]["generated_at"] = "2026-09-12T16:00:00Z"
            return document

        with patch.object(watchdog, "_ha_state_document", side_effect=ha_state), patch.object(
            core, "publish_home_assistant_state"
        ) as publish:
            repaired = watchdog.republish_missing_homeassistant_entities(core, self.options)

        self.assertTrue(repaired)
        publish.assert_called_once()
        self.assertEqual(publish.call_args.args[0], self.options["decision_entity"])

    def test_missing_weather_is_repaired_even_when_decision_is_healthy(self):
        def ha_state(_core, entity_id):
            if entity_id == self.options["weather_entity"]:
                return None
            return self._healthy_document(entity_id)

        with patch.object(watchdog, "_ha_state_document", side_effect=ha_state), patch.object(
            core, "publish_home_assistant_state"
        ) as publish:
            repaired = watchdog.republish_missing_homeassistant_entities(core, self.options)

        self.assertTrue(repaired)
        publish.assert_called_once()
        self.assertEqual(publish.call_args.args[0], self.options["weather_entity"])

    def test_healthy_entities_are_not_republished(self):
        with patch.object(
            watchdog,
            "_ha_state_document",
            side_effect=lambda _core, entity_id: self._healthy_document(entity_id),
        ), patch.object(core, "publish_home_assistant_state") as publish:
            repaired = watchdog.republish_missing_homeassistant_entities(core, self.options)

        self.assertFalse(repaired)
        publish.assert_not_called()

    def test_invalid_backend_decision_is_never_forced_into_home_assistant(self):
        with core.STATE_LOCK:
            core.DECISION_STATE.clear()
            core.DECISION_STATE.update({
                "state": "BEZ DAT",
                "machine_state": "unavailable",
                "generated_at": self.generated,
                "daily": [],
            })

        with patch.object(watchdog, "_ha_state_document") as check, patch.object(
            core, "publish_home_assistant_state"
        ) as publish:
            repaired = watchdog.republish_missing_homeassistant_entities(core, self.options)

        self.assertFalse(repaired)
        check.assert_not_called()
        publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
