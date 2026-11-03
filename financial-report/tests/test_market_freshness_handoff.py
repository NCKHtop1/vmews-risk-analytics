"""No-silent-gap regression tests for FinQuery market publishers."""
from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "financial-report" / "scripts" / "price_session_policy.py"
spec = importlib.util.spec_from_file_location("price_session_policy", MODULE)
policy = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(policy)
VN = ZoneInfo("Asia/Ho_Chi_Minh")


def at(hour: int, minute: int, day: int = 3):
    return datetime(2026, 11, day, hour, minute, tzinfo=VN)


class PriceHandoffTests(unittest.TestCase):
    def check(self, hour, minute, run, oneshot, bridge):
        actual = policy.session_policy(at(hour, minute), "workflow_run")
        self.assertEqual(actual, {"run": run, "oneshot": oneshot, "bridge_afternoon": bridge})

    def test_preopen(self):
        self.check(8, 55, "true", "0", "true")

    def test_morning(self):
        self.check(11, 29, "true", "0", "true")

    def test_boundary_1140(self):
        self.check(11, 40, "true", "0", "true")

    def test_incident_1142_never_exits_green(self):
        self.check(11, 42, "true", "1", "true")

    def test_lunch_successor(self):
        self.check(12, 54, "true", "1", "true")

    def test_afternoon(self):
        self.check(12, 55, "true", "0", "false")
        self.check(13, 47, "true", "0", "false")

    def test_close(self):
        self.check(15, 5, "true", "0", "false")
        self.check(15, 6, "false", "1", "false")

    def test_manual_outside(self):
        self.assertEqual(policy.session_policy(at(16, 0), "workflow_dispatch")["run"], "true")

    def test_weekend_automatic_off(self):
        self.assertEqual(policy.session_policy(at(13, 45, day=7), "schedule")["run"], "false")

    def test_guarded_handoff_contract(self):
        workflow = (ROOT / ".github/workflows/market-price-live.yml").read_text()
        self.assertIn("bridge_afternoon: ${{ steps.session.outputs.bridge_afternoon }}", workflow)
        self.assertIn("needs.prices.outputs.bridge_afternoon == 'true'", workflow)
        self.assertIn("MARKET_MAX_QUOTE_AGE_MINUTES: '18'", workflow)
        self.assertIn("bash financial-report/scripts/live_session_publisher.sh", workflow)
        news = (ROOT / ".github/workflows/market-news-live.yml").read_text()
        self.assertIn("cancel-in-progress: false", news)
        self.assertIn("cron: '7,22,37,52 * * * *'", news)

    def test_ui_does_not_claim_no_trade_when_stale(self):
        text = (ROOT / "financial-report/frontend/market.js").read_text()
        self.assertIn("Giá chưa được cập nhật", text)
        self.assertIn("Tin tức chậm cập nhật", text)
        self.assertNotIn("Chưa có giao dịch mới", text)


if __name__ == "__main__":
    unittest.main()
