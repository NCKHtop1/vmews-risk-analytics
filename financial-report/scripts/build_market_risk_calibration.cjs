'use strict';

const fs=require('fs'),path=require('path');
const {
 SECTORS,avg,median,quantile,correlation,sectorRowsV2,rawComponents,
 calibrationFromObservations,calibratedComponents,overallFromComponents,round
}=require('./risk_model_v2.cjs');

const VERSION='FINQUERY-MARKET-RISK-CAL-2.0';
const MIN_HISTORY=252;
const TRAIN_WINDOW=504;
const MAX_DAYS=900;
const FORWARD_SESSIONS=3;

const num=v=>Number.isFinite(Number(v))?Number(v):null;
function cmf20(bars,i){
 const from=Math.max(0,i-19);let mfv=0,vol=0;
 for(let j=from;j<=i;j++){
  const b=bars[j],h=num(b.high),l=num(b.low),c=num(b.close),v=num(b.volume)||0;
  if(h===null||l===null||c===null||v<=0)continue;
  const mult=h>l?((c-l)-(h-c))/(h-l):0;
  mfv+=mult*v;vol+=v;
 }
 return vol>0?mfv/vol:0;
}
function atr14(bars,i){
 const vals=[];
 for(let j=Math.max(1,i-13);j<=i;j++){
  const b=bars[j],p=bars[j-1];
  const h=num(b.high),l=num(b.low),pc=num(p?.close);
  if(h===null||l===null||pc===null)continue;
  vals.push(Math.max(h-l,Math.abs(h-pc),Math.abs(l-pc)));
 }
 return vals.length?avg(vals):0;
}
function sma(bars,i,len,key='close'){
 const vals=[];
 for(let j=Math.max(0,i-len+1);j<=i;j++){const v=num(bars[j]?.[key]);if(v!==null)vals.push(v);}
 return vals.length>=Math.max(2,Math.floor(len*.7))?avg(vals):null;
}
function loadSymbolFeatures(file,cutoffDay){
 let data;try{data=JSON.parse(fs.readFileSync(file,'utf8'));}catch{return new Map();}
 const bars=(data.bars||[]).filter(x=>x&&x.time&&String(x.time)<String(cutoffDay));
 const out=new Map();
 for(let i=50;i<bars.length;i++){
  const b=bars[i],prev=bars[i-1];
  const close=num(b.close),prevClose=num(prev?.close),high=num(b.high),low=num(b.low),volume=num(b.volume)||0;
  if(!close||!prevClose||high===null||low===null)continue;
  const priorVol=avg(bars.slice(i-20,i).map(x=>num(x.volume)||0));
  const change=(close/prevClose-1)*100;
  const rangePct=Math.max(0,(high-low)/prevClose*100);
  const atr=atr14(bars,i);
  out.set(String(b.time),{
   symbol:String(data.symbol||path.basename(file,'.json')).toUpperCase(),
   price:close,reference:prevClose,change,volume,
   rangePct,atrPct:close>0?atr/close*100:0,
   volumeRatio:priorVol>0?volume/priorVol:0,
   cmf:cmf20(bars,i),sma20:sma(bars,i,20),sma50:sma(bars,i,50)
  });
 }
 return out;
}
function pairwiseDownsideCorrelation(history){
 if(!Array.isArray(history)||history.length<20)return null;
 const keys=SECTORS.map(x=>x.id);
 const pairs=[];
 for(let a=0;a<keys.length;a++)for(let b=a+1;b<keys.length;b++){
  const xs=[],ys=[];
  for(const row of history){
   const x=num(row.sectors?.[keys[a]]),y=num(row.sectors?.[keys[b]]);
   if(x!==null&&y!==null){xs.push(x);ys.push(y);}
  }
  const c=correlation(xs,ys);if(c!==null)pairs.push(c);
 }
 return pairs.length?avg(pairs):null;
}
function buildObservations(marketDir,cutoffDay){
 const histDir=path.join(marketDir,'history');
 const files=fs.readdirSync(histDir).filter(x=>x.endsWith('.json'));
 const maps=new Map(),dates=new Set();
 for(const file of files){
  const map=loadSymbolFeatures(path.join(histDir,file),cutoffDay);
  if(!map.size)continue;
  const symbol=path.basename(file,'.json').toUpperCase();
  maps.set(symbol,map);
  for(const d of map.keys())dates.add(d);
 }
 const allDates=[...dates].sort();
 const selected=allDates.slice(-MAX_DAYS);
 const dateIndex=new Map(selected.map((d,i)=>[d,i]));
 const sectorHistory=[],observations=[];
 const sectorById=new Map(SECTORS.map(x=>[x.id,x]));
 for(const date of selected){
  const rows=[];
  for(const [symbol,map] of maps){
   const r=map.get(date);if(r)rows.push({...r,symbol});
  }
  if(rows.length<80)continue;
  const by=new Map(rows.map(x=>[x.symbol,x]));
  const sectorReturns={};
  for(const [id,group] of sectorById){
   const vals=group.symbols.map(s=>by.get(s)?.change).filter(Number.isFinite);
   if(vals.length>=2)sectorReturns[id]=median(vals);
  }
  const marketMed=median(rows.map(x=>x.change));
  const priorDown=sectorHistory.filter(x=>x.marketReturn<0).slice(-80);
  const downsideCorrelation=pairwiseDownsideCorrelation(priorDown);
  const sourceTime=date+'T14:45:00+07:00';
  const sectors=sectorRowsV2(rows,null,sourceTime);
  const raw=rawComponents(rows,sectors,sourceTime,{downsideCorrelation});
  sectorHistory.push({date,marketReturn:marketMed,sectors:sectorReturns});
  observations.push({date,coverage:rows.length,marketReturn:round(marketMed,4),sectors:sectorReturns,downsideCorrelation,raw});
 }
 for(let i=0;i<observations.length;i++){
  let wealth=1,count=0;
  for(let k=1;k<=FORWARD_SESSIONS;k++){
   const r=num(observations[i+k]?.marketReturn);if(r===null)break;
   wealth*=1+r/100;count++;
  }
  observations[i].forward3Pct=count===FORWARD_SESSIONS?round((wealth-1)*100,4):null;
 }
 return observations;
}
function metrics(rows,threshold){
 let tp=0,fp=0,tn=0,fn=0,signals=0,events=0;
 for(const r of rows){
  const signal=Number(r.score)>=threshold,event=r.event===true;
  if(signal)signals++;if(event)events++;
  if(signal&&event)tp++;else if(signal&&!event)fp++;else if(!signal&&event)fn++;else tn++;
 }
 const precision=tp+fp?tp/(tp+fp):0,recall=tp+fn?tp/(tp+fn):0,fpr=fp+tn?fp/(fp+tn):0,base=rows.length?events/rows.length:0;
 const signalRows=rows.filter(x=>x.score>=threshold);
 const medianCurrentAll=rows.length?median(rows.map(x=>x.marketReturn)):null;
 const medianCurrentSignal=signalRows.length?median(signalRows.map(x=>x.marketReturn)):null;
 const medianForwardAll=rows.length?median(rows.map(x=>x.forward3Pct)):null;
 const medianForwardSignal=signalRows.length?median(signalRows.map(x=>x.forward3Pct)):null;
 return{
  threshold,total:rows.length,signals,events,tp,fp,tn,fn,
  precision:round(precision,4),recall:round(recall,4),falseAlarmRate:round(fpr,4),
  baseRate:round(base,4),precisionLift:round(base>0?precision/base:0,3),youden:round(recall-fpr,4),
  signalRate:round(rows.length?signals/rows.length:0,4),
  medianCurrentAllPct:medianCurrentAll===null?null:round(medianCurrentAll,3),
  medianCurrentSignalPct:medianCurrentSignal===null?null:round(medianCurrentSignal,3),
  currentStateGapPct:medianCurrentAll===null||medianCurrentSignal===null?null:round(medianCurrentSignal-medianCurrentAll,3),
  medianForwardAllPct:medianForwardAll===null?null:round(medianForwardAll,3),
  medianForwardSignalPct:medianForwardSignal===null?null:round(medianForwardSignal,3),
  forwardMedianGapPct:medianForwardAll===null||medianForwardSignal===null?null:round(medianForwardSignal-medianForwardAll,3)
 };
}
function scoreBandStats(rows){
 const specs=[
  {key:'normal',lo:-Infinity,hi:70},
  {key:'watch',lo:70,hi:85},
  {key:'high',lo:85,hi:95},
  {key:'veryHigh',lo:95,hi:Infinity}
 ];
 const out={};
 for(const spec of specs){
  const x=(rows||[]).filter(r=>Number(r.score)>=spec.lo&&Number(r.score)<spec.hi);
  const events=x.filter(r=>r.event===true).length;
  out[spec.key]={
   count:x.length,
   medianCurrentPct:x.length?round(median(x.map(r=>r.marketReturn)),3):null,
   medianForward3Pct:x.length?round(median(x.map(r=>r.forward3Pct)),3):null,
   adverseRate:x.length?round(events/x.length,4):null
  };
 }
 return out;
}
function walkForward(observations){
 const scored=[];
 for(let i=MIN_HISTORY;i<observations.length-FORWARD_SESSIONS;i++){
  const current=observations[i];
  if(!Number.isFinite(Number(current.forward3Pct)))continue;
  const train=observations.slice(Math.max(0,i-TRAIN_WINDOW),i).filter(x=>x.raw&&Number.isFinite(Number(x.forward3Pct)));
  if(train.length<MIN_HISTORY)continue;
  const cal=calibrationFromObservations(train);
  const components=calibratedComponents(current.raw,cal);
  const overall=overallFromComponents(components,cal);
  const adverse=Math.min(-1,Number(quantile(train.map(x=>x.forward3Pct),.20)??-1));
  scored.push({date:current.date,score:overall.score,marketReturn:current.marketReturn,forward3Pct:current.forward3Pct,event:current.forward3Pct<=adverse,adverseCutoffPct:round(adverse,3)});
 }
 const thresholds=[70,85,95].map(t=>metrics(scored,t));
 return{scored,thresholds,stateBands:scoreBandStats(scored)};
}
function buildCalibration(marketDir,forSession){
 const obs=buildObservations(marketDir,forSession);
 if(obs.length<MIN_HISTORY+FORWARD_SESSIONS)throw new Error('Insufficient market history for risk calibration: '+obs.length);
 const usable=obs.filter(x=>x.raw).slice(-TRAIN_WINDOW);
 const calibration=calibrationFromObservations(usable);
 const wf=walkForward(obs);
 const high=wf.thresholds.find(x=>x.threshold===85);
 const bands=wf.stateBands||{};
 const bandOrder=['normal','watch','high','veryHigh'];
 const bandMedians=bandOrder.map(k=>num(bands[k]?.medianCurrentPct));
 const bandCounts=bandOrder.map(k=>Number(bands[k]?.count)||0);
 const stateMonotonic=bandMedians.every(Number.isFinite)&&bandCounts.every(x=>x>=20)&&
  bandMedians[0]>bandMedians[1]&&bandMedians[1]>bandMedians[2]&&bandMedians[2]>bandMedians[3];
 const stateValidated=Boolean(
  high&&high.total>=180&&high.signals>=12&&stateMonotonic&&
  Number.isFinite(Number(high.currentStateGapPct))&&Number(high.currentStateGapPct)<=-0.40&&
  Number(high.signalRate)>=.05&&Number(high.signalRate)<=.25
 );
 const continuationValidated=Boolean(
  stateValidated&&high.precisionLift>=1.10&&high.youden>0&&
  Number.isFinite(Number(high.forwardMedianGapPct))&&Number(high.forwardMedianGapPct)<0
 );
 const recentDown=obs.filter(x=>x.marketReturn<0).slice(-80);
 const downsideCorrelation=pairwiseDownsideCorrelation(recentDown);
 return{
  version:VERSION,status:stateValidated?'ok':'limited',forSession,generatedAt:new Date().toISOString(),
  cutoffPolicy:'ONLY_DAILY_BARS_BEFORE_CURRENT_SESSION',
  samples:obs.length,trainingSamples:usable.length,
  componentGrids:calibration.componentGrids,overallBaseGrid:calibration.overallBaseGrid,
  fragilityContext:{downsideCorrelation:downsideCorrelation===null?null:round(downsideCorrelation,4),downsideSamples:recentDown.length},
  backtest:{
   status:stateValidated?'VALIDATED_STATE':'LIMITED_STATE',stateValidated,stateMonotonic,continuationValidated,walkForwardSamples:wf.scored.length,forwardSessions:FORWARD_SESSIONS,stateBands:wf.stateBands,
   adverseDefinition:'rolling prior-history 20th percentile of forward 3-session market return, capped at -1%',
   thresholds:wf.thresholds
  },
  methodology:{
   normalization:'Intraday price range and return are scaled by square-root trading-time; volume uses a parameter-free U-shaped activity clock. This removes the strongest partial-session bias without claiming a fitted HOSE intraday curve that the repository does not yet contain.',
   breadth:'Cross-sectional decline share, severe standardized losses and median standardized return.',
   volatility:'Maturity-adjusted intraday range, ATR/price regime and share of unusually wide ranges.',
   liquidity:'Downside volume pace, downside high-volume breadth, return-per-volume price-impact proxy and negative CMF breadth.',
   fragility:'Downside sector synchronization combined with rolling downside sector correlation.',
   concentration:'Turnover concentration is multiplied by breadth weakness and active-trading coverage, so concentration alone cannot create market stress.',
   score:'Each component is mapped to its own historical empirical distribution; the weighted composite is mapped again to its historical distribution.'
  }
 };
}
function main(){
 const marketDir=path.resolve(process.argv[2]||'');
 if(!process.argv[2])throw new Error('Usage: node build_market_risk_calibration.cjs <market-dir>');
 const q=JSON.parse(fs.readFileSync(path.join(marketDir,'quotes.json'),'utf8'));
 const value=q.latestSourceTime||q.sourceTime||new Date().toISOString();
 const forSession=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));
 const output=path.join(marketDir,'market-risk-calibration.json');
 try{
  const old=JSON.parse(fs.readFileSync(output,'utf8'));
  if(old?.version===VERSION&&old?.forSession===forSession&&old?.status==='ok'){
   console.log(JSON.stringify({status:old.status,reused:true,forSession,samples:old.samples,backtest:old.backtest?.thresholds}));
   return;
  }
 }catch{}
 const result=buildCalibration(marketDir,forSession);
 fs.writeFileSync(output,JSON.stringify(result));
 console.log(JSON.stringify({status:result.status,reused:false,forSession,samples:result.samples,trainingSamples:result.trainingSamples,fragilityContext:result.fragilityContext,backtest:result.backtest}));
 if(result.status!=='ok')process.exitCode=2;
}
if(require.main===module)main();
module.exports={VERSION,loadSymbolFeatures,pairwiseDownsideCorrelation,buildObservations,metrics,scoreBandStats,walkForward,buildCalibration};
