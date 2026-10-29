import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from smoke_custom_domain import protected_page, verify_hub_page


class AuthAwareDomainSmokeTests(unittest.TestCase):
    def test_login_route_is_valid_and_preserves_next(self):
        loc = "/login?next=%2Ffinancial-report%2Fdata-hub.html"
        self.assertTrue(protected_page(307, loc, "/financial-report/data-hub.html"))

    def test_login_on_other_domain_rejected(self):
        self.assertFalse(protected_page(307, "https://evil.example/login?next=/financial-report/data-hub.html",
                                        "/financial-report/data-hub.html"))

    def test_open_data_hub_is_security_failure(self):
        self.assertFalse(protected_page(200, "", "/financial-report/data-hub.html"))

    def test_wrong_redirect_is_failure(self):
        self.assertFalse(protected_page(307, "/login?next=%2Ffinancial-report%2Findex.html",
                                        "/financial-report/data-hub.html"))

    def test_deployed_hub_markers_required(self):
        doc = pathlib.Path(__file__).resolve().parents[1] / "data-hub.html"
        content = doc.read_bytes()
        self.assertGreater(verify_hub_page(content), 1000)

    def test_hnx_index_equities_not_on_new_hub(self):
        doc = pathlib.Path(__file__).resolve().parents[1] / "data-hub.html"
        s = doc.read_text(encoding="utf-8")
        self.assertIn("Dữ liệu phái sinh được tổng hợp riêng", s)
        self.assertIn("VN30", s)
        self.assertIn("VN100", s)


if __name__ == "__main__":
    unittest.main()
