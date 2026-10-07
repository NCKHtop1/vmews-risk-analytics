import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import finalize_intraday_archive as finalizer


class IntradayArchiveFinalizerTests(unittest.TestCase):
    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def minute_rows(self, base):
        return [
            {"time": "2026-10-07T02:15:00+00:00", "open": base, "high": base + 10, "low": base - 5, "close": base + 5, "volume": 100},
            {"time": "2026-10-07T02:19:00+00:00", "open": base + 5, "high": base + 20, "low": base, "close": base + 15, "volume": 200},
            {"time": "2026-10-07T07:44:00+00:00", "open": base + 15, "high": base + 30, "low": base + 10, "close": base + 25, "volume": 300},
        ]

    def test_completed_session_is_appended_without_deleting_prior_archive(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            symbols = ["AAA", "BBB"]
            self.write(root / "universe.json", {"liveMarketSymbols": symbols})
            self.write(root / "quotes.json", {"latestSourceTime": "2026-10-07T07:45:00+00:00"})
            self.write(root / "intraday-status.json", {"status": "ok"})
            for index, symbol in enumerate(symbols):
                self.write(root / "intraday" / f"{symbol}.json", {
                    "symbol": symbol, "bars": self.minute_rows(1000 + index * 100)
                })
                self.write(root / "intraday-5m" / f"{symbol}.json", {
                    "symbol": symbol, "bars": [
                        {"time": "2026-10-06T02:20:00+00:00", "open": 900, "high": 910, "low": 890, "close": 905, "volume": 50, "session": "CONTINUOUS_AM"}
                    ]
                })

            result = finalizer.finalize(root)
            self.assertEqual(result["session"], "2026-10-07")
            self.assertEqual(result["latestCoverage"], 2)
            self.assertEqual(result["written"], 2)

            status = json.loads((root / "intraday-status.json").read_text())
            self.assertEqual(status["archiveFinalizedSession"], "2026-10-07")
            self.assertEqual(status["archive5mLatestDay"], "2026-10-07")
            self.assertEqual(status["archive5mLatestDayCoverage"], 2)
            for symbol in symbols:
                archive = json.loads((root / "intraday-5m" / f"{symbol}.json").read_text())
                days = {row["time"][:10] for row in archive["bars"]}
                self.assertIn("2026-10-06", days)
                self.assertIn("2026-10-07", days)

    def test_finalizer_fails_closed_when_current_session_coverage_is_low(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            symbols = ["AAA", "BBB", "CCC"]
            self.write(root / "universe.json", {"liveMarketSymbols": symbols})
            self.write(root / "quotes.json", {"latestSourceTime": "2026-10-07T07:45:00+00:00"})
            self.write(root / "intraday-status.json", {"status": "ok"})
            for symbol in symbols[:2]:
                self.write(root / "intraday" / f"{symbol}.json", {"symbol": symbol, "bars": self.minute_rows(1000)})
            with self.assertRaisesRegex(RuntimeError, "coverage"):
                finalizer.finalize(root)


if __name__ == "__main__":
    unittest.main()
