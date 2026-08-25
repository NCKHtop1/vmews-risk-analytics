import unittest
from datetime import datetime, timezone, timedelta

import pandas as pd

from forecast_v21_session_snapshot import build_payload, VN_TZ


class ForecastV21SessionSnapshotTest(unittest.TestCase):
    def dashboard(self, count=120):
        symbols = {}
        for index in range(count):
            symbol = f"T{index:03d}"
            close = 10000 + index * 10
            symbols[symbol] = {
                "symbol": symbol,
                "exchange": "HOSE",
                "dataFreshness": "CURRENT",
                "close": close,
                "riskStatus": "GREEN" if index % 3 else "WATCH",
                "sector": "TEST",
                "horizons": {
                    "5": {
                        "expectedPrice": close * (1.02 + (index % 9) / 1000),
                        "q20Price": close * 0.98,
                        "q80Price": close * 1.06,
                        "priceValidated": True,
                        "validationStatus": "PASS",
                        "directionValidated": True,
                        "probUp": 0.52 + (index % 5) / 100,
                    }
                },
            }
        return {"asOf": "2026-08-24", "symbols": symbols}

    def frame(self, count=120, now=None, price_multiplier=1.0):
        now = now or datetime(2026, 8, 25, 12, 5, tzinfo=VN_TZ)
        epoch = now.astimezone(timezone.utc).timestamp()
        rows = []
        for index in range(count):
            close = (10000 + index * 10) * price_multiplier
            rows.append({
                "name": f"T{index:03d}",
                "exchange": "HOSE",
                "close": close,
                "change": (index % 7) - 3,
                "volume": 1_000_000 + index * 1000,
                "relative_volume_10d_calc": 1.0 + (index % 4) / 10,
                "sector": "TEST",
                "update_mode": "streaming",
                "update_time": epoch,
            })
        return pd.DataFrame(rows)

    def test_passes_with_current_broad_coverage_and_never_rewrites_core(self):
        now = datetime(2026, 8, 25, 12, 5, tzinfo=VN_TZ)
        payload = build_payload(self.dashboard(), self.frame(now=now), now)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["session"], "AM")
        self.assertTrue(payload["coreForecastUnchanged"])
        self.assertEqual(payload["coverage"]["coreEligible"], 120)
        self.assertEqual(payload["coverage"]["quoted"], 120)
        self.assertEqual(payload["coverage"]["currentQuoteDate"], 120)
        self.assertEqual(len(payload["leaders"]), 10)
        self.assertGreater(payload["leaders"][0]["conviction"], payload["leaders"][-1]["conviction"])
        first = payload["symbols"][0]
        self.assertNotEqual(first["liveClose"], first["coreTargetT5"])
        self.assertAlmostEqual(first["coreUpsideT5"], first["coreTargetT5"] / first["coreClose"] - 1.0)

    def test_rejects_partial_provider_coverage(self):
        now = datetime(2026, 8, 25, 12, 5, tzinfo=VN_TZ)
        payload = build_payload(self.dashboard(), self.frame(count=60, now=now), now)
        self.assertEqual(payload["status"], "DEGRADED")
        self.assertEqual(payload["coverage"]["quoted"], 60)
        self.assertLess(payload["coverage"]["coverageRatio"], 0.70)

    def test_rejects_stale_quotes_even_when_symbol_coverage_is_full(self):
        now = datetime(2026, 8, 25, 15, 25, tzinfo=VN_TZ)
        stale = datetime(2026, 8, 24, 15, 25, tzinfo=VN_TZ)
        payload = build_payload(self.dashboard(), self.frame(now=stale), now)
        self.assertEqual(payload["status"], "DEGRADED")
        self.assertEqual(payload["coverage"]["quoted"], 120)
        self.assertEqual(payload["coverage"]["currentQuoteDate"], 0)


    def test_rejects_same_day_quotes_that_are_stale_for_the_session_cutoff(self):
        now = datetime(2026, 8, 25, 15, 25, tzinfo=VN_TZ)
        stale = datetime(2026, 8, 25, 10, 30, tzinfo=VN_TZ)
        payload = build_payload(self.dashboard(), self.frame(now=stale), now)
        self.assertEqual(payload["status"], "DEGRADED")
        self.assertEqual(payload["coverage"]["currentQuoteDate"], 120)
        self.assertEqual(payload["coverage"]["cutoffFresh"], 0)
        self.assertLess(payload["coverage"]["cutoffFreshCoverageRatio"], 0.90)

    def test_falls_back_to_defensive_ranking_when_live_price_exceeds_all_targets(self):
        now = datetime(2026, 8, 25, 15, 25, tzinfo=VN_TZ)
        payload = build_payload(self.dashboard(), self.frame(now=now, price_multiplier=1.10), now)
        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["market"]["defensive"])
        self.assertEqual(payload["market"]["positiveCoreTargetFromLive"], 0)
        self.assertEqual(len(payload["leaders"]), 10)
        self.assertTrue(all(row["remainingUpsideT5"] < 0 for row in payload["leaders"]))


if __name__ == "__main__":
    unittest.main()
