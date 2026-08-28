from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from vn_exchange_calendar import VN_TZ, is_trading_day, latest_completed_session, next_trading_dates


class VietnamExchangeCalendarTest(unittest.TestCase):
    def test_august_28_targets_skip_national_day_break(self):
        self.assertEqual(
            next_trading_dates("2026-08-28", 5),
            ["2026-09-03", "2026-09-04", "2026-09-07", "2026-09-08", "2026-09-09"],
        )

    def test_national_day_break_is_not_trading_time(self):
        for value in ("2026-08-31", "2026-09-01", "2026-09-02"):
            self.assertFalse(is_trading_day(datetime.fromisoformat(value).date(), require_certified=True))
        self.assertTrue(is_trading_day(datetime.fromisoformat("2026-09-03").date(), require_certified=True))

    def test_completed_session_during_holiday_stays_on_august_28(self):
        now = datetime(2026, 9, 2, 16, 0, tzinfo=VN_TZ)
        self.assertEqual(latest_completed_session(now).isoformat(), "2026-08-28")

    def test_uncertified_future_target_year_fails_closed(self):
        with self.assertRaises(RuntimeError):
            next_trading_dates("2026-12-31", 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
