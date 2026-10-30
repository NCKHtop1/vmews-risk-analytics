const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'frontend/liquidity-derivatives.js'),'utf8');
const history=JSON.parse(fs.readFileSync(path.join(root,'data/on-mmonvnd-history.json'),'utf8'));
function runtime(){
 const els=new Map();
 const get=id=>{if(!els.has(id))els.set(id,{innerHTML:'',textContent:'',disabled:false,clientWidth:600,addEventListener(){}});return els.get(id)};
 const ctx={window:{},document:{getElementById:get,addEventListener(){}},fetch:async()=>({ok:false}),AbortSignal,Date,URL,Intl,Number,String,Math,console};
 vm.createContext(ctx);vm.runInContext(source,ctx,{timeout:3000});
 return {api:ctx.window.FinLiquidityDerivatives,get};
}
const payload={schemaVersion:1,asOf:'2026-10-27',interbank:{status:'secondary_source_crosschecked',observations:[{date:'2026-10-27',value:4.9}]},derivatives:{months:[]},vbmaSwap:{status:'unavailable',points:[]}};
test('MMONVND preserves full raw records and documented conflicting duplicate',()=>{
 const {api}=runtime();const records=api._test.historyOnRows(history);
 assert.equal(records.length,462);
 assert.equal(new Set(records.map(x=>x.date)).size,460);
 assert.equal(records[0].date,'2025-01-02');
 assert.equal(records.at(-1).date,'2026-10-23');
 const duplicate=records.filter(x=>x.date==='2026-02-03');
 assert.equal(duplicate.length,2);assert.deepEqual(duplicate.map(x=>x.value).sort((a,b)=>a-b),[11.1,17]);
});
test('ON history accepts month/year selections, preserves daily frequency',()=>{
 const {api}=runtime();const data=api._test.historyOnRows(history);
 const ordered=[...new Map(data.map(p=>[p.date,p])).values()].sort((a,b)=>a.date.localeCompare(b.date));
 const latest=api._test.filterOnTimeline(ordered,'1M','all','all');
 assert.ok(latest.length>15&&latest.length<30);
 assert.equal(latest.at(-1).date,'2026-10-23');
 assert.ok(api._test.filterOnTimeline(ordered,'ALL','2025','02').every(p=>p.date.startsWith('2025-02')));
 assert.equal(api._test.filterOnTimeline(ordered,'ALL','all','all').length,460);
});
test('ON compact chart exposes selectable periods and retains crawled values',()=>{
 const {api,get}=runtime();api.setData(payload);
 const html=get('money-on').innerHTML;
 assert.match(html,/data-on-range="1W"/);
 assert.match(html,/data-on-range="ALL"/);
 assert.match(html,/data-on-filter="year"/);
 assert.match(html,/data-on-filter="month"/);
 assert.match(html,/4,9/);
 assert.doesNotMatch(html,/finquery-on-manual-form/);
});
