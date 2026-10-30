#!/usr/bin/env python3
"""Deterministic offline regression tests for the 30-minute VN100 publisher."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from finquery_vn100_product import make_product
from finquery_vn100_timeseries import build, load_market, quote_anchor
from vn_exchange_calendar import VN_TZ


def sessions():
    cursor = date(2026, 9, 1)
    end = date(2026, 10, 14)
    values = []
    while cursor <= end:
        if cursor.weekday() < 5 and cursor not in {date(2026, 9, 1), date(2026, 9, 2)}:
            values.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return values


def fixtures(root):
    core = [{"symbol": "S%03d" % i, "name": "Official VN100 Company %03d" % i, "exchange": "HOSE"} for i in range(100)]
    (root / "companies.json").write_text(json.dumps(core), encoding="utf-8")
    market = root / "market"
    (market / "history").mkdir(parents=True)
    for i, stock in enumerate(core):
        bars = [
            {"time": day, "close": 10000 + i * 50 + j * 50 + (i % 3) * (j % 2) * 50,
             "volume": 10000 + j * 500}
            for j, day in enumerate(sessions())
        ]
        (market / "history" / (stock["symbol"] + ".json")).write_text(json.dumps({"bars": bars}), encoding="utf-8")
    return root / "companies.json", market


class PublisherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.base = Path(cls.folder.name)
        cls.core, cls.market = fixtures(cls.base)
        cls.now = datetime(2026, 10, 15, 10, 10, tzinfo=VN_TZ)
        cls.full = build(cls.core, cls.market, cls.now)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_verified_prices_all_100_symbols_all_5_horizons(self):
        self.assertEqual(len(self.full["dashboard"]["symbols"]), 100)
        self.assertEqual(self.full["asOf"], "2026-10-14")
        for row in self.full["dashboard"]["symbols"].values():
            self.assertEqual(set(row["horizons"]), {"1", "2", "3", "4", "5"})
            self.assertTrue(all(item["expectedPrice"] > 0 and item["priceValidated"] for item in row["horizons"].values()))
            self.assertEqual(row["date"], "2026-10-14")

    def test_issuer_context_is_from_current_vn100_universe_not_archived_forecast(self):
        from inspect import getsource
        row = self.full["dashboard"]["symbols"]["S000"]
        self.assertEqual(row["name"], "Official VN100 Company 000")
        self.assertEqual(row["companyName"], row["name"])
        self.assertEqual(row["sector"], "UNKNOWN")
        self.assertEqual(row["evidence"], {"recent": [], "decisionRecent": []})
        for field in ("contextAsOf", "flow", "fundContext", "fundamentalContext",
                      "rumorContext", "newsFeatures"):
            self.assertNotIn(field, row, field)
        # Prevent an engineer from silently adding the old main/data read back.
        self.assertNotIn("forecast-dashboard-v12.json", getsource(build))
        self.assertNotIn("legacy_file", getsource(build))

    def test_no_live_quote_does_not_block_verified_eod_forecast(self):
        self.assertEqual(self.full["status"], "PASS")
        self.assertEqual(self.full["universe"]["activeQuotes"], 0)
        self.assertEqual(self.full["universe"]["quoteStatus"], "EOD_FALLBACK")

    def test_current_session_prices_reanchor_every_horizon_not_just_eod(self):
        now = datetime(2026, 10, 15, 10, 10, tzinfo=VN_TZ)
        stamp = datetime(2026, 10, 15, 10, 5, tzinfo=VN_TZ).isoformat()
        prices = {}
        for symbol, row in self.full["dashboard"]["symbols"].items():
            prices[symbol] = {
                "price": row["close"] + 500,
                "sourceTime": stamp, "status": "ok", "unit": "VND",
            }
        (self.market / "quotes.json").write_text(
            json.dumps({"checkedAt": now.isoformat(), "quotes": prices, "coverage": 100}),
            encoding="utf-8",
        )
        try:
            live = build(self.core, self.market, now)
            self.assertEqual(live["universe"]["activeQuotes"], 100)
            self.assertEqual(live["universe"]["quoteStatus"], "LIVE_VERIFIED")
            self.assertEqual(live["universe"]["inputMode"], "INTRADAY")
            fpt = live["dashboard"]["symbols"]["S000"]
            before = self.full["dashboard"]["symbols"]["S000"]
            self.assertEqual(fpt["forecastAnchorClose"], before["close"] + 500)
            self.assertEqual(fpt["forecastAnchorBasis"], "INTRADAY_QUOTE")
            self.assertEqual(fpt["forecastAnchorAt"], stamp)
            self.assertEqual(fpt["forecastCalculatedAt"], now.isoformat())
            self.assertEqual(fpt["date"], "2026-10-14")  # EOD remains history
            self.assertEqual(fpt["forecastSessionDate"], "2026-10-15")
            self.assertEqual(fpt["horizons"]["1"]["targetDate"], "2026-10-16")
            self.assertTrue(any(
                fpt["horizons"][h]["expectedPrice"] != before["horizons"][h]["expectedPrice"]
                for h in ("1", "2", "3", "4", "5")
            ))
            self.assertEqual(live["backtest"]["cases"]["1"], self.full["backtest"]["cases"]["1"])
        finally:
            (self.market / "quotes.json").unlink(missing_ok=True)

    def test_stale_intraday_source_cannot_pass_as_new_price(self):
        now = datetime(2026, 10, 15, 10, 10, tzinfo=VN_TZ)
        stale = {"quotes": {"S000": {
            "price": 12000, "sourceTime": datetime(2026, 10, 15, 9, 35, tzinfo=VN_TZ).isoformat(),
            "status": "ok", "unit": "VND"
        }}, "checkedAt": now.isoformat()}
        self.assertEqual(quote_anchor(stale, "S000", now), (None, None))
        stale["quotes"]["S000"]["status"] = "retained"
        stale["quotes"]["S000"]["sourceTime"] = now.isoformat()
        self.assertEqual(quote_anchor(stale, "S000", now), (None, None))

    def test_lunch_uses_morning_print_but_afternoon_requires_fresh_quote(self):
        stamp = datetime(2026, 10, 15, 11, 30, tzinfo=VN_TZ).isoformat()
        q = {"quotes": {"S000": {"price": 12000, "sourceTime": stamp, "status": "ok"}}}
        self.assertEqual(
            quote_anchor(q, "S000", datetime(2026, 10, 15, 12, 20, tzinfo=VN_TZ)),
            (12000.0, stamp)
        )
        self.assertEqual(
            quote_anchor(q, "S000", datetime(2026, 10, 15, 13, 20, tzinfo=VN_TZ)),
            (None, None)
        )

    def test_compact_product_retains_chart_backtest_and_all_horizons(self):
        p = make_product(self.full, max_cases=4)
        self.assertEqual(p["status"], "PASS")
        self.assertEqual(len(p["dashboard"]["charts"]), 100)
        self.assertEqual(len(p["dashboard"]["symbols"]), 100)
        for horizon, rows in p["backtest"]["cases"].items():
            self.assertEqual(len(rows), 400, horizon)
        self.assertEqual(p["dashboard"]["symbols"]["S000"]["evidence"], {"recent": [], "decisionRecent": []})
        self.assertGreater(len(p["dashboard"]["charts"]["S001"]), 20)

    def test_retained_real_closes_recover_single_provider_history_loss(self):
        previous = self.base / "prior.json"
        previous.write_text(json.dumps(make_product(self.full)), encoding="utf-8")
        (self.market / "history" / "S000.json").unlink()
        try:
            restored = load_market(self.core, self.market, "2026-10-14", previous)
            self.assertEqual(len(restored), 100)
            self.assertEqual(restored["S000"][-1]["date"], "2026-10-14")
        finally:
            # Recover the fixture for any subsequent tests.
            bars = self.full["dashboard"]["charts"]["S000"]
            (self.market / "history" / "S000.json").write_text(
                json.dumps({"bars": [{"time": r["date"], "close": r["close"], "volume": r["volume"]} for r in bars]}),
                encoding="utf-8")

    def test_missing_horizon_rejected(self):
        p = json.loads(json.dumps(self.full))
        del p["dashboard"]["symbols"]["S000"]["horizons"]["5"]
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            make_product(p)

    def test_no_fake_prices_from_unverified_model(self):
        p = json.loads(json.dumps(self.full))
        p["dashboard"]["symbols"]["S002"]["horizons"]["2"]["priceValidated"] = False
        with self.assertRaisesRegex(ValueError, "Invalid"):
            make_product(p)


if __name__ == "__main__":
    unittest.main()
