"""Regression gates for executable price vs model-adjusted chart close.

Never mark a genuinely stale or inconsistent observation as validated.
"""
import unittest
from datetime import datetime

from forecast_freshness_audit import audit, executable_close
from vn_exchange_calendar import VN_TZ, next_trading_dates

SESSION = "2026-10-08"
NOW = datetime(2026, 10, 8, 16, 0, tzinfo=VN_TZ)
SYMBOLS = ("AGR", "ASP", "BTP", "C47", "EIB", "HDB", "LSS", "MIG", "TLD")


def documents(names=SYMBOLS):
    targets = next_trading_dates(SESSION, 5)
    symbols = {}
    charts = {}
    for i, name in enumerate(names):
        raw = 10000 + i * 50
        symbols[name] = {
            "date": SESSION, "dataFreshness": "CURRENT", "close": raw,
            "horizons": {str(h): {"targetDate": day} for h, day in enumerate(targets, 1)},
        }
        # A dividend/corporate-action adjusted training series can differ from
        # exchange close. Chart rawClose must still match the snapshot.
        charts[name] = [
            {"date": "2026-10-07", "close": raw-200, "rawClose": raw-100},
            {"date": SESSION, "close": raw * 0.97, "rawClose": raw},
        ]
    generated = "2026-10-08T17:00:00+07:00"
    dashboard = {"asOf": SESSION, "generatedAt": generated, "symbols": symbols, "charts": charts}
    current = {"asOf": SESSION, "generatedAt": generated, "symbols": symbols}
    market = {"asOf": SESSION, "generatedAt": generated, "model": {"universe": {"listedHOSE": len(symbols)}}}
    return dashboard, current, market


class ForecastFreshnessExecutableCloseTest(unittest.TestCase):
    def test_nine_symbols_with_adjusted_model_series_are_valid(self):
        result = audit(*documents(), now=NOW)
        self.assertEqual(result["status"], "PASS", result["errors"])
        self.assertEqual(result["checkedSymbols"], 9)
        self.assertFalse(result["errors"])

    def test_incorrect_real_close_still_fails(self):
        docs = documents(("AGR",))
        docs[0]["charts"]["AGR"][-1]["rawClose"] += 100
        result = audit(*docs, now=NOW)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("AGR: PRICE_CHART_MISMATCH", result["errors"])

    def test_missing_raw_close_must_not_be_accepted_as_adjusted_close(self):
        docs = documents(("ASP",))
        del docs[0]["charts"]["ASP"][-1]["rawClose"]
        result = audit(*docs, now=NOW)
        self.assertIn("ASP: UNVERIFIED_EXECUTABLE_CHART_CLOSE", result["errors"])

    def test_stale_chart_date_stays_blocked(self):
        docs = documents(("EIB",))
        docs[0]["charts"]["EIB"][-1]["date"] = "2026-10-07"
        result = audit(*docs, now=NOW)
        self.assertIn("EIB: STALE_CHART", result["errors"])

    def test_stale_snapshot_remains_blocked(self):
        docs = documents(("HDB",))
        docs[0]["symbols"]["HDB"]["date"] = "2026-10-07"
        result = audit(*docs, now=NOW)
        self.assertIn("HDB: STALE_PRICE", result["errors"])

    def test_true_false_non_finite_and_zero_close_still_rejected(self):
        for bad in (None, True, False, "", "NaN", "Infinity", -1, 0):
            with self.subTest(value=bad):
                self.assertIsNone(executable_close(bad))

    def test_float_noise_from_json_does_not_reject_same_vnd_close(self):
        docs = documents(("TLD",))
        actual = docs[0]["symbols"]["TLD"]["close"]
        docs[0]["charts"]["TLD"][-1]["rawClose"] = float(actual) + 1e-12
        self.assertEqual(audit(*docs, now=NOW)["status"], "PASS")

    def test_wrong_target_day_cannot_pass(self):
        docs = documents(("BTP",))
        docs[0]["symbols"]["BTP"]["horizons"]["5"]["targetDate"] = "2026-10-09"
        result = audit(*docs, now=NOW)
        self.assertTrue(any("T+5_TARGET_MISMATCH" in e for e in result["errors"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
