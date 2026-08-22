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
        self.assertIn("forecast-live-leaders-v14.js", self.document.assets)
        for asset in self.document.assets:
            with self.subTest(asset=asset):
                self.assertTrue((ROOT / asset).is_file())

    def test_market_event_and_backtest_controls_are_present(self) -> None:
        required = {
            "symbol", "go", "status", "modelBadge", "close", "t1", "t3", "t5",
            "pup", "risk", "drivers", "chart", "forecastCards", "methodProof",
            "eventImpact", "eventImpactMeta", "news", "rumors", "sourceAudit",
            "tabs", "metrics", "btRows", "btDetail", "ablation",
            "heroCanvas", "heroSpark", "sparkSymbol", "symbolSuggestions",
            "marketTape", "tapeTrack", "chartOverlay", "chartPulse", "backToTop",
            "overview", "forecast", "validation", "events", "backtest",
            "leaders", "leadersTitle", "snapshotDate", "vnClock", "marketPulse",
            "signalDeck", "leaderDots", "leaderDetail", "carouselPosition",
            "carouselPrev", "carouselNext", "carouselAutoplay",
        }
        self.assertFalse(required - self.document.ids)

    def test_visual_identity_and_honest_scenario_language(self) -> None:
        css = (ROOT / "forecast-portfolio-v14.css").read_text(encoding="utf-8")
        self.assertIn("#a8eb65", css)
        self.assertIn("#090a08", css)
        self.assertIn("Equity", self.html)
        self.assertIn("Kịch bản xác suất", self.html)
        self.assertIn("Tin ra, giá phản ứng thế nào", self.html)

    def test_motion_is_responsive_accessible_and_reducible(self) -> None:
        css = (ROOT / "forecast-portfolio-v14.css").read_text(encoding="utf-8")
        motion = (ROOT / "forecast-portfolio-v14.js").read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("prefers-reduced-motion", motion)
        self.assertIn("requestAnimationFrame", motion)
        self.assertIn("document.hidden", motion)
        self.assertIn("IntersectionObserver", motion)
        self.assertIn("aria-live=\"polite\"", self.html)
        self.assertIn("focus-visible", css)

    def test_tape_and_sparkline_use_real_snapshot_values(self) -> None:
        motion = (ROOT / "forecast-portfolio-v14.js").read_text(encoding="utf-8")
        self.assertIn("base.dash.symbols", motion)
        self.assertIn("base.dash.charts", motion)
        self.assertIn("snapshot.close", motion)
        self.assertIn("rawClose", motion)
        self.assertIn("EOD", self.html)

    def test_forecast_chart_supports_real_history_ranges(self) -> None:
        app = (ROOT / "forecast-final-v12.js").read_text(encoding="utf-8")
        self.assertIn('data-range="30"', self.html)
        self.assertIn('data-range="65"', self.html)
        self.assertIn('data-range="125"', self.html)
        self.assertIn("chartRange", app)
        self.assertIn("chartOverlay", app)
        self.assertIn("quadraticCurveTo", app)

    def test_leaderboard_uses_validated_current_hose_forecasts(self) -> None:
        leaders = (ROOT / "forecast-live-leaders-v14.js").read_text(encoding="utf-8")
        self.assertIn('snapshot.exchange !== "HOSE"', leaders)
        self.assertIn('snapshot.dataFreshness !== "CURRENT"', leaders)
        self.assertIn("forecast.priceValidated !== true", leaders)
        self.assertIn('forecast.validationStatus !== "PASS"', leaders)
        self.assertIn("target % tickSize !== 0", leaders)
        self.assertIn("upside: target / close - 1", leaders)
        self.assertIn("right.upside - left.upside", leaders)
        self.assertIn("rows.slice(0, 10)", leaders)
        self.assertNotIn("Math.random", leaders)

    def test_signal_quality_uses_real_liquidity_news_risk_and_uncertainty(self) -> None:
        leaders = (ROOT / "forecast-live-leaders-v14.js").read_text(encoding="utf-8")
        self.assertIn("histories[symbol]", leaders)
        self.assertIn("session.volume", leaders)
        self.assertIn("avgVolume20 * close", leaders)
        self.assertIn("snapshot.newsFeatures", leaders)
        self.assertIn("snapshot.evidence?.recent", leaders)
        self.assertIn("issuerNewsMatches(row, item)", leaders)
        self.assertIn("gameplay", leaders)
        self.assertIn("snapshot.flow", leaders)
        self.assertIn("forecast.expertContributions", leaders)
        self.assertIn("forecast.q20Price", leaders)
        self.assertIn("forecast.q80Price", leaders)
        self.assertIn("row.tradedValue20 < 1e9", leaders)
        self.assertIn("không phải xác suất sinh lời", leaders)

    def test_rotating_cards_support_keyboard_touch_filters_and_reduced_motion(self) -> None:
        leaders = (ROOT / "forecast-live-leaders-v14.js").read_text(encoding="utf-8")
        css = (ROOT / "forecast-portfolio-v14.css").read_text(encoding="utf-8")
        self.assertIn("perspective: 1400px", css)
        self.assertIn("rotateY(var(--deck-rotate", css)
        self.assertIn("prefers-reduced-motion", leaders)
        self.assertIn("document.hidden", leaders)
        self.assertIn("ArrowLeft", leaders)
        self.assertIn("pointerup", leaders)
        self.assertIn('data-filter="liquid"', self.html)
        self.assertIn('data-filter="green"', self.html)
        self.assertIn('aria-roledescription="carousel"', self.html)

    def test_leaderboard_can_open_existing_symbol_analysis(self) -> None:
        app = (ROOT / "forecast-final-v12.js").read_text(encoding="utf-8")
        leaders = (ROOT / "forecast-live-leaders-v14.js").read_text(encoding="utf-8")
        self.assertIn("window.__VMEWS_RENDER_SYMBOL__=renderSymbol", app)
        self.assertIn("window.__VMEWS_RENDER_SYMBOL__(symbol)", leaders)
        self.assertIn("snapshot", self.html.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
