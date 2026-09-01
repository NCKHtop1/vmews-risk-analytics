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
        tickSize: 100, priceValidated: true, validationStatus: "PASS", economicPointStatus: "PASS", directionValidated: false, pointDirectionValidated: true, magnitudeValidated: true,
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

test("economic point strength is metadata and cannot erase otherwise validated HOSE forecasts", async () => {
  const window = await loadLeaderboard();
  const lowConfidence = snapshot("FPT", 73_200, 74_000);
  lowConfidence.horizons["5"].economicPointStatus = "LOW_CONFIDENCE";
  const rows = window.__VMEWS_BUILD_LEADERBOARD__(base([lowConfidence]), { all: true });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].symbol, "FPT");
  lowConfidence.horizons["5"].magnitudeValidated = false;
  assert.equal(window.__VMEWS_BUILD_LEADERBOARD__(base([lowConfidence]), { all: true }).length, 0);
});

test("latest production dashboard keeps every structurally valid forecast in the ranking universe", async () => {
  const dashboard = JSON.parse(await readFile(new URL("../data/forecast-dashboard-v12.json", import.meta.url), "utf8"));
  const window = await loadLeaderboard();
  const B = { dash: dashboard, model: { promotion: dashboard.promotion } };
  const horizon = window.__VMEWS_RANKING_HORIZON__(B);
  const structurallyValid = Object.values(dashboard.symbols).filter(item => {
    const forecast = item?.horizons?.[String(horizon)] || {};
    return item.exchange === "HOSE" && item.dataFreshness === "CURRENT"
      && forecast.priceValidated === true && forecast.validationStatus === "PASS"
      && forecast.pointDirectionValidated === true && forecast.magnitudeValidated === true
      && Number(item.close) > 0 && Number(forecast.expectedPrice) > 0
      && Number(forecast.tickSize) > 0 && Number(forecast.expectedPrice) % Number(forecast.tickSize) === 0;
  });
  const ranked = window.__VMEWS_BUILD_LEADERBOARD__(B, { all: true, includeNonPositive: true });
  assert.ok(structurallyValid.length > 0);
  assert.equal(ranked.length, structurallyValid.length);
  assert.deepEqual(
    new Set(ranked.map(row => row.symbol)),
    new Set(structurallyValid.map(row => row.symbol)),
  );
  assert.ok(ranked.some(row => row.upside > 0));
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

test("detail view uses the validated session close without rewriting the sealed forecast", async () => {
  const { window } = await loadMarketDashboard();
  const core = snapshot("FPT", 70_700, 72_100);
  Object.assign(core.horizons["5"], { q20Price: 69_500, q80Price: 72_100, bearScenarioPrice: 69_000, bullScenarioPrice: 72_100 });
  const session = {
    session: "PRE_OPEN", cutoffAt: "2026-08-27T07:54:00+07:00", coreAsOf: "2026-08-26",
    symbols: [{ symbol: "FPT", liveClose: 72_600, quoteCurrent: true, freshForCutoff: true, updateAt: "2026-08-26T15:05:00+07:00" }],
  };
  const view = window.__VMEWS_APPLY_SESSION_VIEW__("FPT", core, session);
  assert.equal(view.close, 72_600);
  assert.equal(view.coreClose, 70_700);
  assert.equal(core.close, 70_700);
  assert.equal(core.horizons["5"].expectedPrice, 72_100);
  assert.equal(window.__VMEWS_SESSION_POSITION__(core.horizons["5"], view.close), "ABOVE_BULL");
});

test("stale-core session publishes price but cannot re-rank the forecast", async () => {
  const leaderboard = await loadLeaderboard();
  const items = [snapshot("FPT", 72_000, 73_000), snapshot("MCH", 128_000, 130_000)];
  const session = {
    status: "PASS",
    forecastAlignment: {
      status: "STALE_CORE",
      rankingEligible: false,
      actualCoreAsOf: "2026-08-26",
      expectedCoreAsOf: "2026-08-28",
    },
    symbols: [
      { symbol: "FPT", liveClose: 74_000, quoteCurrent: true, freshForCutoff: true },
      { symbol: "MCH", liveClose: 129_000, quoteCurrent: true, freshForCutoff: true },
    ],
  };
  const ranked = leaderboard.__VMEWS_FINAL_LEADERBOARD__(base(items), session, { all: true, includeNonPositive: true });
  assert.equal(ranked.find(row => row.symbol === "FPT").close, 72_000);
  assert.equal(ranked.find(row => row.symbol === "MCH").close, 128_000);

  const { window } = await loadMarketDashboard();
  const core = snapshot("FPT", 72_000, 73_000);
  const view = window.__VMEWS_APPLY_SESSION_VIEW__("FPT", core, session);
  assert.equal(view.close, 74_000);
  assert.equal(view.coreClose, 72_000);
  assert.equal(view.liveSession.forecastAligned, false);
  assert.equal(view.liveSession.expectedCoreAsOf, "2026-08-28");
});

test("ranking excludes a REVIEW horizon and uses the audited preferred PASS horizon", async () => {
  const window = await loadLeaderboard();
  const fpt = snapshot("FPT", 70_700, 72_100);
  fpt.horizons["3"] = { ...fpt.horizons["5"], expectedPrice: 72_300, q20Price: 70_400, q80Price: 74_200 };
  fpt.horizons["4"] = { ...fpt.horizons["5"], priceValidated: false, validationStatus: "REVIEW" };
  const B = base([fpt]);
  B.model = { promotion: { status: "PASS", directPriceHorizons: [1, 2, 3, 5], reviewHorizons: [4], preferredRankingHorizon: 3 } };
  const rows = window.__VMEWS_BUILD_LEADERBOARD__(B, { all: true });
  assert.equal(window.__VMEWS_RANKING_HORIZON__(B), 3);
  assert.equal(rows[0].horizon, 3);
  assert.equal(rows[0].target, 72_300);
});

test("detail view selects the audited horizon and exposes one exact up-or-down point forecast", async () => {
  const { window } = await loadMarketDashboard();
  const fpt = snapshot("FPT", 73_200, 72_700);
  fpt.horizons["1"] = { ...fpt.horizons["5"], expectedPrice: 73_000, q20Price: 71_900, q80Price: 74_100 };
  fpt.horizons["3"] = { ...fpt.horizons["5"], expectedPrice: 72_900, q20Price: 71_100, q80Price: 74_800 };
  const B = base([fpt]);
  B.model = { promotion: { status: "PASS", directPriceHorizons: [1, 2, 3], reviewHorizons: [4, 5], preferredRankingHorizon: 3 } };
  assert.equal(window.__VMEWS_PRIMARY_HORIZON__(B, fpt), 3);
  const point = window.__VMEWS_POINT_MOVE__(fpt.horizons["3"], fpt.close);
  assert.equal(point.direction, "GIẢM");
  assert.equal(point.delta, -300);
  assert.equal(point.target, 72_900);
});

test("backtest result date advances by audited trading sessions rather than calendar days", async () => {
  const { window } = await loadMarketDashboard();
  const B = { dash: { charts: { FPT: [
    { date: "2026-08-21", rawClose: 72_000 },
    { date: "2026-08-24", rawClose: 71_400 },
    { date: "2026-08-25", rawClose: 70_700 },
    { date: "2026-08-26", rawClose: 72_600 },
    { date: "2026-08-27", rawClose: 72_200 },
    { date: "2026-08-28", rawClose: 73_200 },
  ] } } };
  assert.equal(window.__VMEWS_BACKTEST_RESULT_DATE__(B, { symbol: "FPT", originDate: "2026-08-25" }, 3), "2026-08-28");
  assert.equal(window.__VMEWS_BACKTEST_RESULT_DATE__(B, { symbol: "FPT", originDate: "2026-08-21" }, 1), "2026-08-24");
  assert.equal(window.__VMEWS_BACKTEST_RESULT_DATE__(B, { symbol: "FPT", originDate: "2026-08-25", targetDate: "2026-09-01" }, 3), "2026-09-01");
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
