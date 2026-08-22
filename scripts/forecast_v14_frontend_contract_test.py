"""Static publication checks for the GitHub-CDN portfolio-style dashboard."""

from __future__ import annotations

import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Document(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(str(values["id"]))
        if tag in {"link", "script"}:
            address = values.get("href" if tag == "link" else "src")
            if address and address.startswith("./"):
                self.assets.append(address.split("?", 1)[0][2:])


class ForecastFrontendContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "forecast-final.html").read_text(encoding="utf-8")
        cls.document = Document()
        cls.document.feed(cls.html)

    def test_every_referenced_local_asset_exists(self) -> None:
        self.assertIn("forecast-portfolio-v14.css", self.document.assets)
        self.assertIn("forecast-portfolio-v14.js", self.document.assets)
        for asset in self.document.assets:
            with self.subTest(asset=asset):
                self.assertTrue((ROOT / asset).is_file())

    def test_market_event_and_backtest_controls_are_present(self) -> None:
        required = {
            "symbol", "go", "status", "modelBadge", "close", "t1", "t3", "t5",
            "pup", "risk", "drivers", "chart", "forecastCards", "methodProof",
            "eventImpact", "eventImpactMeta", "news", "rumors", "sourceAudit",
            "tabs", "metrics", "btRows", "btDetail", "ablation",
        }
        self.assertFalse(required - self.document.ids)

    def test_visual_identity_and_honest_scenario_language(self) -> None:
        css = (ROOT / "forecast-portfolio-v14.css").read_text(encoding="utf-8")
        self.assertIn("#a8eb65", css)
        self.assertIn("#090a08", css)
        self.assertIn("Equity", self.html)
        self.assertIn("Kịch bản xác suất", self.html)
        self.assertIn("Tin ra, giá phản ứng thế nào", self.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
