"""Deterministic fail-closed tests for research-only news-impact evidence."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import news_impact_shadow_research as m
from datetime import date, datetime, timedelta, timezone
import copy
import unittest


def make_record(i=0, ticker="FPT", event="EARNINGS", sent="POS", effect=.011):
    dt = date(2020, 1, 1) + timedelta(days=i * 8)
    pub = datetime(dt.year, dt.month, dt.day, 10, tzinfo=timezone(timedelta(hours=7)))
    return {
        "eventKey": f"{ticker}::item-{ticker}-{i}", "ticker": ticker, "newsId": f"item-{ticker}-{i}",
        "publishedAt": pub.isoformat(), "availableDate": dt.isoformat(),
        "matureDate": {"1": (dt+timedelta(days=1)).isoformat(),
                       "2": (dt+timedelta(days=2)).isoformat(),
                       "5": (dt+timedelta(days=5)).isoformat()},
        "eventType": event, "sentimentLabel": sent,
        "sourceType": "OFFICIAL", "sourceCredibility": .99,
        "materialityScore": .91, "benchmark": "VNINDEX",
        "benchmarkAvailable": {"1": True, "2": True, "5": True},
        "cumulativeAbnormalReturn": {"1": effect / 2, "2": effect, "5": effect * 1.3},
        "preAbnormalReturn": {"2": 0.0},
    }


SECTOR = {"status": "PASS", "sectorAudit": {"pointInTimeEligible": False}}
def package(rows):
    return {"eventIdentity": "TICKER_NEWS_ID", "benchmarkPolicy": {"benchmark": "VNINDEX"},
            "version": "SYNTHETIC", "records": rows}


class ShadowResearchTests(unittest.TestCase):
    def test_duplicates_do_not_count_as_independent_articles(self):
        first = make_record()
        second = copy.deepcopy(first)
        second["newsId"] = "other-id"
        second["eventKey"] = "FPT::other-id"
        selected, errors = m.clean_records([first, second])
        self.assertEqual(len(selected), 1)
        self.assertEqual(errors["duplicate_story_same_day"], 1)

    def test_overlapping_events_for_same_issuer_are_purged(self):
        one = make_record()
        two = make_record(1)
        two["availableDate"] = (date(2020, 1, 1) + timedelta(days=2)).isoformat()
        two["publishedAt"] = "2020-01-03T10:00:00+07:00"
        two["matureDate"]["2"] = "2020-01-05"
        three = make_record(2)
        rows, errors = m.clean_records([one, two, three])
        self.assertEqual(len(rows), 2)
        self.assertEqual(errors["overlapping_issuer_event_window"], 1)

    def test_missing_exact_benchmark_abstains_not_raw_return(self):
        event = make_record()
        event["benchmarkAvailable"]["2"] = False
        selected, errors = m.clean_records([event])
        self.assertFalse(selected)
        self.assertEqual(errors["missing_exact_index"], 1)

    def test_unverified_rumors_do_not_generate_directional_evidence(self):
        event = make_record()
        event["sourceType"] = "RUMOR"
        rows, errors = m.clean_records([event])
        self.assertEqual(rows, [])
        self.assertEqual(errors["rumor_or_clarification"], 1)

    def test_future_publication_is_rejected(self):
        event = make_record()
        event["publishedAt"] = "2020-01-06T11:00:00+07:00"
        rows, errors = m.clean_records([event])
        self.assertFalse(rows)
        self.assertEqual(errors["publication_alignment"], 1)

    def test_date_maturity_embargo(self):
        rows, _ = m.clean_records([make_record(i) for i in range(100)])
        a, b = m.split_date_boundaries(rows)
        sets = m.split_by_maturity(rows, a, b)
        self.assertTrue(all(r["matureDate2"] < a for r in sets["train"]))
        self.assertTrue(all(r["matureDate2"] < b for r in sets["validation"]))
        self.assertTrue(all(r["date"] >= b for r in sets["holdout"]))

    def test_current_sector_map_must_abstain(self):
        with self.assertRaisesRegex(ValueError, "sector-PIT"):
            m.run(package([make_record(i) for i in range(100)]),
                  {"status": "PASS", "sectorAudit": {"pointInTimeEligible": True}})

    def test_research_will_never_enable_live_notifications(self):
        rows = [make_record(i) for i in range(110)]
        report = m.run(package(rows), SECTOR)
        self.assertEqual(report["version"], m.VERSION)
        self.assertFalse(report["policy"]["notificationsEnabled"])
        self.assertFalse(report["policy"]["tickersAutomaticImpactEnabled"])
        self.assertFalse(report["policy"]["sectorsAutomaticImpactEnabled"])
        self.assertFalse(report["policy"]["firstSeenAtArchiveCertified"])
        self.assertGreaterEqual(report["auditedHypotheses"], 1)
        self.assertTrue(all(g["liveNotificationEligible"] is False for g in report["groups"]))

    def test_no_sector_history_cannot_produce_sector_hypotheses(self):
        report = m.run(package([make_record(i) for i in range(110)]), SECTOR)
        self.assertTrue(all(group["group"][0] in ("EVENT", "TICKER")
                            for group in report["groups"]))

    def test_statistical_association_with_pretrend_is_explicitly_flagged(self):
        rows = [make_record(i) for i in range(110)]
        for r in rows:
            r["preAbnormalReturn"]["2"] = .020
        report = m.run(package(rows), SECTOR)
        self.assertGreaterEqual(report["oosAssociationGroups"], 1)
        self.assertEqual(report["pretrendFlaggedOOSGroups"],
                         report["oosAssociationGroups"])
        self.assertEqual(report["oosGroupsWithoutLargePretrend"], 0)
        self.assertTrue(all(g["liveNotificationEligible"] is False
                            for g in report["groups"]))

    def test_cluster_p_and_fdr_deterministic(self):
        values = [0.011, 0.010, .009, .012] * 7
        one = m.cluster_test(values, 23, 399)
        two = m.cluster_test(values, 23, 399)
        self.assertEqual(one, two)
        self.assertGreater(one["ci95"][0], 0)
        rows = [{"holdout": {"p": .01}}, {"holdout": {"p": .03}},
                {"holdout": {"p": .50}}]
        m.bh_qvalues(rows)
        self.assertLessEqual(rows[0]["holdout"]["qBH"], .03)
        self.assertLessEqual(rows[1]["holdout"]["qBH"], .05)


if __name__ == "__main__":
    unittest.main()
