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
        self.assertIn("solution-ai-v17.js", self.document.assets)
        for asset in self.document.assets:
            with self.subTest(asset=asset):
                self.assertTrue((ROOT / asset).is_file())

    def test_market_event_and_backtest_controls_are_present(self) -> None:
        required = {
            "symbol", "go", "status", "modelBadge", "close", "t1", "t3", "t5",
            "pup", "risk", "range5", "drivers", "chart", "forecastCards", "methodProof",
            "scenarioBoard", "move5", "bear5", "scenarioCenter5", "bull5", "scenarioCaveat",
            "eventImpact", "eventImpactMeta", "news", "rumors", "sourceAudit",
            "tabs", "metrics", "btRows", "btDetail", "ablation",
            "heroCanvas", "heroSpark", "sparkSymbol", "symbolSuggestions",
            "marketTape", "tapeTrack", "chartOverlay", "backToTop", "symbolSelector",
            "overview", "forecast", "validation", "events", "backtest",
            "leaders", "leadersTitle", "snapshotDate", "vnClock", "marketPulse",
            "signalDeck", "leaderDots", "leaderDetail", "carouselPosition",
            "carouselPrev", "carouselNext", "carouselAutoplay",
            "solutionAiLauncher", "solutionAiPanel", "solutionAiMessages", "solutionAiForm",
            "solutionAiInput", "solutionAiSuggestions", "solutionAiContext",
            "solutionAiConnect", "solutionAiGoogle", "solutionAiRetry", "solutionAiGeminiWeb",
            "solutionAiKey", "solutionAiDisconnect", "solutionAiBackend", "solutionAiSaveBackend",
        }
        self.assertFalse(required - self.document.ids)

    def test_visual_identity_and_honest_scenario_language(self) -> None:
        css = (ROOT / "forecast-portfolio-v14.css").read_text(encoding="utf-8")
        self.assertIn("#a8eb65", css)
        self.assertIn("#090a08", css)
        self.assertIn("<span>SoluTION.AI</span> define market.", self.html)
        self.assertIn("HOSE · 5 PHIÊN TỚI", self.html)
        self.assertIn("Trọng tâm T+5", self.html)
        self.assertIn("Phản ứng sau sự kiện", self.html)
        self.assertNotIn("Chuyển động giao diện không đại diện", self.html)
        self.assertNotIn("bước giá", self.html)
        self.assertNotIn("không trả lời chung chung", self.html)
        self.assertIn(
            "nghiên cứu nguồn công khai và kết nối thông tin mới với diễn biến của từng mã",
            self.html,
        )
        self.assertIn("release=20.6", self.html)
        self.assertIn("forecast-live-leaders-v14.js?release=21.2", self.html)
        self.assertNotIn("release=19.3", self.html)

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
        self.assertIn("DỮ LIỆU MỚI NHẤT", self.html)

    def test_forecast_chart_supports_real_history_ranges(self) -> None:
        app = (ROOT / "forecast-final-v12.js").read_text(encoding="utf-8")
        self.assertIn('data-range="30"', self.html)
        self.assertIn('data-range="65"', self.html)
        self.assertIn('data-range="125"', self.html)
        self.assertIn("chartRange", app)
        self.assertIn("chartOverlay", app)
        self.assertIn("quadraticCurveTo", app)

    def test_query_symbol_updates_every_visible_and_ai_context_selector(self) -> None:
        app = (ROOT / "forecast-final-v12.js").read_text(encoding="utf-8")
        input_sync = app.index('$("#symbol").value=sym')
        spark_sync = app.index('setText("#sparkSymbol",sym)')
        render = app.index("rerender(B,sym,z)", input_sync)
        self.assertLess(input_sync, render)
        self.assertLess(spark_sync, render)

    def test_leaderboard_defaults_to_validated_hose_with_explicit_vn30_scope(self) -> None:
        leaders = (ROOT / "forecast-live-leaders-v14.js").read_text(encoding="utf-8")
        self.assertIn("base?.dash?.lists?.vn30?.symbols", leaders)
        self.assertIn('options.scope === "vn30"', leaders)
        self.assertIn("!members.has(symbol)", leaders)
        self.assertIn('"MCH"', leaders)
        self.assertIn('"TCX"', leaders)
        self.assertIn('snapshot.exchange !== "HOSE"', leaders)
        self.assertIn('snapshot.dataFreshness !== "CURRENT"', leaders)
        self.assertIn("forecast.priceValidated !== true", leaders)
        self.assertIn('forecast.validationStatus !== "PASS"', leaders)
        self.assertIn("target % tickSize !== 0", leaders)
        self.assertIn("target <= close", leaders)
        self.assertIn("includeNonPositive", leaders)
        self.assertIn("HOSE · TRẠNG THÁI PHÒNG THỦ", leaders)
        self.assertIn("GIẢM ÍT NHẤT TRÊN HOSE", leaders)
        self.assertIn("forecast-session-v21.json", leaders)
        self.assertIn("coreForecastUnchanged", leaders)
        self.assertIn("payload.coreAsOf", leaders)
        self.assertIn("payload.forecastAlignment", leaders)
        self.assertIn("rankingEligible", leaders)
        self.assertIn("upside: target / close - 1", leaders)
        self.assertIn("right.rankScore - left.rankScore", leaders)
        self.assertIn("__VMEWS_FINAL_LEADERBOARD__", leaders)
        self.assertIn("release-pointer-v22.json", self.html)
        self.assertIn("rows.slice(0, 10)", leaders)
        self.assertNotIn("Math.random", leaders)

    def test_leaderboard_loads_before_the_full_backtest_bundle(self) -> None:
        app = (ROOT / "forecast-final-v12.js").read_text(encoding="utf-8")
        leaders = (ROOT / "forecast-live-leaders-v14.js").read_text(encoding="utf-8")
        self.assertIn("window.__VMEWS_LOAD_LEADER_BASE__=loadLeaderBase", app)
        self.assertIn("const JSON_PROMISES=new Map()", app)
        self.assertIn("window.__VMEWS_LOAD_LEADER_BASE__ || window.__VMEWS_LOAD_BASE__", leaders)

    def test_signal_quality_uses_real_liquidity_news_risk_and_uncertainty(self) -> None:
        leaders = (ROOT / "forecast-live-leaders-v14.js").read_text(encoding="utf-8")
        self.assertIn("histories[symbol]", leaders)
        self.assertIn("session.volume", leaders)
        self.assertIn("avgVolume20 * close", leaders)
        self.assertIn("snapshot.newsFeatures", leaders)
        self.assertIn("snapshot.evidence?.recent", leaders)
        self.assertIn("issuerNewsMatches(row, item)", leaders)
        self.assertIn("belongsToLastFiveSessions(row, item)", leaders)
        self.assertIn("gameplay", leaders)
        self.assertIn("snapshot.flow", leaders)
        self.assertIn("forecast.expertContributions", leaders)
        self.assertIn("forecast.q20Price", leaders)
        self.assertIn("forecast.q80Price", leaders)
        self.assertIn("row.tradedValue20 < 1e9", leaders)
        self.assertIn("signalBand", leaders)
        self.assertIn("VÙNG GIÁ", leaders)
        self.assertIn("fundContext", leaders)
        self.assertIn("Quỹ nắm giữ", leaders)

    def test_v17_ui_distinguishes_point_range_and_live_fund_evidence(self) -> None:
        app = (ROOT / "forecast-final-v12.js").read_text(encoding="utf-8")
        polish = (ROOT / "forecast-polish-v12.js").read_text(encoding="utf-8")
        self.assertIn("expectedAbsReturn", app)
        self.assertIn("bearScenarioPrice", app)
        self.assertIn("bullScenarioPrice", app)
        self.assertIn("magnitudeCalibrationRatio", app)
        self.assertIn("Kịch bản hai chiều", app)
        self.assertIn("Dự báo biên độ", app)
        self.assertIn("Danh mục quỹ", app)
        self.assertIn("fundContext", polish)
        self.assertIn("Tác động T+5", polish)
        self.assertIn("fund.holdings", (ROOT / "solution-ai-v17.js").read_text(encoding="utf-8"))
        self.assertNotIn("chưa dùng để fit model", polish)

    def test_solution_ai_is_grounded_and_does_not_expose_a_provider_secret(self) -> None:
        assistant = (ROOT / "solution-ai-v17.js").read_text(encoding="utf-8")
        backend = (ROOT / "api/solution-ai.js").read_text(encoding="utf-8")
        self.assertIn("SoluTION.AI", self.html)
        self.assertIn("window.__VMEWS_LOAD_BASE__", assistant)
        self.assertIn("expertContributions", assistant)
        self.assertIn("directionValidated", assistant)
        self.assertIn("__VMEWS_BUILD_LEADERBOARD__", assistant)
        self.assertIn("solutionAiConnect", assistant)
        self.assertIn("solutionAiGeminiWeb", assistant)
        self.assertIn("https://gemini.google.com/app", assistant)
        self.assertIn("Không mở đầu hoặc kết thúc bằng disclaimer chung", assistant)
        self.assertIn("https://aistudio.google.com/app/apikey", self.html)
        self.assertIn('id="solutionAiKey" type="password"', self.html)
        self.assertIn("sessionStorage", assistant)
        self.assertIn("https://generativelanguage.googleapis.com/v1beta", assistant)
        self.assertIn('"x-goog-api-key": secret', assistant)
        self.assertIn('type: "google_search"', assistant)
        self.assertIn('step.type !== "model_output"', assistant)
        self.assertIn("url_citation", assistant)
        self.assertIn("aiSources", assistant)
        self.assertIn("Vĩ mô & tin mới", self.html)
        self.assertNotIn("vmews-risk-analytics-sojd.vercel.app", self.html)
        self.assertNotIn("localStorage.setItem(SESSION_KEY", assistant)
        self.assertNotIn("window.prompt", assistant)
        self.assertNotIn("GEMINI_API_KEY", assistant)
        self.assertIn("process.env.GEMINI_API_KEY", backend)

    def test_community_evidence_is_corroborated_without_fabricated_fireant_access(self) -> None:
        app = (ROOT / "forecast-final-v12.js").read_text(encoding="utf-8")
        self.assertIn("rumorClaims", app)
        self.assertIn("nguồn độc lập", app)
        self.assertIn("rumorFireant", app)
        self.assertIn("rumor24h", app)
        self.assertIn("communityWatchlist", app)
        self.assertIn("community-intelligence-live-v19.json", app)
        self.assertIn("vmews:community-updated", app)
        self.assertIn("ĐÃ ĐỐI CHIẾU", app)
        self.assertIn("ĐANG ĐỐI CHIẾU", app)
        self.assertNotIn("Chưa ghi nhận thông tin lan truyền đủ điều kiện để theo dõi.", app)

    def test_rotating_cards_support_keyboard_touch_filters_and_reduced_motion(self) -> None:
        leaders = (ROOT / "forecast-live-leaders-v14.js").read_text(encoding="utf-8")
        css = (ROOT / "forecast-portfolio-v14.css").read_text(encoding="utf-8")
        self.assertIn("perspective: 1400px", css)
        self.assertIn("rotateY(var(--deck-rotate", css)
        self.assertIn("prefers-reduced-motion", leaders)
        self.assertIn("document.hidden", leaders)
        self.assertIn("ArrowLeft", leaders)
        self.assertIn("pointerup", leaders)
        self.assertIn("}, 3000);", leaders)
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
