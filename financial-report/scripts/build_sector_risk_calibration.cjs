'use strict';
const fs=require('fs'),path=require('path');
const {SECTORS}=require('./build_risk_monitor.cjs');

const VERSION='FINQUERY-SECTOR-RISK-CAL-1.0';
const FORWARD_SESSIONS=3;
const CANDIDATES=Array.from({length:21},(_,i)=>35+i*2.5);

const num=v=>Number.isFinite(Number(v))?Number(v):null;
const clamp=(v,lo=0,hi=100)=>Math.min(hi,Math.max(lo,Number(v)||0));
const scale=(v,lo,hi)=>hi<=lo?0:clamp((Number(v)-lo)/(hi-lo)*100);
const round=(v,d=1)=>{const p=10**d;return Math.round((Number(v)||0)*p)/p;};
const avg=a=>{const x=(a||[]).map(num).filter(Number.isFinite);return x.length?x.reduce((s,v)=>s+v,0)/x.length:0;};
function median(values){
 const a=(values||[]).map(num).filter(Number.isFinite).sort((x,y)=>x-y);
 if(!a.length)return null;const m=Math.floor(a.length/2);return a.length%2?a[m]:(a[m-1]+a[m])/2;
}
function quantile(values,q){
 const a=(values||[]).map(num).filter(Number.isFinite).sort((x,y)=>x-y);
 if(!a.length)return null;
 const p=(a.length-1)*Math.max(0,Math.min(1,Number(q)||0)),lo=Math.floor(p),hi=Math.ceil(p);
 return lo===hi?a[lo]:a[lo]+(a[hi]-a[lo])*(p-lo);
}
function stressScore(rows){
 if(!rows.length)return 0;
 const declineShare=rows.filter(r=>r.changePct<0).length/rows.length;
 const medChange=median(rows.map(r=>r.changePct))||0;
 const medVolume=median(rows.map(r=>r.volumeRatio))||0;
 return round(clamp(
  0.65*scale(declineShare,0.40,0.85)+
  0.25*scale(-medChange,0,2.5)+
  0.10*scale(medVolume,0.8,1.8)
 ),1);
}
function confusion(rows,threshold,cutoff){
 let tp=0,fp=0,tn=0,fn=0,signals=0,events=0;
 for(const row of rows){
  const signal=Number(row.score)>=Number(threshold),event=Number(row.forward3Pct)<=Number(cutoff);
  if(signal)signals++;if(event)events++;
  if(signal&&event)tp++;else if(signal&&!event)fp++;else if(!signal&&event)fn++;else tn++;
 }
 const tpr=tp+fn?tp/(tp+fn):0,fpr=fp+tn?fp/(fp+tn):0;
 const precision=tp+fp?tp/(tp+fp):0,baseRate=rows.length?events/rows.length:0;
 return{
  total:rows.length,tp,fp,tn,fn,signals,events,
  recall:round(tpr,4),falseAlarmRate:round(fpr,4),precision:round(precision,4),
  baseRate:round(baseRate,4),youden:round(tpr-fpr,4),
  precisionLift:round(baseRate>0?precision/baseRate:0,3)
 };
}
function selectThreshold(train){
 const forwards=train.map(x=>x.forward3Pct);
 const adverseCutoff=Math.min(-1,quantile(forwards,.20)??-1);
 const minSignals=Math.max(10,Math.ceil(train.length*.02));
 let best=null;
 for(const threshold of CANDIDATES){
  const m=confusion(train,threshold,adverseCutoff);
  if(m.signals<minSignals||m.events<10)continue;
  const candidate={threshold,adverseCutoffPct:round(adverseCutoff,2),metrics:m};
  if(!best||m.youden>best.metrics.youden+.0001||
     (Math.abs(m.youden-best.metrics.youden)<.0001&&m.precision>best.metrics.precision+.0001)||
     (Math.abs(m.youden-best.metrics.youden)<.0001&&Math.abs(m.precision-best.metrics.precision)<.0001&&threshold>best.threshold)){
    best=candidate;
  }
 }
 return best;
}
function calibrateSector(id,label,observations){
 const rows=(observations||[]).filter(x=>Number.isFinite(Number(x.score))&&Number.isFinite(Number(x.forward3Pct))).sort((a,b)=>String(a.date).localeCompare(String(b.date)));
 if(rows.length<180){
  return{id,label,status:'INSUFFICIENT_HISTORY',alertEligible:false,samples:rows.length,threshold:round(quantile(rows.map(x=>x.score),.80)??65,1),reason:'Lịch sử hợp lệ chưa đủ 180 phiên để kiểm định theo thời gian.'};
 }
 const splits=[[.55,.70],[.70,.85],[.85,1.00]],folds=[];
 let totals={total:0,tp:0,fp:0,tn:0,fn:0,signals:0,events:0};
 const thresholds=[],cutoffs=[],signalReturns=[];
 for(const [trainFrac,testEndFrac] of splits){
  const trainEnd=Math.floor(rows.length*trainFrac),testEnd=Math.floor(rows.length*testEndFrac);
  const train=rows.slice(0,trainEnd),test=rows.slice(trainEnd,testEnd);
  if(train.length<120||test.length<30)continue;
  const selected=selectThreshold(train);if(!selected)continue;
  const m=confusion(test,selected.threshold,selected.adverseCutoffPct);
  folds.push({trainThrough:train[train.length-1].date,testFrom:test[0].date,testThrough:test[test.length-1].date,threshold:selected.threshold,adverseCutoffPct:selected.adverseCutoffPct,...m});
  thresholds.push(selected.threshold);cutoffs.push(selected.adverseCutoffPct);
  for(const row of test)if(Number(row.score)>=selected.threshold)signalReturns.push(row.forward3Pct);
  for(const key of ['total','tp','fp','tn','fn','signals','events'])totals[key]+=m[key]||0;
 }
 const aggregate=confusionFromTotals(totals);
 const threshold=round(median(thresholds)??quantile(rows.map(x=>x.score),.80)??65,1);
 const spread=thresholds.length?round(Math.max(...thresholds)-Math.min(...thresholds),1):null;
 const medianSignalForward=median(signalReturns);
 const eligible=folds.length>=2&&aggregate.total>=90&&aggregate.signals>=12&&aggregate.events>=12&&
  aggregate.recall>=.12&&aggregate.youden>=.03&&aggregate.precisionLift>=1.10&&(spread===null||spread<=20);
 return{
  id,label,status:eligible?'VALIDATED_OOS':'LIMITED_OOS',alertEligible:eligible,
  threshold,exitThreshold:round(Math.max(25,threshold-7.5),1),
  thresholdSpread:spread,forwardSessions:FORWARD_SESSIONS,samples:rows.length,
  firstDate:rows[0]?.date||null,lastDate:rows[rows.length-1]?.date||null,
  adverseCutoffPct:round(median(cutoffs)??-1,2),
  oos:{...aggregate,folds:folds.length,medianForward3WhenSignalPct:medianSignalForward===null?null:round(medianSignalForward,2)},
  foldDetails:folds,
  reason:eligible?'Ngưỡng đạt kiểm định ngoài mẫu theo thời gian.':'Có lịch sử nhưng độ phân biệt ngoài mẫu chưa đủ mạnh để dùng làm cảnh báo tự động.'
 };
}
function confusionFromTotals(x){
 const total=x.total||0,tp=x.tp||0,fp=x.fp||0,tn=x.tn||0,fn=x.fn||0,events=x.events||0;
 const recall=tp+fn?tp/(tp+fn):0,falseAlarmRate=fp+tn?fp/(fp+tn):0,precision=tp+fp?tp/(tp+fp):0,baseRate=total?events/total:0;
 return{...x,recall:round(recall,4),falseAlarmRate:round(falseAlarmRate,4),precision:round(precision,4),baseRate:round(baseRate,4),youden:round(recall-falseAlarmRate,4),precisionLift:round(baseRate>0?precision/baseRate:0,3)};
}
function loadFeatures(file,cutoffDay){
 let data;try{data=JSON.parse(fs.readFileSync(file,'utf8'));}catch{return new Map();}
 const bars=(data.bars||[]).filter(x=>x&&x.time&&String(x.time)<String(cutoffDay));
 const out=new Map();
 for(let i=20;i<bars.length-FORWARD_SESSIONS;i++){
  const b=bars[i],prev=bars[i-1],future=bars[i+FORWARD_SESSIONS];
  const close=num(b.close),prevClose=num(prev?.close),futureClose=num(future?.close);
  if(!close||!prevClose||!futureClose)continue;
  const priorVol=avg(bars.slice(i-20,i).map(x=>x.volume));
  const volume=num(b.volume)||0;
  out.set(String(b.time),{
   date:String(b.time),changePct:(close/prevClose-1)*100,
   volumeRatio:priorVol>0?volume/priorVol:0,
   forward3Pct:(futureClose/close-1)*100
  });
 }
 return out;
}
function buildObservations(marketDir,group,cutoffDay){
 const maps=new Map(),dates=new Set();
 for(const symbol of group.symbols){
  const map=loadFeatures(path.join(marketDir,'history',symbol+'.json'),cutoffDay);
  if(map.size){maps.set(symbol,map);for(const d of map.keys())dates.add(d);}
 }
 const minMembers=Math.max(2,Math.min(6,Math.ceil(group.symbols.length*.35))),rows=[];
 for(const date of [...dates].sort()){
  const members=[];
  for(const [symbol,map] of maps){const x=map.get(date);if(x)members.push({symbol,...x});}
  if(members.length<minMembers)continue;
  const fwd=median(members.map(x=>x.forward3Pct));if(fwd===null)continue;
  rows.push({date,score:stressScore(members),forward3Pct:round(fwd,3),members:members.length});
 }
 return rows;
}
function sessionDay(quotes){
 const value=quotes?.latestSourceTime||quotes?.sourceTime||new Date().toISOString();
 const d=new Date(value);if(!Number.isFinite(d.getTime()))return new Date().toISOString().slice(0,10);
 return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(d);
}
function buildCalibration(marketDir,forSession){
 const sectors={};
 for(const group of SECTORS){
  const obs=buildObservations(marketDir,group,forSession);
  sectors[group.id]=calibrateSector(group.id,group.label,obs);
 }
 const validated=Object.values(sectors).filter(x=>x.alertEligible).length;
 return{
  version:VERSION,status:'ok',generatedAt:new Date().toISOString(),forSession,cutoffPolicy:'ONLY_DAILY_BARS_BEFORE_CURRENT_SESSION',
  methodology:{
   score:'65% tỷ lệ mã giảm + 25% mức giảm trung vị + 10% khối lượng so với 20 phiên trước.',
   outcome:'Mức giảm trung vị của cổ phiếu trong ngành sau 3 phiên.',
   event:'Biến cố bất lợi dùng phân vị 20% của tập huấn luyện và phải giảm ít nhất 1%.',
   validation:'Ba cửa sổ kiểm định mở rộng theo thời gian; ngưỡng chọn trên tập trước bằng Youden J (tỷ lệ bắt đúng trừ tỷ lệ báo giả), sau đó đánh giá ở giai đoạn sau.',
   eligibility:'Chỉ bật cảnh báo tự động khi có ít nhất 2 fold, đủ mẫu và tín hiệu, recall >= 12%, Youden >= 0,03, precision lift >= 1,10 và ngưỡng giữa các fold không lệch quá 20 điểm.'
  },
  validatedSectors:validated,totalSectors:Object.keys(sectors).length,sectors
 };
}
function main(){
 const marketDir=path.resolve(process.argv[2]||'');
 if(!process.argv[2])throw new Error('Usage: node build_sector_risk_calibration.cjs <market-dir>');
 const quotes=JSON.parse(fs.readFileSync(path.join(marketDir,'quotes.json'),'utf8'));
 const forSession=sessionDay(quotes),output=path.join(marketDir,'sector-risk-calibration.json');
 try{
  const old=JSON.parse(fs.readFileSync(output,'utf8'));
  if(old?.status==='ok'&&old.version===VERSION&&old.forSession===forSession&&Object.keys(old.sectors||{}).length>=8){
   console.log(JSON.stringify({status:'ok',reused:true,forSession,validatedSectors:old.validatedSectors,totalSectors:old.totalSectors}));
   return;
  }
 }catch{}
 const result=buildCalibration(marketDir,forSession);
 fs.writeFileSync(output,JSON.stringify(result));
 console.log(JSON.stringify({status:result.status,reused:false,forSession,validatedSectors:result.validatedSectors,totalSectors:result.totalSectors}));
}
if(require.main===module)main();
module.exports={VERSION,stressScore,confusion,selectThreshold,calibrateSector,buildObservations,buildCalibration,quantile,median};
