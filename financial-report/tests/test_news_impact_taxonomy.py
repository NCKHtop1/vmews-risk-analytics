"""Unit tests for non-predictive mechanism labels and trustworthy receipt times."""
import importlib.util
import pathlib
import unittest
from datetime import datetime, timezone, timedelta

P = pathlib.Path(__file__).resolve().parents[1] / "scripts/news_impact_taxonomy.py"
S = importlib.util.spec_from_file_location("news_impact_taxonomy", P)
m = importlib.util.module_from_spec(S)
S.loader.exec_module(m)

class ImpactTaxonomyTests(unittest.TestCase):
    def test_macro_mechanisms_not_ticker_predictions(self):
        for title, expected in [
            ("NHNN điều chỉnh tăng lãi suất điều hành", "RATE_POLICY"),
            ("Giá dầu Brent tăng mạnh", "OIL_PRICE_MOVE"),
            ("Tỷ giá USD/VND tăng mạnh", "FX_MOVEMENT"),
            ("Mỹ tăng thuế nhập khẩu hàng hóa", "TARIFF_TRADE"),
        ]:
            result = m.exposure_hypothesis({"title": title})
            self.assertEqual(result["eventFamily"], expected)
            self.assertTrue(result["candidateSectorMechanisms"])
            self.assertEqual(result["verifiedAffectedTickers"], [])
            self.assertEqual(result["verifiedAffectedSectors"], [])
            self.assertFalse(result["notificationEligible"])
            self.assertEqual(result["evidenceTier"], "E0_UNTESTED")
            self.assertTrue(all(x["direction"] == "CONDITIONAL_NOT_ESTABLISHED" for x in result["candidateSectorMechanisms"]))

    def test_money_amount_not_fx_event(self):
        data = m.exposure_hypothesis({"title": "Dự án trị giá 8 tỷ USD được phê duyệt"})
        self.assertNotEqual(data["eventFamily"], "FX_MOVEMENT")

    def test_entity_mentions_are_not_verified_impact(self):
        r = m.exposure_hypothesis({
            "title": "FPT công bố kết quả kinh doanh",
            "entityMentions": [{"symbol": "FPT", "confidence": .98},
                               {"symbol": "FRT", "confidence": .78}]
        })
        self.assertEqual(r["directIssuerMentions"], ["FPT"])
        self.assertFalse(r["historicalImpactCertified"])
        self.assertFalse(r["notificationEligible"])

    def test_first_seen_is_receipt_not_publication(self):
        now = datetime(2026, 11, 3, 9, 12, tzinfo=timezone.utc)
        row = {"title": "News", "publishedAt": "2026-11-03T05:00:00+00:00",
               "url": "https://site.test/news?a=1&utm_source=rss",
               "firstSeenAt": "2026-11-02T05:00:00+00:00"}
        first = m.attach_collector_receipts([row], [], now)[0]
        self.assertEqual(first["collectorFirstSeenAt"], now.isoformat())
        self.assertEqual(first["collectorFirstSeenBasis"], "COLLECTOR_RECEIPT")
        next_time = now + timedelta(minutes=15)
        again = m.attach_collector_receipts(
            [{**row, "url": "https://site.test/news?a=1"}], [first], next_time)[0]
        self.assertEqual(again["collectorFirstSeenAt"], now.isoformat())

    def test_legacy_archive_cannot_invent_first_seen(self):
        now = datetime(2026, 11, 3, 9, 12, tzinfo=timezone.utc)
        historical = {"title":"News", "url":"https://site.test/news",
                      "publishedAt":"2026-11-01T10:00:00+00:00"}
        out = m.attach_collector_receipts([historical], [historical], now)
        self.assertIsNone(out[0]["collectorFirstSeenAt"])
        self.assertEqual(out[0]["collectorFirstSeenBasis"], "LEGACY_UNCERTIFIED")
        self.assertIsNone(out[1]["collectorFirstSeenAt"])
        self.assertEqual(out[1]["collectorFirstSeenBasis"], "LEGACY_UNCERTIFIED")

    def test_invalid_future_receipts_do_not_pass(self):
        now = datetime(2026, 11, 3, 9, 12, tzinfo=timezone.utc)
        previous = {"url":"https://site.test/news",
                    "collectorFirstSeenAt":"2026-11-04T00:00:00+00:00",
                    "collectorFirstSeenBasis":"COLLECTOR_RECEIPT"}
        result = m.attach_collector_receipts([previous], [previous], now)
        self.assertEqual(result[0]["collectorFirstSeenBasis"],"LEGACY_UNCERTIFIED")

if __name__ == "__main__":
    unittest.main()
