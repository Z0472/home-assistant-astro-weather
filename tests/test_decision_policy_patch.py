"""Regression tests for the 12.4.18 time-aware decision policy."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astro_weather_backend"))

import astro_weather_backend as core
import decision_policy_patch as policy


NOW = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)


class DecisionPolicyTests(unittest.TestCase):
    def setUp(self):
        policy._BASELINE_GENERATED_AT = None
        policy._BASELINE_DECISION = None
        policy._LAST_OPTIONS = {}
        self.options = {
            "disagreement_warn": 35,
            "disagreement_bad": 55,
            "spatial_radius_km": 30,
        }

    def _night(self, hours_to_start: float, decision: str = "good") -> dict:
        start = NOW + timedelta(hours=hours_to_start)
        label = "SPUSTIT" if decision == "good" else "NESPOUŠTĚT"
        return {
            "decision": decision,
            "label": label,
            "reason": "základní modelové rozhodnutí",
            "darkStart": core.iso_z(start),
            "launchBlock": {
                "start": core.iso_z(start),
                "end": core.iso_z(start + timedelta(hours=5)),
                "hours": 5.0,
            },
            "bestBlock": {
                "start": core.iso_z(start),
                "end": core.iso_z(start + timedelta(hours=5)),
                "hours": 5.0,
            },
            "hours": [],
        }

    def _decision(self, hours_to_start: float, decision: str = "good") -> dict:
        night = self._night(hours_to_start, decision)
        return {
            "state": night["label"],
            "machine_state": decision,
            "generated_at": core.iso_z(NOW),
            "reason": night["reason"],
            "daily": [night],
        }

    def _satellite(self, **overrides) -> dict:
        value = {
            "available": True,
            "cloud_pct": 90.0,
            "center_cloud_pct": 100.0,
            "trend": "steady",
            "trend_slope_pph": 0.0,
            "nowcast_confidence_pct": 85.0,
            "as_of": core.iso_z(NOW),
        }
        value.update(overrides)
        return value

    def test_spatial_boundary_is_informational_more_than_three_hours_before_start(self):
        called = []

        def original(core_arg, options, result, spatial_info):
            called.append(True)
            result.update(decision="uncertain", label="NEJISTÉ", spatialAdjusted=True)

        wrapped = policy._spatial_policy_wrapper(original)
        result = self._night(8.0)
        with patch.object(core, "utc_now", return_value=NOW):
            wrapped(core, self.options, result, {"state": "incoming", "etaMinutes": 60})

        self.assertEqual(result["decision"], "good")
        self.assertEqual(result["label"], "SPUSTIT")
        self.assertEqual(result["spatialDecisionRole"], "informational")
        self.assertFalse(called)

    def test_spatial_boundary_can_adjust_within_three_hours(self):
        called = []

        def original(core_arg, options, result, spatial_info):
            called.append(True)
            result.update(decision="uncertain", label="NEJISTÉ", spatialAdjusted=True)

        wrapped = policy._spatial_policy_wrapper(original)
        result = self._night(2.0)
        with patch.object(core, "utc_now", return_value=NOW):
            wrapped(core, self.options, result, {"state": "incoming", "etaMinutes": 60})

        self.assertEqual(result["decision"], "uncertain")
        self.assertEqual(result["spatialDecisionRole"], "active")
        self.assertTrue(called)

    def test_satellite_is_informational_more_than_six_hours_before_start(self):
        with patch.object(core, "utc_now", return_value=NOW), \
                patch.object(policy, "_model_cloud_at", return_value=10.0):
            out = policy._apply_satellite_policy(
                core, self.options, self._decision(8.0), self._satellite(), {"agreement_pct": 10.0}
            )

        self.assertEqual(out["machine_state"], "good")
        self.assertEqual(out["daily"][0]["decision"], "good")
        self.assertEqual(out["satelliteDecisionPolicy"]["role"], "informational")
        self.assertFalse(out["satelliteDecisionPolicy"]["changed"])

    def test_satellite_is_confidence_only_between_three_and_six_hours(self):
        with patch.object(core, "utc_now", return_value=NOW), \
                patch.object(policy, "_model_cloud_at", return_value=10.0):
            out = policy._apply_satellite_policy(
                core, self.options, self._decision(4.0), self._satellite(), {"agreement_pct": 5.0}
            )

        self.assertEqual(out["machine_state"], "good")
        self.assertEqual(out["satelliteDecisionPolicy"]["role"], "confidence")
        self.assertFalse(out["satelliteDecisionPolicy"]["changed"])

    def test_satellite_nowcast_can_soften_good_between_one_and_three_hours(self):
        with patch.object(core, "utc_now", return_value=NOW), \
                patch.object(policy, "_model_cloud_at", return_value=10.0):
            out = policy._apply_satellite_policy(
                core,
                self.options,
                self._decision(2.0),
                self._satellite(cloud_pct=85.0, center_cloud_pct=100.0),
                {"agreement_pct": 20.0},
            )

        self.assertEqual(out["machine_state"], "uncertain")
        self.assertEqual(out["daily"][0]["decision"], "uncertain")
        self.assertEqual(out["satelliteDecisionPolicy"]["role"], "nowcast")
        self.assertTrue(out["satelliteDecisionPolicy"]["changed"])

    def test_live_satellite_has_strong_weight_inside_one_hour(self):
        with patch.object(core, "utc_now", return_value=NOW), \
                patch.object(policy, "_model_cloud_at", return_value=15.0):
            out = policy._apply_satellite_policy(
                core,
                self.options,
                self._decision(0.5),
                self._satellite(cloud_pct=88.0, center_cloud_pct=100.0, trend="steady"),
                {"agreement_pct": 15.0},
            )

        self.assertEqual(out["machine_state"], "uncertain")
        self.assertEqual(out["satelliteDecisionPolicy"]["role"], "strong")
        self.assertTrue(out["satelliteDecisionPolicy"]["changed"])

    def test_convincing_clearing_inside_one_hour_does_not_block_start(self):
        with patch.object(core, "utc_now", return_value=NOW), \
                patch.object(policy, "_model_cloud_at", return_value=15.0):
            out = policy._apply_satellite_policy(
                core,
                self.options,
                self._decision(0.5),
                self._satellite(
                    cloud_pct=80.0,
                    center_cloud_pct=100.0,
                    trend="clearing",
                    trend_slope_pph=-120.0,
                    nowcast_confidence_pct=85.0,
                ),
                {"agreement_pct": 30.0},
            )

        self.assertEqual(out["machine_state"], "good")
        self.assertEqual(out["satelliteDecisionPolicy"]["role"], "strong")
        self.assertFalse(out["satelliteDecisionPolicy"]["changed"])
        self.assertLessEqual(out["satelliteDecisionPolicy"]["projected_cloud_pct"], 25.0)

    def test_missing_satellite_never_creates_uncertain(self):
        satellite = {
            "available": False,
            "reason": "Poslední CLM snímek je příliš starý (59 min).",
        }
        with patch.object(core, "utc_now", return_value=NOW):
            out = policy._apply_satellite_policy(
                core, self.options, self._decision(0.5), satellite, {}
            )

        self.assertEqual(out["machine_state"], "good")
        self.assertEqual(out["satelliteDecisionPolicy"]["role"], "unavailable")
        self.assertFalse(out["satelliteDecisionPolicy"]["changed"])

    def test_baseline_restores_good_after_previous_satellite_downgrade(self):
        base = self._decision(0.5)
        stored = policy._baseline_for(base, fresh=True)
        with patch.object(core, "utc_now", return_value=NOW), \
                patch.object(policy, "_model_cloud_at", return_value=10.0):
            risky = policy._apply_satellite_policy(
                core, self.options, stored, self._satellite(), {"agreement_pct": 10.0}
            )
        self.assertEqual(risky["machine_state"], "uncertain")

        restored = policy._baseline_for(risky, fresh=False)
        self.assertEqual(restored["machine_state"], "good")
        self.assertEqual(restored["daily"][0]["decision"], "good")
        self.assertNotIn("satelliteDecisionPolicy", restored)


if __name__ == "__main__":
    unittest.main()
