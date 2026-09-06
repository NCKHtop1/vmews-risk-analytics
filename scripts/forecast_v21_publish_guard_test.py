import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from forecast_v21_publish_guard import SKIP, decide


class ForecastV21PublishGuardTest(unittest.TestCase):
    def dashboard(self, as_of="2026-09-04"):
        return {
            "asOf": as_of,
            "promotion": {
                "directPriceHorizons": [1, 2, 3, 5],
                "preferredRankingHorizon": 3,
            },
        }

    def snapshot(self, quote_date="2026-09-04", core="2026-09-04", generated="2026-09-05T21:35:00+07:00"):
        return {
            "version": "VMEWS-FORECAST-SESSION-21.4",
            "status": "PASS",
            "generatedAt": generated,
            "coreAsOf": core,
            "coreForecastUnchanged": True,
            "rankingHorizon": 3,
            "coverage": {
                "expectedQuoteDate": quote_date,
                "coverageRatio": 0.99,
                "currentCoverageRatio": 0.93,
                "cutoffFreshCoverageRatio": 0.93,
            },
        }

    def test_newer_published_snapshot_wins_instead_of_rebase_conflict(self):
        candidate = self.snapshot(generated="2026-09-05T21:35:00+07:00")
        published = self.snapshot(generated="2026-09-05T21:36:00+07:00")
        result = decide(candidate, published, self.dashboard())
        self.assertEqual(result["decision"], "SKIP")
        self.assertEqual(result["reason"], "published_snapshot_is_same_or_newer")

    def test_newer_quote_session_is_publishable(self):
        candidate = self.snapshot(
            quote_date="2026-09-07",
            core="2026-09-04",
            generated="2026-09-07T09:05:00+07:00",
        )
        published = self.snapshot(
            quote_date="2026-09-04",
            core="2026-09-04",
            generated="2026-09-05T21:36:00+07:00",
        )
        result = decide(candidate, published, self.dashboard())
        self.assertEqual(result["decision"], "PUBLISH")
        self.assertEqual(result["reason"], "candidate_quote_session_is_newer")

    def test_same_quote_session_cannot_regress_core(self):
        dashboard = self.dashboard(as_of="2026-09-04")
        candidate = self.snapshot(core="2026-09-04", generated="2026-09-05T21:40:00+07:00")
        published = self.snapshot(core="2026-09-05", generated="2026-09-05T21:36:00+07:00")
        result = decide(candidate, published, dashboard)
        self.assertEqual(result["decision"], "SKIP")
        self.assertEqual(result["reason"], "published_core_is_newer_for_same_quote_session")

    def test_candidate_built_on_old_dashboard_is_skipped_after_main_advances(self):
        candidate = self.snapshot(core="2026-09-04", generated="2026-09-05T21:40:00+07:00")
        result = decide(candidate, None, self.dashboard(as_of="2026-09-05"))
        self.assertEqual(result["decision"], "SKIP")
        self.assertEqual(result["reason"], "candidate_core_is_not_latest_checked_out_dashboard")

    def test_guard_rejects_failed_coverage_instead_of_hiding_it(self):
        candidate = self.snapshot()
        candidate["coverage"]["currentCoverageRatio"] = 0.89
        with self.assertRaisesRegex(RuntimeError, "below 0.90"):
            decide(candidate, None, self.dashboard())

    def test_cli_exit_code_distinguishes_publish_and_stale_skip(self):
        root = Path(__file__).resolve().parents[1]
        script = root / "scripts" / "forecast_v21_publish_guard.py"
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            candidate_path = temp / "candidate.json"
            published_path = temp / "published.json"
            dashboard_path = temp / "dashboard.json"
            candidate_path.write_text(json.dumps(self.snapshot()), encoding="utf-8")
            published_path.write_text(
                json.dumps(self.snapshot(generated="2026-09-05T21:36:00+07:00")),
                encoding="utf-8",
            )
            dashboard_path.write_text(json.dumps(self.dashboard()), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--candidate",
                    str(candidate_path),
                    "--published",
                    str(published_path),
                    "--dashboard",
                    str(dashboard_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, SKIP, completed.stdout + completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["decision"], "SKIP")

    def test_workflow_uses_bounded_fast_forward_retry_not_json_rebase(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github" / "workflows" / "forecast-v21-session-refresh.yml").read_text(encoding="utf-8")
        self.assertIn("vmews-main-data-publisher", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("forecast_v21_publish_guard.py", workflow)
        self.assertIn("git fetch --no-tags origin main", workflow)
        self.assertIn("git reset --hard origin/main", workflow)
        self.assertIn("MAX_PUBLISH_ATTEMPTS", workflow)
        self.assertIn("non-fast-forward", workflow)
        self.assertIn("publication starvation", workflow)
        self.assertNotIn("git pull --rebase origin main", workflow)


if __name__ == "__main__":
    unittest.main()
