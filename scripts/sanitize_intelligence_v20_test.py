"""Regression tests for full-artifact issuer sanitation."""

from __future__ import annotations

import unittest

from sanitize_intelligence_v20 import sanitize_payload


class IntelligenceSanitizationTest(unittest.TestCase):
    def test_competing_primary_ticker_is_removed_but_multi_issuer_news_is_kept(self) -> None:
        universe = {"FPT", "FRT", "DGW", "KBC", "HPG", "VPB", "PET"}
        payload = {"symbols": {
            "FPT": [
                {"title": "FRT: CTCP Bán lẻ Kỹ thuật số FPT | Tổng quan"},
                {"title": "FPT ký hợp đồng chuyển đổi số mới"},
            ],
            "HPG": [{"title": "Digiworld (DGW) đầu tư vào KBC và HPG"}],
            "VPB": [{"title": "PET: được cấp hạn mức tín dụng tại VPB"}],
        }}
        cleaned, audit = sanitize_payload(payload, universe)
        self.assertEqual([row["title"] for row in cleaned["symbols"]["FPT"]], ["FPT ký hợp đồng chuyển đổi số mới"])
        self.assertEqual(len(cleaned["symbols"]["HPG"]), 1)
        self.assertEqual(cleaned["symbols"]["VPB"], [])
        self.assertEqual(audit["rejected"], 2)

    def test_nested_community_lists_are_sanitized(self) -> None:
        payload = {"symbols": {"FPT": {
            "claims": [{"title": "FPT mở rộng trung tâm dữ liệu"}],
            "watchlist": [{"title": "FRT: CTCP Bán lẻ Kỹ thuật số FPT | Tổng quan"}],
        }}}
        cleaned, audit = sanitize_payload(payload, {"FPT", "FRT"})
        self.assertEqual(len(cleaned["symbols"]["FPT"]["claims"]), 1)
        self.assertEqual(cleaned["symbols"]["FPT"]["watchlist"], [])
        self.assertEqual(audit["rejected"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
