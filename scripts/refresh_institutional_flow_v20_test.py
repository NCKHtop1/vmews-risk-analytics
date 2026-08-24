"""No-leakage/no-fabrication regression checks for incremental EOD flows."""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh_institutional_flow_v20 import (
    completed_session,
    load_fetch_shards,
    merge_observations,
    refresh_archive,
)


class InstitutionalFlowRefreshTest(unittest.TestCase):
    def test_intraday_and_weekend_use_only_completed_sessions(self) -> None:
        vn = timezone(timedelta(hours=7))
        self.assertEqual(completed_session(datetime(2026, 8, 24, 14, 0, tzinfo=vn)), date(2026, 8, 21))
        self.assertEqual(completed_session(datetime(2026, 8, 24, 16, 15, tzinfo=vn)), date(2026, 8, 21))
        self.assertEqual(completed_session(datetime(2026, 8, 24, 17, 0, tzinfo=vn)), date(2026, 8, 24))
        self.assertEqual(completed_session(datetime(2026, 8, 23, 20, 0, tzinfo=vn)), date(2026, 8, 21))

    def test_merging_preserves_history_and_rejects_future_or_fabricated_zero(self) -> None:
        previous = [{"date": "2026-08-14", "foreignNetValue": 35, "propNetValue": -7}]
        rows, added = merge_observations(previous, {
            "foreign": [
                {"date": "2026-08-21", "foreignBuyValue": 20, "foreignNetValue": 8},
                {"date": "2026-08-24", "foreignNetValue": 999},
                {"date": "2026-08-20", "foreignNetValue": 0},
            ],
            "proprietary": [{"date": "2026-08-21", "propNetValue": -4}],
        }, date(2026, 8, 21))
        self.assertEqual([row["date"] for row in rows], ["2026-08-14", "2026-08-21"])
        self.assertEqual(rows[0]["propNetValue"], -7)
        self.assertEqual(rows[1]["foreignNetValue"], 8)
        self.assertEqual(rows[1]["propNetValue"], -4)
        self.assertEqual(added, 2)

    def test_partial_provider_failure_cannot_destroy_existing_archive(self) -> None:
        archive = {"symbols": {"FPT": [{"date": "2026-08-14", "foreignNetValue": 6, "propNetValue": -2}]}, "summary": {"status": "PASS"}}

        def download(symbol: str, kind: str, start: date, end: date) -> list[dict[str, object]]:
            if kind == "proprietary":
                raise TimeoutError("temporarily unavailable")
            return [{"date": "2026-08-21", "foreignNetValue": 13}]

        refreshed, audit = refresh_archive(archive, date(2026, 8, 21), downloader=download, workers=1)
        self.assertEqual(refreshed["symbols"]["FPT"][0]["propNetValue"], -2)
        self.assertEqual(refreshed["symbols"]["FPT"][-1]["foreignNetValue"], 13)
        self.assertEqual(audit["summary"]["foreignLatest"], "2026-08-21")
        self.assertEqual(audit["summary"]["freshnessStatus"], "CURRENT")
        self.assertEqual(audit["summary"]["providerRequestFailures"], 1)
        self.assertEqual(audit["incrementalRefresh"]["futureRowsUsed"], 0)

    def test_one_fresh_symbol_cannot_mark_the_whole_market_current(self) -> None:
        archive = {"symbols": {
            "FPT": [{"date": "2026-08-14", "foreignNetValue": 6}],
            "VCB": [{"date": "2026-08-14", "foreignNetValue": 5}],
        }}

        def download(symbol: str, kind: str, start: date, end: date) -> list[dict[str, object]]:
            return [{"date": "2026-08-21", "foreignNetValue": 13}] if kind == "foreign" else []

        _, audit = refresh_archive(archive, date(2026, 8, 21), downloader=download, workers=1, selected_symbols={"FPT"})
        self.assertEqual(audit["summary"]["foreignFreshSymbols"], 1)
        self.assertEqual(audit["summary"]["foreignFreshCoverage"], .5)
        self.assertEqual(audit["summary"]["freshnessStatus"], "PARTIAL")

    def test_freshness_denominator_includes_names_without_provider_rows(self) -> None:
        archive = {"symbols": {
            "FPT": [{"date": "2026-08-14", "foreignNetValue": 6}],
            "NEW": [],
        }}

        def download(symbol: str, kind: str, start: date, end: date) -> list[dict[str, object]]:
            if symbol == "FPT" and kind == "foreign":
                return [{"date": "2026-08-21", "foreignNetValue": 13}]
            return []

        _, audit = refresh_archive(archive, date(2026, 8, 21), downloader=download, workers=1)
        self.assertEqual(audit["summary"]["foreignFreshCoverage"], .5)
        self.assertEqual(audit["summary"]["refreshSuccessCoverage"], 1.0)

    def test_missing_or_wrong_fetch_shards_are_rejected(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "FPT.json").write_text(json.dumps({
                "symbol": "FRT", "attemptedKinds": ["foreign", "proprietary"]
            }), encoding="utf-8")
            shards, rejected = load_fetch_shards(root, {"FPT", "VCB"})
        self.assertEqual(shards, {})
        self.assertEqual(set(rejected), {"FPT", "VCB"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
