"""Hybrid News Impact engine V2: data leakage and source-fact false-positive guard."""
import json
import sys
import tempfile
from pathlib import Path
import unittest
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import hybrid_news_impact as h

NOW=datetime(2026,11,3,9,0,tzinfo=timezone.utc)
COMPANIES=[{"symbol":"FPT"},{"symbol":"MBB"},{"symbol":"HPG"}]

def example_fact(**updates):
    row={
        "issuerSymbol":"FPT","eventFamily":"FX_MOVEMENT",
        "mechanism":"FX_REVENUE","sourceType":"ISSUER_FILING",
        "sourceUrl":"https://company.example.vn/2025-report",
        "sourcePublishedAt":"2026-03-30T06:00:00Z",
        "periodEnd":"2025-12-31T16:59:00Z",
        "validFrom":"2026-03-30T06:00:00Z",
        "validUntil":"2027-03-30T06:00:00Z",
        "shareOfBusiness":.35,"measurementBasis":"REVENUE_SHARE",
        "entityRole":"CONSOLIDATED_GROUP","reviewStatus":"REVIEWED_SOURCE_FACT",
    }
    row.update(updates)
    return row

class HybridEngineTests(unittest.TestCase):
    def test_pit_fact_requires_source_and_asof(self):
        x=h.source_fact_asof(example_fact(),NOW,{"FPT"})
        self.assertEqual(x["issuerSymbol"],"FPT")
        self.assertIsNone(h.source_fact_asof(example_fact(sourcePublishedAt="2026-12-01T00:00:00Z"),NOW,{"FPT"}))
        self.assertIsNone(h.source_fact_asof(example_fact(sourceUrl="javascript:alert(1)"),NOW,{"FPT"}))
        self.assertIsNone(h.source_fact_asof(example_fact(shareOfBusiness=1.7),NOW,{"FPT"}))
        self.assertIsNone(h.source_fact_asof(example_fact(shareOfBusiness=True),NOW,{"FPT"}))
        self.assertIsNone(h.source_fact_asof(example_fact(reviewStatus="UNVERIFIED"),NOW,{"FPT"}))
        self.assertIsNone(h.source_fact_asof(example_fact(issuerSymbol="FRT"),NOW,{"FPT"}))
        self.assertIsNone(h.source_fact_asof(example_fact(mechanism="UNRELATED"),NOW,{"FPT"}))
        self.assertIsNone(h.source_fact_asof(example_fact(validUntil="2026-03-30T00:00:00Z"),NOW,{"FPT"}))

    def test_sentiment_and_source_priority_are_not_impact(self):
        news=[
          {"title":"Tỷ giá USD/VND tăng mạnh", "url":"https://news.example/a",
           "entityMentions":[{"symbol":"FPT","confidence":.98}],
           "newsPriority":100, "sentimentLabel":"POS",
           "collectorFirstSeenBasis":"COLLECTOR_RECEIPT",
           "collectorFirstSeenAt":"2026-11-03T08:00:00Z"},
          {"title":"Tỷ giá USD/VND tăng mạnh", "url":"https://news.example/a?utm_source=x",
           "newsPriority":100,"sentimentLabel":"POS"},
        ]
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);(d/"reports").mkdir()
            (d/"facts.json").write_text(json.dumps({"schema":h.EXPOSURE_SCHEMA,"facts":[]}))
            out=h.analyze_snapshot(news,COMPANIES,d/"reports",d/"facts.json",NOW.isoformat())
        self.assertEqual(out["status"],"SHADOW_ONLY")
        self.assertEqual(out["counts"]["deduplicatedStories"],1)
        self.assertEqual(out["counts"]["eligibleNotifications"],0)
        self.assertEqual(out["counts"]["verifiedImpactRelations"],0)
        self.assertEqual(out["counts"]["reviewedSourceFacts"],0)
        self.assertFalse(out["researchCandidates"][0]["notificationEligible"])
        self.assertEqual(out["researchCandidates"][0]["validatedAffectedTickers"],[])

    def test_real_source_fact_is_not_impact_certification(self):
        news=[{"storyId":"story_test","title":"Tỷ giá USD/VND tăng mạnh",
               "entityMentions":[{"symbol":"FPT","confidence":.98}],
               "collectorFirstSeenBasis":"COLLECTOR_RECEIPT",
               "collectorFirstSeenAt":"2026-11-03T08:20:00Z"}]
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);(d/"reports").mkdir()
            (d/"facts.json").write_text(json.dumps({"schema":h.EXPOSURE_SCHEMA,"facts":[example_fact()]}))
            out=h.analyze_snapshot(news,COMPANIES,d/"reports",d/"facts.json",NOW.isoformat())
        self.assertEqual(out["counts"]["storiesWithEligibleBusinessFacts"],1)
        self.assertEqual(out["counts"]["verifiedImpactRelations"],0)
        self.assertEqual(out["counts"]["eligibleNotifications"],0)

    def test_disclosure_not_public_when_news_first_seen_is_rejected(self):
        event=[{"title":"Tỷ giá USD/VND tăng mạnh", "storyId":"early_news",
                "entityMentions":[{"symbol":"FPT","confidence":.99}],
                "collectorFirstSeenBasis":"COLLECTOR_RECEIPT",
                "collectorFirstSeenAt":"2026-11-03T07:00:00Z"}]
        later=example_fact(sourcePublishedAt="2026-11-03T08:00:00Z",
                           validFrom="2026-11-03T08:00:00Z")
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);(d/"reports").mkdir()
            (d/"facts.json").write_text(json.dumps({"schema":h.EXPOSURE_SCHEMA,"facts":[later]}))
            out=h.analyze_snapshot(event,COMPANIES,d/"reports",d/"facts.json",NOW.isoformat())
        self.assertEqual(out["counts"]["reviewedSourceFacts"],1)
        self.assertEqual(out["counts"]["storiesWithEligibleBusinessFacts"],0)
        self.assertEqual(out["counts"]["eligibleNotifications"],0)

    def test_jurisdictionless_tariff_never_assigns_issuer(self):
        raw=[{"storyId":"tariff_test","title":"Thuế quan nhập khẩu tăng mạnh",
              "entityMentions":[{"symbol":"FPT","confidence":.99}]}]
        t=example_fact(eventFamily="TARIFF_TRADE",mechanism="MARKET_ACCESS",jurisdiction="US")
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);(d/"reports").mkdir()
            (d/"facts.json").write_text(json.dumps({"schema":h.EXPOSURE_SCHEMA,"facts":[t]}))
            out=h.analyze_snapshot(raw,COMPANIES,d/"reports",d/"facts.json",NOW.isoformat())
        self.assertEqual(out["counts"]["storiesWithEligibleBusinessFacts"],0)

    def test_invalid_registry_quarantined_and_no_alert(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);(d/"reports").mkdir()
            (d/"facts.json").write_text(json.dumps({"schema":h.EXPOSURE_SCHEMA,"facts":[example_fact(),example_fact(sourceUrl="bad")]}))
            news=[{"title":"Tỷ giá USD/VND tăng mạnh","entityMentions":[{"symbol":"FPT","confidence":.99}]}]
            out=h.analyze_snapshot(news,COMPANIES,d/"reports",d/"facts.json",NOW.isoformat())
        self.assertEqual(out["counts"]["invalidSourceFacts"],1)
        self.assertEqual(out["counts"]["storiesWithEligibleBusinessFacts"],0)
        self.assertEqual(out["counts"]["eligibleNotifications"],0)

    def test_real_financial_report_is_coverage_not_exposure_certification(self):
        coverage=h.audit_financial_coverage(ROOT/"data",{"MBB","HPG","FPT"})
        self.assertGreaterEqual(coverage["financialStatementCoverageCount"],2)
        self.assertFalse(coverage["sourceReportPublicationTimesCertified"])
        self.assertEqual(coverage["segmentRevenueCoverageCertified"],0)

    def test_unknown_timestamp_and_fake_direct_ticker(self):
        news=[{"title":"Lãi suất tăng mạnh","entityMentions":[{"symbol":"MBB","confidence":.80}],
               "collectorFirstSeenAt":"2026-11-03T07:00:00Z",
               "collectorFirstSeenBasis":"LEGACY_UNCERTIFIED"}]
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);(d/"reports").mkdir()
            (d/"facts.json").write_text(json.dumps({"schema":h.EXPOSURE_SCHEMA,"facts":[]}))
            out=h.analyze_snapshot(news,COMPANIES,d/"reports",d/"facts.json",NOW.isoformat())
        self.assertEqual(out["counts"]["storiesWithoutCertifiedCollectorTime"],1)
        self.assertEqual(out["counts"]["directIssuerMentionStories"],0)
        self.assertEqual(out["counts"]["eligibleNotifications"],0)

if __name__=="__main__":
    unittest.main()
