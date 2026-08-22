"""Regression tests for secure point-in-time external features."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from forecast_v16_external_data import (  # noqa: E402
    FUND_FEATURE_COLUMNS,
    _normalise_weight,
    fund_feature_panel,
    latest_fund_context,
)


class FundPointInTimeTest(unittest.TestCase):
    def _history(self, path: Path, count: int = 4) -> None:
        snapshots = []
        for index, day in enumerate(("2026-07-01", "2026-07-15", "2026-08-01", "2026-08-15")[:count]):
            snapshots.append(
                {
                    "weightUnit": "FRACTION_OF_NAV",
                    "asOf": day,
                    "holdings": [
                        {
                            "fundId": 1,
                            "fundCode": "TEST",
                            "symbol": "FPT",
                            "weight": 0.08 + 0.01 * index,
                            "reportDate": "2026-06-30",
                            "availableDate": day,
                            "navMomentum20": 0.02,
                            "navVolatility20": 0.01,
                        }
                    ],
                }
            )
        path.write_text(json.dumps({"snapshots": snapshots}), encoding="utf-8")

    def test_new_snapshot_is_never_backfilled_into_earlier_rows(self) -> None:
        panel = pd.DataFrame(
            {
                "symbol": ["FPT", "FPT", "FPT"],
                "date": pd.to_datetime(["2026-06-30", "2026-07-02", "2026-08-16"]),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            self._history(path)
            features, audit = fund_feature_panel(panel, path=path)
        self.assertEqual(list(features.columns), FUND_FEATURE_COLUMNS)
        self.assertEqual(features.loc[0, "fund_available"], 0)
        self.assertEqual(features.loc[0, "fund_weight_sum"], 0)
        self.assertEqual(features.loc[1, "fund_weight_sum"], 0.08)
        self.assertAlmostEqual(features.loc[2, "fund_weight_sum"], 0.11)
        self.assertAlmostEqual(features.loc[2, "fund_weight_change"], 0.01)
        self.assertEqual(audit["status"], "PASS")
        self.assertTrue(audit["modelEligible"])

    def test_one_current_snapshot_is_context_only(self) -> None:
        panel = pd.DataFrame({"symbol": ["FPT"], "date": pd.to_datetime(["2026-08-22"])})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            self._history(path, count=1)
            features, audit = fund_feature_panel(panel, path=path)
        self.assertEqual(features.loc[0, "fund_available"], 1)
        self.assertEqual(audit["status"], "CONTEXT_ONLY")
        self.assertFalse(audit["modelEligible"])

    def test_missing_history_has_explicit_unavailable_state(self) -> None:
        panel = pd.DataFrame({"symbol": ["FPT"], "date": pd.to_datetime(["2026-08-22"])})
        with tempfile.TemporaryDirectory() as directory:
            features, audit = fund_feature_panel(panel, path=Path(directory) / "missing.json")
        self.assertEqual(float(features.to_numpy().sum()), 0.0)
        self.assertEqual(audit["status"], "UNAVAILABLE")

    def test_latest_disclosure_is_context_not_a_historical_backfill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            self._history(path, count=1)
            contexts, audit = latest_fund_context(path)
        self.assertEqual(audit["snapshotCount"], 1)
        self.assertEqual(contexts["FPT"]["asOf"], "2026-07-01")
        self.assertEqual(contexts["FPT"]["fundCount"], 1)
        self.assertFalse(contexts["FPT"]["modelEligible"])

    def test_integrated_adapter_contains_no_embedded_secret(self) -> None:
        source = (ROOT / "scripts/forecast_v16_external_data.py").read_text(encoding="utf-8")
        lowered = source.casefold()
        self.assertNotIn("abcd@", lowered)
        self.assertNotIn("tikojog", lowered)
        self.assertNotIn("eyjhb", lowered)
        self.assertIn("FMARKET_BEARER_TOKEN", source)

    def test_fmarket_percent_points_are_converted_to_fraction(self) -> None:
        self.assertAlmostEqual(_normalise_weight(0.66, percentage_points=True), 0.0066)
        self.assertAlmostEqual(_normalise_weight(3.95, percentage_points=True), 0.0395)


if __name__ == "__main__":
    unittest.main(verbosity=2)
