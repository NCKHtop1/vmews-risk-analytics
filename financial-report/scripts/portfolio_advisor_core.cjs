'use strict';
/* Portfolio Advisor: reproducible completed-EOD research; NO order execution.
 * The five signals reuse Strategy Engine presets. Scores are NOT return probabilities.
 * Historical evaluation must be labeled survivorship/adjustment-limited.
 */
const MathCore=require('../frontend/chart-math.js');
const Engine=require('../frontend/strategy-engine.js');
const VERSION='FINQUERY-PORTFOLIO-ADVISOR-RESEARCH-1.0';
const PROFILES=Object.freeze({
 defensive:{label:'Thận trọng',minNames:5,maxNames:8,targetCashPct:40,maxStockPct:12,maxSectorPct:30,maxVol:.50},
 balanced:{label:'Cân bằng',minNames:4,maxNames:8,targetCashPct:20,maxStockPct:18,maxSectorPct:38,maxVol:.75},
 growth:{label:'Tăng trưởng',minNames:4,maxNames:8,targetCashPct:10,maxStockPct:22,maxSectorPct:45,maxVol:1.10}
});
const STRATEGIES=Object.freeze(['breakout_volume','ema_adx','macd_rsi','momentum_recovery','bollinger_rebound']);
const num=x=>x===null||x===undefined||x===''?null:(Number.isFinite(Number(x))?Number(x):null);
const round=(x,n=2)=>Number(x.toFixed(n));
function ema(bars,period,index){
 let v=bars[0].close,alpha=2/(period+1);
 for(let i=1;i<=index;i++)v+=alpha*(bars[i].close-v);
 return v;
}
function volatility(bars,index,n=60){
 if(index<n)return null;
 const ret=[];
 for(let i=index-n+1;i<=index;i++){
  const before=bars[i-1].close,now=bars[i].close;
  if(before<=0||now<=0)return null;
  ret.push(Math.log(now/before));
 }
 const mean=ret.reduce((a,b)=>a+b,0)/ret.length;
 const sd=Math.sqrt(ret.reduce((a,b)=>a+(b-mean)**2,0)/(ret.length-1));
 return sd*Math.sqrt(252);
}
function featuresFor(stock,asOf){
 if(!/^[A-Z0-9]{2,12}$/.test(stock.symbol||''))return null;
 const bars=MathCore.cleanBars(stock.bars||[],false).filter(b=>b.time<=asOf);
 const last=bars.at(-1);
 if(!last||last.time!==asOf||bars.length<210)return null;
 const idx=bars.length-1;
 const indicators=MathCore.indicators(bars.slice(-300),{
  sma:20,ema:20,wma:20,vwma:20,rsi:14,fast:12,slow:26,signal:9,
  bb:20,vma:20,atr:14,adx:14,stoch:14,stochSignal:3,cci:20,
  roc:10,willr:14,mfi:14,cmf:20,supertrend:10,supertrendFactor:3,deviation:2
 });
 const cur=indicators.at(-1),prev=indicators.at(-2);
 if(!cur||!prev)return null;
 const series=bars.slice(-300),j=series.length-1;
 function pack(ind,k){
  const bar=series[k], bbSpan=num(ind.upper)!==null&&num(ind.lower)!==null?ind.upper-ind.lower:null;
  return {
   price:bar.close,sma20:ind.sma,sma50:MathCore.average(series,k,50),
   ema9:ema(series,9,k),ema20:ema(series,20,k),ema50:ema(series,50,k),
   adx14:ind.adx,rsi14:ind.rsi,macd:ind.macd,macdSignal:ind.signal,
   macdHistogram:ind.hist,volumeRatio20:ind.vma>0?bar.volume/ind.vma:null,
   roc10:ind.roc,bbPctB:bbSpan>0?(bar.close-ind.lower)/bbSpan:null
  };
 }
 const current=pack(cur,j),previous=pack(prev,j-1);
 const vol=volatility(bars,idx);
 const liquidity=bars.slice(-20).reduce((a,b)=>a+b.close*b.volume,0)/20;
 if(num(vol)===null||!Number.isFinite(liquidity))return null;
 const row={symbol:stock.symbol,tier:'CORE',current,previous};
 const matched=STRATEGIES.filter(id=>Engine.PRESETS[id]&&Engine.evaluateStrategy(row,Engine.PRESETS[id]));
 const momentum=num(current.roc10)||0;
 const trend=num(current.sma50)>0?100*(current.price/current.sma50-1):0;
 const score=Math.max(0,Math.min(100,Math.round(40+10*Math.min(3,matched.length)+
   Math.max(-10,Math.min(10,momentum))+.5*Math.max(-10,Math.min(10,trend))-
   Math.max(0,vol-.30)*15)));
 return {
  symbol:stock.symbol,sectorId:stock.sectorId||null,price:current.price,
  barDate:last.time,turnoverVnd:Math.round(liquidity),volatility:round(vol,4),
  score,matchedStrategies:matched,indicatorBasis:'COMPLETED_DAILY_BAR'
 };
}
function candidatesAt(stocks,asOf,options={}){
 const minimumTurnover=options.minimumTurnoverVnd??3000000000;
 const eligible=[],counts={input:stocks.length,historyReady:0,liquid:0,withSignal:0,classified:0};
 for(const stock of stocks){
  const p=featuresFor(stock,asOf);if(!p)continue;
  counts.historyReady++;
  if(p.turnoverVnd<minimumTurnover)continue;
  counts.liquid++;
  if(!p.sectorId)continue;
  counts.classified++;
  if(!p.matchedStrategies.length)continue;
  counts.withSignal++;
  eligible.push(p);
 }
 eligible.sort((a,b)=>b.score-a.score||a.symbol.localeCompare(b.symbol));
 return {eligible,counts};
}
function modelFor(profileName,items){
 const config=PROFILES[profileName];if(!config)throw Error('UNKNOWN_PROFILE');
 const filter=items.filter(p=>p.volatility<=config.maxVol);
 const chosen=[],sectorCount=new Map();
 for(const item of filter){
  if(chosen.length===config.maxNames)break;
  const count=sectorCount.get(item.sectorId)||0;
  if(count>=3)continue;
  chosen.push(item);sectorCount.set(item.sectorId,count+1);
 }
 if(chosen.length<config.minNames)return {
  profile:profileName,label:config.label,status:'INSUFFICIENT_SIGNALS',positions:[],
  cashPct:100,why:'Khong du ma dap ung dong thoi tin hieu, thanh khoan va gioi han rui ro.',
  qualifiedCount:filter.length,required:config.minNames
 };
 // Cap each sector; underallocated equity remains in cash, never forced elsewhere.
 const desiredEquity=100-config.targetCashPct,raw=desiredEquity/chosen.length;
 const capped=chosen.map(x=>{
  const s=sectorCount.get(x.sectorId);
  return {...x,weightPct:Math.min(raw,config.maxStockPct,config.maxSectorPct/s)};
 });
 const total=round(capped.reduce((a,x)=>a+x.weightPct,0),4);
 if(total>desiredEquity+.00001)throw Error('EQUITY_OVERALLOCATED');
 if(capped.some(p=>p.weightPct>config.maxStockPct+.001))throw Error('STOCK_LIMIT_BROKEN');
 const sectors=new Map();
 for(const x of capped)sectors.set(x.sectorId,(sectors.get(x.sectorId)||0)+x.weightPct);
 for(const v of sectors.values())if(v>config.maxSectorPct+.001)throw Error('SECTOR_LIMIT_BROKEN');
 return {
  profile:profileName,label:config.label,status:'RESEARCH_ONLY',
  positions:capped.map(x=>({
   symbol:x.symbol,sectorId:x.sectorId,weightPct:round(x.weightPct,3),score:x.score,
   turnoverVnd:x.turnoverVnd,volatility:x.volatility,price:x.price,
   matchedStrategies:x.matchedStrategies
  })),
  cashPct:round(100-total,3),targetCashPct:config.targetCashPct,
  maxStockPct:config.maxStockPct,maxSectorPct:config.maxSectorPct,
  qualifiedCount:filter.length,reviewFrequency:'WEEKLY_OR_MONTHLY_USER_SELECTED',
  note:'Research model only. No predicted return or automatic trading.'
 };
}
function vnDate(iso){
 const d=new Date(iso);if(!Number.isFinite(d.getTime()))return null;
 const p=Object.fromEntries(new Intl.DateTimeFormat('en-US',{
  timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit',
  hour:'2-digit',minute:'2-digit',hourCycle:'h23'
 }).formatToParts(d).map(x=>[x.type,x.value]));
 return {date:p.year+'-'+p.month+'-'+p.day,hour:Number(p.hour),minute:Number(p.minute)};
}
function build(input){
 const asOf=input.asOf,clock=vnDate(input.generatedAt||new Date().toISOString());
 if(!/^\d{4}-\d{2}-\d{2}$/.test(asOf||'')||!clock)throw Error('INVALID_DATES');
 const base={version:VERSION,asOf,generatedAt:input.generatedAt||new Date().toISOString(),
  status:'BLOCKED',publication:'RESEARCH_ONLY',source:{history:'financial-market-data/history',
   quoteDate:input.quoteDate||null,riskDate:input.riskDate||null},
  warnings:['Current-listing survivorship bias; corporate-action adjustments not certified.',
   'Five technical presets are not calibrated expected-return probabilities.',
   'No trading orders or user holdings are generated by this public snapshot.']};
 const opts=input.options||{};
 const earliest=Date.parse(asOf+'T00:00:00Z');
 const today=Date.parse(clock.date+'T00:00:00Z');
 if(asOf>clock.date||clock.date===asOf&&clock.hour<16)
  return {...base,reason:'SESSION_NOT_CLOSED',models:{}};
 if((today-earliest)/86400000>4)
  return {...base,reason:'STALE_EOD',models:{}};
 if(input.riskDate!==asOf||input.quoteDate!==asOf)
  return {...base,reason:'SOURCE_DATE_MISMATCH',models:{}};
 const stocks=Array.isArray(input.stocks)?input.stocks:[];
 const {eligible,counts}=candidatesAt(stocks,asOf,opts);
 base.coverage=counts;
 const minimumHistory=opts.minimumHistoryReady??60;
 if(counts.historyReady<minimumHistory)return {...base,reason:'INSUFFICIENT_COMPLETE_HISTORY',models:{}};
 const models=Object.fromEntries(Object.keys(PROFILES).map(k=>[k,modelFor(k,eligible)]));
 const healthy=Object.values(models).filter(x=>x.status==='RESEARCH_ONLY').length;
 return {...base,status:healthy?'RESEARCH_ONLY':'BLOCKED',
  reason:healthy?null:'NO_DIVERSIFIED_MODEL',eligibleCount:eligible.length,
  models,selectedUniverse:stocks.length,quality:{
   historyCoveragePct:round(100*counts.historyReady/Math.max(1,stocks.length)),
   completeEodOnly:true,liquidityGateVnd:opts.minimumTurnoverVnd??3000000000,
   noLookAhead:true,missingSignalsNotZero:true
  }};
}
module.exports={VERSION,PROFILES,STRATEGIES,featuresFor,candidatesAt,modelFor,vnDate,build};
