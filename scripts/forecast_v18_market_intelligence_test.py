"""Point-in-time, issuer-identity and corroboration checks for V18 intelligence."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

from forecast_v17_live_intelligence import decision_prior
from forecast_v18_market_intelligence import (
    VN30_CONSTITUENTS,
    _adjusted_horizons,
    community_watchlist,
    fireant_article,
    money24h_article,
    parse_24hmoney_social,
    publisher_archive_eligible,
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

    def test_fireant_and_24hmoney_are_independent_without_declaring_the_claim_true(self) -> None:
        output, _ = self.evaluate([
            self.event("GAS dự kiến ký hợp đồng dự án năng lượng tăng trưởng", publisher="FireAnt", published="2026-08-22T09:00:00+07:00"),
            self.event("GAS có thể ký hợp đồng dự án năng lượng tăng trưởng", publisher="24HMoney", published="2026-08-22T10:00:00+07:00"),
        ])
        claim = output["GAS"]["claims"][0]
        self.assertEqual(claim["sources"], 2)
        self.assertEqual(claim["fireantMentions"], 1)
        self.assertEqual(claim["money24hMentions"], 1)
        self.assertEqual(claim["truthState"], "UNVERIFIED")

    def test_single_source_is_visible_but_never_enters_model(self) -> None:
        events = [self.event("GAS dự kiến thoái vốn tại dự án năng lượng", publisher="24HMoney", published="2026-08-22T09:00:00+07:00")]
        watchlist = community_watchlist(events, self.histories, self.decision)
        self.assertEqual(watchlist["GAS"][0]["verificationState"], "PENDING")
        self.assertFalse(watchlist["GAS"][0]["inferenceEligible"])
        self.assertFalse(watchlist["GAS"][0]["usedByForecast"])
        self.assertEqual(self.evaluate(events)[0], {})

    def test_live_adjustment_keeps_hose_grid_and_audited_price_range(self) -> None:
        output, _ = self.evaluate([
            self.event("GAS dự kiến ký hợp đồng dự án năng lượng tăng trưởng", publisher="FireAnt", published="2026-08-22T09:00:00+07:00"),
            self.event("GAS có thể ký hợp đồng dự án năng lượng tăng trưởng", publisher="24HMoney", published="2026-08-22T10:00:00+07:00"),
        ])
        snapshot = {
            "close": 72_000, "dailyVolatility": .025, "flow": {},
            "horizons": {"5": {"priceValidated": True, "expectedPrice": 73_000, "expectedReturn": 73_000 / 72_000 - 1,
                                 "q20Price": 69_000, "q80Price": 76_000, "liveEvidence": {"totalReturn": 0, "components": {}},
                                 "expertContributions": {"RUMOR": 0}}},
        }
        adjustments = _adjusted_horizons(snapshot, output["GAS"], datetime(2026, 8, 23, 10, tzinfo=timezone(timedelta(hours=7))))
        horizon = adjustments["5"]
        self.assertEqual(horizon["expectedPrice"] % 100, 0)
        self.assertLessEqual(horizon["q20Price"], horizon["expectedPrice"])
        self.assertGreaterEqual(horizon["q80Price"], horizon["expectedPrice"])
        self.assertLessEqual(abs(horizon["liveEvidence"]["totalReturn"]), horizon["liveEvidence"]["maximumAbsoluteReturn"])
        self.assertTrue(horizon["liveAdjustment"]["bounded"])


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

    def test_real_24hmoney_publisher_must_have_matching_domain_and_name(self) -> None:
        accepted = money24h_article("FPT", self.item(host="24hmoney.vn", publisher="24HMoney", title="FPT dự kiến ký hợp đồng chuyển đổi số"), {"FPT"})
        self.assertEqual(accepted["publisher"], "24HMoney")
        self.assertIsNone(money24h_article("FPT", self.item(host="spoof.example", publisher="24HMoney", title="FPT dự kiến ký hợp đồng chuyển đổi số"), {"FPT"}))


class Public24HMoneyCommunityTest(unittest.TestCase):
    observed = datetime(2026, 8, 23, 10, 30, tzinfo=timezone(timedelta(hours=7)))

    @staticmethod
    def card(body: str, age: str = "8 phút", widget: str = "") -> str:
        return (
            '<article class="article-item-social">'
            '<a class="app-link user-name">Nhà đầu tư</a>'
            f'<span class="post-time">{age}</span>'
            f'<a href="/posts/-c55a2823967.html?from_source=social" class="app-link description_"><p>{body}</p></a>'
            f'<div class="quote-widget">{widget}</div></article>'
        )

    def test_only_original_post_text_can_attach_an_issuer(self) -> None:
        result = parse_24hmoney_social(self.card("FPT dự kiến ký hợp đồng chuyển đổi số mới", widget="BSR tăng mạnh"), {"FPT", "BSR"}, self.observed)
        self.assertEqual(set(result["symbols"]), {"FPT"})
        self.assertEqual(result["symbols"]["FPT"][0]["publisher"], "24HMoney")
        self.assertEqual(result["symbols"]["FPT"][0]["published"], "2026-08-23T10:22:00+07:00")
        self.assertEqual(result["symbols"]["FPT"][0]["sourceClass"], "RUMOR_UNVERIFIED")
        self.assertFalse(publisher_archive_eligible(result["symbols"]["FPT"][0]))

    def test_verified_publisher_article_remains_eligible_for_the_news_archive(self) -> None:
        self.assertTrue(publisher_archive_eligible({"collectionMethod": "PUBLIC_PUBLISHER_ATTRIBUTED_GOOGLE_NEWS_RSS"}))

    def test_market_context_is_not_incorrectly_attached_to_quote_widget(self) -> None:
        result = parse_24hmoney_social(self.card("Quốc hội thông qua luật dầu khí sửa đổi", widget="BSR"), {"BSR", "FPT"}, self.observed)
        self.assertEqual(result["symbols"], {})
        self.assertEqual(result["marketContext"][0]["theme"], "DẦU KHÍ")
        self.assertEqual(result["marketContext"][0]["verificationState"], "UNVERIFIED")

    def test_missing_publication_time_is_rejected(self) -> None:
        result = parse_24hmoney_social(self.card("FPT dự kiến ký hợp đồng mới", age="không rõ"), {"FPT"}, self.observed)
        self.assertEqual(result["symbols"], {})
        self.assertEqual(result["acceptedPosts"], 0)


class IntradayCommunityPublicationTest(unittest.TestCase):
    def test_workflow_runs_frequently_and_cannot_race_the_full_model_publish(self) -> None:
        workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "forecast-v19-community-live.yml").read_text(encoding="utf-8")
        self.assertIn('"*/15 2-8 * * 1-5"', workflow)
        self.assertIn('"0,30 1-15 * * 0,6"', workflow)
        self.assertIn("group: forecast-v14-daily-refresh", workflow)
        self.assertIn("--collect-community", workflow)
        self.assertIn("--publish-live", workflow)
        self.assertIn("community-intelligence-live-v19.json", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
