from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_forecast_v9_deployable as subject


class LegacyV9ArchiveTest(unittest.TestCase):
    def test_insufficient_cross_section_abstains(self) -> None:
        with self.assertRaises(subject.CoverageAbstention):
            subject.require_cross_sectional_coverage(2)

    def test_abstention_records_attempt_without_overwriting_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            live = Path(directory) / "forecast-live"
            live.mkdir(parents=True)
            integrity = live / "integrity.json"
            integrity.write_text('{"status":"PASS","asOf":"2026-08-26"}', encoding="utf-8")
            with patch.object(subject, "LIVE", live), patch.object(
                subject,
                "snapshot",
                side_effect=subject.CoverageAbstention("coverage 2/8"),
            ):
                subject.live()
            self.assertEqual(json.loads(integrity.read_text(encoding="utf-8"))["asOf"], "2026-08-26")
            attempt = json.loads((live / "last-attempt.json").read_text(encoding="utf-8"))
            self.assertEqual(attempt["status"], "WAITING_OR_REVIEW")
            self.assertTrue(attempt["preservesLastValidatedSnapshot"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
