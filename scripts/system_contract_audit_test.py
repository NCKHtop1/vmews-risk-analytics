from __future__ import annotations

import json
import os
import pathlib
import tempfile
import unittest
from datetime import datetime, timezone

FINQUERY_CORE_ONLY = os.environ.get("FINQUERY_CORE_ONLY", "").strip() == "1"


from system_contract_audit import (
    Audit,
    audit_market_bar_files,
    audit_legacy_forecast_isolation,
    RETIRED_MAIN_FORECAST_FILES,
    compute_intraday_session,
    production_prefers_solution_core,
    risk_eligible_symbols,
    solution_live_freshness,
)


class SystemContractAuditTests(unittest.TestCase):
    def test_risk_eligible_set_excludes_retained_and_misaligned_rows(self):
        quotes = {
            "quotes": {
                "AAA": {"status": "ok", "price": 10, "changePct": 1},
                "BBB": {"status": "retained", "price": 20, "changePct": -1},
                "CCC": {"status": "ok", "price": 30, "changePct": 0},
                "DDD": {"status": "ok", "price": 40, "changePct": None},
            }
        }
        strategy = {
            "symbols": {
                "AAA": {"cadence": "LIVE_15M", "barDate": "2026-10-07"},
                "BBB": {"cadence": "LIVE_15M", "barDate": "2026-10-07"},
                "CCC": {"cadence": "EOD", "barDate": "2026-10-07"},
                "DDD": {"cadence": "LIVE_15M", "barDate": "2026-10-07"},
            }
        }
        self.assertEqual(risk_eligible_symbols(quotes, strategy, "2026-10-07"), ["AAA"])

    def test_intraday_contract_recomputes_bar_lag_instead_of_trusting_status(self):
        quotes = {
            "quotes": {
                "AAA": {"status": "ok", "sourceTime": "2026-10-07T03:30:00+00:00"},
                "BBB": {"status": "ok", "sourceTime": "2026-10-07T03:30:00+00:00"},
                "CCC": {"status": "retained", "sourceTime": "2026-10-07T03:30:00+00:00"},
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "intraday").mkdir()
            (root / "intraday" / "AAA.json").write_text(json.dumps({
                "lastBar": "2026-10-07T03:20:00+00:00", "bars": []
            }))
            (root / "intraday" / "BBB.json").write_text(json.dumps({
                "lastBar": "2026-10-07T02:50:00+00:00", "bars": []
            }))
            out = compute_intraday_session(root, quotes, "2026-10-07", 20)
        self.assertEqual(out["expected"], ["AAA", "BBB"])
        self.assertEqual(out["fresh"], ["AAA"])
        self.assertEqual(out["lagged"], [("BBB", 40.0)])

    def test_deep_history_requires_files_only_for_live_names_not_discovery(self):
        universe = {
            "symbols": {
                "LIVE": {"liveMarketEligible": True, "scannerEligible": True, "latestDate": "2026-10-07"},
                "DISC": {"liveMarketEligible": False, "scannerEligible": True, "latestDate": "2026-10-07"},
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "history").mkdir()
            (root / "intraday").mkdir()
            daily = {
                "symbol": "LIVE", "unit": "VND", "barCount": 1, "lastBar": "2026-10-07",
                "bars": [{"time": "2026-10-07", "open": 100, "high": 110, "low": 95, "close": 105, "volume": 1000}],
            }
            minute = {
                "symbol": "LIVE", "unit": "VND", "barCount": 1, "lastBar": "2026-10-07T03:00:00+00:00",
                "bars": [{"time": "2026-10-07T03:00:00+00:00", "open": 100, "high": 110, "low": 95, "close": 105, "volume": 1000}],
            }
            (root / "history" / "LIVE.json").write_text(json.dumps(daily))
            (root / "intraday" / "LIVE.json").write_text(json.dumps(minute))
            audit = Audit()
            audit_market_bar_files(
                audit, root, universe,
                datetime(2026, 10, 7, 4, 0, tzinfo=timezone.utc),
                "2026-10-07",
            )
        self.assertFalse(any(row["detail"] == "DISC" and row["status"] == "FAIL" for row in audit.results))
        self.assertFalse(audit.errors)

    def test_deep_history_rejects_invalid_live_ohlc(self):
        universe = {
            "symbols": {
                "LIVE": {"liveMarketEligible": True, "scannerEligible": True, "latestDate": "2026-10-07"},
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "history").mkdir()
            (root / "intraday").mkdir()
            daily = {
                "symbol": "LIVE", "unit": "VND", "barCount": 1, "lastBar": "2026-10-07",
                "bars": [{"time": "2026-10-07", "open": 110, "high": 105, "low": 95, "close": 108, "volume": 1000}],
            }
            minute = {
                "symbol": "LIVE", "unit": "VND", "barCount": 1, "lastBar": "2026-10-07T03:00:00+00:00",
                "bars": [{"time": "2026-10-07T03:00:00+00:00", "open": 100, "high": 110, "low": 95, "close": 105, "volume": 1000}],
            }
            (root / "history" / "LIVE.json").write_text(json.dumps(daily))
            (root / "intraday" / "LIVE.json").write_text(json.dumps(minute))
            audit = Audit()
            audit_market_bar_files(
                audit, root, universe,
                datetime(2026, 10, 7, 4, 0, tzinfo=timezone.utc),
                "2026-10-07",
            )
        self.assertTrue(any(row["code"] == "MARKET_HISTORY_OHLC" and row["status"] == "FAIL" for row in audit.results))


    def test_legacy_core_is_archived_and_not_exposed_in_current_repo(self):
        from system_contract_audit import ROOT
        self.assertTrue(production_prefers_solution_core(ROOT))
        audit = Audit()
        audit_legacy_forecast_isolation(audit, ROOT)
        self.assertFalse(audit.errors, audit.errors)

    def test_restore_of_any_retired_data_file_fails_contract(self):
        from system_contract_audit import ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "scripts").mkdir()
            (root / "data").mkdir()
            (root / "scripts" / "finquery_vn100_timeseries.py").write_text(
                (ROOT / "scripts" / "finquery_vn100_timeseries.py").read_text(encoding="utf-8"))
            (root / "forecast-final-v12.js").write_text(
                (ROOT / "forecast-final-v12.js").read_text(encoding="utf-8"))
            (root / RETIRED_MAIN_FORECAST_FILES[0]).write_text('{"asOf":"2026-10-20"}')
            audit = Audit()
            audit_legacy_forecast_isolation(audit, root)
            self.assertIn("FORECAST_RETIRED_MAIN_ASSETS",
                          {row["code"] for row in audit.errors})

    @unittest.skipIf(FINQUERY_CORE_ONLY, "SoluTION.AI is outside the FinQuery system contract")
    def test_solution_live_active_session_requires_real_source_freshness(self):
        now = datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc)  # 10:00 Vietnam
        fresh = {
            "scope": "solution-ai", "status": "ok", "coverage": 600, "expected": 600,
            "generatedAt": "2026-10-07T02:59:00+00:00",
            "sourceTime": "2026-10-07T02:50:00+00:00",
        }
        ok, policy, _ = solution_live_freshness(fresh, now)
        self.assertTrue(ok)
        self.assertEqual(policy, "LIVE")

        stale = dict(fresh, generatedAt="2026-10-07T02:59:00+00:00", sourceTime="2026-10-05T08:00:00+00:00")
        ok, policy, _ = solution_live_freshness(stale, now)
        self.assertFalse(ok)
        self.assertEqual(policy, "LIVE")

    @unittest.skipIf(FINQUERY_CORE_ONLY, "SoluTION.AI is outside the FinQuery system contract")
    def test_solution_live_same_day_close_uses_source_day_not_generated_day(self):
        now = datetime(2026, 10, 7, 5, 30, tzinfo=timezone.utc)  # 12:30 Vietnam
        poisoned = {
            "scope": "solution-ai", "status": "ok", "coverage": 600, "expected": 600,
            "generatedAt": "2026-10-07T05:29:00+00:00",
            "sourceTime": "2026-10-06T08:00:00+00:00",
        }
        ok, policy, _ = solution_live_freshness(poisoned, now)
        self.assertFalse(ok)
        self.assertEqual(policy, "SAME_DAY_SESSION")



class FinQueryCanonicalForecastContractTests(unittest.TestCase):
    """Reproducible regressions for the actual VN100 production model route."""

    @staticmethod
    def fixture(now):
        import hashlib
        from system_contract_audit import ROOT

        symbols = [f"S{i:03d}" for i in range(100)]
        horizons = {"1", "2", "3", "4", "5"}
        stamp = "2026-10-30T09:55:00+07:00"
        dates = [
            "2026-10-20", "2026-10-21", "2026-10-22",
            "2026-10-23", "2026-10-26", "2026-10-27",
            "2026-10-28", "2026-10-29",
        ]
        targets = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
        forecast_symbols = {}
        charts = {}
        for symbol in symbols:
            forecast_symbols[symbol] = {
                "historicalAsOf": "2026-10-29",
                "forecastHistoricalAsOf": "2026-10-29",
                "forecastSessionDate": "2026-10-30",
                "forecastAnchorBasis": "INTRADAY_QUOTE",
                "forecastAnchorAt": "2026-10-30T09:54:00+07:00",
                "forecastAnchorClose": 10000,
                "horizons": {h: {
                    "expectedPrice": 10000 + 100 * int(h),
                    "q20Price": 9900,
                    "q80Price": 11000,
                    "priceValidated": True,
                    "targetDate": targets[int(h) - 1],
                } for h in horizons},
            }
            charts[symbol] = [{"date": d, "close": 10000, "rawClose": 10000} for d in dates]

        scores = {h: {"metrics": {"n": 120, "executableMAESkill": .05}}
                  for h in horizons}
        cases = {h: [{"symbol": symbol} for symbol in symbols] for h in horizons}
        product = {
            "status": "PASS", "asOf": "2026-10-29", "generatedAt": stamp,
            "universe": {"available": 100, "freshHistory": 100, "inputMode": "INTRADAY"},
            "dashboard": {
                "asOf": "2026-10-29", "symbols": forecast_symbols, "charts": charts,
            },
            "model": {"promotion": {"status": "PASS"}, "horizons": scores},
            "gates": {"status": "PASS"},
            "backtest": {"horizons": scores, "cases": cases},
        }
        full = {
            "status": "PASS", "asOf": "2026-10-29", "generatedAt": stamp,
            "gates": {"status": "PASS"},
        }
        status = {
            "status": "PASS", "asOf": "2026-10-29", "generatedAt": stamp,
            "symbols": 100, "horizons": 500, "freshHistory": 100,
            "inputMode": "INTRADAY", "activeQuotes": 100,
            "forecastSessionDate": "2026-10-30",
            "backtestCases": {h: len(rows) for h, rows in cases.items()},
        }
        return symbols, product, full, status

    @staticmethod
    def run_audit(symbols, product, full, status, now):
        import hashlib
        from system_contract_audit import audit_finquery_vn100

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            product_bytes = json.dumps(product, separators=(",", ":")).encode()
            full_bytes = json.dumps(full, separators=(",", ":")).encode()
            status["productBytes"] = len(product_bytes)
            status["sourceSha256"] = hashlib.sha256(full_bytes).hexdigest()
            (root / "finquery-vn100-product.json").write_bytes(product_bytes)
            (root / "finquery-vn100-forecast.json").write_bytes(full_bytes)
            (root / "finquery-vn100-status.json").write_text(json.dumps(status))
            report = Audit()
            ready = audit_finquery_vn100(report, root, set(symbols), now)
            return ready, report

    def test_actual_production_loader_uses_canonical_vn100_not_old_main(self):
        from system_contract_audit import ROOT, production_uses_finquery_vn100_core

        self.assertTrue(production_uses_finquery_vn100_core(ROOT))
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source = (ROOT / "forecast-final-v12.js").read_text(encoding="utf-8")
            (root / "forecast-final-v12.js").write_text(
                source.replace("const bundle=await loadVN100();",
                               'const bundle=await json("forecast-dashboard-v12.json");'))
            self.assertFalse(production_uses_finquery_vn100_core(root))

    def test_valid_complete_verified_vn100_passes_even_when_legacy_is_stale(self):
        now = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
        data = self.fixture(now)
        ready, report = self.run_audit(*data, now)
        self.assertTrue(ready, report.errors)
        self.assertFalse(report.errors)

    def test_stale_vn100_is_not_accepted_by_new_contract(self):
        now = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
        symbols, product, full, status = self.fixture(now)
        for record in (product, full, status):
            record["asOf"] = "2026-10-20"
        ready, report = self.run_audit(symbols, product, full, status, now)
        self.assertFalse(ready)
        self.assertIn("FORECAST_VN100_SESSION", {e["code"] for e in report.errors})

    def test_torn_or_partial_snapshot_is_not_mistaken_for_new_run(self):
        now = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
        symbols, product, full, status = self.fixture(now)
        status["horizons"] = 499
        ready, report = self.run_audit(symbols, product, full, status, now)
        self.assertFalse(ready)
        self.assertIn("FORECAST_VN100_HORIZONS", {e["code"] for e in report.errors})

    def test_source_backtest_skill_is_not_fabricated_as_pass(self):
        now = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
        symbols, product, full, status = self.fixture(now)
        product["backtest"]["horizons"]["3"]["metrics"]["executableMAESkill"] = -.03
        ready, report = self.run_audit(symbols, product, full, status, now)
        self.assertTrue(ready, report.errors)
        self.assertIn("FORECAST_VN100_SKILL_UNPROVEN_3",
                      {w["code"] for w in report.warnings})

    def test_missing_live_market_anchor_blocks_canonical_promotion(self):
        now = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
        symbols, product, full, status = self.fixture(now)
        status["inputMode"] = "EOD"
        status["activeQuotes"] = 0
        ready, report = self.run_audit(symbols, product, full, status, now)
        self.assertFalse(ready)
        self.assertIn("FORECAST_VN100_INTRADAY_SESSION",
                      {e["code"] for e in report.errors})


if __name__ == "__main__":
    unittest.main()
