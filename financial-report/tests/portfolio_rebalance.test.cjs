'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const core=require('../frontend/portfolio-rebalance-core.js');
const time='2026-10-30T07:45:00.004Z',now=Date.parse('2026-11-01T14:00:00Z');
const row=(symbol,quantity,price,sectorId='other')=>({symbol,quantity,price,value:quantity*price,sectorId});
const book=(rows,cash)=>({rows,cash,nav:cash+rows.reduce((a,x)=>a+x.value,0),sectorAllocations:[]});
const go=(portfolio,policy={preset:'balanced'})=>core.review({portfolio,policy,sourceTime:time,now});
test('four real templates and bounded user thresholds',()=>{
 assert.deepEqual(Object.keys(core.PRESETS),['balanced','equal','defensive','focused']);
 assert.equal(core.normalize({preset:'defensive'}).cashPct,30);
 assert.equal(core.normalize({preset:'equal',cashPct:100,driftPct:-5}).cashPct,50);
 assert.equal(core.normalize({preset:'equal',cashPct:100,driftPct:-5}).driftPct,2);
 assert.equal(core.venueDate(time),'2026-10-30');
});
test('empty portfolio is onboarding, not a false rebalance signal',()=>{
 const r=go(book([],0));assert.equal(r.blocked,false);
 assert.equal(r.trades.length,0);assert.equal(r.targets.length,0);
 assert.match(r.why,/Thêm cổ phiếu/);
});
test('target weights respect stock and sector concentration caps',()=>{
 const rows=[row('AAA',1000,30000,'bank'),row('BBB',1000,30000,'bank'),
  row('CCC',1000,30000,'bank'),row('DDD',1000,30000,'bank')];
 const r=go(book(rows,30000000));
 assert.equal(r.targets.length,4);
 assert.ok(r.targets.every(t=>t.targetPct<=30));
 assert.ok(r.targets.reduce((a,x)=>a+x.targetPct,0)<=45.001);
 assert.ok(r.targetCashPct>=54.999);
});
test('overweight stocks produce sells first and never negative shares',()=>{
 const r=go(book([row('AAA',1800,30000,'bank'),row('BBB',1200,30000,'steel')],10000000));
 assert.equal(r.blocked,false);
 assert.ok(r.trades.every(t=>t.side==='SELL'));
 assert.ok(r.trades.every(t=>t.quantity%100===0&&t.quantity>0));
 const ownership={AAA:1800,BBB:1200};
 assert.ok(r.trades.every(t=>t.quantity<=ownership[t.symbol]));
 assert.ok(r.estimatedCostVnd>0);
});
test('underweight allocation buys stay within available cash above reserve including fees',()=>{
 const rows=[row('AAA',400,20000,'bank'),row('BBB',400,20000,'steel'),row('CCC',400,20000,'tech'),
  row('DDD',400,20000,'retail')];
 const portfolio=book(rows,40000000),r=go(portfolio,{preset:'equal',cashPct:10,driftPct:2});
 assert.ok(r.trades.some(t=>t.side==='BUY'));
 const buy=r.trades.filter(t=>t.side==='BUY').reduce((a,t)=>a+t.grossVnd+t.estimatedCostVnd,0);
 const sell=r.trades.filter(t=>t.side==='SELL').reduce((a,t)=>a+t.grossVnd-t.estimatedCostVnd,0);
 assert.ok(buy<=portfolio.cash+sell-portfolio.nav*r.targetCashPct/100+0.01);
});
test('missing valuation and stale snapshots fail closed, never invent quantities',()=>{
 const x=book([row('AAA',1000,20000)],1000000);x.rows[0].price=null;x.nav=null;
 assert.equal(go(x).blocked,true);
 const stale=core.review({portfolio:book([row('AAA',1000,20000)],5000000),
  sourceTime:'2026-10-01T07:45:00Z',now});
 assert.equal(stale.blocked,true);assert.equal(stale.trades.length,0);
});
test('small drift does not cause churn, and trade minimum/lot matters',()=>{
 const r=go(book([row('AAA',100,20000,'bank'),row('BBB',100,20000,'steel')],2000000),
  {preset:'focused',driftPct:15});
 assert.equal(r.trades.length,0);
 assert.ok(r.why);
});
