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

    def test_unit_is_bound_to_official_vbma_product_not_value_magnitude(self):
        raw = b"Date,ON,1W,1M\n22/10/2026,3.9,4.1,4.2\n"
        result = parse_vbma_curve(raw, "fi_bond", TODAY)
        self.assertEqual(result["unit"], "%/năm")
        self.assertEqual(result["unitBasis"], "official_VBMA_curve_product")
        self.assertEqual(result["status"], "verified")

    def test_numeric_formats(self):
        self.assertEqual(parse_number("3,90"), 3.9)
        self.assertEqual(parse_number("-123,50"), -123.5)
        self.assertIsNone(parse_number("<html>"))

    def test_excel_serial_date_in_dated_curve(self):
        # 2026-10-22 Excel date serial relative to 1899-12-30.
        from datetime import timedelta
        serial=(date(2026,10,22)-date(1899,12,30)).days
        raw=f"Date,1W,1M,Yield (%)\n{serial},3.0,3.1,3.2\n".encode()
        result=parse_vbma_curve(raw,"gov_bond",TODAY)
        self.assertEqual(result["asOf"],"2026-10-22")
        self.assertEqual(result["status"],"verified")

    def test_vbma_metadata_date_tenor_yield_table(self):
        raw=b"Observation date,22/10/2026,comment\nTenor,Yield (%),comment\n1W,3.10,x\n1M,3.30,x\n3M,3.50,x\n"
        result=parse_vbma_curve(raw,"fi_bond",TODAY)
        self.assertEqual(len(result["points"]),3)
        self.assertEqual(result["points"][0]["tenor"],"1W")

    def test_stale_curve_is_labeled_stale_not_repackaged_as_current(self):
        raw=b"Date,1W,1M,Yield (%)\n01/09/2026,3.2,3.4,3.5\n"
        result=parse_vbma_curve(raw,"fi_bond",TODAY)
        self.assertEqual(result["asOf"],"2026-09-01")
        self.assertEqual(result["status"],"stale")


    def test_month_first_from_unambiguous_actual_csv_layout(self):
        raw=b"Unnamed: 0,ON,1W,1M\n10/16/2026,3.1,3.2,3.3\n10/20/2026,3.5,3.7,3.8\n10/23/2026,4.1,4.3,4.6\n"
        result=parse_vbma_curve(raw,"swap",TODAY)
        self.assertEqual(result["asOf"],"2026-10-23")
        self.assertEqual(result["dateLayout"],"MM/DD/YYYY")
        self.assertEqual(result["points"][0]["tenor"],"ON")
        self.assertEqual(result["unit"],"%/năm")

    def test_european_days_not_misread_as_months(self):
        raw=b"Unnamed: 0,1Y,2Y,3Y\n18/10/2026,3.1,3.2,3.3\n20/10/2026,3.5,3.7,3.8\n23/10/2026,4.1,4.3,4.6\n"
        result=parse_vbma_curve(raw,"gov_bond",TODAY)
        self.assertEqual(result["asOf"],"2026-10-23")
        self.assertEqual(result["dateLayout"],"DD/MM/YYYY_or_ISO")

if __name__ == "__main__":
    unittest.main()
