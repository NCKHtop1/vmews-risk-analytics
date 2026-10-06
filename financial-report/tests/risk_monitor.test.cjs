const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {buildRiskSnapshot,buildHistoricalBaseline,buildFundMonitor}=require('../scripts/build_risk_monitor.cjs');
const {calibrateSector,stressScore}=require('../scripts/build_sector_risk_calibration.cjs');
const {rawComponents,sectorRowsV2,sessionProgress,calibrationFromObservations,calibratedComponents,overallFromComponents:overallV2}=require('../scripts/risk_model_v2.cjs');
const {bucketFor,resample5m,fullSessionRows}=require('../scripts/build_intraday_risk_replay.cjs');

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

test('broad selloff raises market risk and confirms non-extreme alerts on the next snapshot',()=>{
 const firstFixture=fixture({stress:true,sourceTime:'2026-10-05T07:40:00.000Z'});
 const first=buildRiskSnapshot(firstFixture.quotes,firstFixture.strategy,null,'2026-10-05T07:40:10.000Z');
 assert.ok(first.overall.score>=80,first.overall);
 assert.ok(first.components.breadth.score>=65,first.components.breadth);
 assert.ok(first.components.volatility.score>=65,first.components.volatility);
 assert.ok(first.components.liquidity.score>=65,first.components.liquidity);
 assert.ok(first.components.contagion.score>=60,first.components.contagion);
 if(first.overall.score<95)assert.equal(first.alerts.some(x=>x.id==='market-high'),false);
 const secondFixture=fixture({stress:true,sourceTime:'2026-10-05T07:45:00.000Z'});
 const second=buildRiskSnapshot(secondFixture.quotes,secondFixture.strategy,first,'2026-10-05T07:45:10.000Z');
 assert.ok(second.alerts.some(x=>x.id==='market-high'));
 assert.ok(second.alerts.some(x=>x.id==='breadth'));
 assert.equal(second.topRisk[0].reasons.length>0,true);
});

test('isolated stock shock is surfaced without turning into a market-wide alarm',()=>{
 const {quotes,strategy}=fixture();
 const symbol='ACB',q=quotes.quotes[symbol],s=strategy.symbols[symbol];
 q.changePct=-6;q.price=94000;q.reference=100000;q.open=100000;q.high=101000;q.low=93000;q.volume=2600000;
 s.current={...s.current,price:q.price,changePct:q.changePct,volume:q.volume,volumeSma20:1000000,volumeRatio20:2.6,cmf20:-.4,sma20:101000,sma50:103000,atr14:6500};
 const out=buildRiskSnapshot(quotes,strategy,null,'2026-10-05T07:45:10.000Z');
 assert.equal(out.topRisk[0].symbol,symbol);
 assert.ok(out.topRisk[0].score>=80,out.topRisk[0]);
 assert.ok(out.overall.score<50,out.overall);
 assert.equal(out.alerts.some(x=>x.id==='market-high'),false);
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

test('confirmed alerts keep their confirmation time while the condition remains active',()=>{
 const firstFixture=fixture({stress:true,sourceTime:'2026-10-05T07:40:00.000Z'});
 const first=buildRiskSnapshot(firstFixture.quotes,firstFixture.strategy,null,'2026-10-05T07:40:10.000Z');
 const confirmFixture=fixture({stress:true,sourceTime:'2026-10-05T07:45:00.000Z'});
 const confirmed=buildRiskSnapshot(confirmFixture.quotes,confirmFixture.strategy,first,'2026-10-05T07:45:10.000Z');
 const nextFixture=fixture({stress:true,sourceTime:'2026-10-05T07:50:00.000Z'});
 const next=buildRiskSnapshot(nextFixture.quotes,nextFixture.strategy,confirmed,'2026-10-05T07:50:10.000Z');
 const a=next.alerts.find(x=>x.id==='market-high');
 assert.ok(a);
 assert.equal(a.startedAt,'2026-10-05T07:45:00.000Z');
 assert.equal(a.lastSeen,'2026-10-05T07:50:00.000Z');
});


test('first risk snapshot can compare against previous session close',()=>{
 const {quotes,strategy}=fixture();
 const baseline={
  sourceTime:'2026-10-02T07:45:00.000Z',sourceDate:'2026-10-02',score:31.5,level:'normal',
  components:{breadth:35,volatility:28,liquidity:32,concentration:27,contagion:30},
  basis:'previous-session-close',coverage:symbols.length
 };
 const out=buildRiskSnapshot(quotes,strategy,null,'2026-10-05T07:45:10.000Z',baseline);
 assert.equal(out.timeline.length,2);
 assert.equal(out.trend.previousScore,31.5);
 assert.match(out.trend.comparisonLabel,/cuối phiên/);
 assert.notEqual(out.trend.delta,null);
 assert.equal(out.contributions.length,5);
 assert.ok(out.contributions.every(x=>Number.isFinite(x.points)));
});

test('historical baseline is reconstructed from prior daily bars',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'risk-history-'));
 fs.mkdirSync(path.join(dir,'history'),{recursive:true});
 symbols.forEach((symbol,si)=>{
  const bars=[];
  for(let i=0;i<65;i++){
   const d=new Date(Date.UTC(2026,6,1+i)).toISOString().slice(0,10);
   const base=90000+si*1000+i*30;
   bars.push({time:d,open:base-100,high:base+400,low:base-500,close:base,volume:1000000+i*1000});
  }
  fs.writeFileSync(path.join(dir,'history',symbol+'.json'),JSON.stringify({symbol,bars}));
 });
 const baseline=buildHistoricalBaseline(dir,symbols,'2026-10-05');
 assert.ok(baseline);
 assert.equal(baseline.coverage,symbols.length);
 assert.equal(baseline.basis,'previous-session-close');
 assert.ok(Number.isFinite(baseline.score));
 assert.equal(Object.keys(baseline.components).length,5);
 fs.rmSync(dir,{recursive:true,force:true});
});

test('alert history records new and resolved alerts',()=>{
 const firstFixture=fixture({stress:true,sourceTime:'2026-10-05T07:40:00.000Z'});
 const first=buildRiskSnapshot(firstFixture.quotes,firstFixture.strategy,null,'2026-10-05T07:40:10.000Z');
 assert.ok(first.alertHistory.some(x=>x.type==='Bắt đầu'));
 const calmFixture=fixture({stress:false,sourceTime:'2026-10-05T07:45:00.000Z'});
 const calm=buildRiskSnapshot(calmFixture.quotes,calmFixture.strategy,first,'2026-10-05T07:45:10.000Z');
 assert.ok(calm.alertHistory.some(x=>x.type==='Đã hạ'));
});


test('fund monitor compares disclosed weights without inventing share volume',()=>{
 const history={
  snapshots:[
   {asOf:'2026-10-02',weightUnit:'FRACTION_OF_NAV',generatedAt:'2026-10-02T16:00:00+07:00',holdings:[
    {fundCode:'FUND-A',fundName:'Fund A',symbol:'FPT',weight:.08,reportDate:'2026-09-30',navMomentum20:.02},
    {fundCode:'FUND-B',fundName:'Fund B',symbol:'FPT',weight:.04,reportDate:'2026-09-30',navMomentum20:.01},
    {fundCode:'FUND-C',fundName:'Fund C',symbol:'HPG',weight:.05,reportDate:'2026-09-30',navMomentum20:-.01}
   ]},
   {asOf:'2026-10-05',weightUnit:'FRACTION_OF_NAV',generatedAt:'2026-10-05T16:00:00+07:00',holdings:[
    {fundCode:'FUND-A',fundName:'Fund A',symbol:'FPT',weight:.091,reportDate:'2026-10-03',navMomentum20:.025},
    {fundCode:'FUND-D',fundName:'Fund D',symbol:'FPT',weight:.03,reportDate:'2026-10-03',navMomentum20:.015},
    {fundCode:'FUND-C',fundName:'Fund C',symbol:'HPG',weight:.041,reportDate:'2026-10-03',navMomentum20:-.015}
   ]}
  ]
 };
 const out=buildFundMonitor(history);
 assert.equal(out.status,'ok');
 assert.equal(out.asOf,'2026-10-05');
 assert.equal(out.previousAsOf,'2026-10-02');
 assert.ok(out.materialChanges>=4,out);
 const fpt=out.rows.find(x=>x.symbol==='FPT');
 assert.ok(fpt);
 assert.equal(fpt.currentFundCount,2);
 assert.ok(fpt.details.some(x=>x.fundCode==='FUND-A'&&x.status==='increased'&&x.deltaPP===1.1));
 assert.ok(fpt.details.some(x=>x.fundCode==='FUND-B'&&x.status==='removed'));
 assert.ok(fpt.details.some(x=>x.fundCode==='FUND-D'&&x.status==='new'));
 assert.equal(Object.prototype.hasOwnProperty.call(fpt,'shareVolume'),false);
});


test('fund monitor skips repeated polling snapshots and compares the last real holdings change',()=>{
 const history={snapshots:[
  {asOf:'2026-09-11',weightUnit:'FRACTION_OF_NAV',holdings:[
   {fundCode:'F1',symbol:'FPT',weight:.08,reportDate:'2026-09-11'},
   {fundCode:'F2',symbol:'VCB',weight:.05,reportDate:'2026-09-11'}
  ]},
  {asOf:'2026-09-17',weightUnit:'FRACTION_OF_NAV',holdings:[
   {fundCode:'F1',symbol:'FPT',weight:.091,reportDate:'2026-09-17'},
   {fundCode:'F2',symbol:'VCB',weight:.05,reportDate:'2026-09-11'}
  ]},
  {asOf:'2026-09-29',weightUnit:'FRACTION_OF_NAV',holdings:[
   {fundCode:'F1',symbol:'FPT',weight:.091,reportDate:'2026-09-17'},
   {fundCode:'F2',symbol:'VCB',weight:.05,reportDate:'2026-09-11'}
  ]},
  {asOf:'2026-10-05',weightUnit:'FRACTION_OF_NAV',holdings:[
   {fundCode:'F1',symbol:'FPT',weight:.091,reportDate:'2026-09-17'},
   {fundCode:'F2',symbol:'VCB',weight:.05,reportDate:'2026-09-11'}
  ]}
 ]};
 const out=buildFundMonitor(history);
 assert.equal(out.asOf,'2026-10-05');
 assert.equal(out.lastChangedAsOf,'2026-09-17');
 assert.equal(out.previousAsOf,'2026-09-11');
 assert.equal(out.comparisonMode,'LAST_MEANINGFUL_HOLDING_CHANGE');
 const fpt=out.rows.find(x=>x.symbol==='FPT');
 assert.equal(fpt.largestChangePP,1.1);
 assert.equal(fpt.status,'increased');
 const vcb=out.rows.find(x=>x.symbol==='VCB');
 assert.equal(vcb.largestChangePP,0);
 assert.equal(vcb.status,'stable');
});

test('risk snapshot exposes clickable breadth groups and both sector directions',()=>{
 const {quotes,strategy}=fixture();
 const out=buildRiskSnapshot(quotes,strategy,null,'2026-10-05T07:45:10.000Z');
 assert.equal(
  out.breadthGroups.advancing.length+out.breadthGroups.declining.length+out.breadthGroups.unchanged.length,
  out.coverage.quotes
 );
 assert.ok(out.breadthGroups.advancing.every(x=>x.changePct>0));
 assert.ok(out.breadthGroups.declining.every(x=>x.changePct<0));
 assert.ok(out.sectors.every(x=>Number.isFinite(Number(x.advancePct))&&Number.isFinite(Number(x.declinePct))));
});

test('sector calibration finds a stable warning threshold with time-ordered OOS lift',()=>{
 const observations=[];
 for(let i=0;i<600;i++){
  const score=25+(i%70);
  const stressed=score>=65;
  observations.push({
   date:new Date(Date.UTC(2022,0,1+i)).toISOString().slice(0,10),
   score,
   currentMedianPct:stressed?-1.4:-.1,
   forward3Pct:stressed?(-2.2-(i%5)*.15):(-.1+(i%7)*.05)
  });
 }
 const out=calibrateSector('demo','Ngành thử nghiệm',observations);
 assert.equal(out.status,'VALIDATED_STATE');
 assert.equal(out.alertEligible,true);
 assert.ok(out.threshold>=80&&out.threshold<=95,out);
 assert.ok(out.oos.signalRate>=.03&&out.oos.signalRate<=.25,out.oos);
 assert.ok(out.oos.folds>=2,out.oos);
});

test('sector calibration refuses automatic alerts when history is insufficient',()=>{
 const rows=Array.from({length:90},(_,i)=>({date:'2026-01-'+String((i%28)+1).padStart(2,'0'),score:40+i%30,currentMedianPct:-.2,forward3Pct:-.5}));
 const out=calibrateSector('short','Ngành ngắn',rows);
 assert.equal(out.alertEligible,false);
 assert.equal(out.status,'INSUFFICIENT_HISTORY');
});

test('historical and live sector stress use the same score dimensions',()=>{
 const score=stressScore([
  {changePct:-2.1,volumeRatio:1.5},{changePct:-1.2,volumeRatio:1.3},
  {changePct:-.7,volumeRatio:1.1},{changePct:.2,volumeRatio:.9}
 ]);
 assert.ok(score>40&&score<=100,score);
});

test('validated sector threshold creates a separate sector alert without changing total score formula',()=>{
 const {quotes,strategy}=fixture({stress:true});
 const sectorCalibration={
  version:'TEST',status:'ok',forSession:'2026-10-05',validatedSectors:1,totalSectors:1,
  sectors:{banking:{status:'VALIDATED_STATE',alertEligible:true,stateValidated:true,continuationValidated:true,thresholdMode:'HISTORICAL_P90',threshold:20,exitThreshold:12.5,samples:800,forwardSessions:3,adverseCutoffPct:-1.5,oos:{precision:.45,baseRate:.2,precisionLift:2.25,recall:.4,falseAlarmRate:.15,youden:.25,signalRate:.1,folds:3,signals:60,events:40,medianCurrentReturnWhenSignalPct:-1.2,medianForward3WhenSignalPct:-2.1}}}
 };
 const baseline={sourceTime:'2026-10-02T07:45:00.000Z',sourceDate:'2026-10-02',score:31.5,level:'normal',components:{breadth:35,volatility:28,liquidity:32,concentration:27,contagion:30},basis:'previous-session-close',coverage:symbols.length};
 const out=buildRiskSnapshot(quotes,strategy,null,'2026-10-05T07:45:10.000Z',baseline,null,sectorCalibration);
 const bank=out.sectors.find(x=>x.id==='banking');
 assert.ok(bank&&bank.alertEligible&&bank.alertActive,bank);
 assert.ok(Array.isArray(bank.memberRows)&&bank.memberRows.length>=2);
 assert.ok(out.alerts.some(x=>x.id==='sector-banking'&&x.backtestValidated===true),out.alerts);
 assert.equal(out.sectorCalibration.validatedSectors,1);
});


test('sector alert hysteresis is reflected in the sector state shown to the UI',()=>{
 const sectorCalibration={
  version:'TEST',status:'ok',forSession:'2026-10-05',validatedSectors:1,totalSectors:1,
  sectors:{banking:{status:'VALIDATED_STATE',alertEligible:true,stateValidated:true,continuationValidated:false,thresholdMode:'TEST',threshold:20,exitThreshold:12.5,samples:800,forwardSessions:3,adverseCutoffPct:-1.5,oos:{precision:.3,baseRate:.2,precisionLift:1.5,recall:.2,falseAlarmRate:.1,youden:.1,signalRate:.1,folds:3,signals:60,events:40,medianCurrentReturnWhenSignalPct:-1.2,medianForward3WhenSignalPct:0}}}
 };
 const stressed=fixture({stress:true,sourceTime:'2026-10-05T07:40:00.000Z'});
 const first=buildRiskSnapshot(stressed.quotes,stressed.strategy,null,'2026-10-05T07:40:10.000Z',null,null,sectorCalibration);
 const firstBank=first.sectors.find(x=>x.id==='banking');
 assert.ok(firstBank?.alertActive&&firstBank?.aboveThreshold,firstBank);
 const calm=fixture({stress:false,sourceTime:'2026-10-05T07:45:00.000Z'});
 const second=buildRiskSnapshot(calm.quotes,calm.strategy,first,'2026-10-05T07:45:10.000Z',null,null,sectorCalibration);
 const secondBank=second.sectors.find(x=>x.id==='banking');
 assert.ok(second.alerts.some(x=>x.id==='sector-banking'),second.alerts);
 assert.ok(secondBank?.alertActive,secondBank);
 assert.equal(secondBank?.aboveThreshold,false);
 assert.ok(secondBank.score>=12.5&&secondBank.score<20,secondBank);
});

test('intraday replay uses HOSE-aware five-minute buckets and keeps ATC separate',()=>{
 const bars=[
  {time:'2026-10-05T02:15:00+00:00',open:100,high:101,low:99,close:100,volume:10},
  {time:'2026-10-05T02:19:00+00:00',open:100,high:102,low:100,close:101,volume:20},
  {time:'2026-10-05T06:00:00+00:00',open:101,high:103,low:101,close:103,volume:30},
  {time:'2026-10-05T07:45:00+00:00',open:102,high:104,low:102,close:104,volume:40}
 ];
 const out=resample5m(bars);
 assert.equal(out.length,3);
 assert.equal(out[0].time,'2026-10-05T02:20:00.000Z');
 assert.equal(out[0].session,'CONTINUOUS_AM');
 assert.equal(out[0].volume,30);
 assert.equal(out[1].session,'CONTINUOUS_PM');
 assert.equal(out[2].session,'ATC');
 assert.equal(bucketFor('2026-10-05T04:45:00+00:00'),null);
});

test('incomplete intraday sessions are excluded from validation clocks',()=>{
 const morning=[];
 for(let i=0;i<27;i++)morning.push({time:new Date(Date.UTC(2026,9,6,2,20+i*5)).toISOString()});
 const full=[...morning];
 for(let i=0;i<18;i++)full.push({time:new Date(Date.UTC(2026,9,6,6,5+i*5)).toISOString()});
 full.push({time:'2026-10-06T07:45:00.000Z'});
 assert.equal(fullSessionRows(morning),false);
 assert.equal(fullSessionRows(full),true);
});

test('intraday trading-time normalization is monotonic and bounded',()=>{
 assert.equal(sessionProgress('2026-10-05T01:55:00.000Z'),0);
 const open=sessionProgress('2026-10-05T02:15:00.000Z');
 const lateMorning=sessionProgress('2026-10-05T04:00:00.000Z');
 const afternoon=sessionProgress('2026-10-05T07:00:00.000Z');
 assert.ok(open>0&&open<lateMorning&&lateMorning<afternoon&&afternoon<1,{open,lateMorning,afternoon});
 assert.equal(sessionProgress('2026-10-05T07:45:00.000Z'),1);
});

test('turnover concentration alone cannot create market stress when breadth is healthy',()=>{
 const rows=[];
 for(let i=0;i<20;i++)rows.push({symbol:'X'+i,price:100+i,volume:i<5?1_000_000:10_000,change:i%2===0?.2:-.2,rangePct:.6,atrPct:1.8,volumeRatio:1,cmf:0,sma20:100,sma50:100});
 const sectors=sectorRowsV2(rows,null,'2026-10-05T07:45:00.000Z');
 const raw=rawComponents(rows,sectors,'2026-10-05T07:45:00.000Z',{});
 assert.ok(raw.breadth.raw<20,raw.breadth);
 assert.equal(raw.concentration.raw,0);
});

test('historical calibration maps component scores and overall score into percentile space',()=>{
 const observations=[];
 for(let i=0;i<300;i++)observations.push({raw:{
  breadth:{raw:i%101},volatility:{raw:(i*2)%101},liquidity:{raw:(i*3)%101},concentration:{raw:(i*5)%101},contagion:{raw:(i*7)%101}
 }});
 const cal=calibrationFromObservations(observations);
 const comps=calibratedComponents({breadth:{raw:90},volatility:{raw:85},liquidity:{raw:80},concentration:{raw:70},contagion:{raw:88}},cal);
 const total=overallV2(comps,cal);
 assert.ok(total.score>=0&&total.score<=100,total);
 assert.ok(comps.breadth.score>50,comps.breadth);
});

test('risk method copy is plain-language and versioned to refresh cached snapshots',()=>{
 const {quotes,strategy}=fixture();
 const out=buildRiskSnapshot(quotes,strategy,null,'2026-10-05T07:45:10.000Z');
 assert.equal(out.methodVersion,'FINQUERY-RISK-RULES-2.0');
 assert.doesNotMatch(out.methodology.alertRule,/hysteresis|ngoài mẫu|OOS/i);
 assert.match(out.methodology.alertRule,/chỉ tắt sau khi hạ xuống mức an toàn hơn/);
});
