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
  }
  addEventListener(event, callback) { this.listeners.set(event, callback); }
  querySelector(selector) {
    if (!this.nodes.has(selector)) this.nodes.set(selector, new Element());
    return this.nodes.get(selector);
  }
  setAttribute() {}
  focus() {}
  append() {}
  scrollIntoView() {}
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

test("browser context includes observed holdings/news but withholds unvalidated probability", async () => {
  const source = await readFile(new URL("../solution-ai-v17.js", import.meta.url), "utf8");
  const nodes = new Map();
  const listeners = new Map();
  const document = {
    readyState: "loading",
    querySelector(selector) {
      if (selector.startsWith("meta")) return { content: "" };
      if (!nodes.has(selector)) nodes.set(selector, new Element(selector === "#symbol" ? "FPT" : ""));
      return nodes.get(selector);
    },
    addEventListener(name, callback) { listeners.set(name, callback); },
  };
  const window = {
    __VMEWS_LOAD_BASE__: async () => dashboard(),
    addEventListener() {},
  };
  const context = vm.createContext({
    window, document, location: { search: "?symbol=FPT", hostname: "cdn.githubraw.com", origin: "https://cdn.githubraw.com" },
    localStorage: { getItem: () => null }, URLSearchParams, URL, console,
  });
  vm.runInContext(source, context);
  listeners.get("DOMContentLoaded")();
  const evidence = await window.__SOLUTION_AI_BUILD_CONTEXT__();
  assert.equal(evidence.symbol, "FPT");
  assert.equal(evidence.fund.fundCount, 17);
  assert.equal(evidence.fund.holders[0].code, "ALPHA");
  assert.equal(evidence.news[0].title, "FPT công bố tăng trưởng");
  assert.equal(evidence.horizons["T+5"].probabilityUp, null);
  assert.equal(evidence.horizons["T+5"].liveEvidence.FUND, .002);
  assert.equal(evidence.validation.fundPriorIndependentlyBacktested, false);
});
