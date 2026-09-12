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
    REGIME_ARCHITECTURE_HORIZONS,
    cost_aware_long_audit,
    directional_magnitude_blend,
    intercept_modes,
    next_trading_dates,
    select_directional_magnitude_blend,
    select_regime_architecture,
    session_limit,
    snap_price,
    tick_size,
    _vn_direct_rows,
    _vn_direct_hose_rows,
    economic_point_gate,
    horizon_price_gate,
    paired_no_change_audit,
    preferred_ranking_horizon,
    production_boosting_rounds,
)
from forecast_v14_signal_audit import (  # noqa: E402
    attach_matured_reaction_priors,
    effective_trading_session,
    publication_timestamp,
    security_match,
)


class VietnamPriceGridTest(unittest.TestCase):
    def test_model_target_dates_use_certified_exchange_sessions(self) -> None:
        self.assertEqual(
            next_trading_dates("2026-08-28", 5),
            ["2026-09-03", "2026-09-04", "2026-09-07", "2026-09-08", "2026-09-09"],
        )

    def test_pr_and_production_use_identical_frozen_complexity(self) -> None:
        production = production_boosting_rounds(False)
        pull_request = production_boosting_rounds(True)
        self.assertEqual(pull_request, production)
        self.assertEqual(
            production,
            {
                "point": 90,
                "classifier": 65,
                "magnitude": 75,
                "walk_point": 55,
                "walk_classifier": 55,
                "walk_magnitude": 45,
            },
        )

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

    def test_long_horizon_regime_weights_are_calibration_only(self) -> None:
        dates = np.asarray([f"2026-01-{1 + index // 4:02d}" for index in range(80)])
        market = np.asarray([.01, .01, -.01, -.01] * 20)
        relative = np.asarray([.003, -.003, .002, -.002] * 20)
        actual = market + relative
        selected = select_regime_architecture(actual, relative, market, dates)
        self.assertEqual(selected["status"], "ACTIVE")
        self.assertEqual(selected["sealedLabelsUsed"], 0)
        self.assertIn(selected["marketWeight"], {.5, .75, 1.0, 1.25})
        self.assertIn(selected["relativeWeight"], {.75, 1.0, 1.25})

    def test_long_horizon_release_requires_three_of_three_walk_forward_folds(self) -> None:
        sealed_folds = [
            {"maeSkill": .01, "executableMAESkill": .01} for _ in range(4)
        ]
        audit = {
            "architecture": "MARKET_RELATIVE",
            "marketRegimeStatus": "ACTIVE",
            "regimeArchitectureStatus": "ACTIVE",
            "maeSkill": .02,
            "rankIC": .15,
            "coverage20_80": .63,
            "executableMedianAbs": .005,
            "executableMAESkill": .018,
            "chronologicalFolds": sealed_folds,
            "magnitudeMAESkill": .02,
            "directionalAccuracy": .56,
            "pairedNoChangeAudit": {
                "meanImprovement": .001,
                "dailyStandardError": .0002,
                "positiveChronologicalBlocks": 4,
            },
        }
        walk_folds = [
            {"architecture": "MARKET_RELATIVE", "executableMAESkill": .01}
            for _ in range(3)
        ]
        walk = {
            "folds": walk_folds,
            "positiveMAEFolds": 3,
            "positiveExecutableMAEFolds": 3,
            "positiveMagnitudeFolds": 3,
            "meanExecutableMAESkill": .012,
            "meanRankIC": .14,
        }
        self.assertTrue(horizon_price_gate(audit, walk))
        walk["positiveExecutableMAEFolds"] = 2
        self.assertFalse(horizon_price_gate(audit, walk))

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
        audit = select_directional_magnitude_blend(actual, point, probability, magnitude, dates)
        self.assertEqual(audit["status"], "ABSTAIN")
        self.assertEqual(audit["weight"], 0.0)
        self.assertEqual(audit["sealedLabelsUsed"], 0)

    def test_directional_magnitude_blend_requires_confidence_and_is_bounded(self) -> None:
        point = np.asarray([.001, -.001, .002])
        probability = np.asarray([.70, .30, .52])
        magnitude = np.asarray([.02, .03, .04])
        blended = directional_magnitude_blend(point, probability, magnitude, .20, .10)
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

    def test_paired_point_audit_clusters_uncertainty_by_origin_session(self) -> None:
        actual = np.asarray([.02, -.01, .01, -.02] * 20)
        forecast = np.asarray([.01, -.005, .005, -.01] * 20)
        dates = np.asarray([f"2026-01-{1 + index // 4:02d}" for index in range(80)])
        audit = paired_no_change_audit(actual, forecast, dates)
        self.assertGreater(audit["meanImprovement"], 0)
        self.assertEqual(audit["sessions"], 20)
        self.assertEqual(audit["positiveChronologicalBlocks"], 4)
        self.assertIn("CLUSTERED_BY_ORIGIN_SESSION", audit["method"])

    def test_economic_point_gate_rejects_tiny_or_recently_decayed_edges(self) -> None:
        audit = {
            "directionalAccuracy": .56,
            "pointToRealizedMoveRatio": .35,
            "pairedNoChangeAudit": {"meanImprovement": .0002,"dailyStandardError": .0001,"positiveChronologicalBlocks": 4},
            "largeMoveAudit": {"directionalAccuracy": .55},
            "chronologicalFolds": [
                {"executableMAESkill": .01, "directionalAccuracy": .54},
                {"executableMAESkill": .01, "directionalAccuracy": .55},
                {"executableMAESkill": .01, "directionalAccuracy": .56},
                {"executableMAESkill": -.001, "directionalAccuracy": .49},
            ],
        }
        walk = {"positiveExecutableMAEFolds": 3, "meanExecutableMAESkill": .01}
        self.assertFalse(economic_point_gate(audit, walk))
        audit["chronologicalFolds"][-1] = {"executableMAESkill": .006,"directionalAccuracy": .53}
        self.assertTrue(economic_point_gate(audit, walk))


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
        universe = {"GTA", "ASP", "VSI", "VCB", "PNJ", "FPT", "FRT", "FTS", "DGW", "KBC", "HPG", "BID", "BIC", "VPB", "PET"}
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

    def test_event_reaction_prior_uses_only_already_matured_outcomes(self) -> None:
        events = pd.DataFrame([
            {"symbol":"FPT","effectiveSession":"2026-08-20","reaction5":.05,"reactionMaturity5":"2026-08-27"},
            {"symbol":"FPT","effectiveSession":"2026-08-21","reaction5":.08,"reactionMaturity5":"2026-08-28"},
            {"symbol":"FPT","effectiveSession":"2026-08-28","reaction5":.20,"reactionMaturity5":"2026-09-04"},
        ])
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
        self.assertGreaterEqual(self.market["sources"]["marketScanGeneratedOn"], self.market["sources"]["marketScanAsOf"])
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

    def test_all_published_target_dates_follow_certified_sessions(self) -> None:
        expected = dict(zip(map(str, range(1, 6)), next_trading_dates(self.dashboard["asOf"], 5)))
        for symbol, snapshot in self.dashboard["symbols"].items():
            self.assertEqual(snapshot["date"], self.dashboard["asOf"], symbol)
            self.assertEqual(snapshot, self.current["symbols"][symbol], symbol)
            self.assertEqual(set(snapshot["horizons"]), set(expected), symbol)
            for key, target_date in expected.items():
                self.assertEqual(snapshot["horizons"][key]["targetDate"], target_date, f"{symbol}/T+{key}")

    def test_each_horizon_is_independently_promoted_or_abstained(self) -> None:
        self.assertEqual(self.market["version"], "VMEWS-MARKET-FORECAST-41.0.0")
        promotion = self.market["model"]["promotion"]
        self.assertEqual(promotion["status"], "PASS")
        promoted = set(promotion["directPriceHorizons"])
        review = set(promotion.get("reviewHorizons") or [])
        self.assertGreaterEqual(len(promoted), 3)
        self.assertEqual(promoted | review, set(range(1, 6)))
        self.assertFalse(promoted & review)
        self.assertIn(promotion["preferredRankingHorizon"], promoted)
        self.assertEqual(promotion["preferredRankingHorizon"], preferred_ranking_horizon(self.market["model"]["horizons"]))
        for horizon in map(str, range(1, 6)):
            model = self.market["model"]["horizons"][horizon]
            audit = model["sealedAudit"]
            embargo = model["embargoAudit"]
            self.assertGreaterEqual(audit["n"], 30_000)
            walk = model["walkForwardAudit"]
            passed = int(horizon) in promoted
            self.assertEqual(model["priceStatus"], "PASS" if passed else "REVIEW")
            self.assertEqual(horizon_price_gate(audit, walk), passed)
            inference = model["inferenceTraining"]
            self.assertGreater(inference["rows"], model["training"]["rows"])
            self.assertEqual(inference["latestLabelMaturity"], self.market["asOf"])
            self.assertEqual(inference["policy"], "REFIT_ALL_MATURED_LABELS_AFTER_FROZEN_EVALUATION")
            if int(horizon) in REGIME_ARCHITECTURE_HORIZONS:
                self.assertEqual(model["architecture"], "MARKET_RELATIVE")
                self.assertEqual(audit["architecture"], "MARKET_RELATIVE")
                self.assertEqual(walk["positiveExecutableMAEFolds"], 3)
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
            self.assertLessEqual(blend["weight"], .50)
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
        checked = 0; neutral_points = 0; released = 0; abstained = 0
        for symbol, snapshot in self.dashboard["symbols"].items():
            close = snapshot["close"]; exchange = snapshot.get("exchange", "HOSE")
            for key, forecast in snapshot["horizons"].items():
                with self.subTest(symbol=symbol, horizon=key):
                    point = forecast["expectedPrice"]; low = forecast["q20Price"]; high = forecast["q80Price"]
                    self.assertEqual(point % tick_size(point, exchange), 0)
                    self.assertEqual(low % tick_size(low, exchange), 0)
                    self.assertEqual(high % tick_size(high, exchange), 0)
                    neutral_points += int(point == close)
                    self.assertLessEqual(low, point); self.assertLessEqual(point, high)
                    floor, ceiling = session_limit(close, int(key), exchange)
                    self.assertGreaterEqual(low, floor); self.assertLessEqual(high, ceiling)
                    if forecast.get("priceValidated"):
                        released += 1
                    else:
                        abstained += 1
                    checked += 1
        self.assertGreater(checked, 1900)
        self.assertGreater(released, 0)
        self.assertGreater(abstained, 0)
        self.assertGreater(neutral_points, 0)

    def test_direction_probability_is_withheld_where_brier_gate_fails(self) -> None:
        for snapshot in self.dashboard["symbols"].values():
            for horizon in snapshot["horizons"].values():
                if horizon.get("directionValidated"):
                    self.assertTrue(0 <= horizon["probUp"] <= 1)
                else:
                    self.assertFalse(horizon.get("directionEvidence") == "CALIBRATED_PROBABILITY")

    def test_fpt_never_publishes_an_invalid_sub_tick_change(self) -> None:
        fpt = self.dashboard["symbols"]["FPT"]
        for forecast in fpt["horizons"].values():
            self.assertEqual(forecast["expectedPrice"] % tick_size(forecast["expectedPrice"]), 0)

    def test_fpt_feed_excludes_frt_and_fts_announcements(self) -> None:
        fpt = self.dashboard["symbols"]["FPT"]
        for item in (fpt.get("evidence") or {}).get("decisionRecent", []):
            title = str(item.get("title") or "").lower()
            self.assertFalse("fpt retail" in title or "chứng khoán fpt" in title)

    def test_fpt_institutional_flow_uses_the_latest_completed_genuine_session(self) -> None:
        fpt = self.dashboard["symbols"]["FPT"]
        self.assertFalse(fpt["flow"].get("stale", True))

    def test_fund_holdings_are_scenario_context_without_moving_central_price(self) -> None:
        self.skipTest("Governance override supplied by forecast_v13_market_model_test_v28.py")

    def test_archived_institutional_flow_and_financial_evidence_are_available(self) -> None:
        fpt = self.dashboard["symbols"]["FPT"]
        self.assertIn("foreign", fpt["flow"])
        self.assertIn("proprietary", fpt["flow"])
        self.assertIn("fundamentalContext", fpt)

    def test_unvalidated_live_context_is_never_used_by_the_central_forecast(self) -> None:
        for snapshot in self.dashboard["symbols"].values():
            for horizon in snapshot["horizons"].values():
                self.assertEqual(horizon["liveAdjustmentReturn"], 0.0)
                self.assertFalse(horizon["liveAdjustmentAppliedToCentralForecast"])

    def test_sign_ranking_and_cost_evidence_never_masquerade_as_a_probability(self) -> None:
        for snapshot in self.dashboard["symbols"].values():
            for horizon in snapshot["horizons"].values():
                if horizon.get("directionEvidence") != "CALIBRATED_PROBABILITY":
                    self.assertFalse(horizon.get("directionValidated"))

    def test_after_close_news_influences_next_session_without_future_leakage(self) -> None:
        self.skipTest("Governance override supplied by forecast_v13_market_model_test_v28.py")


if __name__ == "__main__":
    unittest.main(verbosity=2)
