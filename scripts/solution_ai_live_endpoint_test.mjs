import assert from "node:assert/strict";
import { test } from "node:test";
import handler from "../api/solution-ai-live.js";

function responseRecorder() {
  const headers = {};
  return {
    headers,
    statusCode: 200,
    body: null,
    setHeader(name, value) { headers[name] = value; },
    status(code) { this.statusCode = code; return this; },
    json(payload) { this.body = payload; return this; },
    end() { return this; },
  };
}

test("SoluTION live endpoint returns direct TradingView price", async () => {
  const original = global.fetch;
  global.fetch = async url => {
    assert.match(String(url), /scanner\.tradingview\.com/);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        data: [{ s: "HOSE:FPT", d: [73500, 1.25, 1234567, 72800, 73800, 72600] }],
      }),
    };
  };
  try {
    const res = responseRecorder();
    await handler({ method: "GET", query: { symbol: "FPT" } }, res);
    assert.equal(res.statusCode, 200);
    assert.equal(res.body.status, "ok");
    assert.equal(res.body.scope, "solution-ai");
    assert.equal(res.body.quotes.FPT.price, 73500);
    assert.equal(res.body.quotes.FPT.sourceMode, "solution_ai_direct");
    assert.equal(res.headers["Access-Control-Allow-Origin"], "*");
  } finally {
    global.fetch = original;
  }
});

test("SoluTION live endpoint falls back to Yahoo when direct provider fails", async () => {
  const original = global.fetch;
  let calls = 0;
  global.fetch = async url => {
    calls += 1;
    if (String(url).includes("tradingview")) throw new Error("synthetic direct outage");
    assert.match(String(url), /query1\.finance\.yahoo\.com/);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        chart: {
          result: [{
            meta: { chartPreviousClose: 72000, exchangeName: "VSE" },
            timestamp: [1790901000, 1790901060],
            indicators: { quote: [{ close: [72400, 72500], volume: [1000, 1200], open: [72300, 72400], high: [72500, 72600], low: [72200, 72300] }] },
          }],
        },
      }),
    };
  };
  try {
    const res = responseRecorder();
    await handler({ method: "GET", query: { symbol: "FPT" } }, res);
    assert.equal(res.statusCode, 200);
    assert.equal(res.body.quotes.FPT.price, 72500);
    assert.equal(res.body.quotes.FPT.sourceMode, "solution_ai_fallback");
    assert.ok(calls >= 2);
  } finally {
    global.fetch = original;
  }
});

test("SoluTION live endpoint rejects invalid symbols", async () => {
  const original = global.fetch;
  global.fetch = async () => { throw new Error("fetch should not be called"); };
  try {
    const res = responseRecorder();
    await handler({ method: "GET", query: { symbol: "../../secret" } }, res);
    assert.equal(res.statusCode, 400);
    assert.equal(res.body.error, "INVALID_SYMBOL");
  } finally {
    global.fetch = original;
  }
});
