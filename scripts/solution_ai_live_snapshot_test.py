import importlib.util
import pathlib
import unittest
from datetime import datetime, timezone

SCRIPT = pathlib.Path(__file__).with_name("solution_ai_live_snapshot.py")
SPEC = importlib.util.spec_from_file_location("solution_ai_live_snapshot", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def iterrows(self):
        return enumerate(self.rows)


class SnapshotTests(unittest.TestCase):
    def test_build_snapshot_keeps_valid_vietnam_quotes_and_prefers_hose_duplicate(self):
        now = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)
        base_ts = int(now.timestamp())
        rows = []
        exchanges = ["HOSE", "HNX", "UPCOM"]
        for i in range(520):
            rows.append({
                "name": f"X{i:03d}",
                "exchange": exchanges[i % 3],
                "close": 10000 + i,
                "change": 1.25,
                "volume": 1000 + i,
                "open": 9900 + i,
                "high": 10100 + i,
                "low": 9800 + i,
                "update_mode": "delayed_streaming_900",
                "update_time": base_ts - (i % 60),
            })
        rows.extend([
            {
                "name": "DUP",
                "exchange": "UPCOM",
                "close": 12000,
                "change": 0,
                "volume": 1,
                "open": 12000,
                "high": 12000,
                "low": 12000,
                "update_mode": "streaming",
                "update_time": base_ts,
            },
            {
                "name": "DUP",
                "exchange": "HOSE",
                "close": 13000,
                "change": 2,
                "volume": 2,
                "open": 12900,
                "high": 13100,
                "low": 12800,
                "update_mode": "streaming",
                "update_time": base_ts,
            },
        ])

        snapshot = MOD.build_snapshot(FakeFrame(rows), now=now)
        self.assertEqual(snapshot["scope"], "solution-ai")
        self.assertEqual(snapshot["status"], "ok")
        self.assertGreaterEqual(snapshot["coverage"], 500)
        self.assertEqual(snapshot["quotes"]["DUP"]["exchange"], "HOSE")
        self.assertEqual(snapshot["quotes"]["DUP"]["price"], 13000)
        self.assertEqual(snapshot["sourceTime"], now.isoformat())

    def test_small_snapshot_fails_closed(self):
        rows = [{
            "name": "FPT",
            "exchange": "HOSE",
            "close": 100000,
            "update_time": 1790928000,
        }]
        with self.assertRaises(RuntimeError):
            MOD.build_snapshot(FakeFrame(rows))


if __name__ == "__main__":
    unittest.main()
