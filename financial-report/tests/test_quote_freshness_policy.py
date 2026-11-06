"""Deterministic FinQuery quote freshness edge-case tests."""
import pathlib
import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from quote_freshness_policy import assess_quote_source, QuoteFreshnessError
import guard_public_quotes as guard


def vn(day, hour, minute=0):
    return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00+07:00").astimezone(timezone.utc)


def fixture(stamp,checked=None):
    value=stamp.isoformat()
    return {"status":"ok","expected":111,"coverage":111,
            "latestSourceTime":value,"checkedAt":(checked or stamp).isoformat(),
            "quotes":{f"S{i:03d}":{"price":20000,"status":"ok","sourceTime":value} for i in range(111)}}


class SourceFreshnessTests(unittest.TestCase):
    def test_reported_fpt_incident_fails_even_if_source_status_ok(self):
        with self.assertRaisesRegex(QuoteFreshnessError,"source session stale"):
            assess_quote_source(fixture(vn("2026-11-05",14,45)),now=vn("2026-11-06",9,56))

    def test_current_morning_passes(self):
        d=fixture(vn("2026-11-06",9,52))
        self.assertEqual(assess_quote_source(d,now=vn("2026-11-06",9,56))["freshQuotes"],111)

    def test_stale_current_session_fails(self):
        with self.assertRaisesRegex(QuoteFreshnessError,"source quote stale"):
            assess_quote_source(fixture(vn("2026-11-06",9,30)),now=vn("2026-11-06",10,2))

    def test_stale_collector_heartbeat_fails(self):
        d=fixture(vn("2026-11-06",10,5),checked=vn("2026-11-06",9,50))
        with self.assertRaisesRegex(QuoteFreshnessError,"collector heartbeat stale"):
            assess_quote_source(d,now=vn("2026-11-06",10,10))

    def test_individual_quote_coverage_fails(self):
        d=fixture(vn("2026-11-06",10,5))
        for key in list(d["quotes"])[:16]:
            d["quotes"][key]["sourceTime"]=vn("2026-11-06",9,20).isoformat()
        with self.assertRaisesRegex(QuoteFreshnessError,"fresh source quote coverage"):
            assess_quote_source(d,now=vn("2026-11-06",10,10))

    def test_two_illiquid_quotes_tolerated(self):
        d=fixture(vn("2026-11-06",10,5))
        for key in list(d["quotes"])[:2]:
            d["quotes"][key]["sourceTime"]=vn("2026-11-06",9,20).isoformat()
        self.assertEqual(assess_quote_source(d,now=vn("2026-11-06",10,10))["freshQuotes"],109)

    def test_lunch_does_not_fabricate_new_prints(self):
        r=assess_quote_source(fixture(vn("2026-11-06",11,30)),now=vn("2026-11-06",12,53))
        self.assertEqual(r["phase"],"lunch")

    def test_lunch_to_afternoon_must_refresh(self):
        with self.assertRaisesRegex(QuoteFreshnessError,"source quote stale"):
            assess_quote_source(fixture(vn("2026-11-06",11,30)),now=vn("2026-11-06",13,18))

    def test_preopen_prior_day_allowed(self):
        r=assess_quote_source(fixture(vn("2026-11-05",14,45)),now=vn("2026-11-06",9,7))
        self.assertEqual(r["phase"],"preopen")

    def test_weekend_last_friday_allowed(self):
        r=assess_quote_source(fixture(vn("2026-11-06",14,45)),now=vn("2026-11-07",10,30))
        self.assertEqual(r["phase"],"closed")

    def test_postclose_requires_current_session(self):
        with self.assertRaisesRegex(QuoteFreshnessError,"source session stale"):
            assess_quote_source(fixture(vn("2026-11-05",14,45)),now=vn("2026-11-06",16,30))
        r=assess_quote_source(fixture(vn("2026-11-06",14,45)),now=vn("2026-11-06",16,30))
        self.assertEqual(r["phase"],"postclose")

    def test_holiday_uses_previous_completed_session(self):
        r=assess_quote_source(fixture(vn("2026-08-28",14,45)),now=vn("2026-09-02",10,0))
        self.assertEqual(r["expectedSession"],"2026-08-28")

    def test_unknown_2027_calendar_fails_closed(self):
        with self.assertRaisesRegex(QuoteFreshnessError,"calendar not certified"):
            assess_quote_source(fixture(vn("2027-01-06",9,58)),now=vn("2027-01-06",10,0))

    def test_future_source_rejected(self):
        now=vn("2026-11-06",10,0)
        with self.assertRaisesRegex(QuoteFreshnessError,"future"):
            assess_quote_source(fixture(now+timedelta(minutes=8)),now=now)

    def test_main_returns_24_not_success_when_source_stale(self):
        old=fixture(vn("2026-11-05",14,45))
        with patch.object(guard,"read",return_value=old),\
             patch.object(guard,"assess_quote_source",side_effect=QuoteFreshnessError("source session stale")),\
             patch.object(guard,"probe_domain_anonymous") as domain:
            self.assertEqual(guard.main(),24)
            domain.assert_not_called()


if __name__=="__main__":
    unittest.main()
