'use strict';

const fs=require('fs'),path=require('path');
const {
  SECTORS,median,avg,round,sectorRowsV2,rawComponents,calibrationFromObservations,
  calibratedComponents,overallFromComponents,maturityFactors
}=require('./risk_model_v2.cjs');
const {buildObservations,pairwiseDownsideCorrelation}=require('./build_market_risk_calibration.cjs');

const MIN_REPLAY_SYMBOLS=80;
const MIN_VALIDATED_DAYS=40;
const MIN_EVENT_DAYS=8;

const num=v=>Number.isFinite(Number(v))?Number(v):null;
function shifted(value){
  const d=new Date(value); if(!Number.isFinite(d.getTime()))return null;
  return new Date(d.getTime()+7*3600*1000);
}
function localParts(value){
  const d=shifted(value); if(!d)return null;
  return {day:d.toISOString().slice(0,10),hour:d.getUTCHours(),minute:d.getUTCMinutes()};
}
function isoFromLocal(day,minuteOfDay){
  const [y,m,d]=day.split('-').map(Number);
  return new Date(Date.UTC(y,m-1,d,Math.floor(minuteOfDay/60),minuteOfDay%60)-7*3600*1000).toISOString();
}
function bucketFor(value){
  const p=localParts(value); if(!p)return null;
  const mins=p.hour*60+p.minute;
  if(mins>=9*60&&mins<9*60+15)return {time:isoFromLocal(p.day,9*60+15),session:'ATO'};
  if(mins>=9*60+15&&mins<11*60+30){
    const start=9*60+15,end=start+(Math.floor((mins-start)/5)+1)*5;
    return {time:isoFromLocal(p.day,end),session:'CONTINUOUS_AM'};
  }
  if(mins>=13*60&&mins<14*60+30){
    const start=13*60,end=start+(Math.floor((mins-start)/5)+1)*5;
    return {time:isoFromLocal(p.day,end),session:'CONTINUOUS_PM'};
  }
  if(mins>=14*60+30&&mins<=14*60+45)return {time:isoFromLocal(p.day,14*60+45),session:'ATC'};
  return null;
}
function resample5m(bars){
  const map=new Map();
  for(const bar of [...(bars||[])].sort((a,b)=>String(a.time).localeCompare(String(b.time)))){
    const b=bucketFor(bar.time); if(!b)continue;
    const o=num(bar.open),h=num(bar.high),l=num(bar.low),c=num(bar.close),v=num(bar.volume);
    if([o,h,l,c,v].some(x=>x===null))continue;
    const old=map.get(b.time);
    if(!old)map.set(b.time,{time:b.time,session:b.session,open:o,high:h,low:l,close:c,volume:Math.max(0,v)});
    else{old.high=Math.max(old.high,h);old.low=Math.min(old.low,l);old.close=c;old.volume+=Math.max(0,v);}
  }
  return [...map.values()].sort((a,b)=>a.time.localeCompare(b.time));
}
function readJson(file){try{return JSON.parse(fs.readFileSync(file,'utf8'));}catch{return null;}}
function loadIntraday(marketDir){
  const preferred=path.join(marketDir,'intraday-5m');
  const fallback=path.join(marketDir,'intraday');
  const dir=fs.existsSync(preferred)?preferred:fallback;
  if(!fs.existsSync(dir))throw new Error('No intraday archive found');
  const out=new Map();
  for(const file of fs.readdirSync(dir).filter(x=>x.endsWith('.json'))){
    const d=readJson(path.join(dir,file)); if(!d)continue;
    const symbol=String(d.symbol||file.replace('.json','')).toUpperCase();
    const bars=d.interval==='5m'?(d.bars||[]):resample5m(d.bars||[]);
    if(bars.length)out.set(symbol,bars);
  }
  return out;
}
function loadDailyMap(marketDir,symbol){
  const d=readJson(path.join(marketDir,'history',symbol+'.json'))||{};
  return (d.bars||[]).filter(x=>x&&x.time).sort((a,b)=>String(a.time).localeCompare(String(b.time)));
}
function trueRange(bar,prevClose){
  const h=num(bar.high),l=num(bar.low),pc=num(prevClose);
  if(h===null||l===null)return null;
  if(pc===null)return h-l;
  return Math.max(h-l,Math.abs(h-pc),Math.abs(l-pc));
}
function cmf(rows){
  let mfv=0,vol=0;
  for(const b of rows){
    const h=num(b.high),l=num(b.low),c=num(b.close),v=num(b.volume)||0;
    if(h===null||l===null||c===null||v<=0)continue;
    const mult=h>l?((c-l)-(h-c))/(h-l):0;
    mfv+=mult*v;vol+=v;
  }
  return vol>0?mfv/vol:0;
}
function featureRow(symbol,day,partial,daily){
  const prior=daily.filter(x=>String(x.time)<day);
  if(!prior.length)return null;
  const prev=prior[prior.length-1],ref=num(prev.close);
  if(!ref||!partial)return null;
  const avgVol20=avg(prior.slice(-20).map(x=>num(x.volume)||0));
  const tr=[];
  const atrSource=prior.slice(-13);
  for(let i=0;i<atrSource.length;i++){
    const b=atrSource[i],prevClose=i?atrSource[i-1].close:(prior[prior.length-atrSource.length-1]?.close);
    const v=trueRange(b,prevClose); if(v!==null)tr.push(v);
  }
  const currentTr=trueRange(partial,ref);if(currentTr!==null)tr.push(currentTr);
  const atr=tr.length?avg(tr):0;
  const money=prior.slice(-19).concat([{...partial,time:day}]);
  return {
    symbol,price:num(partial.close),reference:ref,
    change:(num(partial.close)/ref-1)*100,
    volume:num(partial.volume)||0,
    rangePct:(num(partial.high)-num(partial.low))/ref*100,
    atrPct:num(partial.close)>0?atr/num(partial.close)*100:0,
    volumeRatio:avgVol20>0?(num(partial.volume)||0)/avgVol20:0,
    cmf:cmf(money),sma20:null,sma50:null
  };
}
function cumulativeUpdate(old,bar){
  if(!old)return {open:bar.open,high:bar.high,low:bar.low,close:bar.close,volume:bar.volume};
  return {open:old.open,high:Math.max(old.high,bar.high),low:Math.min(old.low,bar.low),close:bar.close,volume:old.volume+bar.volume};
}
function minutesBetween(a,b){return Math.round((new Date(b)-new Date(a))/60000);}
function med(values){return median((values||[]).filter(Number.isFinite));}

function empiricalVolumeClock(intraday){
  const bucketValues=new Map();
  for(const [symbol,bars] of intraday){
    const byDay=new Map();
    for(const bar of bars){
      const day=localParts(bar.time)?.day;if(!day)continue;
      if(!byDay.has(day))byDay.set(day,[]);
      byDay.get(day).push(bar);
    }
    for(const [day,rows] of byDay){
      const ordered=rows.sort((a,b)=>a.time.localeCompare(b.time));
      const total=ordered.reduce((s,x)=>s+(num(x.volume)||0),0);
      if(total<=0)continue;
      let cum=0;
      for(const bar of ordered){
        cum+=num(bar.volume)||0;
        const p=localParts(bar.time),key=String(p.hour).padStart(2,'0')+':'+String(p.minute).padStart(2,'0');
        if(!bucketValues.has(key))bucketValues.set(key,[]);
        bucketValues.get(key).push(cum/total);
      }
    }
  }
  const out=[];
  for(const [clock,vals] of [...bucketValues].sort(([a],[b])=>a.localeCompare(b))){
    const sample=vals.length,emp=med(vals);
    const parts=clock.split(':').map(Number);
    const synthetic=isoFromLocal('2026-10-06',parts[0]*60+parts[1]);
    const model=maturityFactors(synthetic).volumeDenominator;
    out.push({clock,samples:sample,empirical:round(emp,4),model:round(model,4),gap:round(emp-model,4)});
  }
  return out;
}
function empiricalRangeClock(intraday){
  const bucketValues=new Map();
  for(const [symbol,bars] of intraday){
    const byDay=new Map();
    for(const bar of bars){
      const day=localParts(bar.time)?.day;if(!day)continue;
      if(!byDay.has(day))byDay.set(day,[]);
      byDay.get(day).push(bar);
    }
    for(const [day,rows] of byDay){
      const ordered=rows.sort((a,b)=>a.time.localeCompare(b.time));
      const fullHigh=Math.max(...ordered.map(x=>num(x.high)).filter(Number.isFinite));
      const fullLow=Math.min(...ordered.map(x=>num(x.low)).filter(Number.isFinite));
      const fullRange=fullHigh-fullLow;
      if(!(fullRange>0))continue;
      let cumHigh=-Infinity,cumLow=Infinity;
      for(const bar of ordered){
        const h=num(bar.high),l=num(bar.low);
        if(h===null||l===null)continue;
        cumHigh=Math.max(cumHigh,h);cumLow=Math.min(cumLow,l);
        const p=localParts(bar.time),key=String(p.hour).padStart(2,'0')+':'+String(p.minute).padStart(2,'0');
        if(!bucketValues.has(key))bucketValues.set(key,[]);
        bucketValues.get(key).push((cumHigh-cumLow)/fullRange);
      }
    }
  }
  const out=[];
  for(const [clock,vals] of [...bucketValues].sort(([a],[b])=>a.localeCompare(b))){
    const sample=vals.length,emp=med(vals);
    const parts=clock.split(':').map(Number);
    const synthetic=isoFromLocal('2026-10-06',parts[0]*60+parts[1]);
    const model=maturityFactors(synthetic).rangeDenominator;
    out.push({clock,samples:sample,empirical:round(emp,4),model:round(model,4),gap:round(emp-model,4)});
  }
  return out;
}

function buildReplay(marketDir){
  const intraday=loadIntraday(marketDir);
  const daily=new Map([...intraday.keys()].map(s=>[s,loadDailyMap(marketDir,s)]));
  const days=[...new Set([...intraday.values()].flatMap(b=>b.map(x=>localParts(x.time)?.day).filter(Boolean)))].sort();
  const dayResults=[],allSnapshots=[];
  for(const day of days){
    const calibrationObs=buildObservations(marketDir,day);
    if(calibrationObs.length<252)continue;
    const cal=calibrationFromObservations(calibrationObs.slice(-504));
    const priorDown=calibrationObs.filter(x=>x.marketReturn<0).slice(-80);
    const downsideCorrelation=pairwiseDownsideCorrelation(priorDown);
    const barsBySymbol=new Map();
    const times=new Set();
    for(const [symbol,bars] of intraday){
      const rows=bars.filter(x=>localParts(x.time)?.day===day);
      if(rows.length){barsBySymbol.set(symbol,new Map(rows.map(x=>[x.time,x])));rows.forEach(x=>times.add(x.time));}
    }
    const cumulative=new Map(),snapshots=[];
    for(const time of [...times].sort()){
      for(const [symbol,map] of barsBySymbol){
        const bar=map.get(time);if(bar)cumulative.set(symbol,cumulativeUpdate(cumulative.get(symbol),bar));
      }
      const rows=[];
      for(const [symbol,partial] of cumulative){
        const x=featureRow(symbol,day,partial,daily.get(symbol)||[]);if(x)rows.push(x);
      }
      if(rows.length<MIN_REPLAY_SYMBOLS)continue;
      const sectors=sectorRowsV2(rows,null,time);
      const raw=rawComponents(rows,sectors,time,{downsideCorrelation});
      const components=calibratedComponents(raw,cal),overall=overallFromComponents(components,cal);
      const marketReturn=med(rows.map(x=>x.change));
      const declinePct=rows.filter(x=>x.change<0).length/rows.length*100;
      const nearFloorPct=rows.filter(x=>x.change<=-6.3).length/rows.length*100;
      const csad=avg(rows.map(x=>Math.abs(x.change-marketReturn)));
      snapshots.push({day,time,coverage:rows.length,score:overall.score,marketReturn:round(marketReturn,3),declinePct:round(declinePct,1),nearFloorPct:round(nearFloorPct,2),csad:round(csad,3),components:Object.fromEntries(Object.entries(components).map(([k,v])=>[k,v.score]))});
    }
    for(let i=0;i<snapshots.length;i++){
      const future=snapshots[Math.min(snapshots.length-1,i+6)];
      snapshots[i].future30mChangePct=future&&future!==snapshots[i]?round(future.marketReturn-snapshots[i].marketReturn,3):null;
    }
    const event=snapshots.find(x=>x.marketReturn<=-1&&x.declinePct>=70)||null;
    const first70=snapshots.find(x=>x.score>=70&&(event?new Date(x.time)<=new Date(event.time):true))||null;
    const first85=snapshots.find(x=>x.score>=85&&(event?new Date(x.time)<=new Date(event.time):true))||null;
    const maxScore=snapshots.length?Math.max(...snapshots.map(x=>x.score)):null;
    dayResults.push({
      day,buckets:snapshots.length,maxScore,eventTime:event?.time||null,
      first70:first70?.time||null,lead70:event&&first70?minutesBetween(first70.time,event.time):null,
      first85:first85?.time||null,lead85:event&&first85?minutesBetween(first85.time,event.time):null,
      signal70State:first70||null,signal85State:first85||null,eventState:event||null,
      closeState:snapshots[snapshots.length-1]||null,
      eventAudit:event?snapshots.filter(x=>new Date(x.time)>=new Date((first70||first85||event).time)&&new Date(x.time)<=new Date(event.time)):[]

    });
    allSnapshots.push(...snapshots);
  }
  const usableDays=dayResults.filter(x=>x.buckets>0);
  const eventDays=usableDays.filter(x=>x.eventTime),detect70=eventDays.filter(x=>x.first70),detect85=eventDays.filter(x=>x.first85);
  const highDays=usableDays.filter(x=>Number(x.maxScore)>=85),falseHigh=highDays.filter(x=>!x.eventTime);
  const thresholdStats=[70,85,95].map(threshold=>{
    const rows=allSnapshots.filter(x=>x.score>=threshold&&Number.isFinite(x.future30mChangePct));
    return {threshold,samples:rows.length,medianFuture30mPct:rows.length?round(med(rows.map(x=>x.future30mChangePct)),3):null,medianCurrentPct:rows.length?round(med(rows.map(x=>x.marketReturn)),3):null};
  });
  const enough=usableDays.length>=MIN_VALIDATED_DAYS&&eventDays.length>=MIN_EVENT_DAYS;
  return {
    version:'FINQUERY-INTRADAY-RISK-REPLAY-0.2',
    status:enough?'READY_FOR_VALIDATION':'LIMITED_INTRADAY_HISTORY',
    generatedAt:new Date().toISOString(),
    sourceInterval:'5m replay from retained 1m/5m HOSE bars',
    calendarDaysSeen:dayResults.length,days:usableDays.length,eventDays:eventDays.length,snapshots:allSnapshots.length,
    detection:{
      threshold70:{detected:detect70.length,rate:eventDays.length?round(detect70.length/eventDays.length,3):null,medianLeadMinutes:detect70.length?med(detect70.map(x=>x.lead70).filter(Number.isFinite)):null},
      threshold85:{detected:detect85.length,rate:eventDays.length?round(detect85.length/eventDays.length,3):null,medianLeadMinutes:detect85.length?med(detect85.map(x=>x.lead85).filter(Number.isFinite)):null},
      highSignalDays:highDays.length,falseHighDays:falseHigh.length,falseHighDayRate:highDays.length?round(falseHigh.length/highDays.length,3):null
    },
    thresholdStats,daysDetail:dayResults,
    empiricalVolumeClock:empiricalVolumeClock(intraday),
    empiricalRangeClock:empiricalRangeClock(intraday),
    challengerDiagnostics:{
      nearFloorDefinition:'changePct <= -6.3% (research-only HOSE near-floor proxy)',
      csadDefinition:'cross-sectional absolute deviation around the equal-weight market return',
      policy:'Near-floor pressure and CSAD remain research-only until they add incremental out-of-sample value beyond breadth/liquidity/co-movement.'
    },
    validationPolicy:{minDays:MIN_VALIDATED_DAYS,minEventDays:MIN_EVENT_DAYS,minCoverageSymbols:MIN_REPLAY_SYMBOLS,note:'Only days with at least one 5-minute snapshot covering the minimum symbol count are usable. Until the minima are met, replay metrics are descriptive only and cannot change production thresholds.'}
  };
}
function main(){
  const marketDir=path.resolve(process.argv[2]||'');
  if(!process.argv[2])throw new Error('Usage: node build_intraday_risk_replay.cjs <market-dir> [output]');
  const result=buildReplay(marketDir);
  const output=process.argv[3]||path.join(marketDir,'intraday-risk-replay.json');
  fs.writeFileSync(output,JSON.stringify(result));
  console.log(JSON.stringify({status:result.status,days:result.days,eventDays:result.eventDays,snapshots:result.snapshots,detection:result.detection,thresholdStats:result.thresholdStats}));
}
if(require.main===module)main();
module.exports={bucketFor,resample5m,featureRow,empiricalVolumeClock,empiricalRangeClock,buildReplay};
