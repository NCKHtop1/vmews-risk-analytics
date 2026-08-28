import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";

async function loadLeaderboard() {
  const source = await readFile(new URL("../forecast-live-leaders-v14.js", import.meta.url), "utf8");
  const document = { readyState: "loading", addEventListener() {}, querySelector() { return null; } };
  const window = { matchMedia() { return { matches: false }; } };
  vm.runInContext(source, vm.createContext({ window, document, console }));
  return window;
}

async function loadMarketDashboard(fetch = async () => { throw new Error("Unexpected network request"); }) {
  const source = await readFile(new URL("../forecast-final-v12.js", import.meta.url), "utf8");
  const emitted = [];
  const document = { addEventListener() {}, querySelector() { return null; } };
  const window = { dispatchEvent(event) { emitted.push(event); } };
  class BrowserEvent { constructor(type, options) { this.type = type; this.detail = options?.detail; } }
  const location = { pathname: "/NCKHtop1/vmews-risk-analytics/hash/forecast-final.html", hostname: "cdn.githubraw.com", search: "" };
  vm.runInContext(source, vm.createContext({ window, document, location, URLSearchParams, CustomEvent: BrowserEvent, fetch, console }));
  return { window, emitted };
}

function snapshot(symbol, close, target, overrides = {}) {
  return {
    symbol, close, exchange: "HOSE", dataFreshness: "CURRENT", riskStatus: "GREEN", dailyVolatility: .024,
    horizons: {
      "5": {
        expectedPrice: target, q20Price: close - 1_000, q80Price: close + 2_000,
        tickSize: 100, priceValidated: true, validationStatus: "PASS", directionValidated: false, pointDirectionValidated: true, magnitudeValidated: true,
      },
    },
    ...overrides,
  };
}

function base(symbols, roster) {
  return {
    dash: {
      symbols: Object.fromEntries(symbols.map(item => [item.symbol, item])),
      charts: Object.fromEntries(symbols.map(item => [item.symbol, [{ volume: 1_000_000, rawClose: item.close }]])),
      ...(roster ? { lists: { vn30: { symbols: roster } } } : {}),
    },
  };
}

test("rendered FPT headlines reject an FRT/FTS primary ticker without removing legitimate multi-issuer coverage", async () => {
  const { window } = await loadMarketDashboard();
  assert.equal(window.__VMEWS_ISSUER_HEADLINE_MATCHES__("FPT", "FRT: CTCP Bán lẻ Kỹ thuật số FPT | Tổng quan"), false);
  assert.equal(window.__VMEWS_ISSUER_HEADLINE_MATCHES__("FPT", "HOSE: FTS - Chứng khoán FPT công bố báo cáo"), false);
  assert.equal(window.__VMEWS_ISSUER_HEADLINE_MATCHES__("FPT", "Dragon Capital tăng tỷ trọng PNJ và FPT"), true);
  assert.equal(window.__VMEWS_ISSUER_HEADLINE_MATCHES__("FRT", "FRT: CTCP Bán lẻ Kỹ thuật số FPT | Tổng quan"), true);
});

test("commit-pinned CDN keeps immutable assets while live data comes from main", async () => {
  const { window } = await loadMarketDashboard();
  assert.equal(window.__VMEWS_ASSET_REF__, "hash");
  assert.equal(window.__VMEWS_DATA_REF__, "main");
  assert.equal(
    window.__VMEWS_DATA_ROOT__,
    "https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/main/data",
  );
});

test("leader loader fetches only the critical dashboard and gates", async () => {
  const requested = [];
  const fetch = async url => {
    requested.push(String(url));
    const dashboard = String(url).includes("forecast-dashboard-v12.json");
    return {
      ok: true,
      async json() { return dashboard ? { promotion: { status: "PASS" } } : { status: "PASS" }; },
    };
  };
  const { window } = await loadMarketDashboard(fetch);
  const result = await window.__VMEWS_LOAD_LEADER_BASE__();
  assert.equal(result.model.promotion.status, "PASS");
  assert.deepEqual(requested.map(url => new URL(url).pathname.split("/").at(-1)).sort(), [
    "forecast-dashboard-v12.json",
    "phase-gates-v12.json",
  ]);
});

test("default leaderboard ranks all validated HOSE names while VN30 remains an explicit scope", async () => {
  const window = await loadLeaderboard();
  const items = [
    snapshot("ASP", 12_000, 16_000),
    snapshot("PLX", 38_000, 42_000),
    snapshot("FPT", 72_000, 72_900),
    snapshot("MCH", 128_000, 130_000),
  ];
  const allHose = window.__VMEWS_BUILD_LEADERBOARD__(base(items), { all: true });
  const vn30 = window.__VMEWS_BUILD_LEADERBOARD__(base(items), { all: true, scope: "vn30" });
  assert.deepEqual(Array.from(allHose, row => row.symbol), ["ASP", "PLX", "MCH", "FPT"]);
  assert.deepEqual(Array.from(vn30, row => row.symbol), ["MCH", "FPT"]);
});


test("session overlay re-filters EOD positives that turn negative at the live cutoff", async () => {
  const window = await loadLeaderboard();
  const items = [snapshot("FPT", 72_000, 73_000), snapshot("MCH", 128_000, 130_000)];
  const session = {
    symbols: [
      { symbol: "FPT", liveClose: 74_000, change: .02, quoteCurrent: true, freshForCutoff: true, quality: .55, conviction: -.009 },
      { symbol: "MCH", liveClose: 129_000, change: .01, quoteCurrent: true, freshForCutoff: true, quality: .70, conviction: .006 },
    ],
  };
  const positive = window.__VMEWS_FINAL_LEADERBOARD__(base(items), session, { all: true });
  assert.deepEqual(Array.from(positive, row => row.symbol), ["MCH"]);
  assert.ok(positive.every(row => row.upside > 0));
  const defensive = window.__VMEWS_FINAL_LEADERBOARD__(base([items[0]]), { symbols: [session.symbols[0]] }, { all: true, includeNonPositive: true });
  assert.equal(defensive[0].symbol, "FPT");
  assert.ok(defensive[0].upside < 0);
});

test("accuracy audit selects the longest eligible recent horizon", async () => {
  const window = await loadLeaderboard();
  const recent = (n, maeSkill, directionalAccuracy) => ({ recent120Dates: { n, maeSkill, directionalAccuracy } });
  const policy = window.__VMEWS_RANKING_POLICY_FROM_REPORT__({ horizons: {
    "1": recent(1100, -.001, .56),
    "2": recent(1100, .009, .58),
    "3": recent(1100, .009, .55),
    "4": recent(1100, .005, .546),
    "5": recent(1100, -.016, .494),
  } });
  assert.equal(policy.selectedHorizon, 4);
  assert.equal(policy.degraded, false);
  assert.equal(policy.coreForecastChanged, false);
});

test("leaderboard obeys the audited horizon instead of hard-coded T+5", async () => {
  const window = await loadLeaderboard();
  const valid = (expectedPrice, alpha) => ({
    expectedPrice, expectedReturn: expectedPrice / 70_700 - 1, alpha,
    q20Price: 68_000, q80Price: 74_000, tickSize: 100,
    priceValidated: true, validationStatus: "PASS", directionValidated: true,
    pointDirectionValidated: true, magnitudeValidated: true, probUp: .57,
  });
  const item = snapshot("FPT", 70_700, 70_800, { horizons: {
    "4": valid(72_000, .018),
    "5": valid(70_800, .0014),
  } });
  const rows = window.__VMEWS_BUILD_LEADERBOARD__(base([item]), { all: true, horizon: 4 });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].horizon, 4);
  assert.equal(rows[0].target, 72_000);
  assert.equal(rows[0].modelReturn, .018);
});

test("session overlay recomputes selected-horizon rank instead of trusting legacy conviction", async () => {
  const window = await loadLeaderboard();
  const item = snapshot("FPT", 72_000, 73_000);
  const session = { symbols: [{
    symbol: "FPT", liveClose: 72_500, change: .01, quoteCurrent: true, freshForCutoff: true,
    quality: 0, conviction: -99,
  }] };
  const rows = window.__VMEWS_FINAL_LEADERBOARD__(base([item]), session, { all: true });
  assert.equal(rows.length, 1);
  assert.notEqual(rows[0].rankScore, -99);
  assert.ok(rows[0].rankScore > 0);
});

test("current market scan is a price-only fallback and cannot partially re-rank HOSE", async () => {
  const window = await loadLeaderboard();
  const generatedAt = new Date().toISOString();
  const reviewDate = generatedAt.slice(0, 10);
  const items = [snapshot("FPT", 70_700, 73_000), snapshot("MCH", 128_000, 130_000)];
  const overlay = window.__VMEWS_BUILD_MARKET_SCAN_OVERLAY__(base(items), {
    generatedAt, reviewDate,
    ranking: [{ symbol: "FPT", exchange: "HOSE", date: reviewDate, close: 72_600, ret1: .0268, volume: 11_461_932, relativeVolume10d: 1.77, stale: false, updateMode: "delayed_streaming_900" }],
  });
  assert.equal(overlay.status, "PASS");
  assert.equal(overlay.priceOnly, true);
  assert.equal(overlay.rankingEligible, false);
  assert.equal(overlay.symbols[0].liveClose, 72_600);
  const ranked = window.__VMEWS_FINAL_LEADERBOARD__(base(items), overlay, { all: true });
  assert.equal(ranked.find(row => row.symbol === "FPT").close, 70_700);
});

test("detail view uses a fresh price overlay without rewriting sealed forecasts", async () => {
  const { window } = await loadMarketDashboard();
  const core = snapshot("FPT", 70_700, 73_000);
  const generatedAt = new Date().toISOString();
  window.__VMEWS_SESSION__ = {
    status: "PASS", source: "MARKET_SCAN_EOD_PRICE_OVERLAY", generatedAt, cutoffAt: generatedAt,
    coreForecastUnchanged: true, priceOnly: true,
    symbols: [{ symbol: "FPT", liveClose: 72_600, change: .0268, quoteCurrent: true, freshForCutoff: true, observedAt: generatedAt, lastTradeAt: generatedAt.slice(0, 10) }],
  };
  const view = window.__VMEWS_WITH_SESSION_PRICE__("FPT", core);
  assert.equal(view.close, 72_600);
  assert.equal(view.priceSession.coreClose, 70_700);
  assert.equal(view.horizons["5"].expectedPrice, 73_000);
  assert.equal(core.close, 70_700);
});

test("VN30 scope rejects nonmembers, removed names, downtrends and nonexecutable prices", async () => {
  const window = await loadLeaderboard();
  const items = [
    snapshot("ASP", 12_000, 16_000),
    snapshot("PLX", 38_000, 42_000),
    snapshot("FPT", 72_000, 72_900),
    snapshot("MCH", 128_000, 130_000),
    snapshot("TCX", 34_000, 33_900),
    snapshot("VHM", 49_000, 49_327),
  ];
  const rows = window.__VMEWS_BUILD_LEADERBOARD__(base(items), { scope: "vn30" });
  assert.deepEqual(Array.from(rows, row => row.symbol), ["MCH", "FPT"]);
  assert.ok(rows.every(row => row.target > row.close));
  assert.equal(window.__VMEWS_VN30_MEMBERS__.length, 30);
});

test("VN30 scope can rank validated defensive names when no positive forecast exists", async () => {
  const window = await loadLeaderboard();
  const items = [
    snapshot("FPT", 72_000, 71_600),
    snapshot("MCH", 128_000, 127_900),
    snapshot("TCX", 34_000, 33_800),
  ];
  const positive = window.__VMEWS_BUILD_LEADERBOARD__(base(items), { all: true, scope: "vn30" });
  const defensive = window.__VMEWS_BUILD_LEADERBOARD__(base(items), { all: true, scope: "vn30", includeNonPositive: true });
  assert.equal(positive.length, 0);
  assert.deepEqual(Array.from(defensive, row => row.symbol), ["MCH", "FPT", "TCX"]);
  assert.ok(defensive.every(row => row.target <= row.close));
});

test("published dated VN30 roster is authoritative and fewer than ten are never padded", async () => {
  const window = await loadLeaderboard();
  const oldRoster = Array.from(window.__VMEWS_VN30_MEMBERS__)
    .filter(symbol => symbol !== "MCH" && symbol !== "TCX")
    .concat("PLX", "TPB");
  const rows = window.__VMEWS_BUILD_LEADERBOARD__(base([
    snapshot("PLX", 38_000, 39_000),
    snapshot("MCH", 128_000, 132_000),
    snapshot("FPT", 72_000, 71_800),
  ], oldRoster), { scope: "vn30" });
  assert.deepEqual(Array.from(rows, row => row.symbol), ["PLX"]);
  assert.equal(rows.length, 1);
});

test("VN30 scope returns at most ten independently validated positive forecasts", async () => {
  const window = await loadLeaderboard();
  const items = Array.from(window.__VMEWS_VN30_MEMBERS__).map((symbol, index) =>
    snapshot(symbol, 50_000, 50_100 + index * 100)
  );
  const rows = window.__VMEWS_BUILD_LEADERBOARD__(base(items), { scope: "vn30" });
  assert.equal(rows.length, 10);
  assert.ok(rows.every((row, index) => index === 0 || rows[index - 1].upside >= row.upside));
  assert.equal(window.__VMEWS_BUILD_LEADERBOARD__(base(items), { all: true, scope: "vn30" }).length, 30);
});

test("live community overlay updates only the matching audited snapshot and valid HOSE quotes", async () => {
  const { window, emitted } = await loadMarketDashboard();
  const market = {
    dash: { asOf: "2026-08-21", symbols: { FPT: {
      evidence: { rumorAudit: { source: {} } }, rumorContext: {},
      horizons: { "5": { priceValidated: true, expectedPrice: 72_000, expectedReturn: 0 } },
    } } },
    market: { sources: { rumorAudit: { source: { articles: 0 } } } },
  };
  const update = {
    asOf: "2026-08-21", generatedAt: new Date().toISOString(),
    publishers: ["FireAnt", "24HMoney"], publisherCounts: { FireAnt: 6, "24HMoney": 4 },
    symbols: { FPT: {
      watchlist: [{ title: "FPT dự kiến ký hợp đồng", verificationState: "PENDING" }],
      claims: [], rumorContext: {},
      horizons: { "5": { expectedPrice: 72_300, expectedReturn: .0041, tickSize: 100 } },
    } },
  };

  assert.equal(window.__VMEWS_APPLY_COMMUNITY_LIVE__(market, update), true);
  assert.equal(market.dash.symbols.FPT.horizons["5"].expectedPrice, 72_000);
  assert.equal(market.dash.symbols.FPT.horizons["5"].liveScenarioOverlay.scenarioPrice, 72_300);
  assert.equal(market.dash.symbols.FPT.horizons["5"].liveScenarioOverlay.appliedToCentralForecast, false);
  assert.equal(market.dash.symbols.FPT.evidence.communityWatchlist[0].verificationState, "PENDING");
  assert.equal(market.market.sources.rumorAudit.source.articles, 10);
  assert.equal(emitted.at(-1).type, "vmews:community-updated");
  assert.equal(emitted.at(-1).detail.forecastUpdates, 0);
  assert.equal(emitted.at(-1).detail.scenarioUpdates, 1);
});

test("a different snapshot or an invalid sub-tick update can never replace the forecast", async () => {
  const { window } = await loadMarketDashboard();
  const market = { dash: { asOf: "2026-08-21", symbols: { FPT: { evidence: {}, horizons: { "5": { priceValidated: true, expectedPrice: 72_000 } } } } } };
  const invalidDate = { asOf: "2026-08-20", generatedAt: new Date().toISOString(), symbols: {} };
  assert.equal(window.__VMEWS_APPLY_COMMUNITY_LIVE__(market, invalidDate), false);

  const invalidTick = {
    asOf: "2026-08-21", generatedAt: new Date().toISOString(),
    symbols: { FPT: { watchlist: [], claims: [], horizons: { "5": { expectedPrice: 72_327, tickSize: 100 } } } },
  };
  assert.equal(window.__VMEWS_APPLY_COMMUNITY_LIVE__(market, invalidTick), true);
  assert.equal(market.dash.symbols.FPT.horizons["5"].expectedPrice, 72_000);
  assert.equal(market.dash.symbols.FPT.horizons["5"].liveScenarioOverlay, undefined);
});

test("source freshness labels are clear and contain no internal data-engineering jargon", async () => {
  const source = await readFile(new URL("../forecast-final-v12.js", import.meta.url), "utf8");
  assert.doesNotMatch(source, new RegExp(["không điền", "giả"].join("\\s+"), "i"));
  assert.doesNotMatch(source, /Object\.assign\(horizon\s*,\s*adjustment\)/);
  assert.doesNotMatch(source, /FORECAST LOCKED/);
  assert.doesNotMatch(source, /\/main\/data/);
  assert.match(source, /CDN_PATH\[2\]/);
  assert.doesNotMatch(source, /Cập nhật chậm|Đã cập nhật cùng phiên|Chưa có dữ liệu từ nguồn|Đang mở rộng nguồn|Bối cảnh tham khảo · chưa điều chỉnh giá trung tâm/);
  assert.match(source, /Phiên gần nhất/);
  assert.match(source, /Mở BCTC/);
  assert.match(source, /Danh mục · tỷ trọng · NAV · biến động/);
});
