import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";

class Element {
  constructor(value = "") {
    this.value = value;
    this.listeners = new Map();
    this.classList = { add() {}, remove() {}, toggle() {} };
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
  append(...children) {
    for (const child of children) if (child && typeof child === "object") child.parentElement = this;
    this.children.push(...children);
    this.textContent += children.map(child => typeof child === "string" ? child : child?.textContent || "").join("");
  }
  scrollIntoView() {}
  remove() {
    this.removed = true;
    if (this.parentElement) {
      this.parentElement.children = this.parentElement.children.filter(child => child !== this);
    }
  }
}

function dashboard() {
  const fpt = {
    symbol: "FPT", date: "2026-08-21", close: 72000, sector: "Công nghệ", riskStatus: "GREEN",
    dailyVolatility: .023,
    horizons: {
      "5": {
        priceValidated: true, expectedPrice: 73000, expectedReturn: .0138,
        q20Price: 70000, q80Price: 75000, directionValidated: false, probUp: .81,
        expectedAbsReturn: .021, bearScenarioPrice: 70500, bullScenarioPrice: 73600, magnitudeValidated: true,
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
    evidence: { decisionRecent: [
      { title: "FPT công bố tăng trưởng", publisher: "Nguồn chính thức", label: "POS", link: "https://fpt.com/vi/nha-dau-tu" },
      { title: "FRT: CTCP Bán lẻ Kỹ thuật số FPT | Tổng quan", publisher: "Sai mã", label: "POS", link: "https://example.org/frt" },
    ] },
  };
  return {
    dash: {
      symbols: { FPT: fpt }, marketForecast: { decisionAt: "2026-08-23T10:00:00+07:00" },
      charts: { FPT: Array.from({ length: 65 }, (_, index) => ({
        date: `2026-06-${String(index + 1).padStart(2, "0")}`,
        rawClose: 68000 + index * 70 + (index % 4) * 45,
        close: 68000 + index * 70 + (index % 4) * 45,
        volume: 900000 + index * 12000 + (index % 5) * 40000,
      })) },
    },
    model: {
      horizons: { "5": { priceStatus: "PASS", directionStatus: "REVIEW", sealedAudit: { n: 44000 } } },
      governance: { livePriorIndependentlyBacktested: false },
    },
  };
}

async function setup(fetch = async () => { throw new Error("Unexpected network request"); }, options = {}) {
  const source = await readFile(new URL("../solution-ai-v17.js", import.meta.url), "utf8");
  const nodes = new Map();
  const listeners = new Map();
  const session = new Map();
  const persistent = [];
  const stored = new Map(Object.entries(options.storage || {}));
  const document = {
    readyState: "loading",
    querySelector(selector) {
      if (selector.startsWith("meta")) return null;
      if (!nodes.has(selector)) nodes.set(selector, new Element(selector === "#symbol" ? "FPT" : ""));
      return nodes.get(selector);
    },
    addEventListener(name, callback) { listeners.set(name, callback); },
    createElement() { return new Element(); },
    createTextNode(value) {
      const node = new Element();
      node.textContent = String(value);
      return node;
    },
  };
  const window = {
    __VMEWS_LOAD_BASE__: async () => dashboard(),
    __VMEWS_BUILD_LEADERBOARD__: base => [{
      symbol: "FPT", close: 72000, target: 73000, upside: .0138,
      forecast: base.dash.symbols.FPT.horizons["5"],
    }],
    addEventListener() {},
    setTimeout() { return 1; },
  };
  const context = vm.createContext({
    window, document, location: { search: "?symbol=FPT", hostname: "cdn.githubraw.com", origin: "https://cdn.githubraw.com" },
    localStorage: {
      getItem: key => stored.get(key) || null,
      setItem: (key, value) => { stored.set(key, value); persistent.push([key, value]); },
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

async function settle() {
  await new Promise(resolve => setTimeout(resolve, 15));
}

function textOf(node) {
  return [node?.textContent || "", ...(node?.children || []).map(textOf)].join(" ");
}

test("browser context includes observed holdings/news but withholds unvalidated probability", async () => {
  const { window } = await setup();
  const evidence = await window.__SOLUTION_AI_BUILD_CONTEXT__();
  assert.equal(evidence.symbol, "FPT");
  assert.equal(evidence.fund.fundCount, 17);
  assert.equal(evidence.fund.holders[0].code, "ALPHA");
  assert.equal(evidence.news[0].title, "FPT công bố tăng trưởng");
  assert.equal(evidence.news.length, 1);
  assert.equal(evidence.news[0].url, "https://fpt.com/vi/nha-dau-tu");
  assert.equal(evidence.horizons["T+5"].probabilityUp, null);
  assert.equal(evidence.horizons["T+5"].expectedAbsReturn, .021);
  assert.equal(evidence.horizons["T+5"].bearScenarioPrice, 70500);
  assert.equal(evidence.horizons["T+5"].bullScenarioPrice, 73600);
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
  await settle();

  assert.equal(requests.length, 2);
  assert.equal(requests[1].url, "https://generativelanguage.googleapis.com/v1beta/interactions");
  const payload = JSON.parse(requests[1].options.body);
  assert.equal(payload.model, "gemini-3.5-flash");
  assert.equal(payload.store, false);
  assert.equal(payload.generation_config.max_output_tokens, 4200);
  assert.equal(payload.generation_config.thinking_level, "high");
  assert.deepEqual(payload.tools, [{ type: "google_search" }, { type: "url_context" }]);
  assert.ok(payload.input.indexOf("Danh mục quỹ FPT ảnh hưởng thế nào?") < payload.input.indexOf('"fundCount":17'));
  assert.match(payload.input, /"fundCount":17/);
  assert.match(payload.input, /"probabilityUp":null/);
  assert.match(payload.system_instruction, /không tự tạo giá/);
  assert.match(payload.system_instruction, /xác suất hướng chưa được kiểm định/);
  assert.match(payload.system_instruction, /Google Search/);
  assert.match(payload.system_instruction, /URL Context/);
  assert.match(payload.system_instruction, /vĩ mô/);
  assert.equal(payload.input.includes(secret), false);
  assert.equal(requests[1].url.includes(secret), false);
  assert.match(nodes.get("#solutionAiStatus").textContent, /Gemini/);
});

test("current Gemini interaction steps expose grounded answers and safe source links", async () => {
  const requests = [];
  const { nodes } = await setup(async (url, options) => {
    requests.push({ url, options });
    if (url.includes("/models?")) {
      return { ok: true, status: 200, json: async () => ({ models: [{ name: "models/gemini-3.7-flash", supportedGenerationMethods: ["generateContent"] }] }) };
    }
    if (url.includes("api.gdeltproject.org")) {
      return { ok: true, status: 200, json: async () => ({ articles: [] }) };
    }
    return {
      ok: true, status: 200,
      json: async () => ({
        steps: [
          { type: "google_search_call", arguments: { queries: ["FPT triển vọng vĩ mô 2026"] } },
          { type: "google_search_result", result: [{}] },
          { type: "model_output", content: [{
            type: "text", text: "FPT có forecast T+5 73.000; lãi suất, nhu cầu chuyển đổi số và tỷ giá là các yếu tố cần đối chiếu.",
            annotations: [
              { type: "url_citation", url: "https://fpt.com/vi/nha-dau-tu", title: "Công bố FPT" },
              { type: "url_citation", url: "javascript:alert(1)", title: "unsafe" },
            ],
          }] },
        ],
      }),
    };
  });
  nodes.get("#solutionAiKey").value = "AQ.synthetic-search-grounding-secret-123456789";
  await nodes.get("#solutionAiRetry").listeners.get("click")();
  nodes.get("#solutionAiInput").value = "Tình hình vĩ mô và triển vọng ngành của FPT ra sao?";

  nodes.get("#solutionAiForm").listeners.get("submit")({ preventDefault() {} });
  await settle();

  const answer = nodes.get("#solutionAiMessages").children.at(-1);
  assert.match(textOf(answer), /chuyển đổi số/);
  const references = answer.children.find(child => child.className === "aiSources");
  assert.equal(references.children.length, 1);
  assert.equal(references.children[0].href, "https://fpt.com/vi/nha-dau-tu");
  assert.equal(references.children[0].rel, "noopener noreferrer");
  assert.match(nodes.get("#solutionAiStatus").textContent, /nghiên cứu web/);
  assert.equal(requests.length, 3);
  assert.equal(requests[1].options.headers, undefined);
});

test("unavailable Google Search falls back to URL Context and open sources without canned text", async () => {
  const requests = [];
  const secret = "AQ.synthetic-search-retry-secret-123456789";
  const { nodes } = await setup(async (url, options) => {
    requests.push({ url, options });
    if (url.includes("/models?")) {
      return { ok: true, status: 200, json: async () => ({ models: [{ name: "models/gemini-3.5-flash", supportedGenerationMethods: ["generateContent"] }] }) };
    }
    if (url.includes("api.gdeltproject.org")) {
      return { ok: true, status: 200, json: async () => ({ articles: [{
        title: "Kinh tế Việt Nam và điều hành lãi suất", url: "https://example.org/viet-nam-lai-suat", domain: "example.org", seendate: "20260822T110000Z",
      }] }) };
    }
    const payload = JSON.parse(options.body);
    if (payload.tools?.some(tool => tool.type === "google_search")) {
      return { ok: false, status: 403, json: async () => ({ error: { message: "Google Search requires billing" } }) };
    }
    return { ok: true, status: 200, json: async () => ({ steps: [
      { type: "url_context_result", result: [{ url: "https://example.org/viet-nam-lai-suat" }] },
      { type: "model_output", content: [{ type: "text", text: "Lãi suất và triển vọng kinh tế được đối chiếu từ nguồn công khai." }] },
    ] }) };
  });
  nodes.get("#solutionAiKey").value = secret;
  await nodes.get("#solutionAiRetry").listeners.get("click")();
  nodes.get("#solutionAiInput").value = "Đánh giá vĩ mô hiện nay";

  nodes.get("#solutionAiForm").listeners.get("submit")({ preventDefault() {} });
  await settle();

  assert.equal(requests.length, 4);
  assert.match(requests[1].url, /api\.gdeltproject\.org/);
  assert.equal(requests[1].options.headers, undefined);
  assert.equal(requests[1].url.includes(secret), false);
  assert.deepEqual(JSON.parse(requests[2].options.body).tools, [{ type: "google_search" }, { type: "url_context" }]);
  assert.deepEqual(JSON.parse(requests[3].options.body).tools, [{ type: "url_context" }]);
  assert.match(JSON.parse(requests[3].options.body).input, /Kinh tế Việt Nam và điều hành lãi suất/);
  assert.doesNotMatch(JSON.parse(requests[3].options.body).input, /"fundCount":17/);
  assert.match(nodes.get("#solutionAiConnectionState").textContent, /nguồn mở/);
  assert.match(nodes.get("#solutionAiStatus").textContent, /nghiên cứu web/);
  const answer = nodes.get("#solutionAiMessages").children.at(-1);
  assert.ok(answer.children.some(child => /triển vọng kinh tế/.test(child.textContent)));
  const references = answer.children.find(child => child.className === "aiSources");
  assert.equal(references.children[0].href, "https://example.org/viet-nam-lai-suat");
});

test("general questions reach Gemini without dragging the open stock snapshot into the prompt", async () => {
  const requests = [];
  const { nodes } = await setup(async (url, options) => {
    requests.push({ url, options });
    if (url.includes("/models?")) {
      return { ok: true, status: 200, json: async () => ({ models: [{ name: "models/gemini-3.7-flash", supportedGenerationMethods: ["generateContent"] }] }) };
    }
    return { ok: true, status: 200, json: async () => ({ output_text: "Machine learning học từ dữ liệu; deep learning sử dụng mạng nơ-ron nhiều lớp." }) };
  });
  nodes.get("#solutionAiKey").value = "AQ.synthetic-general-purpose-secret-123456789";
  await nodes.get("#solutionAiRetry").listeners.get("click")();
  nodes.get("#solutionAiInput").value = "Machine learning khác deep learning thế nào?";

  nodes.get("#solutionAiForm").listeners.get("submit")({ preventDefault() {} });
  await settle();

  assert.equal(requests.length, 3);
  assert.match(requests[1].url, /api\.gdeltproject\.org/);
  const payload = JSON.parse(requests[2].options.body);
  assert.match(payload.input, /Machine learning khác deep learning thế nào/);
  assert.match(payload.input, /CÂU HỎI TỰ DO/);
  assert.doesNotMatch(payload.input, /"fundCount"|"horizons"|"close":72000/);
  const answer = nodes.get("#solutionAiMessages").children.at(-1);
  assert.ok(answer.children.some(child => /mạng nơ-ron/.test(child.textContent)));
});

test("a supplied public URL is offered to Gemini URL Context with no API key sent to open news", async () => {
  const requests = [];
  const secret = "AQ.synthetic-explicit-url-secret-123456789";
  const article = "https://example.org/research/fpt-results";
  const { nodes } = await setup(async (url, options) => {
    requests.push({ url, options });
    if (url.includes("/models?")) return { ok: true, status: 200, json: async () => ({ models: [{ name: "models/gemini-3.7-flash" }] }) };
    if (url.includes("api.gdeltproject.org")) return { ok: true, status: 200, json: async () => ({ articles: [] }) };
    return { ok: true, status: 200, json: async () => ({ steps: [
      { type: "url_context_result", result: [{ url: article }] },
      { type: "model_output", content: [{ type: "text", text: "Bài viết cần được đối chiếu với công bố của doanh nghiệp." }] },
    ] }) };
  });
  nodes.get("#solutionAiKey").value = secret;
  await nodes.get("#solutionAiRetry").listeners.get("click")();
  nodes.get("#solutionAiInput").value = `Đọc và phân tích nguồn này: ${article}`;

  nodes.get("#solutionAiForm").listeners.get("submit")({ preventDefault() {} });
  await settle();

  const openNews = requests.find(request => request.url.includes("api.gdeltproject.org"));
  assert.equal(openNews.options.headers, undefined);
  assert.equal(openNews.url.includes(secret), false);
  const provider = requests.find(request => request.url.endsWith("/interactions"));
  const payload = JSON.parse(provider.options.body);
  assert.match(payload.input, /https:\/\/example\.org\/research\/fpt-results/);
  assert.ok(payload.tools.some(tool => tool.type === "url_context"));
});

test("a Gemini provider outage continues with the audited snapshot and says what failed", async () => {
  const { nodes } = await setup(async (url) => {
    if (url.includes("/models?")) return { ok: true, status: 200, json: async () => ({ models: [{ name: "models/gemini-3.7-flash" }] }) };
    return { ok: false, status: 503, json: async () => ({ error: { message: "provider unavailable" } }) };
  });
  nodes.get("#solutionAiKey").value = "AQ.synthetic-provider-outage-secret-123456789";
  await nodes.get("#solutionAiRetry").listeners.get("click")();
  nodes.get("#solutionAiInput").value = "Phân tích danh mục quỹ FPT";

  nodes.get("#solutionAiForm").listeners.get("submit")({ preventDefault() {} });
  await settle();

  const answer = nodes.get("#solutionAiMessages").children.at(-1);
  assert.match(answer.className, /aiAssistant/);
  assert.ok(answer.children.some(child => /tạm thời gián đoạn/.test(child.textContent)));
  assert.ok(answer.children.some(child => /72\.000/.test(child.textContent)));
  assert.match(nodes.get("#solutionAiStatus").textContent, /dự phòng/);
});

test("Gemini automatically continues with an available backup model", async () => {
  const requests = [];
  const { nodes } = await setup(async (url, options) => {
    requests.push({ url, options });
    if (url.includes("/models?")) {
      return {
        ok: true, status: 200,
        json: async () => ({ models: [
          { name: "models/gemini-3.7-flash", supportedGenerationMethods: ["generateContent"] },
          { name: "models/gemini-3.5-flash", supportedGenerationMethods: ["generateContent"] },
        ] }),
      };
    }
    const payload = JSON.parse(options.body);
    if (payload.model === "gemini-3.7-flash") {
      return { ok: false, status: 503, json: async () => ({ error: { message: "temporary" } }) };
    }
    return { ok: true, status: 200, json: async () => ({ output_text: "FPT có forecast T+5 73.000; mô hình dự phòng đã tiếp tục phân tích." }) };
  });
  nodes.get("#solutionAiKey").value = "AQ.synthetic-model-failover-secret-123456789";
  await nodes.get("#solutionAiRetry").listeners.get("click")();
  nodes.get("#solutionAiInput").value = "Danh mục quỹ của mã đang xem tác động thế nào?";

  nodes.get("#solutionAiForm").listeners.get("submit")({ preventDefault() {} });
  await settle();

  const providerCalls = requests.filter(request => request.url.endsWith("/interactions"));
  assert.equal(providerCalls.length, 2);
  assert.equal(JSON.parse(providerCalls[0].options.body).model, "gemini-3.7-flash");
  assert.equal(JSON.parse(providerCalls[1].options.body).model, "gemini-3.5-flash");
  const answer = nodes.get("#solutionAiMessages").children.at(-1);
  assert.match(textOf(answer), /dự phòng đã tiếp tục/);
  assert.match(nodes.get("#solutionAiStatus").textContent, /Gemini/);
});

test("Gemini quota exhaustion is not retried repeatedly and transfers safely to the configured backend", async () => {
  const requests = [];
  const secret = "AQ.synthetic-quota-circuit-breaker-secret-123456789";
  const address = "https://ai.example.org/api/solution-ai";
  const { nodes } = await setup(async (url, options) => {
    requests.push({ url, options });
    if (url.includes("/models?")) return { ok: true, status: 200, json: async () => ({ models: [
      { name: "models/gemini-3.7-flash" }, { name: "models/gemini-3.5-flash" },
    ] }) };
    if (url.endsWith("/interactions")) return { ok: false, status: 429, json: async () => ({ error: { message: "quota exhausted" } }) };
    assert.equal(url, address);
    return { ok: true, status: 200, json: async () => ({ provider: "Groq", answer: "FPT có forecast T+5 73.000; nhà cung cấp dự phòng tiếp tục phân tích." }) };
  }, { storage: { vmews_solution_ai_endpoint: address } });
  nodes.get("#solutionAiKey").value = secret;
  await nodes.get("#solutionAiRetry").listeners.get("click")();
  nodes.get("#solutionAiInput").value = "Danh mục quỹ FPT ảnh hưởng thế nào?";

  nodes.get("#solutionAiForm").listeners.get("submit")({ preventDefault() {} });
  await settle();

  const direct = requests.filter(request => request.url.endsWith("/interactions"));
  const fallback = requests.filter(request => request.url === address);
  assert.equal(direct.length, 1);
  assert.equal(fallback.length, 1);
  assert.equal(JSON.stringify(fallback[0].options).includes(secret), false);
  assert.match(textOf(nodes.get("#solutionAiMessages").children.at(-1)), /nhà cung cấp dự phòng/);
  assert.match(nodes.get("#solutionAiStatus").textContent, /Groq/);
});

test("questions requiring outside information request a real Gemini connection instead of canned analysis", async () => {
  const { nodes } = await setup();
  nodes.get("#solutionAiInput").value = "Tình hình kinh tế vĩ mô hiện nay như thế nào?";

  nodes.get("#solutionAiForm").listeners.get("submit")({ preventDefault() {} });
  await settle();

  const answer = nodes.get("#solutionAiMessages").children.at(-1);
  assert.match(textOf(answer), /Kết nối Gemini/);
  assert.doesNotMatch(textOf(answer), /17 quỹ đang nắm giữ/);
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

test("Gemini Web handoff carries the full EOD decision state and redacts credentials", async () => {
  const { source, window, nodes } = await setup();
  const context = await window.__SOLUTION_AI_BUILD_CONTEXT__();
  nodes.get("#solutionAiInput").value = "Tôi nên chú ý điều gì ở FPT? AIza123456789012345678901234567890";
  const payload = window.__SOLUTION_AI_GEMINI_HANDOFF_PAYLOAD__("", context);
  const prompt = window.__SOLUTION_AI_BUILD_GEMINI_HANDOFF__("", context);
  assert.equal(payload.handoff.version, "VMEWS-GEMINI-HANDOFF-23.0");
  assert.equal(payload.handoff.dataMode, "EOD");
  assert.equal(payload.forecast.symbol, "FPT");
  assert.equal(payload.forecast.sealedCoreClose, 72000);
  assert.equal(payload.forecast.marketRanking.canonicalVisibleRank, 1);
  assert.equal(payload.forecast.topHOSECandidates[0].symbol, "FPT");
  assert.equal(payload.evidence.fund.fundCount, 17);
  assert.equal(payload.evidence.flow.foreign.net5, 40);
  assert.equal(payload.evidence.financial.profitGrowth, .2);
  assert.equal(payload.evidence.issuerNews[0].title, "FPT công bố tăng trưởng");
  assert.match(payload.userIntent.currentQuestion, /Tôi nên chú ý/);
  assert.doesNotMatch(JSON.stringify(payload), /AIza123456789012345678901234567890/);
  assert.match(prompt, /technical/);
  assert.match(prompt, /dòng tiền/);
  assert.match(prompt, /ranking HOSE/);
  assert.match(prompt, /CONTINUE_CURRENT_SESSION/);
  assert.match(source, /state\.messages \|\| \[\]/);
  assert.match(source, /Tiếp tục trên Gemini Web/);
});

test("Gemini Web handoff distinguishes a fresh SESSION quote from the sealed EOD forecast", async () => {
  const { window } = await setup();
  window.__VMEWS_SESSION__ = {
    status: "PASS", session: "PM", cutoffAt: "2026-08-25T14:30:00+07:00",
    symbols: [{ symbol: "FPT", quoteCurrent: true, freshForCutoff: true, liveClose: 72500, change: .0069, updateAt: "2026-08-25T14:31:00+07:00", updateMode: "delayed_streaming_900" }],
  };
  const context = await window.__SOLUTION_AI_BUILD_CONTEXT__();
  const payload = window.__SOLUTION_AI_GEMINI_HANDOFF_PAYLOAD__("Đánh giá lại khoảng cách tới target", context);
  assert.equal(payload.handoff.dataMode, "SESSION");
  assert.equal(payload.forecast.sealedCoreClose, 72000);
  assert.equal(payload.forecast.activePrice, 72500);
  assert.equal(payload.forecast.session.liveClose, 72500);
  assert.equal(payload.forecast.session.sourceMode, "delayed_streaming_900");
  assert.equal(payload.forecast.horizons["T+5"].price, 73000);
  assert.ok(Math.abs(payload.forecast.horizons["T+5"].remainingReturnFromSession - (73000 / 72500 - 1)) < 1e-12);
  assert.match(payload.userIntent.currentQuestion, /khoảng cách tới target/);
});

test("technical context carries real RSI MACD OBV and volume evidence", async () => {
  const { window } = await setup();
  const context = await window.__SOLUTION_AI_BUILD_CONTEXT__();
  assert.ok(context.technical.rsi14 >= 0 && context.technical.rsi14 <= 100);
  assert.equal(Number.isFinite(context.technical.macd), true);
  assert.equal(Number.isFinite(context.technical.macdHistogram), true);
  assert.equal(Number.isFinite(context.technical.obv), true);
  assert.equal(Number.isFinite(context.technical.obvChange5), true);
  assert.equal(context.technical.volumeSeriesUsesObservedMarketVolume, true);
  assert.ok(context.technical.volumeRatio20 > 0);
});

test("financial deep-dive routes to research and local wording stays decision-focused", async () => {
  const { window, source } = await setup();
  const context = await window.__SOLUTION_AI_BUILD_CONTEXT__();
  const intent = window.__SOLUTION_AI_RESEARCH_INTENT__("Đọc BCTC mới nhất, phân tích dòng tiền và nợ vay của FPT", context);
  assert.equal(intent.useSnapshot, true);
  assert.equal(intent.shouldSearch, true);
  assert.equal(intent.mode, "FORECAST_RESEARCH");
  const fundAnswer = window.__SOLUTION_AI_LOCAL_ANALYSIS__("Phân tích quỹ và danh mục FPT", context);
  assert.match(fundAnswer, /Quỹ nắm giữ/);
  assert.doesNotMatch(fundAnswer, /không phải tỷ lệ sở hữu doanh nghiệp|không chứng minh quỹ đang mua|chưa điều chỉnh giá dự báo trung tâm/i);
  const technical = window.__SOLUTION_AI_LOCAL_ANALYSIS__("Phân tích đầy đủ kỹ thuật FPT", context);
  assert.match(technical, /RSI14/);
  assert.match(technical, /OBV/);
  assert.match(technical, /MACD/);
  assert.doesNotMatch(source, /Tỷ trọng quỹ là tỷ trọng trong danh mục từng quỹ, không phải tỷ lệ sở hữu doanh nghiệp/);
});
