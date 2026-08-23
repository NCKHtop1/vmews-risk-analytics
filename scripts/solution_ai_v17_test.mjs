import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import handler from "../api/solution-ai.js";

const originalFetch = globalThis.fetch;
const originalKey = process.env.GEMINI_API_KEY;

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
