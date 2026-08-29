"""Point-in-time and numerical regression checks for V17 live evidence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from forecast_v17_live_intelligence import (
    decision_news_contexts,
    decision_prior,
    financial_decision_contexts,
    flow_decision_signal,
    fund_decision_contexts,
    typed_flow_summary,
)


class FundDecisionTimeTest(unittest.TestCase):
    def _history(self, path: Path, *, generated: str = "2026-08-23T02:28:30+07:00") -> None:
        payload = {
            "snapshots": [
                {
                    "asOf": "2026-08-22",
                    "generatedAt": "2026-08-22T23:45:00+07:00",
                    "holdings": [{"symbol": "FPT", "weight": .95}],
                },
                {
                    "asOf": "2026-08-23",
                    "generatedAt": generated,
                    "weightUnit": "FRACTION_OF_NAV",
                    "fundsWithMappedHoldings": 2,
                    "holdingRows": 3,
                    "holdings": [
                        {"fundId": 1, "fundCode": "ALPHA", "fundName": "Alpha", "symbol": "FPT", "weight": .08,
                         "reportDate": "2026-08-11", "navMomentum20": .055, "navVolatility20": .008},
                        {"fundId": 2, "fundCode": "BETA", "fundName": "Beta", "symbol": "FPT", "weight": .05,
                         "reportDate": "2026-08-11", "navMomentum20": .034, "navVolatility20": .009},
                        {"fundId": 2, "fundCode": "BETA", "fundName": "Beta", "symbol": "ACB", "weight": .03,
                         "reportDate": "2026-08-11", "navMomentum20": -.012, "navVolatility20": .009},
                    ],
                },
            ]
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_weekend_disclosure_available_before_next_session_is_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "funds.json"
            self._history(path)
            contexts, audit = fund_decision_contexts(
                {"FPT", "ACB"}, "2026-08-21", "2026-08-23T10:00:00+07:00", path=path
            )
        self.assertEqual(audit["snapshotCount"], 1)
        self.assertEqual(audit["postCloseSymbols"], 2)
        self.assertEqual(audit["historicalBackfillRows"], 0)
        self.assertTrue(contexts["FPT"]["collectedAfterForecast"])
        self.assertFalse(contexts["FPT"]["availableForForecast"])
        self.assertTrue(contexts["FPT"]["availableForScenario"])
        self.assertTrue(contexts["FPT"]["scenarioEligible"])
        self.assertFalse(contexts["FPT"]["usedByForecast"])
        self.assertFalse(contexts["FPT"]["fitEligible"])
        self.assertEqual(contexts["FPT"]["fundCount"], 2)
        self.assertGreater(contexts["FPT"]["signalScore"], contexts["ACB"]["signalScore"])

    def test_future_collection_is_rejected_even_when_report_date_is_old(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "funds.json"
            self._history(path, generated="2026-08-23T12:00:00+07:00")
            contexts, audit = fund_decision_contexts(
                {"FPT"}, "2026-08-21", "2026-08-23T10:00:00+07:00", path=path
            )
        self.assertEqual(contexts, {})
        self.assertEqual(audit["snapshotCount"], 0)

    def test_legacy_snapshot_without_unit_contract_is_not_silently_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "funds.json"
            self._history(path)
            contexts, audit = fund_decision_contexts(
                {"FPT"}, "2026-08-21", "2026-08-23T10:00:00+07:00", path=path
            )
        self.assertEqual(audit["snapshotCount"], 1)
        self.assertLess(contexts["FPT"]["largestReportedWeight"], .10)


class FlowAndFinancialContextTest(unittest.TestCase):
    def test_proprietary_billions_are_converted_to_vnd(self) -> None:
        rows = [
            {"date": "2026-08-12", "propBuyValue": 16, "propSellValue": 26, "propNetValue": -10},
            {"date": "2026-08-13", "propBuyValue": 23, "propSellValue": 84, "propNetValue": -61},
        ]
        flow = typed_flow_summary(rows, "proprietary", "2026-08-21")
        self.assertEqual(flow["net1"], -61_000_000_000)
        self.assertEqual(flow["net5"], -71_000_000_000)
        self.assertEqual(flow["ageSessions"], 6)
        self.assertTrue(flow["stale"])

    def test_flow_age_uses_certified_exchange_holidays(self) -> None:
        rows = [
            {
                "date": "2026-04-24",
                "foreignBuyValue": 120,
                "foreignSellValue": 20,
                "foreignNetValue": 100,
            }
        ]
        flow = typed_flow_summary(rows, "foreign", "2026-04-28")
        self.assertEqual(flow["latestDate"], "2026-04-24")
        self.assertEqual(flow["ageSessions"], 1)
        self.assertFalse(flow["stale"])

    def test_missing_flow_is_not_replaced_with_a_zero_observation(self) -> None:
        flow = typed_flow_summary([], "foreign", "2026-08-21")
        self.assertFalse(flow["available"])
        self.assertNotIn("net1", flow)
        placeholder = typed_flow_summary([
            {"date": "2026-08-21", "foreignBuyValue": 0, "foreignSellValue": 0, "foreignNetValue": 0}
        ], "foreign", "2026-08-21")
        self.assertFalse(placeholder["available"])
        self.assertNotIn("net1", placeholder)

    def test_stale_flow_retains_real_value_but_cannot_drive_a_decision(self) -> None:
        fresh = {
            "foreign": {"available": True, "stale": False, "net5": 100, "gross5": 200, "ageSessions": 0},
        }
        stale = {
            "foreign": {"available": True, "stale": True, "net5": 100, "gross5": 200, "ageSessions": 7},
        }
        score1, confidence1 = flow_decision_signal(fresh)
        score2, confidence2 = flow_decision_signal(stale)
        self.assertNotEqual(score1, 0)
        self.assertGreater(confidence1, 0)
        self.assertEqual(score2, 0)
        self.assertEqual(confidence2, 0)

    def test_financial_snapshot_must_exist_before_decision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "financial.json"
            path.write_text(json.dumps({
                "generatedAt": "2026-08-24T08:00:00+07:00",
                "symbols": {"FPT": {"fundamental": {"status": "PASS", "profitQoQ": .2}}},
            }), encoding="utf-8")
            contexts, audit = financial_decision_contexts(
                {"FPT"}, "2026-08-23T10:00:00+07:00", path=path
            )
        self.assertEqual(contexts, {})
        self.assertTrue(audit["futureSnapshotRejected"])


class AfterCloseNewsTest(unittest.TestCase):
    def test_verified_weekend_headline_enters_next_session_decision(self) -> None:
        events = [{
            "symbol": "ACB", "date": "2026-08-24", "publishedAt": "2026-08-22T10:00:00+07:00",
            "title": "ACB: lợi nhuận tăng trưởng", "sentiment": .8, "materiality": .7,
            "credibility": .9, "novelty": .8, "label": "POS", "eventType": "EARNINGS",
        }]
        contexts, audit = decision_news_contexts(events, "2026-08-21", "2026-08-23T10:00:00+07:00")
        self.assertEqual(audit["articles"], 1)
        self.assertEqual(audit["nextSession"], "2026-08-24")
        self.assertTrue(contexts["ACB"]["scenarioEligible"])
        self.assertFalse(contexts["ACB"]["usedByForecast"])
        self.assertGreater(contexts["ACB"]["signalScore"], 0)
        prior = decision_prior(None, None, None, .025, 5, news=contexts["ACB"])
        self.assertGreater(prior["components"]["EVENT"], 0)

    def test_future_headline_is_never_used_even_if_effective_session_matches(self) -> None:
        events = [{
            "symbol": "ACB", "date": "2026-08-24", "publishedAt": "2026-08-23T11:00:00+07:00",
            "title": "ACB: lợi nhuận tăng trưởng", "sentiment": .9,
        }]
        contexts, audit = decision_news_contexts(events, "2026-08-21", "2026-08-23T10:00:00+07:00")
        self.assertEqual(contexts, {})
        self.assertEqual(audit["futurePublicationsRejected"], 1)


class DecisionPriorBoundsTest(unittest.TestCase):
    def test_valid_fund_signal_creates_a_context_scenario_only(self) -> None:
        prior = decision_prior(
            {"inferenceEligible": True, "signalScore": .72, "confidence": .75},
            {},
            None,
            .023,
            5,
        )
        self.assertEqual(prior["status"], "ACTIVE")
        self.assertGreater(prior["components"]["FUND"], 0)
        self.assertGreater(prior["totalReturn"], 0)
        self.assertFalse(prior["centralForecastEligible"])
        self.assertIn("NOT_APPLIED_TO_CENTRAL_FORECAST", prior["policy"])

    def test_prior_cannot_exceed_the_issuer_volatility_cap(self) -> None:
        prior = decision_prior(
            {"inferenceEligible": True, "signalScore": 100.0, "confidence": 100.0},
            {"foreign": {"available": True, "net5": 1e12, "gross5": 1, "ageSessions": 0}},
            {"inferenceEligible": True, "signalScore": 100.0, "confidence": 100.0},
            .09,
            5,
        )
        self.assertLessEqual(abs(prior["totalReturn"]), prior["maximumAbsoluteReturn"] + 1e-12)
        self.assertLessEqual(prior["maximumAbsoluteReturn"], .012)
        self.assertFalse(prior["independentlyBacktested"])
        self.assertFalse(prior["centralForecastEligible"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
