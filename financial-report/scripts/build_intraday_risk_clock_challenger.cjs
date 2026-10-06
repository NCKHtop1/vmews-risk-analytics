'use strict';

const fs=require('fs'),path=require('path');
const {
  median,avg,round,sectorRowsV2,rawComponents,calibrationFromObservations,
  calibratedComponents,overallFromComponents,maturityFactors
}=require('./risk_model_v2.cjs');
const {buildObservations,pairwiseDownsideCorrelation}=require('./build_market_risk_calibration.cjs');
const {
  loadIntraday,loadDailyMap,localParts,cumulativeUpdate,featureRow,fullSessionRows,minutesBetween
}=require('./build_intraday_risk_replay.cjs');

const LOOKBACK_DAYS=30;
const MIN_PROFILE_DAYS=20;
const MIN_REPLAY_SYMBOLS=80;

const num=v=>Number.isFinite(Number(v))?Number(v):null;
const med=values=>median((values||[]).filter(Number.isFinite));

function clockKey(value){
  const p=localParts(value);if(!p)return null;
  return String(p.hour).padStart(2,'0')+':'+String(p.minute).padStart(2,'0');
}
function monotonicMap(bucketValues){
  const out={};let last=0;
  for(const key of [...bucketValues.keys()].sort()){
    const vals=bucketValues.get(key)||[];
    if(!vals.length)continue;
    const value=Math.max(last,Math.min(1,Math.max(.01,med(vals))));
    out[key]=value;last=value;
  }
  return out;
}
function empiricalProfileBeforeDay(intraday,beforeDay){
  const allDays=[...new Set([...intraday.values()].flatMap(bars=>bars.map(x=>localParts(x.time)?.day).filter(Boolean)))]
    .filter(day=>day<beforeDay).sort();
  const selected=new Set(allDays.slice(-LOOKBACK_DAYS));
  const volumeValues=new Map(),rangeValues=new Map();
  let completeSymbolDays=0;
  for(const bars of intraday.values()){
    const byDay=new Map();
    for(const bar of bars){
      const day=localParts(bar.time)?.day;
      if(!day||!selected.has(day))continue;
      if(!byDay.has(day))byDay.set(day,[]);
      byDay.get(day).push(bar);
    }
    for(const rows of byDay.values()){
      const ordered=rows.sort((a,b)=>String(a.time).localeCompare(String(b.time)));
      if(!fullSessionRows(ordered))continue;
      const totalVol=ordered.reduce((s,x)=>s+(num(x.volume)||0),0);
      const highs=ordered.map(x=>num(x.high)).filter(Number.isFinite);
      const lows=ordered.map(x=>num(x.low)).filter(Number.isFinite);
      const fullRange=highs.length&&lows.length?Math.max(...highs)-Math.min(...lows):0;
      if(totalVol<=0||fullRange<=0)continue;
      completeSymbolDays++;
      let cumVol=0,cumHigh=-Infinity,cumLow=Infinity;
      for(const bar of ordered){
        const key=clockKey(bar.time);if(!key)continue;
        cumVol+=num(bar.volume)||0;
        const h=num(bar.high),l=num(bar.low);
        if(h!==null)cumHigh=Math.max(cumHigh,h);
        if(l!==null)cumLow=Math.min(cumLow,l);
        if(!volumeValues.has(key))volumeValues.set(key,[]);
        if(!rangeValues.has(key))rangeValues.set(key,[]);
        volumeValues.get(key).push(cumVol/totalVol);
        if(Number.isFinite(cumHigh)&&Number.isFinite(cumLow))rangeValues.get(key).push((cumHigh-cumLow)/fullRange);
      }
    }
  }
  return{
    days:selected.size,completeSymbolDays,
    volume:monotonicMap(volumeValues),range:monotonicMap(rangeValues)
  };
}
function adjustRowsForProfile(rows,time,profile,mode='both'){
  const key=clockKey(time),model=maturityFactors(time);
  const useVolume=mode==='both'||mode==='volume';
  const useRange=mode==='both'||mode==='range';
  const targetVol=useVolume?(num(profile?.volume?.[key])||model.volumeDenominator):model.volumeDenominator;
  const targetRange=useRange?(num(profile?.range?.[key])||model.rangeDenominator):model.rangeDenominator;
  const vf=model.volumeDenominator/Math.max(.01,targetVol);
  const rf=model.rangeDenominator/Math.max(.01,targetRange);
  return rows.map(r=>({
    ...r,
    volumeRatio:(num(r.volumeRatio)||0)*vf,
    rangePct:(num(r.rangePct)||0)*rf,
    change:(num(r.change)||0)*rf
  }));
}
function scoreRows(rows,time,cal,downsideCorrelation,profile=null,mode='both'){
  const input=profile?adjustRowsForProfile(rows,time,profile,mode):rows;
  const sectors=sectorRowsV2(input,null,time);
  const raw=rawComponents(input,sectors,time,{downsideCorrelation});
  const components=calibratedComponents(raw,cal);
  return overallFromComponents(components,cal).score;
}
function signalOutcome(snapshots,signal){
  if(!signal)return{future30m:null,maxAdverse60m:null};
  const t0=new Date(signal.time).getTime();
  const next=snapshots.filter(x=>{
    const dt=new Date(x.time).getTime()-t0;
    return dt>0&&dt<=60*60*1000;
  });
  const around30=next.find(x=>new Date(x.time).getTime()-t0>=30*60*1000)||null;
  const minRet=next.length?Math.min(...next.map(x=>x.marketReturn)):null;
  return{
    future30m:around30?round(around30.marketReturn-signal.marketReturn,3):null,
    maxAdverse60m:minRet===null?null:round(minRet-signal.marketReturn,3)
  };
}
function summarize(days,model){
  const maxKey=model+'Max',first70Key=model+'First70',first85Key=model+'First85';
  const eligible=days.filter(x=>x.completeDay&&x.profileDays>=MIN_PROFILE_DAYS&&Number.isFinite(x[maxKey]));
  const events=eligible.filter(x=>x.eventTime);
  const signalDays85=eligible.filter(x=>Number(x[maxKey])>=85);
  const false85=signalDays85.filter(x=>!x.eventTime);
  const det70=events.filter(x=>x[first70Key]);
  const det85=events.filter(x=>x[first85Key]);
  const signal85=eligible.map(x=>x[first85Key]).filter(Boolean);
  const current85=signal85.map(x=>x.marketReturn).filter(Number.isFinite);
  const future85=signal85.map(x=>x.future30m).filter(Number.isFinite);
  const adverse85=signal85.map(x=>x.maxAdverse60m).filter(Number.isFinite);
  return{
    validationDays:eligible.length,eventDays:events.length,
    threshold70:{
      detected:det70.length,recall:events.length?round(det70.length/events.length,3):null,
      medianLeadMinutes:det70.length?med(det70.map(x=>x[first70Key]?.leadMinutes).filter(Number.isFinite)):null
    },
    threshold85:{
      detected:det85.length,recall:events.length?round(det85.length/events.length,3):null,
      signalDays:signalDays85.length,falseHighDays:false85.length,
      dayPrecision:signalDays85.length?round((signalDays85.length-false85.length)/signalDays85.length,3):null,
      falseHighDayRate:signalDays85.length?round(false85.length/signalDays85.length,3):null,
      medianLeadMinutes:det85.length?med(det85.map(x=>x[first85Key]?.leadMinutes).filter(Number.isFinite)):null,
      medianCurrentPct:current85.length?round(med(current85),3):null,
      medianFuture30mPct:future85.length?round(med(future85),3):null,
      medianMaxAdverse60mPct:adverse85.length?round(med(adverse85),3):null
    }
  };
}
function nextDay(day){
  return new Date(new Date(day+'T00:00:00+07:00').getTime()+24*3600*1000).toISOString().slice(0,10);
}
function buildChallenger(marketDir){
  const intraday=loadIntraday(marketDir);
  const daily=new Map([...intraday.keys()].map(s=>[s,loadDailyMap(marketDir,s)]));
  const days=[...new Set([...intraday.values()].flatMap(b=>b.map(x=>localParts(x.time)?.day).filter(Boolean)))].sort();
  const allCal=buildObservations(marketDir,nextDay(days[days.length-1]));
  const results=[];
  for(const day of days){
    const calObs=allCal.filter(x=>String(x.date)<day);
    if(calObs.length<252)continue;
    const cal=calibrationFromObservations(calObs.slice(-504));
    const downsideCorrelation=pairwiseDownsideCorrelation(calObs.filter(x=>x.marketReturn<0).slice(-80));
    const profile=empiricalProfileBeforeDay(intraday,day);
    const priorDaily=new Map([...daily].map(([s,bars])=>[s,bars.filter(x=>String(x.time)<day)]));
    const barsBySymbol=new Map(),times=new Set();
    for(const [symbol,bars] of intraday){
      const rows=bars.filter(x=>localParts(x.time)?.day===day);
      if(rows.length){barsBySymbol.set(symbol,new Map(rows.map(x=>[x.time,x])));rows.forEach(x=>times.add(x.time));}
    }
    const cumulative=new Map(),snaps=[];
    for(const time of [...times].sort()){
      for(const [symbol,map] of barsBySymbol){
        const bar=map.get(time);if(bar)cumulative.set(symbol,cumulativeUpdate(cumulative.get(symbol),bar));
      }
      const rows=[];
      for(const [symbol,partial] of cumulative){
        const f=featureRow(symbol,day,partial,priorDaily.get(symbol)||[],true);if(f)rows.push(f);
      }
      if(rows.length<MIN_REPLAY_SYMBOLS)continue;
      const marketReturn=round(med(rows.map(x=>x.change)),3);
      const declinePct=round(rows.filter(x=>x.change<0).length/rows.length*100,1);
      snaps.push({
        time,marketReturn,declinePct,
        baseline:scoreRows(rows,time,cal,downsideCorrelation,null),
        volume:profile.days>=MIN_PROFILE_DAYS?scoreRows(rows,time,cal,downsideCorrelation,profile,'volume'):null,
        range:profile.days>=MIN_PROFILE_DAYS?scoreRows(rows,time,cal,downsideCorrelation,profile,'range'):null,
        empirical:profile.days>=MIN_PROFILE_DAYS?scoreRows(rows,time,cal,downsideCorrelation,profile,'both'):null
      });
    }
    const event=snaps.find(x=>x.marketReturn<=-1&&x.declinePct>=70)||null;
    const completeDay=fullSessionRows([...times].sort().map(time=>({time})));
    const row={day,completeDay,profileDays:profile.days,eventTime:event?.time||null};
    for(const model of ['baseline','volume','range','empirical']){
      const valid=snaps.filter(x=>Number.isFinite(x[model]));
      row[model+'Max']=valid.length?Math.max(...valid.map(x=>x[model])):null;
      for(const threshold of [70,85]){
        const signal=valid.find(x=>x[model]>=threshold&&(event?new Date(x.time)<=new Date(event.time):true))||null;
        const outcome=signalOutcome(snaps,signal);
        row[model+'First'+threshold]=signal?{
          time:signal.time,score:signal[model],marketReturn:signal.marketReturn,
          leadMinutes:event?minutesBetween(signal.time,event.time):null,
          ...outcome
        }:null;
      }
    }
    results.push(row);
  }
  const baseline=summarize(results,'baseline');
  const variants={
    volume:summarize(results,'volume'),
    range:summarize(results,'range'),
    both:summarize(results,'empirical')
  };
  const deltas={};
  for(const [name,v] of Object.entries(variants)){
    deltas[name]={
      recall85:baseline.threshold85.recall===null||v.threshold85.recall===null?null:round(v.threshold85.recall-baseline.threshold85.recall,3),
      precision85:baseline.threshold85.dayPrecision===null||v.threshold85.dayPrecision===null?null:round(v.threshold85.dayPrecision-baseline.threshold85.dayPrecision,3),
      falseHigh85:baseline.threshold85.falseHighDayRate===null||v.threshold85.falseHighDayRate===null?null:round(v.threshold85.falseHighDayRate-baseline.threshold85.falseHighDayRate,3),
      lead85:baseline.threshold85.medianLeadMinutes===null||v.threshold85.medianLeadMinutes===null?null:round(v.threshold85.medianLeadMinutes-baseline.threshold85.medianLeadMinutes,1)
    };
  }
  const qualified=Object.entries(variants).filter(([name,v])=>{
    const d=deltas[name];
    return v.validationDays>=20&&v.eventDays>=5&&(d.recall85??-1)>=-0.05&&(d.precision85??-1)>=0&&(d.falseHigh85??1)<=0;
  }).map(([name])=>name);
  return{
    version:'FINQUERY-INTRADAY-CLOCK-CHALLENGER-0.2',generatedAt:new Date().toISOString(),
    lookbackDays:LOOKBACK_DAYS,minProfileDays:MIN_PROFILE_DAYS,
    baseline,variants,deltas,
    recommendation:qualified.length?{status:'PROMOTE_TO_SHADOW',variants:qualified}:{status:'KEEP_RESEARCH_ONLY',variants:[]},
    policy:'A challenger may enter shadow mode only if it preserves recall, improves day-level precision, and does not increase false-high days on the same validation subset.',
    days:results
  };
}
function main(){
  const marketDir=path.resolve(process.argv[2]||'');
  if(!process.argv[2])throw new Error('Usage: node build_intraday_risk_clock_challenger.cjs <market-dir> [output]');
  const result=buildChallenger(marketDir);
  const output=process.argv[3]||path.join(marketDir,'intraday-risk-clock-challenger.json');
  fs.writeFileSync(output,JSON.stringify(result));
  console.log(JSON.stringify({recommendation:result.recommendation,baseline:result.baseline,variants:result.variants,deltas:result.deltas}));
}
if(require.main===module)main();
module.exports={empiricalProfileBeforeDay,adjustRowsForProfile,buildChallenger};
