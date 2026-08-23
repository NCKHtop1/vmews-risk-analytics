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

async function loadMarketDashboard() {
  const source = await readFile(new URL("../forecast-final-v12.js", import.meta.url), "utf8");
  const emitted = [];
  const document = { addEventListener() {}, querySelector() { return null; } };
  const window = { dispatchEvent(event) { emitted.push(event); } };
  class BrowserEvent { constructor(type, options) { this.type = type; this.detail = options?.detail; } }
  const location = { pathname: "/NCKHtop1/vmews-risk-analytics/hash/forecast-final.html", hostname: "cdn.githubraw.com" };
  vm.runInContext(source, vm.createContext({ window, document, location, URLSearchParams, CustomEvent: BrowserEvent, console }));
  return { window, emitted };
}

function snapshot(symbol, close, target, overrides = {}) {
  return {
    symbol, close, exchange: "HOSE", dataFreshness: "CURRENT", riskStatus: "GREEN", dailyVolatility: .024,
    horizons: {
      "5": {
        expectedPrice: target, q20Price: close - 1_000, q80Price: close + 2_000,
        tickSize: 100, priceValidated: true, validationStatus: "PASS", directionValidated: false,
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

test("VN30 carousel rejects nonmembers, removed names, downtrends and nonexecutable prices", async () => {
  const window = await loadLeaderboard();
  const items = [
    snapshot("ASP", 12_000, 16_000),
    snapshot("PLX", 38_000, 42_000),
    snapshot("FPT", 72_000, 72_900),
    snapshot("MCH", 128_000, 130_000),
    snapshot("TCX", 34_000, 33_900),
    snapshot("VHM", 49_000, 49_327),
  ];
  const rows = window.__VMEWS_BUILD_LEADERBOARD__(base(items));
  assert.deepEqual(Array.from(rows, row => row.symbol), ["MCH", "FPT"]);
  assert.ok(rows.every(row => row.target > row.close));
  assert.equal(window.__VMEWS_VN30_MEMBERS__.length, 30);
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
  ], oldRoster));
  assert.deepEqual(Array.from(rows, row => row.symbol), ["PLX"]);
  assert.equal(rows.length, 1);
});

test("carousel returns at most ten independently validated positive VN30 forecasts", async () => {
  const window = await loadLeaderboard();
  const items = Array.from(window.__VMEWS_VN30_MEMBERS__).map((symbol, index) =>
    snapshot(symbol, 50_000, 50_100 + index * 100)
  );
  const rows = window.__VMEWS_BUILD_LEADERBOARD__(base(items));
  assert.equal(rows.length, 10);
  assert.ok(rows.every((row, index) => index === 0 || rows[index - 1].upside >= row.upside));
  assert.equal(window.__VMEWS_BUILD_LEADERBOARD__(base(items), { all: true }).length, 30);
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
  assert.equal(market.dash.symbols.FPT.horizons["5"].expectedPrice, 72_300);
  assert.equal(market.dash.symbols.FPT.evidence.communityWatchlist[0].verificationState, "PENDING");
  assert.equal(market.market.sources.rumorAudit.source.articles, 10);
  assert.equal(emitted.at(-1).type, "vmews:community-updated");
  assert.equal(emitted.at(-1).detail.forecastUpdates, 1);
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
});
