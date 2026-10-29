'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const read=p=>fs.readFileSync(path.join(root,p),'utf8');
test('ownership source column and MB Bank IR, KBS or Vietcap display links are absent',()=>{
 const js=read('frontend/ownership-intelligence.js');
 assert.doesNotMatch(js,/<th>Nguồn<\/th>|sourceLink\(/);
 assert.match(js,/owner-asof/);
 assert.match(js,/function safeSource\(/,'data validation remains intact');
});
test('futures table preserves quotes but no longer renders a provider or source column',()=>{
 const js=read('frontend/derivatives-market.js');
 assert.doesNotMatch(js,/'Nguồn'|HNX · KBS|Nguồn giá: KBS/);
 assert.match(js,/derivative-board-table/);
 assert.match(js,/datetimeVN\(state\.data\.latestSourceTime\)/);
});
test('Macro ESG maintains real charts while omitting public source links',()=>{
 const js=read('frontend/macro-dashboard.js'),macro=read('frontend/macro.js');
 assert.match(js,/function sourceLink\(\)\{return '';\}/);
 assert.match(js,/corporateRows\(esg/,'verified metric gate preserved');
 const block=macro.slice(macro.indexOf('function renderAssessments()'),macro.indexOf('function renderDashboard()'));
 assert.doesNotMatch(block,/href=|sourceCount|Nguồn chính/);
 assert.match(block,/metricIds\.size/);
});
test('market news, research cards and chart status no longer expose provider names',()=>{
 const market=read('frontend/market.js'),insights=read('frontend/insights.js'),chart=read('frontend/chart-engine.js');
 assert.doesNotMatch(market,/esc\(r\.source\)\+' <span>|nguồn có dữ liệu ·/);
 assert.doesNotMatch(insights,/insight-source-link|sourceLink\(/);
 assert.doesNotMatch(chart,/\$\{data\.source\|\|'Vietcap'\}/);
});
test('Dolphin retains evidence quality audit without visual citations or reference panels',()=>{
 const s=read('frontend/research-ai.js');
 const rendered=s.slice(s.indexOf('function inlineMarkdown('),s.indexOf('function nearBottom('));
 assert.doesNotMatch(rendered,/ai-provenance|ai-anchor|ai-source-tag|Nguồn đối chiếu|Dấu vết dữ liệu/);
 assert.match(s,/function auditDeepAnswer\(/);
 assert.match(s,/missingEvidenceTags/);
});
test('forecast and data hub suppress source audit panels, not forecast or macro data',()=>{
 const forecast=read('../forecast-final.html'),hub=read('data-hub.html');
 assert.match(forecast,/<div class="panel" hidden aria-hidden="true"><div id="sourceAudit"/);
 assert.match(forecast,/\.panel\[hidden\]\{display:none!important\}/);
 assert.match(hub,/<section class="section" aria-labelledby="sources-heading" hidden>/);
 assert.match(hub,/<section class="section" aria-labelledby="quality-heading" hidden>/);
 assert.match(hub,/id="metric-pmi"/);
});
test('source-style safety rules keep verified curve CSV buttons available',()=>{
 const css=read('frontend/market.css'),liq=read('frontend/liquidity-derivatives.js');
 assert.match(css,/\.macro-viz-source:not\(\.money-download-row\)/);
 assert.match(css,/\.macro-viz-source\.money-download-row/);
 assert.match(liq,/data-download-curve=/);
});
