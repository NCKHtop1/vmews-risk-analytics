"""Point-in-time, issuer-identity and corroboration checks for V18 intelligence."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from forecast_v17_live_intelligence import decision_prior
from forecast_v18_market_intelligence import (
    VN30_CONSTITUENTS,
    fireant_article,
    rumor_intelligence,
    vn30_metadata,
)


class DatedVn30MembershipTest(unittest.TestCase):
    def test_august_rebalance_is_exactly_thirty_distinct_constituents(self) -> None:
        roster = vn30_metadata("2026-08-21")
        self.assertEqual(roster["count"], 30)
        self.assertEqual(len(set(roster["symbols"])), 30)
        self.assertEqual(set(roster["symbols"]), set(VN30_CONSTITUENTS))
        self.assertTrue({"MCH", "TCX"}.issubset(roster["symbols"]))
        self.assertFalse({"PLX", "TPB"} & set(roster["symbols"]))

    def test_pre_rebalance_snapshot_keeps_old_membership(self) -> None:
        roster = vn30_metadata("2026-07-31")
        self.assertEqual(roster["count"], 30)
        self.assertTrue({"PLX", "TPB"}.issubset(roster["symbols"]))
        self.assertFalse({"MCH", "TCX"} & set(roster["symbols"]))


class CorroboratedRumorTest(unittest.TestCase):
    decision = "2026-08-23T10:00:00+07:00"
    histories = {
        "GAS": [
            {"date": f"2026-08-{day:02d}", "rawClose": 72_000 + day * 100, "volume": 1_000_000 + day * 20_000}
            for day in range(1, 22)
        ],
        "FPT": [{"date": "2026-08-21", "rawClose": 72_000, "volume": 1_000_000}],
        "FRT": [{"date": "2026-08-21", "rawClose": 160_000, "volume": 500_000}],
    }

    def event(self, title: str, *, publisher: str, published: str, source: str = "MAINSTREAM", symbol: str = "GAS", sentiment: float = .75) -> dict:
        return {
            "symbol": symbol,
            "title": title,
            "publisher": publisher,
            "publishedAt": published,
            "sourceType": source,
            "credibility": .86,
            "sentiment": sentiment,
        }

    def evaluate(self, events: list[dict]) -> tuple[dict, dict]:
        return rumor_intelligence(events, self.histories, "2026-08-21", self.decision)

    def test_single_source_gossip_never_becomes_a_claim(self) -> None:
        output, audit = self.evaluate([
            self.event("GAS dự kiến thoái vốn tại dự án năng lượng", publisher="Một nguồn", published="2026-08-20T09:00:00+07:00"),
        ])
        self.assertEqual(output, {})
        self.assertEqual(audit["qualifiedClaims"], 0)

    def test_independent_sources_are_disclosed_without_claiming_confirmation(self) -> None:
        output, audit = self.evaluate([
            self.event("GAS dự kiến thoái vốn tại dự án năng lượng", publisher="FireAnt", published="2026-08-19T09:00:00+07:00"),
            self.event("Kế hoạch GAS thoái vốn tại dự án năng lượng", publisher="Vietstock", published="2026-08-20T10:00:00+07:00"),
        ])
        claim = output["GAS"]["claims"][0]
        self.assertEqual(claim["sources"], 2)
        self.assertEqual(claim["truthState"], "UNVERIFIED")
        self.assertEqual(claim["verificationState"], "CORROBORATED")
        self.assertEqual(claim["fireantMentions"], 1)
        self.assertFalse(claim["inferenceEligible"])
        self.assertFalse(output["GAS"]["usedByForecast"])
        self.assertEqual(audit["historicalBackfillRows"], 0)

    def test_official_denial_is_reported_and_cannot_move_the_forecast(self) -> None:
        output, _ = self.evaluate([
            self.event("GAS dự kiến thoái vốn tại dự án năng lượng", publisher="FireAnt", published="2026-08-20T09:00:00+07:00"),
            self.event("GAS chính thức bác bỏ kế hoạch thoái vốn tại dự án năng lượng", publisher="Công bố GAS", source="OFFICIAL", published="2026-08-21T10:00:00+07:00"),
        ])
        claim = output["GAS"]["claims"][0]
        self.assertEqual(claim["truthState"], "DENIED")
        self.assertEqual(claim["sentimentScore"], 0)
        self.assertFalse(claim["inferenceEligible"])

    def test_future_or_wrong_issuer_publications_are_rejected(self) -> None:
        output, audit = self.evaluate([
            self.event("GAS dự kiến thoái vốn tại dự án năng lượng", publisher="FireAnt", published="2026-08-23T12:00:00+07:00"),
            self.event("GAS có thể thoái vốn tại dự án năng lượng", publisher="Vietstock", published="2026-08-23T12:10:00+07:00"),
            self.event("FPT Long Châu dự kiến phát hành cổ phiếu tăng vốn", symbol="FPT", publisher="FireAnt", published="2026-08-22T09:00:00+07:00"),
            self.event("FPT Long Châu có thể phát hành cổ phiếu tăng vốn", symbol="FPT", publisher="Vietstock", published="2026-08-22T09:10:00+07:00"),
        ])
        self.assertEqual(output, {})
        self.assertEqual(audit["futurePublicationsUsed"], 0)

    def test_fresh_corroborated_claim_enters_a_bounded_decision_prior(self) -> None:
        output, audit = self.evaluate([
            self.event("GAS dự kiến ký hợp đồng dự án năng lượng tăng trưởng", publisher="FireAnt", published="2026-08-22T09:00:00+07:00"),
            self.event("GAS có thể ký hợp đồng dự án năng lượng tăng trưởng", publisher="Vietstock", published="2026-08-22T10:00:00+07:00"),
        ])
        context = output["GAS"]
        self.assertTrue(context["inferenceEligible"])
        self.assertEqual(audit["decisionPriorSymbols"], 1)
        prior = decision_prior(None, None, None, .025, 5, rumor=context)
        self.assertGreater(prior["components"]["RUMOR"], 0)
        self.assertLessEqual(abs(prior["totalReturn"]), prior["maximumAbsoluteReturn"])
        self.assertFalse(prior["independentlyBacktested"])


class PublicFireAntPublisherTest(unittest.TestCase):
    def item(self, *, host: str, publisher: str, title: str) -> ET.Element:
        return ET.fromstring(
            f"<item><title>{title}</title><link>https://news.google.com/rss/articles/example</link>"
            "<pubDate>Sat, 22 Aug 2026 02:00:00 GMT</pubDate>"
            f'<source url="https://{host}">{publisher}</source></item>'
        )

    def test_real_fireant_publisher_can_be_admitted(self) -> None:
        article = fireant_article("GAS", self.item(host="fireant.vn", publisher="FireAnt", title="GAS dự kiến thoái vốn tại dự án năng lượng"), {"GAS"})
        self.assertIsNotNone(article)
        self.assertEqual(article["publisher"], "FireAnt")
        self.assertEqual(article["sourceClass"], "RUMOR_UNVERIFIED")

    def test_unrelated_publisher_and_wrong_issuer_cannot_be_labeled_fireant(self) -> None:
        self.assertIsNone(fireant_article("GAS", self.item(host="vietstock.vn", publisher="Vietstock", title="GAS dự kiến thoái vốn tại dự án năng lượng"), {"GAS"}))
        self.assertIsNone(fireant_article("FPT", self.item(host="fireant.vn", publisher="FireAnt", title="FPT Long Châu dự kiến phát hành cổ phiếu tăng vốn"), {"FPT", "FRT"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
