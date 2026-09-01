"""Regression tests for strict issuer identity in the research-news generator."""

from __future__ import annotations

import unittest

from update_research_news import issuer_relevant


class ResearchNewsIssuerTest(unittest.TestCase):
    def test_rejects_cross_issuer_and_brand_collisions(self) -> None:
        cases = (
            ("FPT", "Cổ phiếu FPT Retail tăng gần 40% chỉ sau 2 tuần"),
            ("ACB", "AGR: Nghị quyết HĐQT phê duyệt hạn mức tín dụng tại ACB"),
            ("MWG", "SSI: Cổ phiếu Thế Giới Di Động (MWG) còn dư địa tăng"),
            ("HCM", "BFC: Quyết định của Thuế TP.HCM về xử phạt thuế"),
            ("HCM", "TPC: Kết luận kiểm tra thuế tại TP.HCM"),
        )
        for symbol, title in cases:
            with self.subTest(symbol=symbol, title=title):
                self.assertFalse(issuer_relevant(symbol, title))

    def test_keeps_explicit_single_and_multi_issuer_news(self) -> None:
        self.assertTrue(issuer_relevant("FPT", "FPT ký hợp đồng chuyển đổi số mới"))
        self.assertTrue(issuer_relevant("HPG", "Digiworld (DGW) đầu tư vào KBC và HPG"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
