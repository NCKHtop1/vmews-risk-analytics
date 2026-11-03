#!/usr/bin/env python3
"""A data-only change cannot turn retrospective associations into alerts."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / 'scripts/news_impact_publication_gate.py').exists():
    raise unittest.SkipTest('Full-data publication gate omitted by sparse checkout')
sys.path.insert(0, str(ROOT / 'scripts'))
import news_impact_publication_gate as m

class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "financial-report/data/news-impact-reviewed.json").read_text())
        self.report = {
            "inputRecords": 12785, "filteredIndependentEvents": 1625,
            "directTickerGroups": 0, "pooledEventGroups": 2,
            "policy": {"notificationsEnabled": False},
            "groups": [{"group": ["EVENT", "REGULATORY", "NEG"], "researchEvidence": "UNCONFIRMED", "preNewsTrendFlagged": False, "liveNotificationEligible": False}],
            "splitCounts": {"train": 601, "validation": 306, "holdout": 709},
            "oosAssociationGroups": 1, "pretrendFlaggedOOSGroups": 1,
            "oosGroupsWithoutLargePretrend": 0,
        }
        self.sector = {"sectorAudit": {"pointInTimeEligible": False}}

    def check(self, release=None, research=None, sector=None, receipts=0):
        return m.verify_publication_manifest(
            self.manifest if release is None else release,
            self.report if research is None else research,
            self.sector if sector is None else sector, receipts
        )

    def test_realistic_manifest_remains_unapproved(self):
        result = self.check()
        self.assertEqual(result["notificationsEligible"], 0)
        self.assertEqual(result["verifiedRelations"], 0)

    def test_forged_issuer_impact_rejected(self):
        item = copy.deepcopy(self.manifest)
        item["verifiedImpacts"] = [{"symbol": "FPT", "claimedImpact": "POSITIVE"}]
        with self.assertRaisesRegex(ValueError, "promoted"):
            self.check(release=item)

    def test_manual_notification_flag_rejected(self):
        item = copy.deepcopy(self.manifest)
        item["notificationsEnabled"] = True
        with self.assertRaisesRegex(ValueError, "notification"):
            self.check(release=item)

    def test_manual_promotion_rejected(self):
        item = copy.deepcopy(self.manifest)
        item["status"] = "PRODUCTION_APPROVED"
        with self.assertRaisesRegex(ValueError, "promoted"):
            self.check(release=item)

    def test_current_sector_data_cannot_pass_for_historical(self):
        with self.assertRaisesRegex(ValueError, "sector"):
            self.check(sector={"sectorAudit": {"pointInTimeEligible": True}})

    def test_first_seen_archive_change_rejected(self):
        with self.assertRaisesRegex(ValueError, "receipt"):
            self.check(receipts=12)

    def test_source_study_change_rejected(self):
        item = copy.deepcopy(self.report)
        item["filteredIndependentEvents"] += 1
        with self.assertRaisesRegex(ValueError, "Stale"):
            self.check(research=item)

    def test_shadow_cannot_become_alert(self):
        item = copy.deepcopy(self.report)
        item["groups"][0]["liveNotificationEligible"] = True
        with self.assertRaisesRegex(ValueError, "promoted"):
            self.check(research=item)

if __name__ == "__main__":
    unittest.main()
