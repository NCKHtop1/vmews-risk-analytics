import copy
import unittest
from datetime import date
import refresh_liquidity as ingest

BASE={
 "schemaVersion":1,"asOf":"2026-10-22",
 "interbank":{"status":"secondary_source_crosschecked","asOf":"2026-10-22",
              "observations":[{"date":"2026-10-21","value":3.39},{"date":"2026-10-22","value":4.31}]},
 "derivatives":{"lastMonth":"2026-09","months":[{"month":"2026-08"},{"month":"2026-09"}]},
 "vbmaSwap":{"status":"awaiting_verified_source","licenseStatus":"review_required",
             "asOf":None,"points":[],"unit":None}
}
ON_TEXT="""<html><body><h1>Lãi suất liên ngân hàng qua đêm</h1>
<h2>Số liệu các kỳ gần đây</h2>
<table><tr><td>22/10/2026</td><td>4,31%</td></tr>
<tr><td>21/10/2026</td><td>3,39%</td></tr>
<tr><td>20/10/2026</td><td>3,71%</td></tr></table></body></html>""".encode()
CROSS="""<html><body><h2>Lãi suất thị trường liên ngân hàng qua đêm</h2>
<div>22-10-2026 · Qua đêm: 4,31%/năm</div></body></html>""".encode()
MALFORMED_CSV=b"<html>503 Service unavailable</html>"
def fetcher(url):
    if url==ingest.ON_URL:return ON_TEXT
    if url==ingest.ON_CROSS:return CROSS
    if url==ingest.SWAP_URL:return MALFORMED_CSV
    raise AssertionError("Unexpected URL")

class LiquidityIngestionTests(unittest.TestCase):
    def test_dated_on_rates_are_parsed_correctly(self):
        pts=ingest.parse_on_history(ON_TEXT,date(2026,10,24))
        self.assertEqual(pts[-1],{"date":"2026-10-22","value":4.31})
        self.assertEqual(len(pts),3)

    def test_stale_or_wrong_content_rejected(self):
        with self.assertRaises(ValueError):
            ingest.parse_on_history(b"<html>4,31% today</html>",date(2026,10,24))
        with self.assertRaises(ValueError):
            ingest.parse_on_history(ON_TEXT,date(2026,11,20))

    def test_independent_source_must_match_on_date_and_rate(self):
        self.assertTrue(ingest.verify_crosscheck(CROSS,{"date":"2026-10-22","value":4.31}))
        self.assertFalse(ingest.verify_crosscheck(CROSS,{"date":"2026-10-22","value":9.99}))
        self.assertFalse(ingest.verify_crosscheck(CROSS,{"date":"2026-10-23","value":4.31}))

    def test_refresh_retains_actual_futures_and_disallows_unverified_swap(self):
        data=ingest.refresh(copy.deepcopy(BASE),fetcher=fetcher,clock=date(2026,10,24))
        self.assertEqual(data["interbank"]["observations"][-1]["value"],4.31)
        self.assertEqual(data["derivatives"],BASE["derivatives"])
        self.assertEqual(data["vbmaSwap"]["status"],"awaiting_verified_source")
        self.assertEqual(data["vbmaSwap"]["points"],[])
        self.assertTrue(data["sourceIssues"])

    def test_no_feeds_keeps_existing_snapshot(self):
        def offline(url): raise ConnectionError("offline")
        data=ingest.refresh(copy.deepcopy(BASE),fetcher=offline,clock=date(2026,10,24))
        self.assertEqual(data["interbank"]["observations"],BASE["interbank"]["observations"])
        self.assertEqual(data["derivatives"],BASE["derivatives"])
        self.assertEqual(data["vbmaSwap"]["points"],[])

    def test_swap_curve_without_explicit_unit_is_not_published(self):
        csv=b"Date,ON,1W,1M,3M\n22/10/2026,4.2,4.3,4.6,4.9\n"
        self.assertIsNone(ingest.parse_swap_verified(csv,date(2026,10,24)))

if __name__=="__main__":
    unittest.main()
