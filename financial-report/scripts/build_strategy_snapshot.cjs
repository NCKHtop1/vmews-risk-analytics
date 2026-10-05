#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),path=require('node:path');
const math=require('../frontend/chart-math.js');
const out=path.resolve(process.argv[2]||'financial-report/market');
const read=(p,d={})=>{try{return JSON.parse(fs.readFileSync(p,'utf8'));}catch{return d;}};
const write=(p,x)=>{fs.mkdirSync(path.dirname(p),{recursive:true});fs.writeFileSync(p,JSON.stringify(x));};
const num=v=>Number.isFinite(Number(v))?Number(v):null;
function emaValues(bars,period){
 let value=null,out=[];
 const k=2/(period+1);
 for(const b of bars){const c=num(b.close);value=value===null?c:value+k*(c-value);out.push(value);}
 return out;
}
function smaAt(bars,n,i=bars.length-1,key='close'){if(i<n-1)return null;let s=0;for(let j=i-n+1;j<=i;j++){const v=num(bars[j]?.[key]);if(v===null)return null;s+=v;}return s/n;}
function currentChange(bars,i){if(i<1)return null;const a=num(bars[i-1]?.close),b=num(bars[i]?.close);return a&&b?(b/a-1)*100:null;}
function normalizeBars(rows){
 return (rows||[]).map(b=>({time:b.time,open:num(b.open),high:num(b.high),low:num(b.low),close:num(b.close),volume:Math.max(0,num(b.volume)||0)})).filter(math.validBar);
}
const universe=read(path.join(out,'universe.json'),{}),canonical=read(path.resolve(process.argv[3]||'financial-report/data/universe.json'),{}),quotes=read(path.join(out,'quotes.json'),{}),old=read(path.join(out,'strategy-indicators.json'),{symbols:{}});
const records=universe.symbols||canonical.symbols||{},discoveryTechnical=universe.discoveryTechnical||canonical.discoveryTechnical||{},files=fs.existsSync(path.join(out,'history'))?fs.readdirSync(path.join(out,'history')).filter(f=>f.endsWith('.json')):[];
const symbols={};
for(const file of files){
 const symbol=path.basename(file,'.json').toUpperCase(),bars=normalizeBars(read(path.join(out,'history',file),{}).bars);
 if(bars.length<35)continue;
 const meta=records[symbol]||{},tier=String(meta.tier||meta.marketTier||'DISCOVERY').toUpperCase();
 const recent=bars.slice(-420),rows=math.indicators(recent,{sma:20,ema:20,wma:20,vwma:20,rsi:14,fast:12,slow:26,signal:9,bb:20,vma:20,atr:14,adx:14,stoch:14,stochSignal:3,cci:20,roc:10,willr:14,mfi:14,cmf:20,supertrend:10,supertrendFactor:3,deviation:2});
 if(rows.length<2)continue;
 const e9=emaValues(recent,9),e20=emaValues(recent,20),e50=emaValues(recent,50),i=recent.length-1,base=rows.at(-1),prevBase=rows.at(-2),q=quotes.quotes?.[symbol]||{};
 const pack=(idx,row)=>{const b=recent[idx],close=num(q.price)&&idx===i?num(q.price):num(b.close),bbSpan=num(row.upper)!==null&&num(row.lower)!==null?num(row.upper)-num(row.lower):null;return{
  price:close,
  changePct:idx===i&&num(q.changePct)!==null?num(q.changePct):currentChange(recent,idx),
  sma20:smaAt(recent,20,idx),sma50:smaAt(recent,50,idx),sma200:smaAt(recent,200,idx),
  ema9:e9[idx],ema20:e20[idx],ema50:e50[idx],vwma20:num(row.vwma),
  supertrend:num(row.supertrend),supertrendDir:num(row.supertrendDir),adx14:num(row.adx),
  rsi14:num(row.rsi),macd:num(row.macd),macdSignal:num(row.signal),macdHistogram:num(row.hist),
  stochK:num(row.stoch),stochD:num(row.stochSignal),cci20:num(row.cci),roc10:num(row.roc),willr14:num(row.willr),mfi14:num(row.mfi),
  bbUpper:num(row.upper),bbMiddle:num(row.middle),bbLower:num(row.lower),bbPctB:bbSpan?((close-num(row.lower))/bbSpan):null,atr14:num(row.atr),
  volume:num(b.volume),volumeSma20:num(row.vma),volumeRatio20:num(row.vma)>0?num(b.volume)/num(row.vma):null,
  obv:num(row.obv),obvSlope5:idx>=5&&num(rows[idx-5]?.obv)!==null?num(row.obv)-num(rows[idx-5].obv):null,cmf20:num(row.cmf)
 };};
 const current=pack(i,base),dailyPrevious=pack(i-1,prevBase),oldRow=old.symbols?.[symbol],barDate=recent[i].time;
 const currentSourceTime=q.sourceTime||q.collectedAt||null;
 const sameLiveBar=oldRow&&oldRow.barDate===barDate&&oldRow.current&&tier!=='DISCOVERY';
 const sameMarketSnapshot=sameLiveBar&&currentSourceTime&&String(oldRow.sourceTime||'')===String(currentSourceTime);
 const previous=sameLiveBar?(sameMarketSnapshot&&oldRow.previous?oldRow.previous:oldRow.current):dailyPrevious;
 symbols[symbol]={symbol,tier,cadence:tier==='DISCOVERY'?'EOD':'LIVE_15M',barDate,sourceTime:currentSourceTime,current,previous};
}
// Discovery names are intentionally EOD-only in the market branch. Merge their
// validated technical snapshot so Strategy Lab can scan the full HOSE universe
// without fabricating indicators that are not available for those names.
for(const [symbol,d] of Object.entries(discoveryTechnical)){
 if(symbols[symbol]||!d)continue;
 const current={
  price:num(d.price),changePct:num(d.changePct),rsi14:num(d.rsi14),
  macd:num(d.macd),macdSignal:num(d.macdSignal),macdHistogram:num(d.macdHistogram),
  volume:num(d.volume),volumeSma20:num(d.averageVolume20),volumeRatio20:num(d.volumeRatio20)
 };
 const previous={
  price:null,changePct:null,rsi14:num(d.previousRsi14),
  macd:null,macdSignal:null,macdHistogram:num(d.previousMacdHistogram),
  volume:null,volumeSma20:null,volumeRatio20:null
 };
 symbols[symbol]={symbol,tier:'DISCOVERY',cadence:'EOD',barDate:d.barDate||null,sourceTime:null,current,previous,partial:true};
}
const rows=Object.values(symbols),payload={
 version:'FINQUERY-STRATEGY-SNAPSHOT-1.0',
 checkedAt:new Date().toISOString(),
 sourceTime:quotes.latestSourceTime||null,
 status:rows.length?'ok':'empty',
 library:'FinChartMath · pandas-ta compatible indicator set',
 coverage:rows.length,
 liveCoverage:rows.filter(x=>x.cadence==='LIVE_15M').length,
 discoveryCoverage:rows.filter(x=>x.cadence==='EOD').length,
 symbols
};
write(path.join(out,'strategy-indicators.json'),payload);
console.log(JSON.stringify({status:payload.status,coverage:payload.coverage,live:payload.liveCoverage,discovery:payload.discoveryCoverage,sourceTime:payload.sourceTime}));
