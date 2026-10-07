'use strict';

const MODEL_VERSION='FINQUERY-RISK-V2.0';
const METHOD_VERSION='FINQUERY-RISK-RULES-2.0';
const WEIGHTS={breadth:0.30,volatility:0.20,liquidity:0.20,concentration:0.10,contagion:0.20};
const SECTORS=[
 {id:'banking',label:'Ngân hàng',symbols:['ACB','BID','CTG','EIB','HDB','LPB','MBB','MSB','OCB','SHB','SSB','STB','TCB','TPB','VCB','VIB','VPB']},
 {id:'securities',label:'Chứng khoán',symbols:['SSI','VND','VCI','HCM','BSI','FTS','CTS','ORS','SHS','VIX']},
 {id:'real-estate',label:'Bất động sản',symbols:['VIC','VHM','VRE','NVL','PDR','DXG','KDH','NLG','BCM','KBC','SZC','DIG']},
 {id:'steel',label:'Thép',symbols:['HPG','HSG','NKG','POM','GDA','SMC','TLH','TVN','VGS']},
 {id:'technology',label:'Công nghệ',symbols:['FPT','CMG','ELC','CTR']},
 {id:'retail',label:'Bán lẻ',symbols:['MWG','FRT','PNJ','DGW']},
 {id:'oil-gas',label:'Dầu khí',symbols:['GAS','PLX','PVD','PVS','BSR','OIL']},
 {id:'utilities',label:'Điện và tiện ích',symbols:['POW','REE','NT2','GEG','PC1']},
 {id:'construction',label:'Xây dựng và hạ tầng',symbols:['CTD','HBC','HHV','CII','VCG']},
 {id:'seafood',label:'Thủy sản',symbols:['VHC','ANV','FMC']},
 {id:'chemicals',label:'Hóa chất và phân bón',symbols:['DGC','CSV','DCM','DPM']},
 {id:'transport',label:'Vận tải và logistics',symbols:['GMD','HAH','VSC','VJC','HVN']},
 {id:'insurance',label:'Bảo hiểm',symbols:['BVH','MIG','BIC','PVI']},
 {id:'consumer',label:'Tiêu dùng',symbols:['VNM','SAB','MSN','QNS']}
];

const n=v=>Number.isFinite(Number(v))?Number(v):null;
const clamp=(v,lo=0,hi=100)=>Math.min(hi,Math.max(lo,Number(v)||0));
const scale=(v,lo,hi)=>hi<=lo?0:clamp((Number(v)-lo)/(hi-lo)*100);
const round=(v,d=1)=>{const p=10**d;return Math.round((Number(v)||0)*p)/p;};
const avg=values=>{const a=(values||[]).map(n).filter(Number.isFinite);return a.length?a.reduce((x,y)=>x+y,0)/a.length:0;};
function median(values){
 const a=(values||[]).map(n).filter(Number.isFinite).sort((a,b)=>a-b);
 if(!a.length)return 0;
 const m=Math.floor(a.length/2);
 return a.length%2?a[m]:(a[m-1]+a[m])/2;
}
function quantile(values,q){
 const a=(values||[]).map(n).filter(Number.isFinite).sort((a,b)=>a-b);
 if(!a.length)return null;
 const p=(a.length-1)*Math.max(0,Math.min(1,Number(q)||0)),lo=Math.floor(p),hi=Math.ceil(p);
 return lo===hi?a[lo]:a[lo]+(a[hi]-a[lo])*(p-lo);
}
function percentileGrid(values){
 const out=[];
 for(let i=0;i<=100;i++)out.push(round(quantile(values,i/100)??0,6));
 return out;
}
function percentileFromGrid(value,grid){
 const x=Number(value);
 if(!Number.isFinite(x)||!Array.isArray(grid)||grid.length<2)return null;
 if(x<=Number(grid[0]))return 0;
 const last=grid.length-1;
 if(x>=Number(grid[last]))return 100;
 for(let i=1;i<grid.length;i++){
  const hi=Number(grid[i]),lo=Number(grid[i-1]);
  if(x<=hi){
   const frac=hi>lo?(x-lo)/(hi-lo):0;
   return clamp(((i-1)+frac)/(last)*100);
  }
 }
 return 100;
}
function correlation(xs,ys){
 const pairs=[];
 const m=Math.min(xs?.length||0,ys?.length||0);
 for(let i=0;i<m;i++){
  const x=n(xs[i]),y=n(ys[i]);if(x!==null&&y!==null)pairs.push([x,y]);
 }
 if(pairs.length<6)return null;
 const mx=avg(pairs.map(x=>x[0])),my=avg(pairs.map(x=>x[1]));
 let sxx=0,syy=0,sxy=0;
 for(const [x,y] of pairs){const dx=x-mx,dy=y-my;sxx+=dx*dx;syy+=dy*dy;sxy+=dx*dy;}
 if(sxx<=0||syy<=0)return null;
 return Math.max(-1,Math.min(1,sxy/Math.sqrt(sxx*syy)));
}
function vnParts(value){
 const d=new Date(value);if(!Number.isFinite(d.getTime()))return null;
 const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(d);
 const get=t=>Number(parts.find(x=>x.type===t)?.value||0);
 return{hour:get('hour'),minute:get('minute')};
}
function sessionProgress(sourceTime){
 const p=vnParts(sourceTime);if(!p)return 1;
 const mins=p.hour*60+p.minute;
 let elapsed=0;
 if(mins<=540)elapsed=0;
 else if(mins<690)elapsed=mins-540;
 else if(mins<780)elapsed=150;
 else if(mins<885)elapsed=150+(mins-780);
 else elapsed=255;
 return Math.max(0,Math.min(1,elapsed/255));
}
function maturityFactors(sourceTime){
 const progress=sessionProgress(sourceTime);
 const p=Math.max(.01,progress);
 // Parameter-free symmetric U-shaped activity clock: faster accumulation near
 // the open and close, slower through the middle of the trading day.
 const activity=(2/Math.PI)*Math.asin(Math.sqrt(p));
 return{
  progress,
  volumeDenominator:Math.max(.12,Math.min(1,activity)),
  rangeDenominator:Math.sqrt(Math.max(.12,p))
 };
}
function level(score){
 const s=Number(score)||0;
 if(s>=95)return{key:'very-high',label:'Rất cao',tone:'red'};
 if(s>=85)return{key:'high',label:'Cao',tone:'red'};
 if(s>=70)return{key:'watch',label:'Cần theo dõi',tone:'yellow'};
 return{key:'normal',label:'Bình thường',tone:'green'};
}
function componentLevel(score){return level(score);}
function normalizeRows(rows,sourceTime){
 const f=maturityFactors(sourceTime);
 return (rows||[]).map(r=>{
  const volumeRatio=n(r.volumeRatio)||0;
  const change=n(r.change)||0;
  const rangePct=n(r.rangePct)||0;
  const volumePace=volumeRatio/f.volumeDenominator;
  const rangePace=rangePct/f.rangeDenominator;
  const returnPace=change/f.rangeDenominator;
  const impact=Math.abs(returnPace)/Math.max(.15,volumePace);
  return{...r,volumePace,rangePace,returnPace,impact,sessionProgress:f.progress};
 });
}
function sectorRowsV2(rows,calibration=null,sourceTime=null){
 const norm=normalizeRows(rows,sourceTime);
 const by=new Map(norm.map(r=>[r.symbol,r])),calibrated=calibration?.sectors||{};
 return SECTORS.map(group=>{
  const members=group.symbols.map(s=>by.get(s)).filter(Boolean);
  if(members.length<2)return null;
  const declineShare=members.filter(r=>r.change<0).length/members.length;
  const advanceShare=members.filter(r=>r.change>0).length/members.length;
  const unchangedShare=members.filter(r=>r.change===0).length/members.length;
  const medChange=median(members.map(r=>r.returnPace));
  const medVolume=median(members.map(r=>r.volumePace));
  const score=clamp(
   0.65*scale(declineShare,0.40,0.85)+
   0.25*scale(-medChange,0,2.5)+
   0.10*scale(medVolume,0.8,1.8)
  );
  const cal=calibrated[group.id]||null,threshold=n(cal?.threshold),exitThreshold=n(cal?.exitThreshold);
  const alertEligible=cal?.alertEligible===true&&threshold!==null;
  const aboveThreshold=alertEligible&&score>=threshold;
  const memberRows=[...members].sort((a,b)=>a.change-b.change).map(r=>({
   symbol:r.symbol,changePct:round(r.change,2),volumeRatio:round(r.volumeRatio,2),volumePace:round(r.volumePace,2),
   price:round(r.price,2),rangePct:round(r.rangePct,2),cmf:r.cmf===null?null:round(r.cmf,3)
  }));
  return{
   id:group.id,label:group.label,score:round(score,1),level:componentLevel(score),members:members.length,
   declinePct:round(declineShare*100,1),advancePct:round(advanceShare*100,1),unchangedPct:round(unchangedShare*100,1),
   medianChangePct:round(median(members.map(r=>r.change)),2),medianAdjustedChangePct:round(medChange,2),
   medianVolumeRatio:round(median(members.map(r=>r.volumeRatio)),2),medianVolumePace:round(medVolume,2),
   memberRows,threshold:threshold===null?null:round(threshold,1),exitThreshold:exitThreshold===null?null:round(exitThreshold,1),
   alertEligible,aboveThreshold,alertActive:aboveThreshold,
   nearThreshold:alertEligible&&!aboveThreshold&&score>=Math.max(0,threshold-10),
   backtest:cal?{
    status:cal.status||null,samples:cal.samples||0,forwardSessions:cal.forwardSessions||3,thresholdMode:cal.thresholdMode||null,
    stateValidated:cal.stateValidated===true,continuationValidated:cal.continuationValidated===true,
    adverseCutoffPct:n(cal.adverseCutoffPct),thresholdSpread:n(cal.thresholdSpread),
    precision:n(cal.oos?.precision),baseRate:n(cal.oos?.baseRate),precisionLift:n(cal.oos?.precisionLift),
    recall:n(cal.oos?.recall),falseAlarmRate:n(cal.oos?.falseAlarmRate),youden:n(cal.oos?.youden),
    signalRate:n(cal.oos?.signalRate),folds:cal.oos?.folds||0,signals:cal.oos?.signals||0,events:cal.oos?.events||0,
    medianCurrentReturnWhenSignalPct:n(cal.oos?.medianCurrentReturnWhenSignalPct),
    medianForward3WhenSignalPct:n(cal.oos?.medianForward3WhenSignalPct),reason:cal.reason||''
   }:null
  };
 }).filter(Boolean);
}
function rawComponents(rows,sectors,sourceTime,fragilityContext={}){
 const norm=normalizeRows(rows,sourceTime);
 const declines=norm.filter(r=>r.change<0);
 const declineShare=norm.length?declines.length/norm.length:0;
 const severeShare=norm.length?norm.filter(r=>r.returnPace<=-2).length/norm.length:0;
 const medianChange=median(norm.map(r=>r.returnPace));
 const breadth=clamp(
  0.55*scale(declineShare,0.40,0.85)+
  0.25*scale(severeShare,0.05,0.45)+
  0.20*scale(-medianChange,0,2.5)
 );

 const medianRange=median(norm.map(r=>r.rangePace));
 const medianAtr=median(norm.map(r=>r.atrPct));
 const bigRangeShare=norm.length?norm.filter(r=>r.rangePace>=3).length/norm.length:0;
 const volatility=clamp(
  0.45*scale(medianRange,1,4)+
  0.35*scale(medianAtr,1.5,5)+
  0.20*scale(bigRangeShare,0.10,0.50)
 );

 const medianDownVol=median(declines.map(r=>r.volumePace));
 const heavyDownShare=norm.length?norm.filter(r=>r.change<0&&r.volumePace>=1.2).length/norm.length:0;
 const negativeCmfShare=norm.length?norm.filter(r=>r.cmf!==null&&r.cmf<=-0.1).length/norm.length:0;
 const medianImpact=median(declines.map(r=>r.impact));
 const liquidity=clamp(
  0.30*scale(medianDownVol,0.8,2.0)+
  0.25*scale(heavyDownShare,0.15,0.55)+
  0.30*scale(medianImpact,0.35,2.2)+
  0.15*scale(negativeCmfShare,0.25,0.70)
 );

 const turnovers=norm.map(r=>Math.max(0,r.price*r.volume)).sort((a,b)=>b-a);
 const total=turnovers.reduce((a,b)=>a+b,0)||1;
 const top5=turnovers.slice(0,5).reduce((a,b)=>a+b,0)/total;
 const top10=turnovers.slice(0,10).reduce((a,b)=>a+b,0)/total;
 const concentrationRaw=clamp(0.70*scale(top5,0.18,0.45)+0.30*scale(top10,0.32,0.65));
 const activityCoverage=norm.length?norm.filter(r=>r.volume>0).length/norm.length:0;
 const breadthWeakness=Math.max(0,Math.min(1,(breadth-20)/80));
 const concentration=clamp(concentrationRaw*breadthWeakness*activityCoverage);

 const sectorDecline=sectors.length?sectors.filter(s=>s.medianAdjustedChangePct<0).length/sectors.length:0;
 const sectorMedian=median(sectors.map(s=>s.medianAdjustedChangePct));
 const downsideSync=clamp(
  0.65*scale(sectorDecline,0.45,0.90)+
  0.35*scale(-sectorMedian,0,2.0)
 );
 const downsideCorrelation=n(fragilityContext.downsideCorrelation);
 const correlationStress=downsideCorrelation===null?50:scale(downsideCorrelation,0.05,0.75);
 const contagion=clamp((0.65*downsideSync+0.35*correlationStress)*(0.35+0.65*breadth/100));

 return{
  breadth:{raw:round(breadth,3),stats:{declinePct:round(declineShare*100,1),severeDeclinePct:round(severeShare*100,1),medianAdjustedChangePct:round(medianChange,2)}},
  volatility:{raw:round(volatility,3),stats:{medianAdjustedRangePct:round(medianRange,2),medianAtrPct:round(medianAtr,2),bigAdjustedRangePct:round(bigRangeShare*100,1)}},
  liquidity:{raw:round(liquidity,3),stats:{medianDownVolumePace:round(medianDownVol,2),heavyDownPct:round(heavyDownShare*100,1),medianPriceImpact:round(medianImpact,2),negativeCmfPct:round(negativeCmfShare*100,1)}},
  concentration:{raw:round(concentration,3),stats:{top5TurnoverPct:round(top5*100,1),top10TurnoverPct:round(top10*100,1),activityCoveragePct:round(activityCoverage*100,1),unmodifiedScore:round(concentrationRaw,1)}},
  contagion:{raw:round(contagion,3),stats:{decliningSectorPct:round(sectorDecline*100,1),medianAdjustedSectorChangePct:round(sectorMedian,2),downsideCorrelation:downsideCorrelation===null?null:round(downsideCorrelation,3)}}
 };
}
function calibratedComponents(raw,calibration=null){
 const grids=calibration?.componentGrids||{};
 const defs={
  breadth:{label:'Mức giảm lan rộng'},
  volatility:{label:'Biến động bất thường'},
  liquidity:{label:'Thanh khoản & áp lực bán'},
  concentration:{label:'Tập trung khi thị trường suy yếu'},
  contagion:{label:'Đồng biến giữa các ngành'}
 };
 const out={};
 for(const [key,def] of Object.entries(defs)){
  const r=raw[key]||{raw:0,stats:{}};
  const pct=percentileFromGrid(r.raw,grids[key]);
  let score=pct===null?r.raw:pct,absoluteGate=null;
  if(key==='liquidity'){
   const stats=r.stats||{};
   const sellingActivity=Number(stats.medianDownVolumePace)>=0.8||Number(stats.heavyDownPct)>=15;
   const sellingQuality=Number(stats.medianPriceImpact)>=0.35||Number(stats.negativeCmfPct)>=25;
   if(!sellingActivity)score=Math.min(score,69.9);
   else if(!sellingQuality)score=Math.min(score,84.9);
   absoluteGate={sellingActivity,sellingQuality,passedHigh:sellingActivity&&sellingQuality};
  }
  out[key]={...def,score:round(score,1),rawScore:round(r.raw,1),level:componentLevel(score),stats:r.stats,...(absoluteGate?{absoluteGate}:{})};
 }
 return out;
}
function overallFromComponents(components,calibration=null){
 const base=Object.entries(WEIGHTS).reduce((sum,[key,w])=>sum+(components[key]?.score||0)*w,0);
 const p=percentileFromGrid(base,calibration?.overallBaseGrid);
 const score=round(p===null?base:p,1);
 return{score,level:level(score),baseScore:round(base,1),systemWideAdd:0};
}
function contributionRows(components,previousPoint){
 return Object.entries(WEIGHTS).map(([key,weight])=>{
  const x=components[key],prev=n(previousPoint?.components?.[key]);
  return{
   key,label:x?.label||key,score:round(x?.score||0,1),weight:round(weight*100,0),
   points:round((x?.score||0)*weight,1),
   change:prev===null?null:round((x?.score||0)-prev,1),
   pointChange:prev===null?null:round(((x?.score||0)-prev)*weight,1),
   level:x?.level||level(x?.score||0)
  };
 }).sort((a,b)=>b.points-a.points);
}
function detailsForComponents(components){
 const c=JSON.parse(JSON.stringify(components));
 if(c.breadth)c.breadth.detail=`${c.breadth.stats.declinePct}% số mã đang giảm; mức giảm đã được chuẩn hóa theo thời điểm trong phiên.`;
 if(c.volatility)c.volatility.detail=`Biên độ chuẩn hóa trung vị ${c.volatility.stats.medianAdjustedRangePct}%; ATR/giá trung vị ${c.volatility.stats.medianAtrPct}%.`;
 if(c.liquidity)c.liquidity.detail=`Nhịp khối lượng nhóm giảm ${c.liquidity.stats.medianDownVolumePace} lần; price-impact proxy trung vị ${c.liquidity.stats.medianPriceImpact}.`;
 if(c.concentration)c.concentration.detail=`Top 5 chiếm ${c.concentration.stats.top5TurnoverPct}% giao dịch; chỉ làm tăng rủi ro khi độ rộng thị trường suy yếu.`;
 if(c.contagion)c.contagion.detail=`${c.contagion.stats.decliningSectorPct}% nhóm ngành đang giảm; tương quan downside lịch sử ${c.contagion.stats.downsideCorrelation??'—'}.`;
 return c;
}
function calibrationFromObservations(observations){
 const rows=(observations||[]).filter(x=>x&&x.raw);
 const componentGrids={};
 for(const key of Object.keys(WEIGHTS))componentGrids[key]=percentileGrid(rows.map(x=>x.raw[key]?.raw));
 const baseScores=rows.map(row=>{
  const c=calibratedComponents(row.raw,{componentGrids});
  return Object.entries(WEIGHTS).reduce((sum,[key,w])=>sum+(c[key]?.score||0)*w,0);
 });
 return{componentGrids,overallBaseGrid:percentileGrid(baseScores),samples:rows.length};
}
module.exports={
 MODEL_VERSION,METHOD_VERSION,WEIGHTS,SECTORS,n,clamp,scale,round,avg,median,quantile,percentileGrid,percentileFromGrid,
 correlation,sessionProgress,maturityFactors,normalizeRows,sectorRowsV2,rawComponents,calibratedComponents,
 overallFromComponents,contributionRows,detailsForComponents,calibrationFromObservations,level
};
