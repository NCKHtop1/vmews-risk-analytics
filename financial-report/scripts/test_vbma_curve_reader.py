import io
import unittest
import zipfile
from datetime import date
from vbma_curve_reader import parse_vbma_curve, parse_number, VBMA_URLS

TODAY = date(2026, 10, 24)


class VBMASourceTests(unittest.TestCase):
    def test_four_curves_dated_csv_with_percent_unit(self):
        raw = b"Date,ON,1W,1M,Yield (%)\n22/10/2026,3.9,4.1,4.2,4.3\n"
        for kind in ("swap", "fi_bond", "gov_bond", "short_benchmark"):
            result = parse_vbma_curve(raw, kind, TODAY)
            self.assertEqual(result["asOf"], "2026-10-22")
            self.assertEqual(result["unit"], "%/năm")
            self.assertEqual(len(result["points"]), 3)
            self.assertEqual(result["source"], VBMA_URLS[kind])
        self.assertEqual(result["status"], "verified")

    def test_swap_points_not_relabelled_as_percent(self):
        raw = b"Date;1W;1M;3M;Swap points\n22/10/2026;-10;-32;-123;MID\n"
        parsed = parse_vbma_curve(raw, "swap", TODAY)
        self.assertEqual(parsed["unit"], "swap points")
        self.assertEqual(parsed["points"][1]["value"], -32.0)

    def test_long_form_csv(self):
        raw = b"Date,Tenor,Yield (%),MID\n2026-10-22,1W,4.3,4.3\n2026-10-22,1M,4.5,4.5\n"
        result = parse_vbma_curve(raw, "gov_bond", TODAY)
        self.assertEqual(len(result["points"]), 2)

    def test_date_not_verified_does_not_publish(self):
        with self.assertRaises(ValueError):
            parse_vbma_curve(b"ON;1W;1M;Yield (%)\n3.1;3.2;3.3;4.1\n", "gov_bond", TODAY)

    def test_unit_not_synthesized(self):
        raw = b"Date,ON,1W,1M\n22/10/2026,3.9,4.1,4.2\n"
        result = parse_vbma_curve(raw, "fi_bond", TODAY)
        self.assertIsNone(result["unit"])
        self.assertEqual(result["status"], "unit_unverified")

    def test_numeric_formats(self):
        self.assertEqual(parse_number("3,90"), 3.9)
        self.assertEqual(parse_number("-123,50"), -123.5)
        self.assertIsNone(parse_number("<html>"))
if __name__ == "__main__":
    unittest.main()
