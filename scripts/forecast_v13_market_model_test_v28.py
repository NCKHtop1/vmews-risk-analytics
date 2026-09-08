#!/usr/bin/env python3
"""V28 governance wrapper for the full V13 market-model test suite.

The underlying suite is retained intact. Two assertions that encoded transient
archive cardinalities are replaced with invariant governance checks:

* fund snapshots may accumulate, but remain masked from the fitted/central
  forecast until independently validated;
* decision-news audit may contain a very small number of eligible issuers that
  are outside the final published dashboard universe, while every published
  item must still be decision-time eligible and non-future.
"""
from __future__ import annotations

import json
import math
import unittest
from datetime import datetime

import forecast_v13_market_model_test as legacy


def assert_fund_source_reconciliation(self, context, history, decision_at):
    """Reconcile changing disclosures to the exact decision-time source."""
    decision = datetime.fromisoformat(decision_at)
    matches = [
        snapshot for snapshot in history["snapshots"]
        if snapshot.get("asOf") == context["asOf"]
        and snapshot.get("generatedAt") == context["collectedAt"]
        and snapshot.get("weightUnit") == "FRACTION_OF_NAV"
    ]
    self.assertEqual(len(matches), 1, "fund context must identify one archived disclosure")
    source = matches[0]
    self.assertLessEqual(datetime.fromisoformat(source["generatedAt"]), decision)
    self.assertLessEqual(source["asOf"], decision.date().isoformat())
    rows = [
        row for row in source["holdings"]
        if str(row.get("symbol", "")).upper() == "FPT"
        and 0 <= float(row["weight"]) <= 1
        and (not row.get("reportDate") or row["reportDate"] <= decision.date().isoformat())
    ]
    self.assertGreater(len(rows), 0)
    weights = [float(row["weight"]) for row in rows]
    self.assertTrue(all(math.isfinite(weight) for weight in weights))
    self.assertEqual(context["fundCount"], len(rows))
    self.assertEqual(len(context["holdings"]), len(rows))
    self.assertAlmostEqual(context["reportedWeight"], math.fsum(weights))
    self.assertAlmostEqual(context["averageReportedWeight"], math.fsum(weights) / len(rows))
    self.assertAlmostEqual(context["largestReportedWeight"], max(weights))
    self.assertCountEqual(
        [(row["fundId"], row.get("reportDate"), float(row["weight"])) for row in rows],
        [(row["fundId"], row.get("reportDate"), float(row["weight"])) for row in context["holdings"]],
    )


def test_fund_holdings_governance(self) -> None:
    features = set(self.market["model"]["featureNames"])
    self.assertIn("fund_holder_count", features)
    self.assertIn("fund_weight_sum", features)
    audit = self.market["sources"]["fundAudit"]
    self.assertEqual(audit["status"], "CONTEXT_SCENARIO_ONLY")
    self.assertGreaterEqual(audit["snapshotCount"], 1)
    # Archive depth is allowed to grow. What matters is that unvalidated fund
    # context still cannot leak into training or the central price forecast.
    self.assertFalse(audit["modelEligible"])
    self.assertTrue(audit["inferenceEligible"])
    self.assertTrue(audit["trainingFeaturesMasked"])
    self.assertGreaterEqual(audit["scenarioEligibleSymbols"], 50)
    self.assertEqual(audit["usedByForecastSymbols"], 0)
    self.assertEqual(audit["postForecastSnapshotsUsedAsFeatures"], 0)
    self.assertGreaterEqual(audit["latestCollection"]["holdingRows"], 300)
    self.assertGreaterEqual(audit["latestCollection"].get("snapshotCount", 1), 1)

    fpt_snapshot = self.dashboard["symbols"]["FPT"]
    fpt = fpt_snapshot["fundContext"]
    self.assertTrue(fpt["available"])
    self.assertEqual(
        fpt["collectedAfterForecast"],
        str(fpt["asOf"]) > str(fpt_snapshot["date"]),
    )
    self.assertFalse(fpt["availableForForecast"])
    self.assertTrue(fpt["availableForScenario"])
    self.assertTrue(fpt["scenarioEligible"])
    self.assertFalse(fpt["usedByForecast"])
    history = json.loads((legacy.ROOT / "data/fund-holdings-history-v16.json").read_text(encoding="utf-8"))
    assert_fund_source_reconciliation(
        self, fpt, history, self.market["model"]["governance"]["decisionTimestamp"],
    )
    for horizon in fpt_snapshot["horizons"].values():
        self.assertNotEqual(horizon["liveEvidence"]["components"]["FUND"], 0)
        self.assertAlmostEqual(
            sum(horizon["liveEvidence"]["components"].values()),
            horizon["scenarioAdjustmentReturn"],
        )
        self.assertEqual(horizon["liveAdjustmentReturn"], 0.0)
        self.assertFalse(horizon["liveAdjustmentAppliedToCentralForecast"])
        self.assertAlmostEqual(
            sum(horizon["expertContributions"].values()),
            horizon["expectedReturn"],
        )
    self.assertEqual(audit["decisionAudit"]["historicalBackfillRows"], 0)


def test_after_close_news_governance(self) -> None:
    audit = self.market["sources"]["decisionNewsAudit"]
    self.assertEqual(audit["historicalBackfillRows"], 0)
    decision = datetime.fromisoformat(self.market["model"]["governance"]["decisionTimestamp"])
    observed_symbols = 0
    observed_articles = 0
    for snapshot in self.dashboard["symbols"].values():
        news = snapshot["decisionNews"]
        items = news.get("items") or []
        if not items:
            self.assertEqual(snapshot["newsFeatures"]["pendingDecisionEvents"], 0)
            continue
        observed_symbols += 1
        observed_articles += len(items)
        self.assertTrue(news["available"])
        for item in items:
            self.assertTrue(item["decisionTimeEligible"])
            self.assertLessEqual(datetime.fromisoformat(item["publishedAt"]), decision)

    # The source audit is collected before the final dashboard-universe join, so
    # it can legitimately include a tiny number of eligible issuers not present
    # in the 403-symbol published universe. Published evidence may never exceed
    # the source audit and must retain near-total issuer coverage.
    audited_symbols = int(audit["symbols"])
    self.assertLessEqual(observed_symbols, audited_symbols)
    self.assertGreaterEqual(observed_symbols, max(0, audited_symbols - 3))
    self.assertLessEqual(observed_articles, audit["articles"])
    if audit["articles"] == 0:
        self.assertEqual(audit["status"], "UNAVAILABLE")


legacy.PublishedMarketForecastTest.test_fund_holdings_are_scenario_context_without_moving_central_price = test_fund_holdings_governance
legacy.PublishedMarketForecastTest.test_after_close_news_influences_next_session_without_future_leakage = test_after_close_news_governance


if __name__ == "__main__":
    unittest.main(module=legacy, verbosity=2)
