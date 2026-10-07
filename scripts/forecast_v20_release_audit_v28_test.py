from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name("forecast_v20_release_audit_v28.py")
SPEC = importlib.util.spec_from_file_location("forecast_v20_release_audit_v28_under_test", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class TargetedFlowRefreshContractTests(unittest.TestCase):
    def setUp(self):
        self.original_data = MOD.legacy.DATA
        self.tmp = tempfile.TemporaryDirectory()
        MOD.legacy.DATA = pathlib.Path(self.tmp.name)

    def tearDown(self):
        MOD.legacy.DATA = self.original_data
        self.tmp.cleanup()

    def write_audit(self, **summary):
        base = {
            "refreshRequestedSymbols": 30,
            "refreshRequestedKinds": 60,
            "refreshSuccessCoverage": 1.0,
            "rejectedFetchShards": 0,
            "refreshTargetSession": "2026-10-06",
        }
        base.update(summary)
        (MOD.legacy.DATA / "flow-audit-v12.json").write_text(
            json.dumps({"summary": base}), encoding="utf-8"
        )

    def test_targeted_refresh_is_safe_only_when_other_flow_contracts_are_clean(self):
        self.write_audit()
        report = {"blockers": sorted(MOD._PARTIAL_REFRESH_BLOCKERS)}
        ok, detail = MOD._partial_flow_refresh_is_safe(
            report, {"asOf": "2026-10-06"}
        )
        self.assertTrue(ok)
        self.assertEqual(detail["requestedSymbols"], 30)

    def test_targeted_refresh_cannot_hide_stale_flow_prior_violation(self):
        self.write_audit()
        report = {
            "blockers": sorted(MOD._PARTIAL_REFRESH_BLOCKERS)
            + ["stale flow still drives live prior: ['FPT/T+3']"]
        }
        ok, _ = MOD._partial_flow_refresh_is_safe(
            report, {"asOf": "2026-10-06"}
        )
        self.assertFalse(ok)

    def test_targeted_refresh_requires_complete_requested_batch_and_same_session(self):
        for overrides in (
            {"refreshSuccessCoverage": 0.99},
            {"rejectedFetchShards": 1},
            {"refreshRequestedKinds": 59},
            {"refreshTargetSession": "2026-10-03"},
        ):
            self.write_audit(**overrides)
            ok, _ = MOD._partial_flow_refresh_is_safe(
                {"blockers": sorted(MOD._PARTIAL_REFRESH_BLOCKERS)},
                {"asOf": "2026-10-06"},
            )
            self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
