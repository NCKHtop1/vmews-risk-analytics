"""Regression and publication checks for executable Vietnam-equity forecasts."""

from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from forecast_v13_market_model import session_limit, snap_price, tick_size  # noqa: E402


class VietnamPriceGridTest(unittest.TestCase):
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


class PublishedMarketForecastTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dashboard = json.loads((ROOT / "data/forecast-dashboard-v12.json").read_text())
        cls.current = json.loads((ROOT / "data/forecast-current-v12.json").read_text())
        cls.market = json.loads((ROOT / "data/forecast-market-v13.json").read_text())

    def test_current_source_and_coverage(self) -> None:
        self.assertGreaterEqual(len(self.dashboard["symbols"]), 320)
        self.assertEqual(self.dashboard["asOf"], self.market["sources"]["marketScanAsOf"])
        self.assertEqual(set(self.dashboard["symbols"]), set(self.current["symbols"]))
        fpt = self.dashboard["symbols"]["FPT"]
        self.assertGreaterEqual(fpt["date"], self.dashboard["asOf"])
        self.assertGreater(fpt["close"], 0)
        self.assertIn(fpt["marketDataSource"], {"VNDIRECT_PUBLIC_EOD", "MARKET_SCAN_EOD"})
        chart_fpt = self.dashboard["charts"]["FPT"][-1]
        self.assertEqual(fpt["date"], chart_fpt["date"])
        self.assertEqual(fpt["close"], chart_fpt["rawClose"])

    def test_all_horizons_are_independently_validated(self) -> None:
        self.assertEqual(self.market["model"]["promotion"]["status"], "PASS")
        self.assertEqual(self.market["model"]["promotion"]["directPriceHorizons"], [1, 2, 3, 4, 5])
        for horizon in map(str, range(1, 6)):
            audit = self.market["model"]["horizons"][horizon]["sealedAudit"]
            embargo = self.market["model"]["horizons"][horizon]["embargoAudit"]
            self.assertGreaterEqual(audit["n"], 30_000)
            self.assertGreater(audit["maeSkill"], 0)
            self.assertGreater(audit["rankIC"], .02)
            self.assertGreater(audit["medianForecastAbs"], .0015)
            self.assertTrue(.45 <= audit["coverage20_80"] <= .75)
            self.assertEqual(audit["futureRowsUsedForTraining"], 0)
            self.assertEqual(audit["futureLabelsUsedForCalibration"], 0)
            self.assertLess(embargo["trainingLatestMaturity"], embargo["calibrationStarts"])
            self.assertLess(embargo["calibrationLatestMaturity"], embargo["holdoutStarts"])

    def test_every_quote_is_executable_and_nonflat(self) -> None:
        checked = 0
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
                    self.assertNotEqual(point, close)
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
                    checked += 1
        self.assertGreaterEqual(checked, 1600)

    def test_fpt_no_longer_publishes_invalid_27_vnd_change(self) -> None:
        fpt = self.dashboard["symbols"]["FPT"]
        for forecast in fpt["horizons"].values():
            self.assertEqual(forecast["tickSize"], 100)
            self.assertGreaterEqual(abs(forecast["expectedPrice"] - fpt["close"]), 100)
            self.assertNotEqual(forecast["expectedPrice"], 68_327)


if __name__ == "__main__":
    unittest.main(verbosity=2)
