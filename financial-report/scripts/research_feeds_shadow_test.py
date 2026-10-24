"""Offline contract checks for isolated research feeds."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

MOD = Path(__file__).with_name("research_feeds_shadow.py")
spec = importlib.util.spec_from_file_location("finquery_research_feeds_shadow", MOD)
rf = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = rf
spec.loader.exec_module(rf)

class ResearchFeedsTests(unittest.TestCase):
    def test_provider_urls_are_allowlisted(self):
        self.assertTrue(rf.approved_url("https://vbma.org.vn/csv/markets/charts/vi/fx_swap_curve.csv", "vbma"))
        self.assertFalse(rf.approved_url("http://vbma.org.vn/a.csv", "vbma"))
        self.assertFalse(rf.approved_url("https://vbma.org.vn.evil.test/data", "vbma"))
        self.assertFalse(rf.approved_url("https://example.org/", "events"))

    def test_csv_fails_closed_on_html(self):
        with self.assertRaises(ValueError):
            rf.parse_vbma_csv(b"<html><body>blocked</body></html>")

    def test_csv_keeps_values_and_no_unit_assumption(self):
        d = rf.parse_vbma_csv(b"Date,ON,1W\\n23/10/2026,4.12,4.55\\n22/10/2026,4.30,4.70\\n".replace(b"\\n", b"\n"))
        self.assertEqual(d["rows"][0]["ON"], "4.12")
        self.assertIsNone(d.get("derivedRate"))
        self.assertFalse(d["modelEligible"])
        self.assertFalse(d["publicationEligible"])
        self.assertEqual(d["quality"], "date_and_unit_unverified")

    def test_csv_utf16(self):
        payload = "Date;Tenor;Value\n2026-10-23;ON;3.9\n2026-10-22;ON;4.4".encode("utf-16")
        d = rf.parse_vbma_csv(payload)
        self.assertEqual(len(d["rows"]), 2)

    def test_event_date_not_publication_timestamp(self):
        d = rf.review_pit_events({"events": [{
            "id":"TEST", "symbol":"MBB", "type":"cash_dividend",
            "date":"2026-10-23",
            "details":{"publishedAt":"2026-10-20"},
            "source":{"publisher":"HOSE","url":"https://www.hsx.vn/news"}
        }]})
        self.assertEqual(d["checked"],1)
        self.assertEqual(len(d["verifiedCandidates"]),0)
        self.assertEqual(len(d["withheld"]),1)

    def test_crawler_does_not_publish_or_inject_on(self):
        def fake(url, provider):
            if provider=="vbma": return b"Date;Tenor;Rate\n2026-10-23;ON;3.9\n"
            if provider=="events":return json.dumps({"events":[]}).encode()
            return b"<html>no monthly listing</html>"
        d=rf.probe(fetch=fake)
        self.assertEqual(d["mode"],"SHADOW_ONLY")
        self.assertFalse(d["publicServingEnabled"])
        self.assertFalse(d["forecastInputsChanged"])
        self.assertEqual(d["scope"]["equities"]["allowedExchanges"], ["HOSE"])
        self.assertNotIn("HNX", d["scope"]["equities"]["allowedExchanges"])
        self.assertEqual(d["scope"]["derivatives"], ["VN30_FUTURES", "VN100_FUTURES"])
        self.assertIn("hnx_derivatives_monthly", d["sources"])
        self.assertIn("nhnn_omo", d["sources"])
        self.assertIn("nhnn_tin_phieu", d["sources"])
        self.assertIn("nhnn_unsecured_interbank_6m", d["sources"])
        self.assertFalse(d["sources"]["nhnn_unsecured_interbank_on"]["modelEligible"])
        self.assertIsNone(d["sources"]["nhnn_unsecured_interbank_on"]["rate"])

    def test_derivatives_hnx_is_allowed_but_equities_are_not(self):
        listing = (
            '<a href="/vi-vn/chi-tiet-thong-ke">Phái sinh tháng 9/2026</a>'
        ).encode()
        found = rf.monthly_hnx_link(listing)
        self.assertEqual(found[2], "2026-09")
        html = (
            '<h1>Phái sinh tháng 9/2026</h1>'
            '<p>Khối lượng hợp đồng mở đạt 25.000 hợp đồng</p>'
            '<h2>Về giao dịch hợp đồng tương lai chỉ số VN100</h2>'
            '<p>OI là 1.234 hợp đồng</p>'
        ).encode()
        result = rf.parse_hnx_monthly(html, found[1], "2026-09")
        self.assertEqual(result["assetClass"], "EQUITY_INDEX_FUTURES")
        self.assertEqual(result["contracts"]["VN30_FUTURES"]["oi"], 25000)
        self.assertEqual(result["contracts"]["VN100_FUTURES"]["oi"], 1234)
        self.assertFalse(result["equityShareFeed"])
        self.assertFalse(result["publicationEligible"])

    def test_hnx_equity_is_withheld_even_if_official(self):
        def event(publisher, exchange):
            return {"id":"TEST-"+exchange, "symbol":"ABC","type":"cash_dividend",
                "date":"2026-10-23","exchange":exchange,
                "details":{"publishedAt":"2026-10-20T08:00:00+07:00"},
                "source":{"publisher":publisher,"url":"https://example.com/source"}}
        d=rf.review_pit_events({"events":[
            event("HNX","HNX"), event("HOSE","HOSE"),
            event("VSDC","UPCOM")]})
        self.assertEqual(d["checked"],3)
        self.assertEqual(len(d["verifiedCandidates"]),1)
        self.assertEqual(d["verifiedCandidates"][0]["equityExchange"],"HOSE")
        self.assertEqual(len(d["withheld"]),2)

    def test_no_oi_without_official_validation(self):
        with self.assertRaises(ValueError):
            rf.parse_hnx_monthly(b"<html>No actual futures figures</html>",rf.HNX_LISTING)

if __name__=="__main__":
    unittest.main()
