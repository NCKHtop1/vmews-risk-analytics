"""Regression and publication checks for executable Vietnam-equity forecasts."""

from __future__ import annotations

import json
import math
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from forecast_v13_market_model import (  # noqa: E402
    INTERCEPT_RETENTION,
    intercept_modes,
    session_limit,
    snap_price,
    tick_size,
)
from forecast_v14_signal_audit import effective_trading_session, publication_timestamp, security_match  # noqa: E402


class VietnamPriceGridTest(unittest.TestCase):
    def test_t2_market_intercept_is_regime_shrunk_before_holdout(self) -> None:
        self.assertEqual(INTERCEPT_RETENTION[2], .25)
        self.assertEqual(intercept_modes(2), ("BLEND_0.25",))

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
        universe = {"GTA", "ASP", "VSI", "VCB", "PNJ", "FPT"}
        self.assertFalse(security_match("GTA", 'GTA 6 vừa lộ gameplay, Take-Two đã "bay màu" 2 tỷ USD', universe, require_explicit=True))
        self.assertFalse(security_match("ASP", "Western Digital Corp (WDC) cổ phiếu giảm 6,69%", universe, require_explicit=True))
        self.assertFalse(security_match("VSI", "Khi đầu tư chứng khoán đặt trong kế hoạch tích lũy dài hạn", universe, require_explicit=True))
        self.assertTrue(security_match("GTA", "Cổ phiếu GTA: Công ty Gỗ Thuận An báo lợi nhuận tăng", universe, require_explicit=True))
        self.assertTrue(security_match("VCB", "Vietcombank công bố kế hoạch chia cổ tức", universe, require_explicit=True))
        self.assertTrue(security_match("PNJ", "PNJ: Sức mua trang sức tăng trưởng", universe, require_explicit=True))
        self.assertTrue(security_match("ASP", "Doanh nghiệp công bố kết quả kinh doanh", universe, require_explicit=False))


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
        self.assertEqual(universe["currentSymbols"] + len(universe["insufficientHistorySymbols"]), universe["listedHOSE"])
        self.assertEqual(set(universe["insufficientHistorySymbols"]), {"DMX"})
        fpt = self.dashboard["symbols"]["FPT"]
        self.assertGreaterEqual(fpt["date"], self.dashboard["asOf"])
        self.assertGreater(fpt["close"], 0)
        self.assertIn(fpt["marketDataSource"], {"VNDIRECT_PUBLIC_EOD", "MARKET_SCAN_EOD"})
        chart_fpt = self.dashboard["charts"]["FPT"][-1]
        self.assertEqual(fpt["date"], chart_fpt["date"])
        self.assertEqual(fpt["close"], chart_fpt["rawClose"])

    def test_all_horizons_are_independently_validated(self) -> None:
        self.assertEqual(self.market["version"], "VMEWS-MARKET-FORECAST-16.0.0")
        self.assertEqual(self.market["model"]["promotion"]["status"], "PASS")
        self.assertEqual(self.market["model"]["promotion"]["directPriceHorizons"], [1, 2, 3, 4, 5])
        for horizon in map(str, range(1, 6)):
            audit = self.market["model"]["horizons"][horizon]["sealedAudit"]
            embargo = self.market["model"]["horizons"][horizon]["embargoAudit"]
            self.assertGreaterEqual(audit["n"], 30_000)
            walk = self.market["model"]["horizons"][horizon]["walkForwardAudit"]
            self.assertGreaterEqual(audit["maeSkill"], .005)
            self.assertGreaterEqual(audit["executableMAESkill"], .003)
            self.assertGreaterEqual(audit["rankIC"], .05)
            self.assertGreater(audit["executableMedianAbs"], .0015)
            self.assertTrue(.52 <= audit["coverage20_80"] <= .72)
            self.assertGreater(audit["magnitudeMAESkill"], 0)
            self.assertEqual(audit["futureRowsUsedForTraining"], 0)
            self.assertEqual(audit["futureLabelsUsedForCalibration"], 0)
            self.assertEqual(audit["invalidExecutableQuotes"], 0)
            self.assertEqual(len(audit["chronologicalFolds"]), 4)
            self.assertEqual(walk["status"], "PASS")
            self.assertEqual(len(walk["folds"]), 3)
            self.assertGreaterEqual(walk["positiveExecutableMAEFolds"], 2)
            self.assertGreaterEqual(walk["positiveMagnitudeFolds"], 2)
            self.assertGreater(walk["meanExecutableMAESkill"], 0)
            self.assertGreaterEqual(walk["meanRankIC"], .05)
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

    def test_every_quote_is_executable_with_nonflat_move_scenarios(self) -> None:
        checked = 0
        neutral_points = 0
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
                    self.assertTrue(forecast["magnitudeValidated"])
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
        self.assertLessEqual(neutral_points / checked, .05)

    def test_fpt_no_longer_publishes_invalid_27_vnd_change(self) -> None:
        fpt = self.dashboard["symbols"]["FPT"]
        for forecast in fpt["horizons"].values():
            self.assertEqual(forecast["tickSize"], 100)
            self.assertGreaterEqual(abs(forecast["expectedPrice"] - fpt["close"]), 100)
            self.assertNotEqual(forecast["expectedPrice"], 68_327)

    def test_news_and_flow_are_actual_model_features(self) -> None:
        features = set(self.market["model"]["featureNames"])
        self.assertIn("news_sentiment5", features)
        self.assertIn("news_earnings5", features)
        self.assertIn("flow_foreign_imbalance5", features)
        self.assertIn("flow_prop_available", features)
        self.assertEqual(self.market["model"]["governance"]["outcomeFieldsUsedAsFeatures"], 0)
        signal = self.market["sources"]["signalAudit"]
        self.assertGreater(signal["acceptedEvents"], 12_000)
        self.assertGreater(signal["rejected"].get("issuer_mismatch", 0), 0)
        for horizon in self.market["model"]["horizons"].values():
            self.assertIn("EVENT", horizon["activeExperts"])
            self.assertIn("FLOW", horizon["activeExperts"])
            self.assertGreater(horizon["eventImpactAudit"]["observations"], 100)
            self.assertEqual(horizon["eventImpactAudit"]["futureOutcomeFieldsAsFeatures"], 0)

    def test_fund_holdings_are_context_only_until_point_in_time_history_exists(self) -> None:
        features = set(self.market["model"]["featureNames"])
        self.assertIn("fund_holder_count", features)
        self.assertIn("fund_weight_sum", features)
        audit = self.market["sources"]["fundAudit"]
        self.assertEqual(audit["status"], "CONTEXT_ONLY")
        self.assertEqual(audit["snapshotCount"], 1)
        self.assertFalse(audit["modelEligible"])
        self.assertEqual(audit["postForecastSnapshotsUsedAsFeatures"], 0)
        self.assertEqual(audit["latestCollection"]["holdingRows"], 369)
        fpt = self.dashboard["symbols"]["FPT"]["fundContext"]
        self.assertTrue(fpt["available"])
        self.assertTrue(fpt["collectedAfterForecast"])
        self.assertFalse(fpt["availableForForecast"])
        self.assertFalse(fpt["usedByForecast"])
        self.assertEqual(fpt["fundCount"], 17)
        self.assertAlmostEqual(fpt["averageReportedWeight"], .042094117647058824)
        self.assertLessEqual(fpt["largestReportedWeight"], .10)

    def test_direction_probability_is_withheld_where_brier_gate_fails(self) -> None:
        self.assertEqual(self.market["model"]["promotion"]["directionHorizons"], [1, 2, 3, 4])
        for snapshot in self.dashboard["symbols"].values():
            self.assertTrue(snapshot["horizons"]["3"]["directionValidated"])
            self.assertTrue(snapshot["horizons"]["4"]["directionValidated"])
            self.assertFalse(snapshot["horizons"]["5"]["directionValidated"])

    def test_fpt_feed_excludes_frt_and_fts_announcements(self) -> None:
        for item in self.dashboard["symbols"]["FPT"]["evidence"]["recent"]:
            self.assertNotIn("FPT Retail (FRT)", item["title"])
            self.assertNotIn("Chứng khoán FPT (FTS)", item["title"])
            self.assertLessEqual(item["availableDate"], self.dashboard["symbols"]["FPT"]["date"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
