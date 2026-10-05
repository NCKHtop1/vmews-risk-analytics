'use strict';
const fs=require('fs'),path=require('path');
const {SECTORS}=require('./build_risk_monitor.cjs');

const VERSION='FINQUERY-SECTOR-RISK-CAL-1.1';
const FORWARD_SESSIONS=3;
const STATE_QUANTILE=.90;

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
function confusionFromTotals(x){
 const total=x.total||0,tp=x.tp||0,fp=x.fp||0,tn=x.tn||0,fn=x.fn||0,events=x.events||0;
 const recall=tp+fn?tp/(tp+fn):0,falseAlarmRate=fp+tn?fp/(fp+tn):0,precision=tp+fp?tp/(tp+fp):0,baseRate=total?events/total:0;
 return{...x,recall:round(recall,4),falseAlarmRate:round(falseAlarmRate,4),precision:round(precision,4),baseRate:round(baseRate,4),youden:round(recall-falseAlarmRate,4),precisionLift:round(baseRate>0?precision/baseRate:0,3)};
}
function calibrateSector(id,label,observations){
 const rows=(observations||[]).filter(x=>Number.isFinite(Number(x.score))&&Number.isFinite(Number(x.forward3Pct))&&Number.isFinite(Number(x.currentMedianPct))).sort((a,b)=>String(a.date).localeCompare(String(b.date)));
 if(rows.length<180){
  return{id,label,status:'INSUFFICIENT_HISTORY',alertEligible:false,stateValidated:false,continuationValidated:false,samples:rows.length,thresholdMode:'HISTORICAL_P90',threshold:round(quantile(rows.map(x=>x.score),STATE_QUANTILE)??65,1),reason:'Lịch sử hợp lệ chưa đủ 180 phiên để kiểm định độ ổn định của ngưỡng.'};
 }
 const splits=[[.55,.70],[.70,.85],[.85,1.00]],folds=[];
 let totals={total:0,tp:0,fp:0,tn:0,fn:0,signals:0,events:0};
 const thresholds=[],cutoffs=[],signalForward=[],signalCurrent=[];
 for(const [trainFrac,testEndFrac] of splits){
  const trainEnd=Math.floor(rows.length*trainFrac),testEnd=Math.floor(rows.length*testEndFrac);
  const train=rows.slice(0,trainEnd),test=rows.slice(trainEnd,testEnd);
  if(train.length<120||test.length<30)continue;
  const threshold=round(quantile(train.map(x=>x.score),STATE_QUANTILE)??65,1);
  const adverseCutoff=round(Math.min(-1,quantile(train.map(x=>x.forward3Pct),.20)??-1),2);
  const m=confusion(test,threshold,adverseCutoff);
  folds.push({trainThrough:train[train.length-1].date,testFrom:test[0].date,testThrough:test[test.length-1].date,threshold,adverseCutoffPct:adverseCutoff,...m});
  thresholds.push(threshold);cutoffs.push(adverseCutoff);
  for(const row of test)if(Number(row.score)>=threshold){signalForward.push(row.forward3Pct);signalCurrent.push(row.currentMedianPct);}
  for(const key of ['total','tp','fp','tn','fn','signals','events'])totals[key]+=m[key]||0;
 }
 const aggregate=confusionFromTotals(totals);
 const threshold=round(median(thresholds)??quantile(rows.map(x=>x.score),STATE_QUANTILE)??65,1);
 const spread=thresholds.length?round(Math.max(...thresholds)-Math.min(...thresholds),1):null;
 const signalRate=aggregate.total?aggregate.signals/aggregate.total:0;
 const medianSignalForward=median(signalForward),medianSignalCurrent=median(signalCurrent);
 const stateValidated=folds.length>=2&&aggregate.total>=90&&aggregate.signals>=20&&
  signalRate>=.03&&signalRate<=.25&&(spread===null||spread<=15)&&medianSignalCurrent!==null&&medianSignalCurrent<0;
 const continuationValidated=stateValidated&&aggregate.events>=12&&aggregate.recall>=.12&&aggregate.youden>=.05&&
  aggregate.precisionLift>=1.20&&medianSignalForward!==null&&medianSignalForward<0;
 return{
  id,label,status:stateValidated?'VALIDATED_STATE':'LIMITED_STATE',alertEligible:stateValidated,stateValidated,continuationValidated,
  thresholdMode:'HISTORICAL_P90',threshold,exitThreshold:round(Math.max(25,threshold-7.5),1),
  thresholdSpread:spread,forwardSessions:FORWARD_SESSIONS,samples:rows.length,
  firstDate:rows[0]?.date||null,lastDate:rows[rows.length-1]?.date||null,
  adverseCutoffPct:round(median(cutoffs)??-1,2),
  oos:{...aggregate,folds:folds.length,signalRate:round(signalRate,4),medianCurrentReturnWhenSignalPct:medianSignalCurrent===null?null:round(medianSignalCurrent,2),medianForward3WhenSignalPct:medianSignalForward===null?null:round(medianSignalForward,2)},
  foldDetails:folds,
  reason:stateValidated?(continuationValidated?'Ngưỡng căng thẳng lịch sử ổn định; bằng chứng giảm tiếp 3 phiên cũng đạt gate ngoài mẫu.':'Ngưỡng căng thẳng lịch sử ổn định; chưa đủ bằng chứng để kết luận ngành sẽ tiếp tục giảm trong 3 phiên sau.'):'Ngưỡng phân vị lịch sử chưa đủ ổn định hoặc chưa đủ mẫu tín hiệu để bật cảnh báo tự động.'
 };
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
 if(maps.size<2)return[];
 const minMembers=Math.max(2,Math.min(6,Math.ceil(maps.size*.50))),rows=[];
 for(const date of [...dates].sort()){
  const members=[];
  for(const [symbol,map] of maps){const x=map.get(date);if(x)members.push({symbol,...x});}
  if(members.length<minMembers)continue;
  const fwd=median(members.map(x=>x.forward3Pct)),current=median(members.map(x=>x.changePct));
  if(fwd===null||current===null)continue;
  rows.push({date,score:stressScore(members),currentMedianPct:round(current,3),forward3Pct:round(fwd,3),members:members.length});
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
 const continuationValidated=Object.values(sectors).filter(x=>x.continuationValidated).length;
 return{
  version:VERSION,status:'ok',generatedAt:new Date().toISOString(),forSession,cutoffPolicy:'ONLY_DAILY_BARS_BEFORE_CURRENT_SESSION',
  methodology:{
   score:'65% tỷ lệ mã giảm + 25% mức giảm trung vị + 10% khối lượng so với 20 phiên trước.',
   threshold:'Ngưỡng căng thẳng của từng ngành là phân vị 90% của điểm lịch sử, ước lượng riêng trong từng cửa sổ huấn luyện.',
   validation:'Ba cửa sổ mở rộng theo thời gian kiểm tra độ ổn định của ngưỡng và tần suất chạm ngưỡng ở giai đoạn sau. Cảnh báo trạng thái không được diễn giải thành dự báo giảm tiếp.',
   continuation:'Khả năng giảm tiếp 3 phiên được đánh giá riêng trên dữ liệu ngoài mẫu bằng adverse-tail 20% (tối thiểu -1%), precision lift, Youden, recall và lợi suất trung vị sau tín hiệu.',
   eligibility:'Cảnh báo trạng thái chỉ bật khi có ít nhất 2 fold, đủ mẫu/tín hiệu, tần suất chạm ngưỡng hợp lý, ngưỡng giữa các fold lệch không quá 15 điểm và phản ứng cùng ngày có lợi suất trung vị âm.'
  },
  validatedSectors:validated,continuationValidatedSectors:continuationValidated,totalSectors:Object.keys(sectors).length,sectors
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
   console.log(JSON.stringify({status:'ok',reused:true,forSession,validatedSectors:old.validatedSectors,continuationValidatedSectors:old.continuationValidatedSectors,totalSectors:old.totalSectors}));
   return;
  }
 }catch{}
 const result=buildCalibration(marketDir,forSession);
 fs.writeFileSync(output,JSON.stringify(result));
 console.log(JSON.stringify({status:result.status,reused:false,forSession,validatedSectors:result.validatedSectors,continuationValidatedSectors:result.continuationValidatedSectors,totalSectors:result.totalSectors}));
}
if(require.main===module)main();
module.exports={VERSION,stressScore,confusion,calibrateSector,buildObservations,buildCalibration,quantile,median};
