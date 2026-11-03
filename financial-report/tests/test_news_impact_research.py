import importlib.util
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "financial-report/scripts/research_news_impact.py"
SPEC = importlib.util.spec_from_file_location("finquery_news_impact_research", PATH)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class NewsImpactResearchTests(unittest.TestCase):
    def test_timestamps_and_trading_session_boundary(self):
        self.assertEqual(M.parse_time("Tue, 03 Nov 2026 07:00:00 GMT").hour, 7)
        days = ["2026-10-30", "2026-11-02", "2026-11-03", "2026-11-04"]
        vn = ZoneInfo("Asia/Ho_Chi_Minh")
        self.assertEqual(M.entry_index(days, datetime(2026, 11, 3, 8, 45, tzinfo=vn)), 2)
        self.assertEqual(M.entry_index(days, datetime(2026, 11, 3, 9, 1, tzinfo=vn)), 3)
        self.assertEqual(M.entry_index(days, datetime(2026, 11, 1, 15, 30, tzinfo=vn)), 1)

    def test_issuer_guard_quarantines_subsidiary_and_currency_collision(self):
        self.assertFalse(M.issuer_identity("FPT", "FPT Retail lên kế hoạch chia cổ tức"))
        self.assertTrue(M.issuer_identity("FPT", "Cổ phiếu FPT tăng sau báo cáo"))
        self.assertFalse(M.issuer_identity("VND", "USD/VND tăng sau cuộc họp"))
        self.assertTrue(M.issuer_identity("HCM", "Cổ phiếu HCM công bố thông tin"))

    def test_unknown_tone_never_fabricates_direction(self):
        self.assertEqual(M.polarity("Doanh nghiệp công bố thông tin tài chính"), "UNKNOWN")
        self.assertEqual(M.polarity("Doanh nghiệp lỗ ròng, lợi nhuận giảm"), "NEG")
        self.assertEqual(M.polarity("Lợi nhuận tăng mạnh"), "POS")

    def test_future_bar_and_bad_split_rejected(self):
        h = {"bars": [
            {"day":"2026-10-01", "open":100, "close":110},
            {"day":"2026-10-02", "open":110, "close":250}
        ], "days":["2026-10-01","2026-10-02"]}
        self.assertIsNotNone(M.log_return(h, 0, 1))
        self.assertIsNone(M.log_return(h, 0, 3))
        self.assertIsNone(M.log_return(h, 1, 1))

    def test_multiple_hypotheses_are_corrected(self):
        q = M.benjamini_hochberg([0.01, 0.02, 0.9])
        self.assertAlmostEqual(q[0], 0.03, places=5)
        self.assertAlmostEqual(q[1], 0.03, places=5)
        self.assertAlmostEqual(q[2], 0.9, places=5)

    def test_no_data_never_becomes_alert(self):
        out = M.report_impact([], {}, {})
        self.assertEqual(out["status"], "NO_MATURE_EVENTS")

    def test_insufficient_price_history_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            rows = [{"time":f"2026-10-{day:02d}","open":100,"close":101,"volume":1000}
                    for day in range(1, 30)]
            (base/"FPT.json").write_text(json.dumps({"bars":rows}))
            h = M.read_history(base)
            self.assertEqual(h, {})

    def test_v12_maturity_and_benchmark_are_mandatory(self):
        row = {"benchmarkAvailable": {"3": True}, "matureDate": {"3": "2025-01-10"},
               "cumulativeAbnormalReturn": {"3": 0.02}}
        self.assertEqual(M._finite_outcome(row, 3), (0.02, "2025-01-10"))
        row["benchmarkAvailable"]["3"] = False
        self.assertIsNone(M._finite_outcome(row, 3))

    def test_v12_research_cannot_issue_alerts_on_tiny_backfill(self):
        event = {"ticker":"FPT","title":"Cổ phiếu FPT báo lãi tăng","availableDate":"2019-01-02",
                 "publishedAt":"2019-01-02T02:00:00+00:00","eventType":"EARNINGS",
                 "sentimentLabel":"POS", "source":"TestPress",
                 "benchmarkAvailable":{"1":True},
                 "matureDate":{"1":"2019-01-03"},
                 "cumulativeAbnormalReturn":{"1":0.03}}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"events.json"
            path.write_text(json.dumps({"version":"test","records":[event]}))
            report=M.analyze_v12_events(path)
            self.assertEqual(report["productionReadyGroups"],0)
            self.assertEqual(report["descriptiveCandidates"],0)

    def test_live_notification_cannot_be_enabled_by_research_workflow(self):
        workflow = (ROOT / ".github/workflows/finquery-news-impact-research.yml").read_text()
        self.assertIn("contents: read", workflow)
        self.assertIn("research_news_impact.py", workflow)
        self.assertIn("ref: financial-market-data", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("push origin", workflow)
        self.assertNotIn("git push", workflow)


if __name__ == "__main__":
    unittest.main()
