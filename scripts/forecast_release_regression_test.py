"""Regression cases for changing fund disclosures and exact horizon diagnostics."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from forecast_horizon_gate_diagnostics import describe_horizon_price_gate
from forecast_v13_market_model import horizon_price_gate
from forecast_v13_market_model_test_v28 import assert_fund_source_reconciliation


class FundDisclosureRegressionTest(unittest.TestCase):
    def setUp(self):
        rows = [
            {"symbol": "FPT", "fundId": 1, "reportDate": "2026-09-01", "weight": .08},
            {"symbol": "FPT", "fundId": 2, "reportDate": "2026-09-01", "weight": .0032},
        ]
        self.history = {"snapshots": [{
            "asOf": "2026-09-08", "generatedAt": "2026-09-08T09:00:00+07:00",
            "weightUnit": "FRACTION_OF_NAV", "holdings": rows,
        }]}
        self.context = {
            "asOf": "2026-09-08", "collectedAt": "2026-09-08T09:00:00+07:00",
            "fundCount": 2, "reportedWeight": .0832, "averageReportedWeight": .0416,
            "largestReportedWeight": .08, "holdings": copy.deepcopy(rows),
        }
        self.decision = "2026-09-08T21:59:12+07:00"

    def test_updated_weights_and_holder_count_reconcile_without_frozen_live_values(self):
        assert_fund_source_reconciliation(self, self.context, self.history, self.decision)

    def test_stale_average_or_wrong_fund_cannot_pass(self):
        for field, value in [("averageReportedWeight", .042094117647058824), ("fundCount", 17)]:
            context = {**self.context, field: value}
            with self.subTest(field=field), self.assertRaises(AssertionError):
                assert_fund_source_reconciliation(self, context, self.history, self.decision)
        self.context["holdings"][0]["fundId"] = 999
        with self.assertRaises(AssertionError):
            assert_fund_source_reconciliation(self, self.context, self.history, self.decision)

    def test_future_collection_and_unmatched_source_cannot_pass(self):
        with self.assertRaises(AssertionError):
            assert_fund_source_reconciliation(self, self.context, self.history, "2026-09-08T08:59:59+07:00")
        self.context["collectedAt"] = "2026-09-08T10:00:00+07:00"
        with self.assertRaises(AssertionError):
            assert_fund_source_reconciliation(self, self.context, self.history, self.decision)


class HorizonDiagnosticsRegressionTest(unittest.TestCase):
    def test_all_published_horizon_diagnostics_agree_with_the_sealed_gate(self):
        market = json.loads((Path(__file__).resolve().parents[1] / "data/forecast-market-v13.json").read_text())
        for horizon, result in market["backtest"]["horizons"].items():
            audit = result["metrics"]
            walk = market["model"]["horizons"][horizon]["walkForwardAudit"]
            passed = horizon_price_gate(audit, walk)
            diagnostic = describe_horizon_price_gate(int(horizon), audit, walk, passed)
            with self.subTest(horizon=horizon):
                self.assertEqual(diagnostic["horizon"], int(horizon))
                self.assertEqual(not diagnostic["failedChecks"], passed)
                self.assertEqual(diagnostic["passed"], passed)
                json.dumps(diagnostic, allow_nan=False)

    def test_sparse_horizon_request_and_failed_latest_fold_remain_explicit(self):
        market = json.loads((Path(__file__).resolve().parents[1] / "data/forecast-market-v13.json").read_text())
        audit = copy.deepcopy(market["backtest"]["horizons"]["5"]["metrics"])
        walk = copy.deepcopy(market["model"]["horizons"]["5"]["walkForwardAudit"])
        walk["folds"][-1]["executableMAESkill"] = -.001
        passed = horizon_price_gate(audit, walk)
        diagnostic = describe_horizon_price_gate(5, audit, walk, passed)
        self.assertFalse(passed)
        self.assertEqual(diagnostic["horizon"], 5)
        self.assertIn("latestWalkForwardExecutableMAE>0", diagnostic["failedChecks"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
