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
    audit_main_forecast,
    audit_market_bar_files,
    compute_intraday_session,
    production_uses_finquery_main_core,
    risk_eligible_symbols,
    solution_live_freshness,
)


class SystemContractAuditTests(unittest.TestCase):
    def test_system_contract_workflow_verifies_pages_on_push_with_safe_sha_parsing(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        workflow=(root/'.github'/'workflows'/'system-contract-audit.yml').read_text(encoding='utf-8')
        self.assertIn("github.event_name == 'push'",workflow)
        self.assertIn("Verify current Pages production generation",workflow)
        self.assertIn("read -r code_sha financial_sha insight_sha market_sha",workflow)
        self.assertNotIn('python -c \\"import json; print(json.load',workflow)

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


    def test_production_loader_uses_finquery_main_core_and_market_quotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "forecast-final-v12.js").write_text(
                'const FINQUERY_LIVE_URL="https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/quotes.json";\n'
                'const roots=[ROOT];\n'
                'window.dispatchEvent(new CustomEvent("vmews:live-quotes-updated",{detail:{scope:"finquery-market"}}));\n',
                encoding="utf-8",
            )
            self.assertTrue(production_uses_finquery_main_core(root))

    @unittest.skipIf(FINQUERY_CORE_ONLY, "SoluTION.AI is outside the FinQuery system contract")
    def test_stale_main_becomes_warning_only_when_dedicated_core_is_authoritative_and_fallback_abstains(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            data = root / "data"
            data.mkdir()
            dashboard = {
                "asOf": "2026-09-29",
                "modelVersion": "V",
                "symbols": {"AAA": {}},
                "promotion": {"preferredRankingHorizon": 3},
            }
            current = {"asOf": "2026-09-29", "modelVersion": "V", "symbols": {"AAA": {}}}
            market = {
                "asOf": "2026-09-29",
                "version": "V",
                "sources": {
                    "marketScanAsOf": "2026-09-29",
                    "priceSessionAsOf": "2026-09-29",
                    "priceCrossSource": {
                        "status": "PASS",
                        "coverage": 1.0,
                        "requiredCoverage": 0.9,
                        "mismatchCount": 0,
                    },
                },
            }
            release = {"asOf": "2026-09-29", "status": "PASS", "blockers": [], "scope": {"symbols": 1}}
            session = {
                "status": "PASS",
                "coreAsOf": "2026-09-29",
                "coreForecastUnchanged": True,
                "mode": "PRICE_ONLY_STALE_CORE",
                "rankingHorizon": 3,
                "leaders": [],
                "coverage": {
                    "coverageRatio": 1.0,
                    "currentCoverageRatio": 0.8,
                    "cutoffFreshCoverageRatio": 0.8,
                },
                "forecastAlignment": {
                    "status": "STALE_CORE",
                    "rankingEligible": False,
                    "actualCoreAsOf": "2026-09-29",
                    "expectedCoreAsOf": "2026-10-06",
                },
            }
            for name, payload in {
                "forecast-dashboard-v12.json": dashboard,
                "forecast-current-v12.json": current,
                "forecast-market-v13.json": market,
                "release-audit-v20.json": release,
                "forecast-session-v21.json": session,
            }.items():
                (data / name).write_text(json.dumps(payload), encoding="utf-8")

            audit = Audit()
            audit_main_forecast(
                audit,
                root,
                datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc),
                authoritative_core_ready=True,
            )

        self.assertFalse(audit.errors)
        warning_codes = {row["code"] for row in audit.results if row["status"] == "WARN"}
        self.assertIn("FORECAST_MAIN_SESSION", warning_codes)
        self.assertIn("FORECAST_V21_FALLBACK_STALE", warning_codes)
        self.assertTrue(any(row["code"] == "FORECAST_V21_FALLBACK_SAFE" and row["status"] == "PASS" for row in audit.results))

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


if __name__ == "__main__":
    unittest.main()
