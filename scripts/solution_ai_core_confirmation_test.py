import gzip
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from unittest.mock import patch

from solution_ai_core_confirmation import build_snapshot, load_symbols, parse_tcbs_payload, parse_vci_payload, parse_yahoo_payload

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

    def test_parse_vci_vector_payload_for_matching_session(self):
        stamps = [
            int(datetime(2026, 10, 1, 9, 0, tzinfo=VN).timestamp()),
            int(datetime(2026, 10, 2, 9, 0, tzinfo=VN).timestamp()),
        ]
        payload = [{"t": stamps, "c": [62000, 62100]}]
        self.assertEqual(parse_vci_payload(payload, "2026-10-02"), 62100)

    def test_parse_vci_row_payload_rejects_other_session(self):
        stamp = int(datetime(2026, 10, 1, 9, 0, tzinfo=VN).timestamp())
        self.assertIsNone(parse_vci_payload([{"t": stamp, "c": 62000}], "2026-10-02"))

    def test_build_snapshot_uses_independent_gap_fill_in_order(self):
        symbols = ["AAA", "BBB", "CCC"]

        def yahoo(symbol, session_date):
            return {"AAA": 10000}.get(symbol)

        def vci(symbol, session_date):
            return {"BBB": 20000}.get(symbol)

        def tcbs(symbol, session_date):
            return {"CCC": 30000}.get(symbol)

        with patch("solution_ai_core_confirmation.yahoo_close", side_effect=yahoo), \
             patch("solution_ai_core_confirmation.vci_close", side_effect=vci), \
             patch("solution_ai_core_confirmation.tcbs_close", side_effect=tcbs):
            snapshot = build_snapshot(symbols, "2026-10-02", workers=3)

        self.assertEqual(snapshot["coverage"], 3)
        self.assertEqual(snapshot["expected"], 3)
        self.assertEqual(snapshot["coverageRatio"], 1.0)
        self.assertEqual(snapshot["sourceCounts"]["YAHOO_FINANCE_DAILY"], 1)
        self.assertEqual(snapshot["sourceCounts"]["VCI_VNSTOCK_DAILY_GAPFILL"], 1)
        self.assertEqual(snapshot["sourceCounts"]["TCBS_PUBLIC_DAILY_GAPFILL"], 1)
        by_symbol = {row["symbol"]: row for row in snapshot["predictions"]}
        self.assertEqual(by_symbol["AAA"]["source"], "YAHOO_FINANCE_DAILY")
        self.assertEqual(by_symbol["BBB"]["source"], "VCI_VNSTOCK_DAILY_GAPFILL")
        self.assertEqual(by_symbol["CCC"]["source"], "TCBS_PUBLIC_DAILY_GAPFILL")



if __name__ == "__main__":
    unittest.main()
