"""Corporate ESG source coverage and no-fabrication regression tests."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "refresh_esg.py"
spec = importlib.util.spec_from_file_location("finquery_refresh_esg", MODULE)
esg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(esg)


class EsgRegistryTests(unittest.TestCase):
    def test_core_universe_and_nonbank_issuer_disclosures(self):
        config = json.loads((ROOT / "config" / "esg_sources.json").read_text(encoding="utf-8"))
        registry = esg.build_company_registry(config)
        self.assertEqual(len(registry), 100)
        self.assertEqual(registry["MBB"]["entityType"], "bank")
        self.assertEqual(registry["VCB"]["entityType"], "bank")
        for sym in ("FPT", "HPG", "GAS", "MWG", "VNM"):
            self.assertEqual(registry[sym]["entityType"], "company")
            self.assertIn("curated-issuer", registry[sym]["sourcePolicy"])
            self.assertTrue(registry[sym]["seed_urls"])
            self.assertTrue(all(url.startswith("https://") for url in registry[sym]["seed_urls"]))
        self.assertIn("disclosure-index", registry["FPT"]["sourcePolicy"])

    def test_verified_pdf_types_are_not_inferred_from_random_file_names(self):
        config = json.loads((ROOT / "config" / "esg_sources.json").read_text(encoding="utf-8"))
        registry = esg.build_company_registry(config)
        pdf = registry["HPG"]["seed_urls"][0]
        row = esg.corrected_document_year({"url": pdf, "title": "hpg-bao-cao-ptbv-2025.pdf"}, registry["HPG"])
        self.assertEqual(row["type"], "sustainability_report")
        self.assertEqual(row["year"], 2025)
        self.assertTrue(esg.metric_document_allowed(row))

    def test_billion_vnd_table_unit_before_value_is_corrected_with_source_evidence(self):
        original = {
            "metricId": "sustainable_finance", "year": 2025,
            "value": 0.000002, "rawValue": "2000", "unit": "billion VND",
            "snippet": "Doanh số huy động tiền gửi xanh năm 2025 đạt khoảng tỷ VND 2000; "
                       "báo cáo phát triển bền vững của Vietcombank.",
            "sourceType": "sustainability_report",
            "sourceUrl": "https://example.com/verified-esg.pdf",
            "confidence": "medium",
        }
        corrected = esg.repair_canonical_row(original)
        self.assertEqual(corrected["unit"], "billion VND")
        self.assertEqual(corrected["value"], 2000)
        self.assertTrue(corrected["repaired"])
        self.assertIn("unit", corrected["repairEvidence"])

    def test_ambiguous_vnd_amount_is_not_promoted_to_verified_esg(self):
        original = {
            "metricId": "sustainable_finance", "year": 2025,
            "value": 0.000002, "rawValue": "2000", "unit": "billion VND",
            "snippet": "Green finance disclosure 2000 VND, year 2025 with no stated billion unit.",
            "sourceType": "annual_report", "confidence": "medium"
        }
        corrected = esg.repair_canonical_row(original)
        self.assertFalse(corrected.get("repaired", False))
        self.assertFalse(esg.metric_row_valid(corrected))

    def test_generic_nonbank_disclosure_does_not_create_numeric_values(self):
        registry = esg.build_company_registry(json.loads(
            (ROOT / "config" / "esg_sources.json").read_text(encoding="utf-8")))
        generic = registry["VIC"]
        self.assertIn("curated-issuer", generic["sourcePolicy"])
        self.assertIn("https://vingroup.net/phat-trien-ben-vung", generic["seed_urls"])
        self.assertFalse(generic.get("validated_metrics"))
        self.assertEqual(esg.fill_validated_metrics([], generic), [])


if __name__ == "__main__":
    unittest.main()
