#!/usr/bin/env python3
"""Regression tests for independently abstained release-audit horizons."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import forecast_v20_release_audit as audit
from vn_exchange_calendar import latest_completed_session, trading_session_age


class ReleaseAuditAbstentionTest(unittest.TestCase):
    def test_negative_magnitude_review_is_withheld_without_adding_a_blocker(self) -> None:
        original_data = audit.DATA
        audit._business_age = lambda observed, as_of: trading_session_age(observed, as_of)
        audit.completed_session = latest_completed_session
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw) / "data"
            shutil.copytree(original_data, data)
            market_path = data / "forecast-market-v13.json"
            dashboard_path = data / "forecast-dashboard-v12.json"
            current_path = data / "forecast-current-v12.json"
            market = json.loads(market_path.read_text(encoding="utf-8"))
            dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
            current = json.loads(current_path.read_text(encoding="utf-8"))

            horizon = market["model"]["horizons"]["4"]
            horizon["sealedAudit"]["magnitudeMAESkill"] = -0.0012392646565968501
            horizon["priceStatus"] = "REVIEW"
            promotion = market["model"]["promotion"]
            promotion["directPriceHorizons"] = [value for value in promotion["directPriceHorizons"] if value != 4]
            promotion["reviewHorizons"] = sorted(set(promotion.get("reviewHorizons") or []) | {4})

            for snapshot in dashboard["symbols"].values():
                forecast = snapshot["horizons"]["4"]
                forecast["magnitudeValidated"] = True
                forecast["priceValidated"] = False
                forecast["validationStatus"] = "REVIEW"
            current["symbols"] = dashboard["symbols"]

            market_path.write_text(json.dumps(market, ensure_ascii=False), encoding="utf-8")
            dashboard_path.write_text(json.dumps(dashboard, ensure_ascii=False), encoding="utf-8")
            current_path.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
            audit.DATA = data
            mismatched = audit.run_audit()
            self.assertEqual(mismatched["status"], "FAIL")
            self.assertTrue(any("magnitude gate mismatch" in blocker for blocker in mismatched["blockers"]))

            for snapshot in dashboard["symbols"].values():
                snapshot["horizons"]["4"]["magnitudeValidated"] = False
            current["symbols"] = dashboard["symbols"]
            dashboard_path.write_text(json.dumps(dashboard, ensure_ascii=False), encoding="utf-8")
            current_path.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
            released = audit.run_audit()
            self.assertFalse(any("magnitude gate mismatch" in blocker for blocker in released["blockers"]))
            self.assertFalse(any("T+4 has no magnitude skill" in blocker for blocker in released["blockers"]))
            self.assertLess(released["horizons"]["4"]["magnitudeMAESkill"], 0)
        audit.DATA = original_data


if __name__ == "__main__":
    unittest.main(verbosity=2)
