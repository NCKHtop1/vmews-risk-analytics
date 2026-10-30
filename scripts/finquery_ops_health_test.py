"""Offline, deterministic regression tests for FinQuery reliability policy."""
import copy
import unittest
from datetime import datetime, timezone

from finquery_ops_health import clock, evaluate, parse_ts, markdown_report

NOW = datetime(2026, 10, 24, 4, 30, tzinfo=timezone.utc)  # Saturday in Vietnam
SESSION = "2026-10-23"
SOURCE_TIME = "2026-10-23T07:45:00+00:00"


def fixtures():
    return {
        "quotes": {"latestSourceTime": SOURCE_TIME, "coverage": 111,
                   "expected": 111, "status": "ok"},
        "risk": {"sourceDate": SESSION, "sourceTime": SOURCE_TIME},
        "strategy": {"sourceTime": SOURCE_TIME,
                     "symbols": {
                         "MBB": {"tier": "CORE", "barDate": SESSION},
                         "AAA": {"tier": "DISCOVERY", "barDate": SESSION}}},
        "forecast": {"status": "PASS", "asOf": SESSION, "symbols": 100, "horizons": 500,
                     "freshHistory": 100, "generatedAt": "2026-10-23T08:00:00+00:00",
                     "forecastSessionDate": SESSION, "inputMode": "EOD",
                     "activeQuotes": 0},
        "intraday": {"success": 111, "expected": 111, "errors": []},
        "financial": {"coverage": {"members": 100, "annual": 100, "quarterly": 100},
                      "updatedAt": "2026-10-23T23:42:00+00:00"},
        "news": {"checkedAt": "2026-10-24T04:00:00+00:00"},
        "macro": {"lastSuccessAt": "2026-10-23T03:00:00+00:00", "sources": []},
        "esg": {"companies": 100, "companiesWithMetrics": 100},
        "live_track": {"calibrationLiveMonitor": {"status": "STABLE"}},
    }


def prod():
    return {"ok": True, "sessionAnonymous": True,
            "adminProtected": True, "dashboardProtected": True}


def find(result, code):
    return next(row for row in result["checks"] if row["code"] == code)


class OperationsMonitorTest(unittest.TestCase):
    def test_weekend_uses_friday_and_does_not_alarm_stale_minutes(self):
        self.assertEqual(clock(NOW)["expectedQuoteDate"], "2026-10-23")
        result = evaluate(fixtures(), NOW, prod())
        self.assertEqual(result["overall"], "OK", result)
        self.assertIsNone(next((x for x in result["checks"] if x["code"] == "QUOTE_LAG"), None))

    def test_stale_real_vn100_source_is_critical_even_if_old_overlay_reports_current(self):
        data = fixtures()
        data["forecast"]["asOf"] = "2026-10-20"
        result = evaluate(data, NOW, prod())
        self.assertEqual(find(result, "FORECAST_CORE")["severity"], "CRITICAL")

    def test_ops_monitor_does_not_poll_retired_legacy_core(self):
        from finquery_ops_health import SOURCES
        self.assertNotIn("forecast_legacy", SOURCES)
        self.assertIn("finquery-vn100-data", SOURCES["forecast"])
        result = evaluate(fixtures(), NOW, prod())
        self.assertFalse(any("LEGACY" in row["code"] for row in result["checks"]))
        self.assertEqual(find(result, "FORECAST_CORE")["severity"], "OK")

    def test_live_vn100_heartbeat_and_price_anchor_required(self):
        now = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)  # Friday 10:00 VN
        data = fixtures()
        data["forecast"].update({
            "asOf": "2026-10-29", "generatedAt": "2026-10-30T02:45:00+00:00",
            "inputMode": "INTRADAY", "activeQuotes": 100,
            "forecastSessionDate": "2026-10-30",
        })
        fresh = evaluate(data, now, prod())
        self.assertEqual(find(fresh, "FORECAST_CORE")["severity"], "OK")
        degraded = copy.deepcopy(data)
        degraded["forecast"]["activeQuotes"] = 0
        result = evaluate(degraded, now, prod())
        self.assertEqual(find(result, "FORECAST_CORE")["severity"], "CRITICAL")
        stale = copy.deepcopy(data)
        stale["forecast"]["generatedAt"] = "2026-10-30T01:20:00+00:00"
        result = evaluate(stale, now, prod())
        self.assertEqual(find(result, "FORECAST_CORE")["severity"], "CRITICAL")

    def test_inconsistent_market_snapshots_fail(self):
        data = fixtures()
        data["risk"]["sourceDate"] = "2026-10-22"
        result = evaluate(data, NOW, prod())
        self.assertEqual(find(result, "RISK_QUOTE_SYNC")["severity"], "CRITICAL")

    def test_quote_coverage_cannot_pass_on_small_sample(self):
        data = fixtures()
        data["quotes"]["coverage"] = 87
        result = evaluate(data, NOW, prod())
        self.assertEqual(find(result, "QUOTE_COVERAGE")["severity"], "CRITICAL")

    def test_discovery_staleness_is_visible_without_breaking_core(self):
        data = fixtures()
        data["strategy"]["symbols"]["AAA"]["barDate"] = "2026-08-13"
        result = evaluate(data, NOW, prod())
        self.assertEqual(find(result, "DISCOVERY_HISTORY")["severity"], "WARNING")
        self.assertEqual(find(result, "QUOTE_SESSION")["severity"], "OK")

    def test_anonymous_admin_route_must_be_denied(self):
        bad = prod()
        bad["adminProtected"] = False
        result = evaluate(fixtures(), NOW, bad)
        self.assertEqual(find(result, "AUTH_GUARD")["severity"], "CRITICAL")

    def test_unsupported_timestamp_is_not_silently_current(self):
        self.assertIsNone(parse_ts("2026-10-23"))
        self.assertIsNone(parse_ts("this-morning"))

    def test_official_2026_holiday_calendar(self):
        moment = datetime(2026, 9, 2, 3, 0, tzinfo=timezone.utc)
        self.assertFalse(clock(moment)["tradingDay"])
        self.assertEqual(clock(moment)["expectedQuoteDate"], "2026-08-28")

    def test_report_has_named_conditions(self):
        result = evaluate(fixtures(), NOW, prod())
        report = markdown_report(result)
        self.assertIn("RISK_QUOTE_SYNC", report)
        self.assertIn("FORECAST_CORE", report)


if __name__ == "__main__":
    unittest.main()
