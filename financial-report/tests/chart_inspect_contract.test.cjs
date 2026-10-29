'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ROOT=path.resolve(__dirname,'..');
const read=p=>fs.readFileSync(path.join(ROOT,p),'utf8');

test('one delegated inspector is included in both the frontend and standalone HTML build',()=>{
 const html=read('frontend/index.html'),build=read('scripts/build_cdn.py'),source=read('frontend/chart-inspect.js');
 assert.equal((html.match(/src="chart-inspect.js"/g)||[]).length,1);
 assert.ok(html.indexOf('src="chart-inspect.js"')<html.indexOf('src="dashboard.js"'));
 assert.match(build,/front \/ 'chart-inspect\.js'/);
 assert.match(build,/'metrics\.js','chart-inspect\.js','dashboard\.js'/);
 assert.match(source,/document\.addEventListener\('pointermove'/);
 assert.match(source,/document\.addEventListener\('pointerdown'/);
 assert.match(source,/document\.addEventListener\('keydown'/);
 assert.match(source,/sort\(\(a,b\)=>a\.x-b\.x\|\|a\.y-b\.y\)/);
 assert.match(source,/document\.createElement\('div'\)/);
 assert.doesNotMatch(source,/innerHTML\s*=\s*.*point\.value/);
});
test('macro cards render a real historical value and its unit on every point',()=>{
 const elements=new Map();
 const get=id=>{if(!elements.has(id))elements.set(id,{innerHTML:'',value:'',textContent:'',disabled:false});return elements.get(id);};
 const ctx={window:{},document:{getElementById:get},Intl,Number,Date,URL};vm.createContext(ctx);
 vm.runInContext(read('frontend/macro-dashboard.js'),ctx,{timeout:3000});
 const source=[
  {label:'T8 2026',y:3.39321},{label:'T9 2026',y:4.3125},
  {label:'T10 2026',y:4.1}
 ];
 const svg=ctx.window.FinMacroDashboard.plot(source,{title:'Lãi suất',unit:'%/năm'});
 assert.equal((svg.match(/data-fq-point="/g)||[]).length,3);
 assert.match(svg,/data-fq-label="T9 2026"/);
 assert.match(svg,/data-fq-value="4,3125"/);
 assert.match(svg,/data-fq-unit="%\/năm"/);
 assert.match(svg,/data-fq-inspect="line"/);
 assert.doesNotMatch(svg,/<title>/);
 const empty=ctx.window.FinMacroDashboard.plot(source.slice(0,1),{});
 assert.doesNotMatch(empty,/data-fq-point/);
});
test('trading/risk/statement chart families expose real point metadata, not a decorative fake tooltip',()=>{
 for(const file of ['macro.js','risk-monitor.js','market.js','derivatives-market.js','dashboard.js','liquidity-derivatives.js']){
  const js=read('frontend/'+file);
  assert.match(js,/data-fq-inspect=/,file+' missing inspector chart root');
  assert.match(js,/data-fq-point=/,file+' missing indexed real observations');
  assert.match(js,/data-fq-label=/,file+' missing publication date / tenor');
  assert.match(js,/data-fq-value=/,file+' missing source value');
 }
 const market=read('frontend/market.js');
 assert.match(market,/data-fq-series=/,'stock vs sector comparison must distinguish series');
 const liquid=read('frontend/liquidity-derivatives.js');
 assert.match(liquid,/data-tenor-point=/,'existing verified tenor semantics must remain');
 assert.match(liquid,/bindONTooltip\(\)/,'ON existing interaction is left intact');
 const chart=read('frontend/chart-engine.js');
 assert.match(chart,/subscribeCrosshairMove/,'price candles retain native trading chart inspection');
});
test('shared chart popup never includes the source/provider labels or interpolates unknown periods',()=>{
 const src=read('frontend/chart-inspect.js');
 assert.doesNotMatch(src,/\bKBS\b|Vietcap|VBMA|sourceUrl|interpolat/i);
 assert.match(src,/point\.value/);
 assert.match(src,/point\.label/);
 assert.match(src,/minDx/);
 assert.match(src,/tooltip\.textContent|children\[2\]\.textContent/);
 const css=read('frontend/market.css');
 assert.match(css,/\.fq-chart-tooltip\[hidden\]/);
 assert.match(css,/z-index:2147480000/);
});
