from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from datetime import datetime, timezone

from system_contract_audit import (
    compute_intraday_session,
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
