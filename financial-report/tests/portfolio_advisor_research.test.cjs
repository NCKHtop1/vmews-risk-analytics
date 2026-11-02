'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const Core=require('../scripts/portfolio_advisor_core.cjs');
const Proxy=require('../scripts/portfolio_advisor_proxy.cjs');
const Engine=require('../frontend/strategy-engine.js');
const asOf='2026-10-30',generatedAt='2026-10-30T10:00:00Z';
function dates(){
 const list=[];
 const d=new Date('2025-05-01T00:00:00Z');
 while(d.toISOString().slice(0,10)<=asOf){
  if(![0,6].includes(d.getUTCDay()))list.push(d.toISOString().slice(0,10));
  d.setUTCDate(d.getUTCDate()+1);
 }
 return list;
}
const trading=dates();
function makeStock(i){
 const symbol='T'+String(i).padStart(2,'0'),sectorId='G'+Math.floor(i/4);
 const bars=trading.map((time,j)=>{
  const close=10000*(1+(.002+(.00011*(i%4))))**j;
  const vol=4000000+(j%7)*100000;
  return {time,open:close*.998,high:close*1.01,low:close*.99,close,volume:vol};
 });
 return {symbol,sectorId,bars};
}
const stocks=Array.from({length:16},(_,i)=>makeStock(i));
const input=(changes={})=>({stocks,asOf,generatedAt,quoteDate:asOf,riskDate:asOf,
 options:{minimumHistoryReady:12,minimumTurnoverVnd:1000000},...changes});
test('data missing is not a numeric zero in strategy evaluation',()=>{
 const row={tier:'CORE',current:{rsi14:null},previous:{}};
 assert.equal(Engine.evaluateCondition(row,{left:'rsi14',op:'lte',rightType:'value',rightValue:30}),false);
});
test('snapshot blocks open market session and misaligned data',()=>{
 assert.equal(Core.build(input({generatedAt:'2026-10-30T02:15:00Z'})).reason,'SESSION_NOT_CLOSED');
 assert.equal(Core.build(input({quoteDate:'2026-10-29'})).reason,'SOURCE_DATE_MISMATCH');
 assert.equal(Core.build(input({generatedAt:'2026-11-05T12:00:00Z'})).reason,'STALE_EOD');
 assert.equal(Core.build(input({stocks:[]})).reason,'INSUFFICIENT_COMPLETE_HISTORY');
});
test('research-only allocations are deterministic, never overallocated',()=>{
 const a=Core.build(input()),b=Core.build(input());
 assert.equal(a.status,'RESEARCH_ONLY');
 assert.deepEqual(a.models,b.models);
 for(const p of Object.values(a.models)){
  assert.equal(p.status,'RESEARCH_ONLY');
  const total=p.cashPct+p.positions.reduce((s,x)=>s+x.weightPct,0);
  assert.ok(Math.abs(total-100)<.05,JSON.stringify(p));
  assert.ok(p.positions.length>=Core.PROFILES[p.profile].minNames);
  assert.ok(p.positions.every(x=>x.weightPct<=p.maxStockPct+.001));
  const sec=new Map();
  for(const x of p.positions)sec.set(x.sectorId,(sec.get(x.sectorId)||0)+x.weightPct);
  assert.ok([...sec.values()].every(w=>w<=p.maxSectorPct+.001));
  assert.equal(p.positions.some(x=>x.quantity!==undefined),false);
 }
 assert.equal(a.publication,'RESEARCH_ONLY');
});
test('if signal set cannot diversify, cash remains 100%',()=>{
 const few=Core.modelFor('balanced',Core.candidatesAt(stocks.slice(0,2),asOf,{minimumTurnoverVnd:1000000}).eligible);
 assert.equal(few.status,'INSUFFICIENT_SIGNALS');
 assert.equal(few.cashPct,100);
 assert.equal(few.positions.length,0);
});
test('missing/partial EOD candle does not leak into screening',()=>{
 const bad=makeStock(21);
 bad.bars.at(-1).time='2026-10-29';
 assert.equal(Core.featuresFor(bad,asOf),null);
});
test('walk-forward proxy is explicitly NOT certified alpha',()=>{
 const p=Proxy.calc(stocks,asOf,{windows:6,holdingSessions:20,minimumTurnoverVnd:1000000});
 assert.ok(['RESEARCH_PROXY_NOT_VALIDATED','INSUFFICIENT_EVALUATION'].includes(p.status));
 if(p.status==='RESEARCH_PROXY_NOT_VALIDATED'){
  assert.ok(p.periods.every(w=>w.from<w.to));
  assert.ok(p.notes.some(x=>/survivorship bias/.test(x)));
  assert.ok(!('probabilityOfProfit' in p));
 }
});
