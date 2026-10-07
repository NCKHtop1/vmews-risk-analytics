from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class SolutionAIWorkflowContracts(unittest.TestCase):
    def test_delayed_live_schedule_is_recovery_not_green_noop(self):
        flow = (ROOT / ".github/workflows/solution-ai-live-price.yml").read_text()
        self.assertIn("publishing one recovery snapshot", flow)
        self.assertNotIn('echo "Outside SoluTION.AI live window: $now"\n            exit 0', flow)
        self.assertIn("sourceTime", flow)
        self.assertIn("source_age<=25", flow)
        self.assertIn("generated_age<=6", flow)
        self.assertIn("policy='LIVE'", flow)
        self.assertIn("source_age<=96*60", flow)

    def test_market_guard_is_independent_solution_live_recovery_path(self):
        guard = (ROOT / ".github/workflows/market-realtime-guard.yml").read_text()
        self.assertIn("SoluTION.AI independent live prices", guard)
        self.assertIn("solution-ai-live-price.yml", guard)
        self.assertIn("solution-ai-live-data/solution-ai/live.json", guard)
        self.assertIn("source_age<=25", guard)
        self.assertIn("generated_age<=6", guard)
        self.assertIn("SoluTION live freshness OK", guard)

    def test_live_guard_checks_real_market_source_outside_session(self):
        guard = (ROOT / ".github/workflows/solution-ai-live-guard.yml").read_text()
        self.assertNotIn("Outside SoluTION.AI live window; no recovery required.", guard)
        self.assertIn("sourceTime", guard)
        self.assertIn("SAME_DAY_SESSION", guard)
        self.assertIn("LAST_COMPLETED_SESSION", guard)
        self.assertIn("gh workflow run solution-ai-live-price.yml", guard)

    def test_production_smoke_uses_source_time_not_only_generation_time(self):
        smoke = (ROOT / ".github/workflows/solution-ai-production-smoke.yml").read_text()
        self.assertIn("sourceTime", smoke)
        self.assertIn("source_age", smoke)
        self.assertIn("SAME_DAY_SESSION", smoke)
        self.assertIn("push:", smoke)

    def test_core_optional_flow_contract_is_stale_safe(self):
        test = (ROOT / "scripts/forecast_v13_market_model_test_v28.py").read_text()
        self.assertIn("test_stale_institutional_flow_is_inert", test)
        self.assertIn('"foreign": foreign', test)
        self.assertIn("self.assertEqual(signal, 0.0)", test)
        self.assertNotIn('self.assertFalse(foreign["stale"])', test)


if __name__ == "__main__":
    unittest.main()
