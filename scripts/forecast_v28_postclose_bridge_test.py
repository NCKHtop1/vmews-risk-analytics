from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from forecast_v28_postclose_bridge import bridge_completed_session

VN_TZ = timezone(timedelta(hours=7))


def frame_for(symbols, date_text="2026-08-28"):
    ts = datetime.fromisoformat(f"{date_text}T15:10:00+07:00").timestamp()
    rows = []
    for i, symbol in enumerate(symbols):
        rows.append({
            "name": symbol,
            "exchange": "HOSE",
            "close": 50000 + i * 100,
            "change": 0.5,
            "volume": 1_000_000 + i,
            "update_mode": "streaming",
            "update_time": ts,
        })
    return pd.DataFrame(rows)


def histories(symbols, as_of="2026-08-27"):
    return {
        symbol: [{
            "date": as_of,
            "open": 49000,
            "high": 51000,
            "low": 48500,
            "close": 50000,
            "modelClose": 50000,
            "volume": 900000,
            "provider": "fixture",
            "exchange": "HOSE",
        }]
        for symbol in symbols
    }


class PostCloseBridgeTest(unittest.TestCase):
    def test_advances_only_after_high_coverage_same_day_proof(self):
        symbols = [f"S{i:02d}" for i in range(10)]
        h = histories(symbols)
        freshness = {"forecastAsOf": "2026-08-27", "currentHOSESymbols": symbols, "providerBySymbol": {}}
        now = datetime(2026, 8, 28, 16, 0, tzinfo=VN_TZ)
        out, meta = bridge_completed_session(h, freshness, now=now, frame=frame_for(symbols), min_coverage=0.90)
        self.assertEqual(meta["forecastAsOf"], "2026-08-28")
        self.assertEqual(meta["postCloseBridge"]["status"], "PASS")
        self.assertEqual(meta["postCloseBridge"]["appendedSymbols"], 10)
        for symbol in symbols:
            self.assertEqual(out[symbol][-1]["date"], "2026-08-28")
            self.assertTrue(out[symbol][-1]["ohlcUnavailable"])
            self.assertEqual(meta["providerBySymbol"][symbol], "TRADINGVIEW_POST_CLOSE")

    def test_rejects_stale_coverage(self):
        symbols = [f"S{i:02d}" for i in range(10)]
        h = histories(symbols)
        freshness = {"forecastAsOf": "2026-08-27", "currentHOSESymbols": symbols, "providerBySymbol": {}}
        now = datetime(2026, 8, 28, 16, 0, tzinfo=VN_TZ)
        with self.assertRaises(RuntimeError):
            bridge_completed_session(h, freshness, now=now, frame=frame_for(symbols[:8]), min_coverage=0.90)
        self.assertEqual(freshness["forecastAsOf"], "2026-08-27")
        self.assertEqual(freshness["postCloseBridge"]["status"], "REJECTED_STALE")

    def test_does_not_mutate_preopen(self):
        symbols = ["FPT", "VCB"]
        h = histories(symbols)
        freshness = {"forecastAsOf": "2026-08-27", "currentHOSESymbols": symbols, "providerBySymbol": {}}
        now = datetime(2026, 8, 28, 8, 0, tzinfo=VN_TZ)
        out, meta = bridge_completed_session(h, freshness, now=now, frame=frame_for(symbols), min_coverage=0.90)
        self.assertEqual(meta["forecastAsOf"], "2026-08-27")
        self.assertEqual(meta["postCloseBridge"]["status"], "NOT_APPLICABLE")
        self.assertEqual(out["FPT"][-1]["date"], "2026-08-27")


if __name__ == "__main__":
    unittest.main(verbosity=2)
