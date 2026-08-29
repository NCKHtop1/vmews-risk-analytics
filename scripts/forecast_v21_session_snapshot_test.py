import unittest
from datetime import datetime, timezone, timedelta

import pandas as pd

from forecast_v21_session_snapshot import build_payload, VN_TZ


class ForecastV21SessionSnapshotTest(unittest.TestCase):
    def dashboard(self, count=120, as_of="2026-08-24"):
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
        return {"asOf": as_of, "symbols": symbols}

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

    def test_pre_open_accepts_latest_completed_quote_matching_core_date(self):
        now = datetime(2026, 8, 25, 7, 15, tzinfo=VN_TZ)
        completed = datetime(2026, 8, 24, 15, 5, tzinfo=VN_TZ)
        payload = build_payload(self.dashboard(), self.frame(now=completed), now)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["session"], "PRE_OPEN")
        self.assertEqual(payload["coverage"]["expectedQuoteDate"], "2026-08-24")
        self.assertEqual(payload["coverage"]["currentQuoteDate"], 120)
        self.assertEqual(payload["coverage"]["cutoffFresh"], 120)
        self.assertEqual(payload["forecastAlignment"]["status"], "PASS")
        self.assertTrue(payload["forecastAlignment"]["rankingEligible"])

    def test_pre_open_rejects_quote_not_matching_latest_completed_session(self):
        now = datetime(2026, 8, 25, 7, 15, tzinfo=VN_TZ)
        wrong = datetime(2026, 8, 22, 15, 5, tzinfo=VN_TZ)
        payload = build_payload(self.dashboard(), self.frame(now=wrong), now)
        self.assertEqual(payload["status"], "DEGRADED")
        self.assertEqual(payload["coverage"]["currentQuoteDate"], 0)

    def test_pre_open_publishes_verified_prices_but_abstains_when_core_is_stale(self):
        now = datetime(2026, 8, 27, 7, 15, tzinfo=VN_TZ)
        completed = datetime(2026, 8, 26, 15, 5, tzinfo=VN_TZ)
        payload = build_payload(self.dashboard(as_of="2026-08-24"), self.frame(now=completed), now)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["mode"], "PRICE_ONLY_STALE_CORE")
        self.assertEqual(payload["coverage"]["expectedQuoteDate"], "2026-08-26")
        self.assertEqual(payload["coverage"]["currentQuoteDate"], 120)
        self.assertFalse(payload["forecastAlignment"]["rankingEligible"])
        self.assertEqual(payload["forecastAlignment"]["expectedCoreAsOf"], "2026-08-26")
        self.assertEqual(payload["leaders"], [])
        self.assertTrue(all(row["rankingHorizon"] is None for row in payload["symbols"]))

    def test_holiday_uses_latest_completed_session_for_quotes_and_core(self):
        now = datetime(2026, 9, 2, 12, 5, tzinfo=VN_TZ)
        completed = datetime(2026, 8, 28, 15, 5, tzinfo=VN_TZ)
        payload = build_payload(self.dashboard(as_of="2026-08-28"), self.frame(now=completed), now)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["session"], "MARKET_CLOSED")
        self.assertEqual(payload["coverage"]["expectedQuoteDate"], "2026-08-28")
        self.assertEqual(payload["forecastAlignment"]["status"], "PASS")

    def test_review_horizon_is_skipped_for_ranking(self):
        now = datetime(2026, 8, 25, 12, 5, tzinfo=VN_TZ)
        dashboard = self.dashboard()
        dashboard["promotion"] = {
            "directPriceHorizons": [1, 2, 3, 5],
            "reviewHorizons": [4],
            "preferredRankingHorizon": 3,
        }
        for snapshot in dashboard["symbols"].values():
            snapshot["horizons"]["3"] = dict(snapshot["horizons"]["5"])
        payload = build_payload(dashboard, self.frame(now=now), now)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["rankingHorizon"], 3)
        self.assertTrue(all(row["rankingHorizon"] == 3 for row in payload["symbols"]))

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
        payload = build_payload(self.dashboard(as_of="2026-08-25"), self.frame(now=now, price_multiplier=1.10), now)
        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["market"]["defensive"])
        self.assertEqual(payload["market"]["positiveCoreTargetFromLive"], 0)
        self.assertEqual(len(payload["leaders"]), 10)
        self.assertTrue(all(row["remainingUpsideT5"] < 0 for row in payload["leaders"]))


if __name__ == "__main__":
    unittest.main()
