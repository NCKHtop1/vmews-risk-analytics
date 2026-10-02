import gzip
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from solution_ai_core_confirmation import load_symbols, normalize_vn_close, parse_tcbs_payload, parse_yahoo_payload

VN = ZoneInfo("Asia/Ho_Chi_Minh")


class SolutionAICoreConfirmationTest(unittest.TestCase):
    def test_extracts_matching_session_close(self):
        stamps = [
            int(datetime(2026, 10, 1, 9, 0, tzinfo=VN).timestamp()),
            int(datetime(2026, 10, 2, 9, 0, tzinfo=VN).timestamp()),
        ]
        payload = {
            "chart": {
                "result": [{
                    "timestamp": stamps,
                    "indicators": {"quote": [{"close": [62000, 62100]}]},
                }]
            }
        }
        self.assertEqual(parse_yahoo_payload(payload, "2026-10-02"), 62100)

    def test_missing_session_returns_none(self):
        stamp = int(datetime(2026, 10, 1, 9, 0, tzinfo=VN).timestamp())
        payload = {
            "chart": {
                "result": [{
                    "timestamp": [stamp],
                    "indicators": {"quote": [{"close": [62000]}]},
                }]
            }
        }
        self.assertIsNone(parse_yahoo_payload(payload, "2026-10-02"))

    def test_current_hose_universe_from_frozen_source_has_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dashboard = root / "forecast-dashboard-v12.json"
            dashboard.write_text(json.dumps({"symbols": {"FPT": {}, "HPG": {}}}), encoding="utf-8")
            frozen = root / "v12-frozen-source.json.gz"
            with gzip.open(frozen, "wt", encoding="utf-8") as stream:
                json.dump({"currentHOSESymbols": ["FPT", "HPG", "VCB", "MBB"]}, stream)
            self.assertEqual(load_symbols(dashboard, frozen), ["FPT", "HPG", "MBB", "VCB"])

    def test_tcbs_parser_extracts_matching_session_close(self):
        payload = {
            "data": [
                {"tradingDate": "2026-10-01T00:00:00", "close": 62000},
                {"tradingDate": "2026-10-02T00:00:00", "close": 62100},
            ]
        }
        self.assertEqual(parse_tcbs_payload(payload, "2026-10-02"), 62100)

    def test_tcbs_parser_rejects_other_session(self):
        payload = {"data": [{"tradingDate": "2026-10-01T00:00:00", "close": 62000}]}
        self.assertIsNone(parse_tcbs_payload(payload, "2026-10-02"))

    def test_normalize_vci_thousand_unit_close(self):
        self.assertEqual(normalize_vn_close(62.1), 62100.0)
        self.assertEqual(normalize_vn_close(62100), 62100.0)
        self.assertIsNone(normalize_vn_close(None))


if __name__ == "__main__":
    unittest.main()
