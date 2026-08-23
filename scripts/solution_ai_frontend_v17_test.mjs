import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";

class Element {
  constructor(value = "") {
    this.value = value;
    this.listeners = new Map();
    this.classList = { add() {}, remove() {} };
    this.nodes = new Map();
    this.children = [];
    this.hidden = false;
    this.textContent = "";
  }
  addEventListener(event, callback) { this.listeners.set(event, callback); }
  querySelector(selector) {
    if (!this.nodes.has(selector)) this.nodes.set(selector, new Element());
    return this.nodes.get(selector);
  }
  setAttribute() {}
  focus() {}
  append(...children) { this.children.push(...children); }
  scrollIntoView() {}
  remove() { this.removed = true; }
}

function dashboard() {
  const fpt = {
    symbol: "FPT", date: "2026-08-21", close: 72000, sector: "Công nghệ", riskStatus: "GREEN",
    dailyVolatility: .023,
    horizons: {
      "5": {
        priceValidated: true, expectedPrice: 73000, expectedReturn: .0138,
        q20Price: 70000, q80Price: 75000, directionValidated: false, probUp: .81,
        expertContributions: { FUND: .002, EVENT: .001 },
        liveEvidence: { components: { FUND: .002, EVENT: .001 } }, targetDate: "2026-08-28",
      },
    },
    fundContext: {
      available: true, fundCount: 17, averageReportedWeight: .04, weightedNavMomentum20: .03,
      usedByForecast: true, asOf: "2026-08-23",
      holdings: [{ fundCode: "ALPHA", fundName: "Alpha Fund", weight: .08 }],
    },
    flow: { foreign: { available: true, latestDate: "2026-08-14", ageSessions: 5, net1: 10, net5: 40 } },
    fundamentalContext: { available: true, profitQoQ: .2, revenueQoQ: .1, ratios: { pe: { value: 14 } } },
    evidence: { decisionRecent: [{ title: "FPT công bố tăng trưởng", publisher: "Nguồn chính thức", label: "POS" }] },
  };
  return {
    dash: { symbols: { FPT: fpt }, marketForecast: { decisionAt: "2026-08-23T10:00:00+07:00" } },
    model: {
      horizons: { "5": { priceStatus: "PASS", directionStatus: "REVIEW", sealedAudit: { n: 44000 } } },
      governance: { livePriorIndependentlyBacktested: false },
    },
  };
}

async function setup(fetch = async () => { throw new Error("Unexpected network request"); }) {
  const source = await readFile(new URL("../solution-ai-v17.js", import.meta.url), "utf8");
  const nodes = new Map();
  const listeners = new Map();
  const session = new Map();
  const persistent = [];
  const document = {
    readyState: "loading",
    querySelector(selector) {
      if (selector.startsWith("meta")) return null;
      if (!nodes.has(selector)) nodes.set(selector, new Element(selector === "#symbol" ? "FPT" : ""));
      return nodes.get(selector);
    },
    addEventListener(name, callback) { listeners.set(name, callback); },
    createElement() { return new Element(); },
  };
  const window = {
    __VMEWS_LOAD_BASE__: async () => dashboard(),
    __VMEWS_BUILD_LEADERBOARD__: base => [{
      symbol: "FPT", close: 72000, target: 73000, upside: .0138,
      forecast: base.dash.symbols.FPT.horizons["5"],
    }],
    addEventListener() {},
  };
  const context = vm.createContext({
    window, document, location: { search: "?symbol=FPT", hostname: "cdn.githubraw.com", origin: "https://cdn.githubraw.com" },
    localStorage: {
      getItem: () => null,
      setItem: (key, value) => persistent.push([key, value]),
    },
    sessionStorage: {
      getItem: key => session.get(key) || null,
      setItem: (key, value) => session.set(key, value),
      removeItem: key => session.delete(key),
    },
    fetch, URLSearchParams, URL, console,
  });
  vm.runInContext(source, context);
  listeners.get("DOMContentLoaded")();
  return { source, nodes, session, persistent, window };
}

test("browser context includes observed holdings/news but withholds unvalidated probability", async () => {
  const { window } = await setup();
  const evidence = await window.__SOLUTION_AI_BUILD_CONTEXT__();
  assert.equal(evidence.symbol, "FPT");
  assert.equal(evidence.fund.fundCount, 17);
  assert.equal(evidence.fund.holders[0].code, "ALPHA");
  assert.equal(evidence.news[0].title, "FPT công bố tăng trưởng");
  assert.equal(evidence.horizons["T+5"].probabilityUp, null);
  assert.equal(evidence.horizons["T+5"].liveEvidence.FUND, .002);
  assert.equal(evidence.validation.fundPriorIndependentlyBacktested, false);
  assert.equal(evidence.topMovers.length, 1);
  assert.equal(evidence.topMovers[0].symbol, "FPT");
  assert.ok(evidence.topMovers[0].forecast > evidence.topMovers[0].close);
});

test("CDN connects directly to Google and keeps the key only in tab session storage", async () => {
  const requests = [];
  const secret = "AQ.synthetic-browser-session-secret-123456789";
  const { nodes, session, persistent } = await setup(async (url, options) => {
    requests.push({ url, options });
    return {
      ok: true, status: 200,
      json: async () => ({ models: [{ name: "models/gemini-3.7-flash", supportedGenerationMethods: ["generateContent"] }] }),
    };
  });
  nodes.get("#solutionAiKey").value = secret;

  assert.equal(await nodes.get("#solutionAiRetry").listeners.get("click")(), true);

  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "https://generativelanguage.googleapis.com/v1beta/models?pageSize=100");
  assert.equal(requests[0].options.headers["x-goog-api-key"], secret);
  assert.equal(requests[0].url.includes(secret), false);
  assert.equal(session.get("vmews_solution_ai_browser_session"), secret);
  assert.equal(persistent.length, 0);
  assert.equal(nodes.get("#solutionAiKey").value, "");
  assert.equal(nodes.get("#solutionAiDisconnect").hidden, false);
  assert.match(nodes.get("#solutionAiConnectionState").textContent, /gemini-3\.7-flash/);
});

test("direct Gemini receives audited context and guardrails without exposing the key in prompts", async () => {
  const requests = [];
  const secret = "AQ.synthetic-grounded-context-secret-123456789";
  const { nodes } = await setup(async (url, options) => {
    requests.push({ url, options });
    if (url.includes("/models?")) {
      return {
        ok: true, status: 200,
        json: async () => ({ models: [{ name: "models/gemini-3.5-flash", supportedGenerationMethods: ["generateContent"] }] }),
      };
    }
    return { ok: true, status: 200, json: async () => ({ output_text: "FPT có 17 quỹ đang nắm giữ." }) };
  });
  nodes.get("#solutionAiKey").value = secret;
  await nodes.get("#solutionAiRetry").listeners.get("click")();
  nodes.get("#solutionAiInput").value = "Danh mục quỹ FPT ảnh hưởng thế nào?";

  nodes.get("#solutionAiForm").listeners.get("submit")({ preventDefault() {} });
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(requests.length, 2);
  assert.equal(requests[1].url, "https://generativelanguage.googleapis.com/v1beta/interactions");
  const payload = JSON.parse(requests[1].options.body);
  assert.equal(payload.model, "gemini-3.5-flash");
  assert.equal(payload.store, false);
  assert.match(payload.input, /"fundCount":17/);
  assert.match(payload.input, /"probabilityUp":null/);
  assert.match(payload.system_instruction, /không tự tạo giá/);
  assert.match(payload.system_instruction, /xác suất hướng chưa được kiểm định/);
  assert.equal(payload.input.includes(secret), false);
  assert.equal(requests[1].url.includes(secret), false);
  assert.match(nodes.get("#solutionAiStatus").textContent, /Gemini/);
});

test("rejected Gemini key is never stored", async () => {
  const { nodes, session, persistent } = await setup(async () => ({
    ok: false, status: 401, json: async () => ({ error: { message: "unauthorized" } }),
  }));
  nodes.get("#solutionAiKey").value = "AQ.synthetic-rejected-key-123456789";

  assert.equal(await nodes.get("#solutionAiRetry").listeners.get("click")(), false);
  assert.equal(session.size, 0);
  assert.equal(persistent.length, 0);
  assert.match(nodes.get("#solutionAiConnectionState").textContent, /không hợp lệ/);
});

test("disconnect removes the Gemini key and restores local-only analysis", async () => {
  const { nodes, session } = await setup(async () => ({
    ok: true, status: 200,
    json: async () => ({ models: [{ name: "models/gemini-3.7-flash", supportedGenerationMethods: ["generateContent"] }] }),
  }));
  nodes.get("#solutionAiKey").value = "AQ.synthetic-disconnect-secret-123456789";
  await nodes.get("#solutionAiRetry").listeners.get("click")();

  nodes.get("#solutionAiDisconnect").listeners.get("click")();

  assert.equal(session.size, 0);
  assert.equal(nodes.get("#solutionAiDisconnect").hidden, true);
  assert.match(nodes.get("#solutionAiConnectionState").textContent, /Đã xóa khóa/);
  assert.match(nodes.get("#solutionAiStatus").textContent, /dữ liệu hiện có/);
});
