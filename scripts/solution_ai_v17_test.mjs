import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import handler from "../api/solution-ai.js";

const originalFetch = globalThis.fetch;
const originalKey = process.env.GEMINI_API_KEY;
const fallbackKeys = ["OPENAI_API_KEY", "GROQ_API_KEY", "XAI_API_KEY", "OPENROUTER_API_KEY", "OPENAI_BASE_URL", "SOLUTION_AI_PROVIDER_ORDER"];
const originalFallback = Object.fromEntries(fallbackKeys.map(key => [key, process.env[key]]));

function response() {
  return {
    headers: {}, code: null, payload: null, ended: false,
    setHeader(name, value) { this.headers[name] = value; },
    status(code) { this.code = code; return this; },
    json(payload) { this.payload = payload; return this; },
    end() { this.ended = true; return this; },
  };
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalKey === undefined) delete process.env.GEMINI_API_KEY;
  else process.env.GEMINI_API_KEY = originalKey;
  for (const key of fallbackKeys) {
    if (originalFallback[key] === undefined) delete process.env[key];
    else process.env[key] = originalFallback[key];
  }
});

test("health check reports configuration without exposing a Gemini key", async () => {
  delete process.env.GEMINI_API_KEY;
  const output = response();
  await handler({ method: "GET", headers: { origin: "https://cdn.githubraw.com" } }, output);
  assert.equal(output.code, 200);
  assert.equal(output.payload.brand, "SoluTION.AI");
  assert.equal(output.payload.ready, false);
  assert.equal(output.headers["Access-Control-Allow-Origin"], "https://cdn.githubraw.com");
  assert.equal(JSON.stringify(output.payload).includes("GEMINI_API_KEY"), false);
});

test("unconfigured public backend fails closed", async () => {
  delete process.env.GEMINI_API_KEY;
  const output = response();
  await handler({ method: "POST", headers: {}, body: {} }, output);
  assert.equal(output.code, 503);
  assert.equal(output.payload.error, "AI_NOT_CONFIGURED");
});

test("configured Gemini request receives only grounded current context", async () => {
  process.env.GEMINI_API_KEY = "server-only-test-secret";
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options, body: JSON.parse(options.body) };
    return { ok: true, json: async () => ({ outputs: [{ text: "FPT đang có tín hiệu quỹ hỗ trợ." }] }) };
  };
  const output = response();
  await handler({
    method: "POST", headers: { "x-forwarded-for": "203.0.113.17" },
    body: { question: "Phân tích FPT", context: { symbol: "FPT", close: 68300 }, history: [] },
  }, output);
  assert.equal(output.code, 200);
  assert.match(output.payload.answer, /tín hiệu quỹ/);
  assert.match(request.url, /interactions$/);
  assert.equal(request.options.headers["x-goog-api-key"], "server-only-test-secret");
  assert.match(request.body.input, /68300/);
  assert.equal(request.body.store, false);
  assert.equal(JSON.stringify(output.payload).includes("server-only-test-secret"), false);
});

test("invalid question and untrusted origin do not pass through", async () => {
  process.env.GEMINI_API_KEY = "server-only-test-secret";
  const output = response();
  await handler({
    method: "POST", headers: { origin: "https://example.invalid", "x-forwarded-for": "203.0.113.18" },
    body: { question: "x".repeat(1801), context: { symbol: "FPT" } },
  }, output);
  assert.equal(output.code, 400);
  assert.notEqual(output.headers["Access-Control-Allow-Origin"], "https://example.invalid");
});

test("malformed request bodies are rejected without leaking credentials", async () => {
  process.env.GEMINI_API_KEY = "server-only-test-secret";
  const output = response();
  await handler({ method: "POST", headers: { "x-forwarded-for": "203.0.113.19" }, body: "{" }, output);
  assert.equal(output.code, 400);
  assert.equal(output.payload.error, "INVALID_JSON");
  assert.equal(JSON.stringify(output.payload).includes("server-only-test-secret"), false);
});

test("a Gemini quota failure automatically fails over to another configured provider", async () => {
  process.env.GEMINI_API_KEY = "gemini-server-only-secret";
  process.env.OPENAI_API_KEY = "openai-server-only-secret";
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options, body: JSON.parse(options.body) });
    if (url.includes("generativelanguage.googleapis.com")) return { ok: false, status: 429 };
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: "FPT: dữ liệu đã kiểm chứng vẫn là cơ sở phân tích." } }] }) };
  };
  const output = response();
  await handler({ method: "POST", headers: { "x-forwarded-for": "203.0.113.45" }, body: {
    question: "Phân tích FPT", context: { symbol: "FPT", close: 71800 },
    sources: [{ title: "Công bố doanh nghiệp", url: "https://fpt.com/vi/nha-dau-tu" }, { title: "unsafe", url: "javascript:alert(1)" }],
  } }, output);
  assert.equal(output.code, 200);
  assert.equal(output.payload.provider, "OpenAI");
  assert.equal(output.payload.failoverUsed, true);
  assert.deepEqual(output.payload.unavailableProviders, ["Gemini"]);
  assert.equal(requests.length, 2);
  assert.equal(requests[1].options.headers.Authorization, "Bearer openai-server-only-secret");
  assert.match(requests[1].body.messages[1].content, /71800/);
  assert.match(requests[1].body.messages[1].content, /Công bố doanh nghiệp/);
  assert.doesNotMatch(requests[1].body.messages[1].content, /javascript:/);
  assert.equal(JSON.stringify(output.payload).includes("server-only-secret"), false);
});

test("a non-Gemini provider can serve as the only configured backend", async () => {
  delete process.env.GEMINI_API_KEY;
  process.env.GROQ_API_KEY = "groq-private-secret";
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({ choices: [{ message: { content: "Phân tích dự phòng hoạt động." } }] }) });
  const health = response();
  await handler({ method: "GET", headers: {} }, health);
  assert.equal(health.payload.ready, true);
  assert.equal(health.payload.provider, "Groq");
  assert.equal(JSON.stringify(health.payload).includes("groq-private-secret"), false);
  const output = response();
  await handler({ method: "POST", headers: { "x-forwarded-for": "203.0.113.46" }, body: { question: "Phân tích", context: { symbol: "FPT" } } }, output);
  assert.equal(output.code, 200);
  assert.equal(output.payload.provider, "Groq");
});
