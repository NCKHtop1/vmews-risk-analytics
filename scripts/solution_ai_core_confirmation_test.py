import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from solution_ai_core_confirmation import parse_yahoo_payload

VN = ZoneInfo("Asia/Ho_Chi_Minh")


class SolutionAICoreConfirmationTest(unittest.TestCase):
    def test_extracts_matching_session_close(self):
        stamps = [
            int(datetime(2026, 10, 1, 9, 0, tzinfo=VN).timestamp()),
            int(datetime(2026, 10, 2, 9, 0, tzinfo=VN).timestamp()),
        ]
        payload = {
            "chart": {
                "result": [{
                    "timestamp": stamps,
                    "indicators": {"quote": [{"close": [62000, 62100]}]},
                }]
            }
        }
        self.assertEqual(parse_yahoo_payload(payload, "2026-10-02"), 62100)

    def test_missing_session_returns_none(self):
        stamp = int(datetime(2026, 10, 1, 9, 0, tzinfo=VN).timestamp())
        payload = {
            "chart": {
                "result": [{
                    "timestamp": [stamp],
                    "indicators": {"quote": [{"close": [62000]}]},
                }]
            }
        }
        self.assertIsNone(parse_yahoo_payload(payload, "2026-10-02"))


if __name__ == "__main__":
    unittest.main()
