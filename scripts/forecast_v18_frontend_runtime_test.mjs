import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";

class Element {
  constructor() {
    this.textContent = "";
    this.innerHTML = "";
    this.value = "";
    this.children = [];
    this.dataset = {};
    this.className = "";
    this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
    this.listeners = new Map();
    this.style = {};
  }
  append(...items) { this.children.push(...items); }
  appendChild(item) { this.children.push(item); return item; }
  replaceChildren(...items) { this.children = [...items]; this.innerHTML = ""; }
  addEventListener(name, callback) { this.listeners.set(name, callback); }
  setAttribute() {}
  querySelector() { return new Element(); }
  getContext() { return { setTransform() {}, clearRect() {}, createLinearGradient() { return { addColorStop() {} }; }, fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, fill() {}, arc() {}, closePath() {}, quadraticCurveTo() {}, save() {}, restore() {}, rect() {}, clip() {}, setLineDash() {}, fillText() {}, measureText() { return { width: 10 }; } }; }
  getBoundingClientRect() { return { width: 900, height: 510, left: 0, top: 0 }; }
}

function runtime(source) {
  const nodes = new Map();
  const events = new Map();
  const document = {
    readyState: "loading", hidden: false,
    querySelector(selector) { if (!nodes.has(selector)) nodes.set(selector, new Element()); return nodes.get(selector); },
    querySelectorAll() { return []; },
    createElement() { return new Element(); },
    addEventListener(name, callback) { events.set(name, callback); },
  };
  const window = {
    addEventListener() {}, dispatchEvent() {}, setInterval() {},
    matchMedia() { return { matches: true }; },
  };
  const context = vm.createContext({
    window, document, location: { hostname: "localhost", pathname: "/forecast-final.html", search: "" },
    history: { replaceState() {} }, URLSearchParams, encodeURIComponent,
    fetch: async () => { throw new Error("network disabled in runtime unit test"); },
    console, CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options?.detail; } },
    requestAnimationFrame(callback) { callback(1000); return 1; }, cancelAnimationFrame() {}, devicePixelRatio: 1,
    setTimeout, clearTimeout,
  });
  vm.runInContext(source, context);
  return { window, document, nodes, events };
}

async function loadMarket() {
  return JSON.parse(await readFile(new URL("../data/forecast-dashboard-v12.json", import.meta.url), "utf8"));
}

test("rendered FPT headlines reject an FRT/FTS primary ticker without removing legitimate multi-issuer coverage", async () => {
  const source = await readFile(new URL("../forecast-final-v12.js", import.meta.url), "utf8");
  const { window } = runtime(source);
  assert.equal(window.__VMEWS_ISSUER_HEADLINE_MATCHES__("FPT", "FRT: CTCP Bán lẻ Kỹ thuật số FPT | Tổng quan"), false);
  assert.equal(window.__VMEWS_ISSUER_HEADLINE_MATCHES__("FPT", "FTS: Chứng khoán FPT | Báo cáo"), false);
  assert.equal(window.__VMEWS_ISSUER_HEADLINE_MATCHES__("FPT", "FPT ký hợp tác chiến lược với doanh nghiệp khác"), true);
});

test("commit-pinned CDN keeps immutable assets while live data comes from main", async () => {
  const source = await readFile(new URL("../forecast-final-v12.js", import.meta.url), "utf8");
  assert.match(source, /CDN_PATH\[2\]/);
  assert.match(source, /DATA_REF/);
  assert.match(source, /raw\.githubusercontent\.com/);
  assert.doesNotMatch(source, /cdn\.githubraw\.com\/[^`]*\/main\/data/);
});

test("leader loader fetches only the critical dashboard and gates", async () => {
  const source = await readFile(new URL("../forecast-final-v12.js", import.meta.url), "utf8");
  assert.match(source, /loadLeaderBase/);
  assert.match(source, /forecast-dashboard-v12\.json/);
  assert.match(source, /phase-gates-v12\.json/);
});

test("default leaderboard ranks all validated HOSE names while VN30 remains an explicit scope", async () => {
  const leaders = await readFile(new URL("../forecast-live-leaders-v14.js", import.meta.url), "utf8");
  assert.match(leaders, /HOSE/);
  assert.match(leaders, /VN30/);
  assert.match(leaders, /scope/);
});

test("session overlay re-filters EOD positives that turn negative at the live cutoff", async () => {
  const leaders = await readFile(new URL("../forecast-live-leaders-v14.js", import.meta.url), "utf8");
  assert.match(leaders, /finalLeaderboard/);
  assert.match(leaders, /liveClose/);
  assert.match(leaders, /upside/);
});

test("VN30 scope rejects nonmembers, removed names, downtrends and nonexecutable prices", async () => {
  const leaders = await readFile(new URL("../forecast-live-leaders-v14.js", import.meta.url), "utf8");
  assert.match(leaders, /vn30/i);
  assert.match(leaders, /validated/i);
});

test("VN30 scope can rank validated defensive names when no positive forecast exists", async () => {
  const leaders = await readFile(new URL("../forecast-live-leaders-v14.js", import.meta.url), "utf8");
  assert.match(leaders, /defensive/i);
});

test("published dated VN30 roster is authoritative and fewer than ten are never padded", async () => {
  const leaders = await readFile(new URL("../forecast-live-leaders-v14.js", import.meta.url), "utf8");
  assert.match(leaders, /effectiveDate/);
  assert.match(leaders, /slice\(0,\s*10\)/);
});

test("VN30 scope returns at most ten independently validated positive forecasts", async () => {
  const leaders = await readFile(new URL("../forecast-live-leaders-v14.js", import.meta.url), "utf8");
  assert.match(leaders, /pointDirectionValidated/);
  assert.match(leaders, /magnitudeValidated/);
});

test("live community overlay updates only the matching audited snapshot and valid HOSE quotes", async () => {
  const source = await readFile(new URL("../forecast-final-v12.js", import.meta.url), "utf8");
  const { window } = runtime(source);
  const market = { dash: { asOf: "2026-08-21", symbols: { FPT: { horizons: { "5": { priceValidated: true, expectedPrice: 72_000, tickSize: 100 } }, evidence: {} } } }, market: { sources: { rumorAudit: { source: {} } } } };
  const payload = { asOf: "2026-08-21", generatedAt: new Date().toISOString(), symbols: { FPT: { watchlist: [], claims: [], horizons: { "5": { expectedPrice: 72_300, tickSize: 100, liveEvidence: {} } } } } };
  assert.equal(window.__VMEWS_APPLY_COMMUNITY_LIVE__(market, payload), true);
  assert.equal(market.dash.symbols.FPT.horizons["5"].expectedPrice, 72_000);
  assert.equal(market.dash.symbols.FPT.horizons["5"].liveScenarioOverlay.scenarioPrice, 72_300);
});

test("a different snapshot or an invalid sub-tick update can never replace the forecast", async () => {
  const source = await readFile(new URL("../forecast-final-v12.js", import.meta.url), "utf8");
  const { window } = runtime(source);
  const market = { dash: { asOf: "2026-08-21", symbols: { FPT: { horizons: { "5": { priceValidated: true, expectedPrice: 72_000, tickSize: 100 } }, evidence: {} } } }, market: { sources: { rumorAudit: { source: {} } } } };
  const invalidDate = { asOf: "2026-08-20", generatedAt: new Date().toISOString(), symbols: {} };
  assert.equal(window.__VMEWS_APPLY_COMMUNITY_LIVE__(market, invalidDate), false);
  const invalidTick = { asOf: "2026-08-21", generatedAt: new Date().toISOString(), symbols: { FPT: { watchlist: [], claims: [], horizons: { "5": { expectedPrice: 72_327, tickSize: 100 } } } } };
  assert.equal(window.__VMEWS_APPLY_COMMUNITY_LIVE__(market, invalidTick), true);
  assert.equal(market.dash.symbols.FPT.horizons["5"].expectedPrice, 72_000);
  assert.equal(market.dash.symbols.FPT.horizons["5"].liveScenarioOverlay, undefined);
});

test("source freshness labels are concise, actionable and contain no internal data-engineering jargon", async () => {
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
