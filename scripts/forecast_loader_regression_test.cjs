"use strict";
// Reproduces blocked network, aborted downloads, retry, and GitHub mirror
// fallback without modifying production data or relying on public network.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const src = fs.readFileSync(path.join(ROOT, "forecast-final-v12.js"), "utf8");
const leader = fs.readFileSync(path.join(ROOT, "forecast-live-leaders-v14.js"), "utf8");

function makeContext() {
  const state = { calls: [], handler: null };
  const origin = "https://finquery.info.vn";
  const window = { __FINQUERY_FORECAST_TIMEOUT_MS: 35, addEventListener() {} };
  const location = { hostname: "finquery.info.vn", origin, pathname: "/forecast-final.html", search: "",
                     href: origin + "/forecast-final.html", reload() {} };
  const document = { hidden: false, addEventListener() {}, querySelector() { return null; } };
  const context = {window,location,document,Date,Intl,URL,URLSearchParams,AbortController,
                   setTimeout,clearTimeout,console,CustomEvent:class{}};
  context.fetch = async (url, opts) => {state.calls.push(String(url));return state.handler(url,opts);};
  vm.runInNewContext(src, context, {filename: "forecast-final-v12.js"});
  return { context, state };
}

function abortingFetch(url, opts) {
  return new Promise((resolve, reject) => {
    opts.signal.addEventListener("abort", () => reject(new Error("AbortError")), {once:true});
  });
}

const payloads = {
  "forecast-dashboard-v12.json": {asOf:"2026-10-08",generatedAt:"2026-10-08T16:00:00+07:00", symbols:{MBB:{close:25000}}, charts:{}},
  "forecast-model-v12.json": {promotion:{status:"PASS"}},
  "data-audit-v12.json": {status:"PASS"},
  "phase-gates-v12.json": {status:"PASS"},
  "forecast-market-v13.json": {model:{promotion:{status:"PASS"}},backtest:{horizons:{}}}
};
function goodFetch(url) {
  const name = new URL(url, "https://finquery.info.vn/forecast-final.html").pathname.split("/").pop();
  if (!Object.prototype.hasOwnProperty.call(payloads,name)) throw new Error("Unexpected "+name);
  return {ok:true,status:200,json:async()=>payloads[name]};
}
(async () => {
  assert(src.includes("hist.map(CHART_EXECUTABLE_CLOSE)"), "chart must plot executable rather than adjusted prices");
  assert(src.includes("y:y(CHART_EXECUTABLE_CLOSE(item))"), "chart history points must use executable close");
  assert(src.includes("UNUSED_IMPOSSIBLE_TOKEN") === false);
  assert(src.includes("Thử tải lại"), "bounded-error UI must allow retry");
  assert(leader.includes("controller.abort()"), "session overlay must have abort timeout");

  const {context,state} = makeContext();
  state.handler = abortingFetch;
  const started = Date.now();
  await assert.rejects(context.window.__VMEWS_LOAD_BASE__(), /quá thời hạn|chưa sẵn sàng/);
  const elapsed = Date.now()-started;
  assert(elapsed < 1000, "blocked network must not hang FOREVER; elapsed "+elapsed);
  assert(state.calls.length >= 5, "parallel core data requests expected");

  // Failover with all primary Vercel URLs returning 503 and raw/main succeeding.
  state.calls.length=0;
  state.handler = async url => String(url).startsWith("./data/") ?
    {ok:false,status:503} : goodFetch(url);
  const b=await context.window.__VMEWS_LOAD_BASE__();
  assert.equal(b.dash.asOf, "2026-10-08");
  assert.equal(b.model.promotion.status, "PASS");
  assert(b.back.horizons);
  assert(state.calls.some(u=>u.startsWith("https://raw.githubusercontent.com/")), "fallback to independent path required");

  // Successful cache must remain coherent and NOT trigger needless requests.
  const count=state.calls.length;
  const repeat=await context.window.__VMEWS_LOAD_BASE__();
  assert.equal(repeat,b);
  assert.equal(state.calls.length,count);
  console.log("FORECAST LOADER PASS: bounded stalls, recoverable promise, Vercel->raw fallback, coherent cache, executable chart");
})().catch(error=>{console.error(error);process.exitCode=1;});