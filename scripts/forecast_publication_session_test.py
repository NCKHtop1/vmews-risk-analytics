"""Prevent a cutoff-time race without weakening financial-data source contracts."""
import unittest
from datetime import datetime
from forecast_publication_session import publication_session_status
from vn_exchange_calendar import VN_TZ

def at(h, m):
    return datetime(2026, 10, 9, h, m, tzinfo=VN_TZ)

class ForecastPublicationSessionCutoverTest(unittest.TestCase):
    def test_before_boundary_publishes_current_completed_session(self):
        r=publication_session_status("2026-10-08",at(15,4))
        self.assertEqual(r["status"],"CURRENT_VERIFIED_SESSION")
        self.assertFalse(r["staleCore"])
    def test_after_boundary_can_publish_new_current_session(self):
        r=publication_session_status("2026-10-09",at(15,6))
        self.assertFalse(r["staleCore"])
    def test_just_completed_prior_is_dated_and_explicitly_stale(self):
        r=publication_session_status("2026-10-08",at(15,20))
        self.assertEqual(r["status"],"PREVIOUS_VERIFIED_SESSION_DURING_CUTOVER")
        self.assertTrue(r["staleCore"])
        self.assertEqual(r["expectedSessionNow"],"2026-10-09")
        self.assertEqual(r["validatedSession"],"2026-10-08")
    def test_reject_old_session_even_in_cutover(self):
        with self.assertRaisesRegex(ValueError,"STALE_OR_FUTURE_FORECAST_REJECTED"):
            publication_session_status("2026-10-07",at(15,20))
    def test_reject_previous_after_cutover_grace_expires(self):
        with self.assertRaisesRegex(ValueError,"STALE_OR_FUTURE_FORECAST_REJECTED"):
            publication_session_status("2026-10-08",at(16,21))
    def test_reject_future_session_before_its_eod(self):
        with self.assertRaisesRegex(ValueError,"STALE_OR_FUTURE_FORECAST_REJECTED"):
            publication_session_status("2026-10-09",at(14,55))
    def test_reject_missing_or_malformed_session(self):
        for value in ("",None,"2026-10-xx"):
            with self.subTest(value=value),self.assertRaises(ValueError):
                publication_session_status(value,at(15,20))
    def test_previous_friday_at_monday_cutover(self):
        r=publication_session_status("2026-10-09",datetime(2026,10,12,15,10,tzinfo=VN_TZ))
        self.assertTrue(r["staleCore"])
        self.assertEqual(r["expectedSessionNow"],"2026-10-12")

if __name__ == "__main__":
    unittest.main()
