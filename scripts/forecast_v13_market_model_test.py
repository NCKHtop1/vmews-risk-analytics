"""Regression and publication checks for executable Vietnam-equity forecasts."""

from __future__ import annotations

import json
import math
import sys
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from forecast_v13_market_model import (  # noqa: E402
    INTERCEPT_RETENTION,
    cost_aware_long_audit,
    directional_magnitude_blend,
    intercept_modes,
    select_directional_magnitude_blend,
    session_limit,
    snap_price,
    tick_size,
    _vn_direct_rows,
    _vn_direct_hose_rows,
    horizon_price_gate,
    preferred_ranking_horizon,
)
from forecast_v14_signal_audit import (  # noqa: E402
    attach_matured_reaction_priors,
    effective_trading_session,
    publication_timestamp,
    security_match,
)


class VietnamPriceGridTest(unittest.TestCase):
    def test_vndirect_decimal_quotes_are_normalized_to_integer_vnd(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        payload = {
            "data": [{
                "date": "2026-08-24", "open": 32.55, "high": 32.9,
                "low": 32.45, "close": 32.7, "adClose": 32.7,
                "nmVolume": 2_715_700, "floor": "HOSE",
            }]
        }
        response = Response()
        response.read = lambda: json.dumps(payload).encode("utf-8")
        with patch("forecast_v13_market_model.urlopen", return_value=response):
            row = _vn_direct_rows("BAF")[0]
        self.assertEqual(row["open"], 32_550)
        self.assertEqual(row["high"], 32_900)
        self.assertEqual(row["low"], 32_450)
        self.assertEqual(row["close"], 32_700)
        self.assertIsInstance(row["close"], int)

    def test_vndirect_bulk_route_groups_hose_quotes_in_one_response(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        payload = {"data": [
            {"code": "FPT", "date": "2026-08-26", "close": 72.6, "floor": "HOSE"},
            {"code": "FPT", "date": "2026-08-25", "close": 70.7, "floor": "HOSE"},
            {"code": "VCB", "date": "2026-08-26", "close": 61.2, "floor": "HOSE"},
        ]}
        response = Response()
        response.read = lambda: json.dumps(payload).encode("utf-8")
        with patch("forecast_v13_market_model.urlopen", return_value=response) as mocked:
            rows = _vn_direct_hose_rows()
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual([row["close"] for row in rows["FPT"]], [70_700, 72_600])
        self.assertEqual(rows["VCB"][-1]["close"], 61_200)

    def test_t2_market_intercept_is_regime_shrunk_before_holdout(self) -> None:
        self.assertEqual(INTERCEPT_RETENTION[2], .25)
        self.assertEqual(intercept_modes(2), ("BLEND_0.25",))
        self.assertEqual(intercept_modes(4), ("RAW",))

    def test_hose_price_bands(self) -> None:
        self.assertEqual(tick_size(9_990), 10)
        self.assertEqual(tick_size(10_000), 50)
        self.assertEqual(tick_size(49_950), 50)
        self.assertEqual(tick_size(50_000), 100)
        self.assertEqual(tick_size(68_300), 100)

    def test_hnx_and_upcom(self) -> None:
        self.assertEqual(tick_size(8_330, "HNX"), 100)
        self.assertEqual(tick_size(12_550, "UPCOM"), 100)

    def test_sub_tick_regression(self) -> None:
        self.assertEqual(snap_price(68_327), 68_300)
        self.assertEqual(snap_price(68_351), 68_400)
        self.assertEqual(snap_price(9_997, mode="down"), 9_990)
        self.assertEqual(snap_price(9_997, mode="up"), 10_000)

    def test_user_reported_hose_quotes_can_never_be_published(self) -> None:
        self.assertEqual(snap_price(65_050), 65_100)
        self.assertEqual(snap_price(65_070), 65_100)
        self.assertEqual(snap_price(66_127), 66_100)

    def test_directional_magnitude_blend_abstains_without_stable_evidence(self) -> None:
        actual = np.asarray([.01, -.01] * 80)
        point = np.zeros_like(actual)
        probability = np.full_like(actual, .55)
        magnitude = np.full_like(actual, .012)
        dates = np.asarray([f"2026-01-{1 + index // 4:02d}" for index in range(len(actual))])
        audit = select_directional_magnitude_blend(
            actual, point, probability, magnitude, dates
        )
        self.assertEqual(audit["status"], "ABSTAIN")
        self.assertEqual(audit["weight"], 0.0)
        self.assertEqual(audit["sealedLabelsUsed"], 0)

    def test_directional_magnitude_blend_requires_confidence_and_is_bounded(self) -> None:
        point = np.asarray([.001, -.001, .002])
        probability = np.asarray([.70, .30, .52])
        magnitude = np.asarray([.02, .03, .04])
        blended = directional_magnitude_blend(
            point, probability, magnitude, .20, .10
        )
        np.testing.assert_allclose(blended, [.0048, -.0068, .002])

    def test_cost_aware_screen_is_long_only_and_subtracts_declared_costs(self) -> None:
        audit = cost_aware_long_audit(
            np.asarray([.010, -.020, .002, .009]),
            np.asarray([.006, -.030, .002, .008]),
            np.asarray([.015, .025, .010, .012]),
            np.asarray(["2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20"]),
            round_trip_cost_bps=35,
        )
        self.assertEqual(audit["observations"], 2)
        self.assertAlmostEqual(audit["meanNetRealizedReturn"], .006)
        self.assertFalse(audit["selectionFitOnHoldout"])
        self.assertFalse(audit["portfolioSimulation"])


class PointInTimeSignalTest(unittest.TestCase):
    def test_after_close_and_weekend_news_shift_to_next_session(self) -> None:
        vn = timezone(timedelta(hours=7))
        self.assertEqual(effective_trading_session(datetime(2026, 8, 21, 14, 59, tzinfo=vn)), "2026-08-21")
        self.assertEqual(effective_trading_session(datetime(2026, 8, 21, 15, 0, tzinfo=vn)), "2026-08-24")
        self.assertEqual(effective_trading_session(datetime(2026, 8, 22, 9, 0, tzinfo=vn)), "2026-08-24")
        self.assertEqual(publication_timestamp("Fri, 21 Aug 2026 11:13:31 GMT").hour, 18)

    def test_parent_and_subsidiary_tickers_are_not_confused(self) -> None:
        universe = {"FPT", "FRT", "FTS", "PNJ", "VCB"}
        self.assertFalse(security_match("FPT", "FPT Retail (FRT): Lợi nhuận tăng trưởng 123%", universe))
        self.assertFalse(security_match("FPT", "Chứng khoán FPT (FTS) chia cổ tức", universe))
        self.assertTrue(security_match("FPT", "FPT: Doanh thu dịch vụ CNTT tăng trưởng", universe))
        self.assertTrue(security_match("FPT", "Dragon Capital tăng tỷ trọng PNJ và FPT", universe))

    def test_unrelated_ticker_collisions_and_missing_issuer_are_rejected(self) -> None:
        universe = {
            "GTA", "ASP", "VSI", "VCB", "PNJ", "FPT", "FRT", "FTS",
            "DGW", "KBC", "HPG", "BID", "BIC", "VPB", "PET",
        }
        self.assertFalse(security_match("GTA", 'GTA 6 vừa lộ gameplay, Take-Two đã "bay màu" 2 tỷ USD', universe, require_explicit=True))
        self.assertFalse(security_match("ASP", "Western Digital Corp (WDC) cổ phiếu giảm 6,69%", universe, require_explicit=True))
        self.assertFalse(security_match("VSI", "Khi đầu tư chứng khoán đặt trong kế hoạch tích lũy dài hạn", universe, require_explicit=True))
        self.assertTrue(security_match("GTA", "Cổ phiếu GTA: Công ty Gỗ Thuận An báo lợi nhuận tăng", universe, require_explicit=True))
        self.assertTrue(security_match("VCB", "Vietcombank công bố kế hoạch chia cổ tức", universe, require_explicit=True))
        self.assertTrue(security_match("PNJ", "PNJ: Sức mua trang sức tăng trưởng", universe, require_explicit=True))
        self.assertTrue(security_match("ASP", "Doanh nghiệp công bố kết quả kinh doanh", universe, require_explicit=False))
        self.assertFalse(security_match("FPT", "FRT: CTCP Bán lẻ Kỹ thuật số FPT | Tổng quan", universe, require_explicit=True))
        self.assertFalse(security_match("FPT", "HOSE: FTS - Chứng khoán FPT công bố báo cáo", universe, require_explicit=True))
        self.assertTrue(security_match("FRT", "FRT: CTCP Bán lẻ Kỹ thuật số FPT | Tổng quan", universe, require_explicit=True))
        self.assertTrue(security_match("FPT", "Dragon Capital tăng tỷ trọng PNJ và FPT", universe, require_explicit=True))
        self.assertTrue(security_match("HPG", "Digiworld (DGW) đầu tư vào KBC và HPG", universe, require_explicit=True))
        self.assertTrue(security_match("BID", "BID: hợp đồng bảo hiểm thẻ BIDV (BIC)", universe, require_explicit=True))
        self.assertFalse(security_match("VPB", "PET: được cấp hạn mức tín dụng tại VPB", universe, require_explicit=True))

    def test_event_reaction_prior_uses_only_already_matured_outcomes(self) -> None:
        events = pd.DataFrame(
            [
                {
                    "symbol": "FPT", "date": pd.Timestamp("2026-01-02"),
                    "publishedAt": "2026-01-02T08:00:00+07:00",
                    "eventType": "EARNINGS", "label": "POS",
                    "_matureDate": {"5": "2026-01-09"},
                    "_cumulativeAbnormalReturn": {"5": .10},
                },
                {
                    "symbol": "FPT", "date": pd.Timestamp("2026-01-08"),
                    "publishedAt": "2026-01-08T08:00:00+07:00",
                    "eventType": "EARNINGS", "label": "POS",
                    "_matureDate": None, "_cumulativeAbnormalReturn": None,
                },
                {
                    "symbol": "FPT", "date": pd.Timestamp("2026-01-12"),
                    "publishedAt": "2026-01-12T08:00:00+07:00",
                    "eventType": "EARNINGS", "label": "POS",
                    "_matureDate": None, "_cumulativeAbnormalReturn": None,
                },
            ]
        )
        enriched, audit = attach_matured_reaction_priors(events)
        self.assertEqual(enriched.loc[1, "reactionPrior5"], 0.0)
        self.assertGreater(enriched.loc[2, "reactionPrior5"], 0.0)
        self.assertEqual(audit["sameOrFutureEventOutcomesUsed"], 0)
        self.assertNotIn("_cumulativeAbnormalReturn", enriched.columns)


class PublishedMarketForecastTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dashboard = json.loads((ROOT / "data/forecast-dashboard-v12.json").read_text())
        cls.current = json.loads((ROOT / "data/forecast-current-v12.json").read_text())
        cls.market = json.loads((ROOT / "data/forecast-market-v13.json").read_text())

    def test_current_source_and_coverage(self) -> None:
        self.assertGreaterEqual(len(self.dashboard["symbols"]), 400)
        self.assertEqual(self.dashboard["asOf"], self.market["sources"]["marketScanAsOf"])
        self.assertEqual(set(self.dashboard["symbols"]), set(self.current["symbols"]))
        universe = self.market["model"]["universe"]
        self.assertGreaterEqual(universe["hoseCoverage"], .99)
        self.assertEqual(universe["freshSymbols"], universe["currentSymbols"])
        self.assertEqual(universe["staleSymbols"], 0)
        self.assertEqual(universe["currentSymbols"] + len(universe["insufficientHistorySymbols"]), universe["listedHOSE"])
        self.assertEqual(set(universe["insufficientHistorySymbols"]), {"DMX"})
        price_audit = self.market["sources"]["priceCrossSource"]
        self.assertEqual(price_audit["status"], "PASS")
        self.assertGreaterEqual(price_audit["eligibleCoverage"], price_audit["requiredEligibleCoverage"])
        self.assertGreaterEqual(price_audit["universeCoverage"], price_audit["requiredUniverseCoverage"])
        self.assertGreaterEqual(price_audit["coverage"], price_audit["requiredCoverage"])
        self.assertEqual(price_audit["mismatchCount"], 0)
        fpt = self.dashboard["symbols"]["FPT"]
        self.assertGreaterEqual(fpt["date"], self.dashboard["asOf"])
        self.assertGreater(fpt["close"], 0)
        self.assertIn(fpt["marketDataSource"], {"VNDIRECT_PUBLIC_EOD", "MARKET_SCAN_EOD", "PREVIOUS_VALIDATED_EOD"})
        self.assertEqual(fpt["priceSourceAgreement"]["status"], "PASS")
        chart_fpt = self.dashboard["charts"]["FPT"][-1]
        self.assertEqual(fpt["date"], chart_fpt["date"])
        self.assertEqual(fpt["close"], chart_fpt["rawClose"])

    def test_each_horizon_is_independently_promoted_or_abstained(self) -> None:
        self.assertEqual(self.market["version"], "VMEWS-MARKET-FORECAST-20.1.0")
        promotion = self.market["model"]["promotion"]
        self.assertEqual(promotion["status"], "PASS")
        promoted = set(promotion["directPriceHorizons"])
        review = set(promotion.get("reviewHorizons") or [])
        self.assertGreaterEqual(len(promoted), 3)
        self.assertEqual(promoted | review, set(range(1, 6)))
        self.assertFalse(promoted & review)
        self.assertIn(promotion["preferredRankingHorizon"], promoted)
        self.assertEqual(
            promotion["preferredRankingHorizon"],
            preferred_ranking_horizon(self.market["model"]["horizons"]),
        )
        for horizon in map(str, range(1, 6)):
            model = self.market["model"]["horizons"][horizon]
            audit = model["sealedAudit"]
            embargo = model["embargoAudit"]
            self.assertGreaterEqual(audit["n"], 30_000)
            walk = model["walkForwardAudit"]
            passed = int(horizon) in promoted
            self.assertEqual(model["priceStatus"], "PASS" if passed else "REVIEW")
            self.assertEqual(horizon_price_gate(audit, walk), passed)
            self.assertEqual(audit["futureRowsUsedForTraining"], 0)
            self.assertEqual(audit["futureLabelsUsedForCalibration"], 0)
            self.assertEqual(audit["invalidExecutableQuotes"], 0)
            self.assertEqual(len(audit["chronologicalFolds"]), 4)
            self.assertEqual(walk["status"], "PASS")
            self.assertEqual(len(walk["folds"]), 3)
            if passed:
                self.assertGreater(audit["magnitudeMAESkill"], 0)
                self.assertGreaterEqual(audit["maeSkill"], .005)
                self.assertGreaterEqual(audit["executableMAESkill"], .003)
                self.assertGreaterEqual(audit["rankIC"], .05)
                self.assertGreater(audit["executableMedianAbs"], .0015)
                self.assertTrue(.52 <= audit["coverage20_80"] <= .72)
                self.assertGreaterEqual(walk["positiveExecutableMAEFolds"], 2)
                self.assertGreaterEqual(walk["positiveMagnitudeFolds"], 2)
                self.assertGreater(walk["meanExecutableMAESkill"], 0)
                self.assertGreaterEqual(walk["meanRankIC"], .05)
            blend = self.market["model"]["horizons"][horizon]["directionalMagnitudeBlend"]
            self.assertEqual(blend["sealedLabelsUsed"], 0)
            self.assertIn(blend["status"], {"ACTIVE", "ABSTAIN"})
            self.assertLessEqual(blend["weight"], .40)
            for fold in walk["folds"]:
                self.assertEqual(fold["futureRowsUsedForTraining"], 0)
                self.assertEqual(fold["futureLabelsUsedForCalibration"], 0)
                self.assertLess(fold["trainingLatestMaturity"], fold["calibrationStart"])
                self.assertLess(fold["calibrationLatestMaturity"], fold["testStart"])
            self.assertLess(embargo["trainingLatestMaturity"], embargo["calibrationStarts"])
            self.assertLess(embargo["calibrationLatestMaturity"], embargo["holdoutStarts"])
            if horizon == "1":
                calibration = self.market["model"]["horizons"][horizon]["calibration"]
                self.assertLessEqual(calibration["scale"], .85)
                self.assertLessEqual(calibration["convictionFloor"], .04)
                self.assertEqual(calibration["shortHorizonScaleCeiling"], .85)
                self.assertEqual(calibration["shortHorizonFloorCeiling"], .04)

    def test_every_quote_uses_the_exchange_grid_and_review_horizons_abstain(self) -> None:
        checked = 0
        neutral_points = 0
        released = 0
        abstained = 0
        for symbol, snapshot in self.dashboard["symbols"].items():
            close = snapshot["close"]
            exchange = snapshot.get("exchange", "HOSE")
            for key, forecast in snapshot["horizons"].items():
                with self.subTest(symbol=symbol, horizon=key):
                    point = forecast["expectedPrice"]
                    low = forecast["q20Price"]
                    high = forecast["q80Price"]
                    self.assertEqual(point % tick_size(point, exchange), 0)
                    self.assertEqual(low % tick_size(low, exchange), 0)
                    self.assertEqual(high % tick_size(high, exchange), 0)
                    neutral_points += int(point == close)
                    self.assertLessEqual(low, point)
                    self.assertLessEqual(point, high)
                    floor, ceiling = session_limit(close, int(key), exchange)
                    self.assertGreaterEqual(low, floor)
                    self.assertLessEqual(high, ceiling)
                    self.assertAlmostEqual(math.log(point / close), forecast["expectedReturn"], places=12)
                    self.assertAlmostEqual(
                        sum(forecast["expertContributions"].values()),
                        forecast["expectedReturn"],
                        places=12,
                    )
                    self.assertGreater(forecast["expectedAbsReturn"], 0)
                    price_pass = int(key) in self.market["model"]["promotion"]["directPriceHorizons"]
                    self.assertEqual(forecast["priceValidated"], price_pass)
                    self.assertEqual(forecast["validationStatus"], "PASS" if price_pass else "REVIEW")
                    if price_pass:
                        self.assertTrue(forecast["magnitudeValidated"])
                        released += 1
                    else:
                        self.assertFalse(forecast["priceValidated"])
                        abstained += 1
                    self.assertLessEqual(forecast["bearScenarioPrice"], close)
                    self.assertGreaterEqual(forecast["bullScenarioPrice"], close)
                    self.assertTrue(
                        forecast["bearScenarioPrice"] < close
                        or forecast["bullScenarioPrice"] > close
                    )
                    self.assertGreaterEqual(forecast["bearScenarioPrice"], floor)
                    self.assertLessEqual(forecast["bullScenarioPrice"], ceiling)
                    checked += 1
        self.assertGreaterEqual(checked, 2000)
        self.assertGreater(released, 0)
        self.assertEqual(released + abstained, checked)
        self.assertLessEqual(neutral_points / checked, .05)

    def test_fpt_never_publishes_an_invalid_sub_tick_change(self) -> None:
        fpt = self.dashboard["symbols"]["FPT"]
        for horizon, forecast in fpt["horizons"].items():
            self.assertEqual(forecast["tickSize"], 100)
            difference = abs(forecast["expectedPrice"] - fpt["close"])
            self.assertTrue(difference == 0 or difference >= 100)
            if horizon != "1":
                self.assertGreaterEqual(difference, 100)
            self.assertNotEqual(forecast["expectedPrice"], 68_327)

    def test_news_and_flow_are_actual_model_features(self) -> None:
        features = set(self.market["model"]["featureNames"])
        self.assertIn("news_sentiment5", features)
        self.assertIn("news_earnings5", features)
        self.assertIn("news_reaction_prior5", features)
        self.assertIn("flow_foreign_imbalance5", features)
        self.assertIn("flow_prop_available", features)
        self.assertEqual(self.market["model"]["governance"]["outcomeFieldsUsedAsFeatures"], 0)
        signal = self.market["sources"]["signalAudit"]
        self.assertGreater(signal["acceptedEvents"], 12_000)
        self.assertGreater(signal["rejected"].get("issuer_mismatch", 0), 0)
        reaction = signal["maturedReactionPrior"]
        self.assertEqual(reaction["status"], "ACTIVE")
        self.assertGreater(reaction["maturedOutcomes"], 30_000)
        self.assertEqual(reaction["sameOrFutureEventOutcomesUsed"], 0)
        for horizon in self.market["model"]["horizons"].values():
            self.assertIn("EVENT", horizon["activeExperts"])
            self.assertIn("FLOW", horizon["activeExperts"])
            self.assertGreater(horizon["eventImpactAudit"]["observations"], 100)
            self.assertEqual(horizon["eventImpactAudit"]["futureOutcomeFieldsAsFeatures"], 0)

    def test_fund_holdings_are_scenario_context_without_moving_central_price(self) -> None:
        features = set(self.market["model"]["featureNames"])
        self.assertIn("fund_holder_count", features)
        self.assertIn("fund_weight_sum", features)
        audit = self.market["sources"]["fundAudit"]
        self.assertEqual(audit["status"], "CONTEXT_SCENARIO_ONLY")
        self.assertGreaterEqual(audit["snapshotCount"], 1)
        self.assertLess(audit["snapshotCount"], 4)
        self.assertFalse(audit["modelEligible"])
        self.assertTrue(audit["inferenceEligible"])
        self.assertTrue(audit["trainingFeaturesMasked"])
        self.assertGreaterEqual(audit["scenarioEligibleSymbols"], 50)
        self.assertEqual(audit["usedByForecastSymbols"], 0)
        self.assertEqual(audit["postForecastSnapshotsUsedAsFeatures"], 0)
        self.assertGreaterEqual(audit["latestCollection"]["holdingRows"], 300)
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
        self.assertEqual(fpt["fundCount"], 17)
        self.assertAlmostEqual(fpt["averageReportedWeight"], .042094117647058824)
        self.assertLessEqual(fpt["largestReportedWeight"], .10)
        self.assertEqual(len(fpt["holdings"]), 17)
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

    def test_archived_institutional_flow_and_financial_evidence_are_available(self) -> None:
        acb = self.dashboard["symbols"]["ACB"]
        self.assertTrue(acb["flow"]["foreign"]["available"])
        self.assertTrue(acb["flow"]["proprietary"]["available"])
        self.assertGreater(abs(acb["flow"]["proprietary"]["net1"]), 1_000_000_000)
        self.assertEqual(acb["flow"]["proprietary"]["sourceUnit"], "billion_VND")
        fpt = self.dashboard["symbols"]["FPT"]
        self.assertTrue(fpt["fundamentalContext"]["available"])
        self.assertTrue(fpt["fundamentalContext"]["scenarioEligible"])
        self.assertFalse(fpt["fundamentalContext"]["usedByForecast"])
        self.assertNotEqual(fpt["horizons"]["5"]["liveEvidence"]["components"]["FUNDAMENTAL"], 0)
        self.assertFalse(fpt["horizons"]["5"]["liveAdjustmentAppliedToCentralForecast"])

    def test_unvalidated_live_context_is_never_used_by_the_central_forecast(self) -> None:
        governance = self.market["model"]["governance"]
        self.assertFalse(governance["livePriorIndependentlyBacktested"])
        self.assertFalse(governance["centralForecastUsesUnvalidatedPrior"])
        self.assertTrue(governance["fundHoldingsContextOnlyUntilHistoryGate"])
        self.assertIn("NOT_APPLIED_TO_CENTRAL_FORECAST", governance["livePriorPolicy"])
        for snapshot in self.dashboard["symbols"].values():
            for horizon in snapshot["horizons"].values():
                self.assertFalse(horizon["liveAdjustmentAppliedToCentralForecast"])
                self.assertEqual(horizon["liveAdjustmentReturn"], 0.0)

    def test_after_close_news_influences_next_session_without_future_leakage(self) -> None:
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
        self.assertEqual(observed_symbols, audit["symbols"])
        self.assertLessEqual(observed_articles, audit["articles"])
        if audit["articles"] == 0:
            self.assertEqual(audit["status"], "UNAVAILABLE")

    def test_direction_probability_is_withheld_where_brier_gate_fails(self) -> None:
        validated = self.market["model"]["promotion"]["directionHorizons"]
        expected = [
            int(horizon)
            for horizon, model in self.market["model"]["horizons"].items()
            if model["directionStatus"] == "PASS"
        ]
        self.assertEqual(validated, expected)
        for snapshot in self.dashboard["symbols"].values():
            for horizon in map(str, range(1, 6)):
                self.assertEqual(
                    snapshot["horizons"][horizon]["directionValidated"],
                    int(horizon) in validated,
                )

    def test_sign_ranking_and_cost_evidence_never_masquerade_as_a_probability(self) -> None:
        model = self.market["model"]["horizons"]["5"]
        audit = model["sealedAudit"]
        fpt = self.dashboard["symbols"]["FPT"]["horizons"]["5"]
        self.assertGreater(audit["directionalAccuracy"], .52)
        self.assertEqual(model["pointDirectionStatus"], "PASS")
        self.assertTrue(fpt["pointDirectionValidated"])
        self.assertEqual(fpt["directionValidated"], model["directionStatus"] == "PASS")
        self.assertAlmostEqual(fpt["historicalDirectionAccuracy"], audit["directionalAccuracy"])
        self.assertTrue(fpt["crossSectionalRankValidated"])
        self.assertTrue(0 < fpt["crossSectionalRankPercentile"] <= 1)
        self.assertEqual(
            fpt["conditionalValueValidated"],
            model["priceStatus"] == "PASS" and audit["costAwareLongAudit"]["status"] == "PASS",
        )
        self.assertFalse(audit["costAwareLongAudit"]["selectionFitOnHoldout"])

    def test_fpt_institutional_flow_uses_the_latest_completed_genuine_session(self) -> None:
        flow = self.dashboard["symbols"]["FPT"]["flow"]
        self.assertGreaterEqual(flow["foreign"]["latestDate"], "2026-08-21")
        self.assertGreaterEqual(flow["proprietary"]["latestDate"], "2026-08-21")
        self.assertFalse(flow["foreign"]["stale"])
        self.assertFalse(flow["proprietary"]["stale"])
        self.assertGreater(abs(flow["foreign"]["net1"]), 1_000_000)
        self.assertGreater(abs(flow["proprietary"]["net1"]), 1_000_000)

    def test_fpt_feed_excludes_frt_and_fts_announcements(self) -> None:
        for item in self.dashboard["symbols"]["FPT"]["evidence"]["recent"]:
            self.assertNotIn("FPT Retail (FRT)", item["title"])
            self.assertNotIn("Chứng khoán FPT (FTS)", item["title"])
            self.assertLessEqual(item["availableDate"], self.dashboard["symbols"]["FPT"]["date"])
        for item in self.dashboard["symbols"]["FPT"]["evidence"].get("decisionRecent", []):
            self.assertFalse(item["title"].startswith(("FRT:", "FTS:")), item["title"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
