const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8');
const js=fs.readFileSync(path.join(root,'frontend/liquidity-derivatives.js'),'utf8');
const hub=fs.readFileSync(path.join(root,'data-hub.html'),'utf8');
const build=fs.readFileSync(path.join(root,'scripts/build_cdn.py'),'utf8');
const fixture={
 schemaVersion:1,asOf:'2026-10-22',
 interbank:{status:'secondary_source_crosschecked',asOf:'2026-10-22',source:'https://stockbiz.vn/vi-mo/du-lieu/lai-suat-lien-ngan-hang',
   crossCheck:'https://dulieukinhte.com/du-lieu-dong/lai-suat-thi-truong-lien-ngan-hang-qua-dem-34248',
   observations:[{date:'2026-10-20',value:3.71},{date:'2026-10-21',value:3.39},{date:'2026-10-22',value:4.31}]},
 derivatives:{source:'https://www.gov.hnx.vn/vi-vn/chi-tiet-tin-60023563-0.html',months:[
   {month:'2026-08',vn30:{openInterest:27984,avgVolume:228905},vn100:{openInterest:77,avgVolume:66}},
   {month:'2026-09',vn30:{openInterest:39543,avgVolume:219121},vn100:{openInterest:203,avgVolume:259}}
 ]},
 vbmaSwap:{source:'https://vbma.org.vn/csv/markets/charts/vi/fx_swap_curve.csv',status:'awaiting_verified_source',points:[],unit:null,asOf:null}
};
function makeEnv(payload=fixture){
 const nodes=new Map();
 const get=id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',textContent:'',disabled:false,addEventListener(name,fn){this['on_'+name]=fn;}});return nodes.get(id);};
 const doc={getElementById:get};
 const ctx={window:{},document:doc,fetch:async()=>({ok:true,json:async()=>payload}),AbortSignal,Date,URL,Intl,Number,String,Math,console};
 vm.createContext(ctx);
 vm.runInContext(js,ctx,{timeout:3000});
 return {api:ctx.window.FinLiquidityDerivatives,get};
}
test('real ON and VN30/VN100 charts are part of the primary FinQuery section',()=>{
 assert.match(html,/id="macro-liquidity-overview"/);
 assert.match(html,/id="money-on"/);
 assert.match(html,/id="money-futures"/);
 assert.match(html,/id="money-swap"/);
 assert.match(html,/src="liquidity-derivatives.js"/);
 assert.match(build,/liquidity-derivatives\.js/);
});
test('old source-card destination redirects to the main Macro & ESG charts',()=>{
 assert.match(hub,/http-equiv="refresh"/);
 assert.match(hub,/content="0; url=\/financial-report\/index\.html#macro"/);
 assert.doesNotMatch(html,/>Kho dữ liệu<\/a>/);
});
test('removed all banned user-facing copy from the primary dashboard',()=>{
 assert.doesNotMatch(html,/Mỗi biểu đồ dùng đúng đơn vị, kỳ quan sát và nguồn/);
 assert.doesNotMatch(html,/không coi số liệu tháng là realtime/);
 const dashboard=fs.readFileSync(path.join(root,'frontend/macro-dashboard.js'),'utf8');
 assert.doesNotMatch(dashboard,/Bản kiểm tra .*không phải giá trực tiếp/);
});
test('interbank ON uses actual dated observations, not VBMA government repo',()=>{
 const {api,get}=makeEnv();
 api.setData(fixture);
 const out=get('money-on').innerHTML;
 assert.match(out,/4,31/);
 assert.match(out,/22\/10\/2026/);
 assert.match(out,/0,92 điểm %/);
 assert.match(out,/<svg/);
 assert.match(out,/stockbiz\.vn/);
 assert.doesNotMatch(out,/vbma\.org\.vn/);
});
test('HNX VN30 and VN100 derivatives keep OI and volume with monthly labels',()=>{
 const {api,get}=makeEnv();
 api.setData(fixture);
 let out=get('money-futures').innerHTML;
 assert.match(out,/VN30/);
 assert.match(out,/VN100/);
 assert.match(out,/39\.543/);
 assert.match(out,/203/);
 assert.match(out,/08\/2026/);
 assert.match(out,/09\/2026/);
 assert.match(out,/gov\.hnx\.vn/);
});
test('unverified swap is empty, never fabricated; verified points show a curve',()=>{
 const {api,get}=makeEnv();
 api.setData(fixture);
 assert.match(get('money-swap').innerHTML,/Chưa có dữ liệu/);
 assert.doesNotMatch(get('money-swap').innerHTML,/money-swap-chart|money-swap-point/);
 const other=JSON.parse(JSON.stringify(fixture));
 other.vbmaSwap.status='verified';
 other.vbmaSwap.unit='swap points';
 other.vbmaSwap.asOf='2026-10-22';
 other.vbmaSwap.measurement='MID swap points';
 other.vbmaSwap.points=[{tenor:'1W',value:-5},{tenor:'1M',value:-22},{tenor:'3M',value:-90}];
 api.setData(other);
 assert.equal((get('money-swap').innerHTML.match(/data-tenor-point=/g)||[]).length,3);
 assert.match(get('money-swap').innerHTML,/22\/10\/2026/);
});
test('unverified ON or missing observations cannot masquerade as valid chart',()=>{
 const {api,get}=makeEnv();
 const other=JSON.parse(JSON.stringify(fixture));
 other.interbank.status='unavailable';
 api.setData(other);
 assert.match(get('money-on').innerHTML,/Chưa có dữ liệu/);
 assert.doesNotMatch(get('money-on').innerHTML,/<svg/);
});
test('URL sanitation and SVG injection gates',()=>{
 const {api}=makeEnv();
 assert.equal(api._test.safeURL('https://stockbiz.vn/data','stockbiz.vn'),'https://stockbiz.vn/data');
 assert.equal(api._test.safeURL('javascript:alert(1)','stockbiz.vn'),'');
 assert.equal(api._test.safeURL('https://stockbiz.vn.evil.org/data','stockbiz.vn'),'');
 const image=api._test.miniLine([{date:'2026-10-21',value:3.39},{date:'2026-10-22',value:4.31}],{title:'<b>x</b>'});
 assert.match(image,/&lt;b&gt;/);
 assert.doesNotMatch(image,/<b>x<\/b>/);
});

test('ON timeline adapts date labels and VBMA references use compact export icons',()=>{
 const {api,get}=makeEnv();
 const points=Array.from({length:22},(_,i)=>({date:'2026-10-'+String(i+1).padStart(2,'0'),value:3+i*.06}));
 const compact=api._test.miniLine(points,{title:'Liên ngân hàng ON',width:304});
 const wide=api._test.miniLine(points,{title:'Liên ngân hàng ON',width:920});
 assert.ok((compact.match(/data-on-tick=/g)||[]).length<=3,'mobile tick budget');
 assert.ok((wide.match(/data-on-tick=/g)||[]).length>=4,'desktop tick labels');
 assert.match(compact,/01\/10/);
 assert.doesNotMatch(compact,/<text[^>]*data-on-tick[^>]*>01\/10\/2026/);
 const swap={...fixture,vbmaSwap:{source:'https://vbma.org.vn/csv/markets/charts/vi/fx_swap_curve.csv',status:'verified',unit:'swap points',asOf:'2026-10-22',points:[{tenor:'1W',value:-5},{tenor:'1M',value:-22}]}};
 api.setData(swap);
 const html=get('money-swap').innerHTML;
 assert.match(html,/money-vbma-download/);
 assert.match(html,/aria-label="Tải dữ liệu nguồn/);
 assert.doesNotMatch(html,/>VBMA FX Swap ↗</);
});

test('Fixed income yield tenors display signed and accessible chart, not absolute magnitude bars',()=>{
 const {api,get}=makeEnv();
 const signed=[{tenor:'1W',value:-2.5},{tenor:'1M',value:1.2},{tenor:'3M',value:3.1}];
 const svg=api._test.tenorCurve(signed,{title:'FX Swap',unit:'%/năm',width:304});
 assert.match(svg,/money-tenor-curve/);
 assert.match(svg,/stroke-dasharray="4 3"/);
 assert.equal((svg.match(/data-tenor-point=/g)||[]).length,3);
 assert.ok((svg.match(/data-tenor-label=/g)||[]).length<=4);
 const next={...fixture,vbmaCurves:{gov_bond:{source:'https://vbma.org.vn/csv/markets/charts/vi/government_bond_yield.csv',
  status:'verified',unit:'%/năm',licenseStatus:'source_attributed',asOf:'2026-10-23',
  points:[{tenor:'1Y',value:3.1},{tenor:'2Y',value:3.2},{tenor:'5Y',value:3.7}]}}};
 api.setData(next);
 assert.match(get('money-vbma-curves').innerHTML,/data-tenor-point="1Y"/);
 assert.match(get('money-vbma-curves').innerHTML,/money-vbma-download/);
});
