const {test}=require('node:test');
const assert=require('node:assert/strict');
const {buildRiskSnapshot}=require('../scripts/build_risk_monitor.cjs');

const symbols=['ACB','BID','CTG','MBB','TCB','VCB','VIC','VHM','NVL','PDR','SSI','VIX'];
function fixture({stress=false,sourceTime='2026-10-05T07:45:00.000Z'}={}){
 const quotes={status:'ok',expected:symbols.length,coverage:symbols.length,latestSourceTime:sourceTime,checkedAt:sourceTime,quotes:{}};
 const strategy={status:'ok',coverage:400,sourceTime,checkedAt:sourceTime,symbols:{}};
 symbols.forEach((symbol,i)=>{
  const change=stress?-(2.8+(i%3)*.45):(i%2===0?.35:-.28);
  const price=100000+i*1000,reference=price/(1+change/100);
  const rangePct=stress?4.2:1.15;
  const high=price*(1+rangePct/200),low=price*(1-rangePct/200);
  quotes.quotes[symbol]={symbol,price,reference,changePct:change,volume:stress?2400000+i*120000:900000+i*50000,open:reference,high,low,sourceTime,status:'ok'};
  strategy.symbols[symbol]={
   symbol,tier:'CORE',cadence:'LIVE_15M',barDate:'2026-10-05',sourceTime,
   current:{
    price,changePct:change,atr14:price*(stress?.05:.018),volume:quotes.quotes[symbol].volume,
    volumeSma20:quotes.quotes[symbol].volume/(stress?2.1:1.0),volumeRatio20:stress?2.1:1.0,
    cmf20:stress?-.24:.03,sma20:stress?price*1.06:price*.99,sma50:stress?price*1.08:price*.98
   },
   previous:{price,changePct:change}
  };
 });
 return{quotes,strategy};
}

test('calm market stays below high-risk threshold',()=>{
 const {quotes,strategy}=fixture();
 const out=buildRiskSnapshot(quotes,strategy,null,'2026-10-05T07:45:10.000Z');
 assert.equal(out.status,'ok');
 assert.equal(out.coverage.quotes,symbols.length);
 assert.ok(out.overall.score<50,out.overall);
 assert.equal(out.sourceTime,quotes.latestSourceTime);
 assert.ok(out.sectors.length>=3);
 assert.equal(out.timeline.length,1);
});

test('broad selloff raises market risk and creates explainable alerts',()=>{
 const {quotes,strategy}=fixture({stress:true});
 const out=buildRiskSnapshot(quotes,strategy,null,'2026-10-05T07:45:10.000Z');
 assert.ok(out.overall.score>=65,out.overall);
 assert.ok(out.components.breadth.score>=65,out.components.breadth);
 assert.ok(out.components.volatility.score>=65,out.components.volatility);
 assert.ok(out.components.liquidity.score>=65,out.components.liquidity);
 assert.ok(out.components.contagion.score>=60,out.components.contagion);
 assert.ok(out.alerts.some(x=>x.id==='market-high'));
 assert.ok(out.alerts.some(x=>x.id==='breadth'));
 assert.equal(out.topRisk[0].reasons.length>0,true);
});

test('risk snapshot refuses a different strategy generation',()=>{
 const {quotes,strategy}=fixture();
 strategy.sourceTime='2026-10-05T07:30:00.000Z';
 assert.throws(()=>buildRiskSnapshot(quotes,strategy),/not aligned/);
});

test('timeline is deduplicated by market source time',()=>{
 const {quotes,strategy}=fixture({stress:true});
 const first=buildRiskSnapshot(quotes,strategy,null,'2026-10-05T07:45:10.000Z');
 const same=buildRiskSnapshot(quotes,strategy,first,'2026-10-05T07:46:10.000Z');
 assert.equal(same.timeline.length,1);
 const nextFixture=fixture({stress:true,sourceTime:'2026-10-05T07:50:00.000Z'});
 const next=buildRiskSnapshot(nextFixture.quotes,nextFixture.strategy,same,'2026-10-05T07:50:10.000Z');
 assert.equal(next.timeline.length,2);
 assert.notEqual(next.trend.delta,null);
});

test('active alerts keep their original start time while the condition remains active',()=>{
 const firstFixture=fixture({stress:true,sourceTime:'2026-10-05T07:40:00.000Z'});
 const first=buildRiskSnapshot(firstFixture.quotes,firstFixture.strategy,null,'2026-10-05T07:40:10.000Z');
 const nextFixture=fixture({stress:true,sourceTime:'2026-10-05T07:45:00.000Z'});
 const next=buildRiskSnapshot(nextFixture.quotes,nextFixture.strategy,first,'2026-10-05T07:45:10.000Z');
 const a=next.alerts.find(x=>x.id==='market-high');
 assert.ok(a);
 assert.equal(a.startedAt,'2026-10-05T07:40:00.000Z');
 assert.equal(a.lastSeen,'2026-10-05T07:45:00.000Z');
});
