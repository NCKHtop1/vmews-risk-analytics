const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const core = read('forecast-final-v12.js');
const leaders = read('forecast-live-leaders-v14.js').replace(
  '  async function init() {',
  '  window.testSession = { loadSessionOverlay, sessionUsableNow };\n  async function init() {'
);
function context(url) {
  const window = { addEventListener() {}, matchMedia: () => ({ matches: false }) };
  const sandbox = { window, location: new URL(url), URL, URLSearchParams, console,
    document: { readyState: 'loading', addEventListener() {}, querySelector() {} } };
  vm.createContext(sandbox);
  vm.runInContext(core, sandbox);
  vm.runInContext(leaders, sandbox);
  return sandbox;
}
(async () => {
  const href = read('financial-report/frontend/index.html').match(/id="forecast-link" href="([^"]+)"/)[1];
  const link = new URL(href);
  link.searchParams.set('symbol', 'FPT');
  assert.equal(link.href, 'https://nckhtop1.github.io/vmews-risk-analytics/forecast-final.html?symbol=FPT');
  const ctx = context(link.href);
  assert.equal(ctx.window.__VMEWS_DATA_ROOT__, 'https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/main/data');
  assert.equal(context('http://localhost:8000/forecast-final.html').window.__VMEWS_DATA_ROOT__, './data');
  assert.equal(context('https://cdn.githubraw.com/NCKHtop1/vmews-risk-analytics/abc/forecast-final.html?dataRef=test-branch').window.__VMEWS_DATA_REF__, 'test-branch');
  const date = new Date().toISOString();
  const session = { status: 'PASS', coreForecastUnchanged: true, coreAsOf: '2026-09-18',
    cutoffAt: date, rankingHorizon: 3,
    forecastAlignment: { status: 'STALE_CORE', rankingEligible: false, expectedCoreAsOf: '2026-09-25' },
    coverage: { coverageRatio: .99, currentCoverageRatio: .91, cutoffFreshCoverageRatio: .91 },
    symbols: [{ symbol: 'FPT', liveClose: 64700, quoteCurrent: true, freshForCutoff: true, updateAt: date }] };
  const base = { dash: { asOf: '2026-09-18', promotion: { directPriceHorizons: [3,4,5], preferredRankingHorizon: 3 } } };
  ctx.fetch = async url => {
    assert.ok(url.startsWith(ctx.window.__VMEWS_DATA_ROOT__ + '/forecast-session-v21.json?refresh='));
    return { ok: true, json: async () => session };
  };
  assert.equal(await ctx.window.testSession.loadSessionOverlay(base), session);
  const snapshot = { close: 71700, horizons: { '3': { expectedPrice: 71900 } } };
  const view = ctx.window.__VMEWS_APPLY_SESSION_VIEW__('FPT', snapshot, session);
  assert.equal(view.close, 64700);
  assert.equal(view.coreClose, 71700);
  assert.equal(view.horizons['3'].expectedPrice, 71900);
  assert.equal(view.liveSession.forecastAligned, false);
  assert.equal(snapshot.close, 71700);
  const portfolio = read('forecast-portfolio-v14.js');
  const tape = { innerHTML: '' };
  session.symbols[0].change = -.0091883614;
  ctx.window.__VMEWS_SESSION__ = session;
  const tapeContext = { window: ctx.window, document: { querySelector: () => tape },
    number: value => value == null ? null : Number(value), price: String, escapeHTML: String };
  vm.runInNewContext(portfolio.slice(portfolio.indexOf('  function renderMarketTape('), portfolio.indexOf('  function updateSymbolPresentation(')) + '\nthis.render = renderMarketTape;', tapeContext);
  tapeContext.render({ dash: { symbols: { FPT: snapshot }, charts: { FPT: [{close: 72000}, {close: 71700}] } } });
  assert.ok(tape.innerHTML.includes('64700'));
  assert.ok(tape.innerHTML.includes('-0.92%'));
  assert.equal(ctx.window.__VMEWS_APPLY_SESSION_VIEW__('UNKNOWN', snapshot, session), snapshot);
  session.coverage.currentCoverageRatio = .5;
  assert.equal(await ctx.window.testSession.loadSessionOverlay(base), null);
  assert.match(leaders, /setInterval\(\(\) => \{ void refreshSession\(\); \}, 60000\)/);
  assert.match(leaders, /addEventListener\("visibilitychange"/);
  console.log('PASS: navigation, data roots, latest quote, immutable forecast, invalid overlay rejection, refresh hooks');
})().catch(error => { console.error(error); process.exitCode = 1; });
