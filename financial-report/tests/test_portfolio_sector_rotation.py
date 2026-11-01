"""Deterministic regression tests for the Portfolio sector 5/20-session quant snapshot."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import date, timedelta

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_portfolio_sector_rotation.py"
spec = importlib.util.spec_from_file_location("portfolio_rs_builder", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PortfolioRS(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.market = Path(self.temp.name)
        (self.market / "history").mkdir()
        trading = []
        today = date(2026, 10, 30)
        day = today - timedelta(days=46)
        while day <= today:
            if day.weekday() < 5:
                trading.append(day.isoformat())
            day += timedelta(days=1)
        self.trading = trading
        self.symbols = [f"A{i:02}" for i in range(14)]
        for k, symbol in enumerate(self.symbols):
            drift = (k - 6) * .001
            bars = [{"time": d, "close": round(100 * (1 + drift) ** j, 7)}
                    for j, d in enumerate(trading)]
            (self.market / "history" / (symbol + ".json")).write_text(json.dumps({
                "interval": "1D", "bars": bars
            }))
        sectors = [
            {"id": "g1", "label": "Group 1", "memberRows": [{"symbol": x} for x in self.symbols[:5]]},
            {"id": "g2", "label": "Group 2", "memberRows": [{"symbol": x} for x in self.symbols[5:10]]},
            {"id": "g3", "label": "Group 3", "memberRows": [{"symbol": x} for x in self.symbols[10:]]},
        ]
        (self.market / "risk-monitor.json").write_text(json.dumps({
            "sourceDate": today.isoformat(), "sourceTime": "2026-10-30T07:45:00Z", "sectors": sectors
        }))

    def tearDown(self):
        self.temp.cleanup()

    def test_5_and_20_session_relative_median_and_ranks(self):
        result = module.build(self.market)
        self.assertEqual(result["sourceDate"], "2026-10-30")
        self.assertEqual(result["benchmark"]["eligibleSymbols"], 14)
        self.assertEqual(len(result["sectors"]), 3)
        self.assertGreater(result["stocks"]["A13"]["rs20"], result["stocks"]["A00"]["rs20"])
        self.assertEqual(result["stocks"]["A04"]["rankWithinSector"], 1)
        self.assertEqual(result["stocks"]["A00"]["rankWithinSector"], 5)
        self.assertEqual(len(result["sectors"][0]["trail"]), 6)
        self.assertEqual(result["note"].startswith("Not JdK RRG"), True)

    def test_stale_history_is_excluded_not_fabricated(self):
        stale = self.symbols[0]
        path = self.market / "history" / (stale + ".json")
        doc = json.loads(path.read_text())
        doc["bars"] = doc["bars"][:-1]
        path.write_text(json.dumps(doc))
        result = module.build(self.market)
        self.assertNotIn(stale, result["stocks"])
        self.assertEqual(result["benchmark"]["eligibleSymbols"], 13)
        self.assertEqual(next(x for x in result["sectors"] if x["id"] == "g1")["used"], 4)

    def test_insufficient_market_fails_closed(self):
        for symbol in self.symbols[:6]:
            (self.market / "history" / (symbol + ".json")).unlink()
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            module.build(self.market)


if __name__ == "__main__":
    unittest.main()
