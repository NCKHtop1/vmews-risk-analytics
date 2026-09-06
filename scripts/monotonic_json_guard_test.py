import unittest

from monotonic_json_guard import decide


class TestMonotonicGuard(unittest.TestCase):
    def test_date_newer(self):
        self.assertEqual(decide({"asOf": "2026-09-07"}, {"asOf": "2026-09-04"}, "asOf", "date")["decision"], "PUBLISH")

    def test_date_older_skips(self):
        self.assertEqual(decide({"asOf": "2026-09-04"}, {"asOf": "2026-09-07"}, "asOf", "date")["decision"], "SKIP")

    def test_same_revalidated_can_publish(self):
        self.assertEqual(decide({"asOf": "2026-09-04"}, {"asOf": "2026-09-04"}, "asOf", "date")["decision"], "PUBLISH")

    def test_datetime_timezone(self):
        result = decide(
            {"generatedAt": "2026-09-06T12:00:00Z"},
            {"generatedAt": "2026-09-06T18:00:00+07:00"},
            "generatedAt",
            "datetime",
        )
        self.assertEqual(result["decision"], "PUBLISH")

    def test_nested_field(self):
        self.assertEqual(decide({"meta": {"n": 3}}, {"meta": {"n": 4}}, "meta.n", "int")["decision"], "SKIP")

    def test_missing_candidate_rejected(self):
        with self.assertRaises(RuntimeError):
            decide({}, {"asOf": "2026-09-04"}, "asOf", "date")


if __name__ == "__main__":
    unittest.main()
