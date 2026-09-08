from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_forecast_v9_deployable as subject


class LegacyV9ArchiveTest(unittest.TestCase):
    def test_mismatched_or_missing_eod_never_relabels_the_panel(self) -> None:
        for panel, scan in [("2026-09-04", "2026-09-08"), ("2026-09-08", ""), ("", "2026-09-08")]:
            with self.subTest(panel=panel, scan=scan), self.assertRaises(subject.PITAlignmentAbstention):
                subject.require_same_completed_eod(panel, scan)
        subject.require_same_completed_eod("2026-09-08", "2026-09-08")

    def test_pit_abstention_preserves_archive_and_does_not_score_a_new_forecast(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            live = Path(directory)
            integrity = live / "integrity.json"
            integrity.write_bytes(b'{"status":"PASS","asOf":"2026-08-26"}')
            before = integrity.read_bytes()
            with patch.object(subject, "LIVE", live), patch.object(
                subject, "snapshot", side_effect=subject.PITAlignmentAbstention("2026-09-04", "2026-09-08"),
            ), patch.object(subject, "archive") as archive, patch.object(subject, "evaluate") as evaluate:
                subject.live()
            archive.assert_not_called()
            evaluate.assert_not_called()
            self.assertEqual(integrity.read_bytes(), before)
            attempt = json.loads((live / "last-attempt.json").read_text())
            self.assertEqual(attempt["status"], "WAITING_OR_REVIEW")
            self.assertEqual(attempt["reasonCode"], "PIT_SESSION_MISMATCH")
            self.assertEqual(attempt["panelAsOf"], "2026-09-04")
            self.assertEqual(attempt["scanAsOf"], "2026-09-08")
            self.assertFalse(attempt["automaticPromotion"])

    def test_model_failures_still_stop_the_workflow(self) -> None:
        with patch.object(subject, "snapshot", side_effect=RuntimeError("V9 model gate not PASS")):
            with self.assertRaisesRegex(RuntimeError, "model gate not PASS"):
                subject.live()

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
