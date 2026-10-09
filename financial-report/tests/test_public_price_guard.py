import pathlib
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from guard_public_quotes import PricePublicationError, compare, validate


def sample(minutes_ago=2, missing=0):
    date = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    return {"status": "ok", "latestSourceTime": date, "expected": 113,
            "coverage": 113 - missing,
            "quotes": {f"S{i:02d}": {"symbol": f"S{i:02d}", "price": 20000,
                                  "sourceTime": date}
                       for i in range(113 - missing)}}


class PricePublicationTests(unittest.TestCase):
    def test_aligned_public_snapshot_passes(self):
        self.assertEqual(compare(sample(2), sample(4), "pages")["coverage"], 113)

    def test_stale_public_data_fails_even_if_status_ok(self):
        with self.assertRaisesRegex(PricePublicationError, "lag source"):
            compare(sample(2), sample(45), "domain")

    def test_mass_blank_prices_fail_even_if_status_ok(self):
        with self.assertRaisesRegex(PricePublicationError, "coverage"):
            compare(sample(2), sample(2, missing=20), "pages")

    def test_zero_price_is_not_valid(self):
        p = sample()
        for symbol in list(p["quotes"])[:6]:
            p["quotes"][symbol]["price"] = 0
        with self.assertRaisesRegex(PricePublicationError, "coverage"):
            validate(p, "source")

    def test_wrong_universe_is_rejected(self):
        p = sample()
        p["expected"] = 114
        with self.assertRaisesRegex(PricePublicationError, "universe mismatch"):
            compare(sample(), p, "pages")

    def test_future_stamp_is_rejected(self):
        p = sample(-20)
        with self.assertRaisesRegex(PricePublicationError, "future quote source"):
            validate(p, "pages")


if __name__ == "__main__":
    unittest.main()
