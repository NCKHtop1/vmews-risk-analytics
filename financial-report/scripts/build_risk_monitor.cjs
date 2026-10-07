'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const RISK_V2=require('./risk_model_v2.cjs');

const VERSION=RISK_V2.MODEL_VERSION;
const METHOD_VERSION=RISK_V2.METHOD_VERSION;
const FUND_HISTORY_PATH=path.resolve(__dirname,'../../data/fund-holdings-history-v16.json');
const FUND_CHANGE_THRESHOLD_PP=0.50;
const WEIGHTS=RISK_V2.WEIGHTS;
const SECTORS=RISK_V2.SECTORS;

const n=v=>Number.isFinite(Number(v))?Number(v):null;
const clamp=(v,lo=0,hi=100)=>Math.min(hi,Math.max(lo,Number(v)||0));
const scale=(v,lo,hi)=>hi<=lo?0:clamp((Number(v)-lo)/(hi-lo)*100);
const pct=v=>Math.round(clamp(v,0,1)*1000)/10;
const round=(v,d=1)=>{const p=10**d;return Math.round((Number(v)||0)*p)/p;};
const avg=values=>{const a=(values||[]).map(n).filter(Number.isFinite);return a.length?a.reduce((x,y)=>x+y,0)/a.length:0;};
function median(values){
 const a=(values||[]).map(n).filter(Number.isFinite).sort((x,y)=>x-y);
 if(!a.length)return 0;const m=Math.floor(a.length/2);return a.length%2?a[m]:(a[m-1]+a[m])/2;
}
function fundLabel(status){
 return({new:'Mới xuất hiện trong top công bố',removed:'Không còn trong top công bố',increased:'Tăng tỷ trọng công bố',decreased:'Giảm tỷ trọng công bố',mixed:'Có cả tăng và giảm',stable:'Ít thay đổi'})[status]||'Ít thay đổi';
}
function fundTone(status){
 if(status==='new'||status==='increased')return'green';
 if(status==='removed'||status==='decreased')return'red';
 if(status==='mixed')return'yellow';
 return'neutral';
}
function holdingPositionSignature(snapshot){
 const rows=(snapshot?.holdings||[]).map(item=>({
  fund:String(item?.fundCode||item?.fundId||item?.fundName||'').trim(),
  symbol:String(item?.symbol||'').toUpperCase().trim(),
  weight:n(item?.weight)
 })).filter(x=>x.fund&&x.symbol).sort((a,b)=>(a.symbol+'|'+a.fund).localeCompare(b.symbol+'|'+b.fund));
 return crypto.createHash('sha256').update(JSON.stringify(rows)).digest('hex').slice(0,24);
}
function buildFundMonitor(history){
 const snapshots=(history?.snapshots||[]).filter(x=>x&&typeof x==='object'&&x.weightUnit==='FRACTION_OF_NAV'&&x.asOf);
 if(!snapshots.length)return{status:'unavailable',source:'FMARKET',reason:'Chưa có dữ liệu công bố quỹ'};
 const ordered=[...snapshots].sort((a,b)=>String(a.asOf).localeCompare(String(b.asOf)));
 const latest=ordered[ordered.length-1],latestPositionSignature=holdingPositionSignature(latest);
 let previous=null,lastChangedAsOf=String(latest.asOf);
 for(let i=ordered.length-2;i>=0;i--){
  const sig=holdingPositionSignature(ordered[i]);
  if(sig===latestPositionSignature){lastChangedAsOf=String(ordered[i].asOf);continue;}
  previous=ordered[i];break;
 }
 const previousPositionSignature=previous?holdingPositionSignature(previous):null;
 const signature=crypto.createHash('sha256').update(JSON.stringify({
  asOf:String(latest.asOf),latestPositionSignature,
  previousAsOf:previous?String(previous.asOf):null,previousPositionSignature
 })).digest('hex').slice(0,20);
 const group=snapshot=>{
  const by=new Map();
  for(const item of snapshot?.holdings||[]){
   const symbol=String(item?.symbol||'').toUpperCase().trim();if(!symbol)continue;
   const fundKey=String(item?.fundCode||item?.fundId||item?.fundName||'').trim();if(!fundKey)continue;
   if(!by.has(symbol))by.set(symbol,new Map());
   by.get(symbol).set(fundKey,item);
  }
  return by;
 };
 const current=group(latest),prior=group(previous);
 const symbols=[...new Set([...current.keys(),...prior.keys()])].sort();
 const rows=[],alerts=[];
 for(const symbol of symbols){
  const now=current.get(symbol)||new Map(),old=prior.get(symbol)||new Map();
  const fundKeys=[...new Set([...now.keys(),...old.keys()])].sort();
  const details=fundKeys.map(fundKey=>{
   const a=now.get(fundKey)||null,b=old.get(fundKey)||null;
   const cw=a?n(a.weight):null,pw=b?n(b.weight):null;
   let status='stable',deltaPP=null;
   if(a&&!b)status='new';
   else if(!a&&b)status='removed';
   else if(cw!==null&&pw!==null){
    deltaPP=round((cw-pw)*100,2);
    if(deltaPP>=FUND_CHANGE_THRESHOLD_PP)status='increased';
    else if(deltaPP<=-FUND_CHANGE_THRESHOLD_PP)status='decreased';
   }
   const material=status!=='stable';
   const src=a||b||{};
   return{
    fundCode:String(src.fundCode||fundKey),fundName:String(src.fundName||src.fundCode||fundKey),
    status,label:fundLabel(status),tone:fundTone(status),material,
    currentWeightPct:cw===null?null:round(cw*100,2),
    previousWeightPct:pw===null?null:round(pw*100,2),
    deltaPP,
    reportDate:a?.reportDate||b?.reportDate||null,
    navMomentum20Pct:n(a?.navMomentum20)===null?null:round(n(a.navMomentum20)*100,2),
    navVolatility20Pct:n(a?.navVolatility20)===null?null:round(n(a.navVolatility20)*100,2)
   };
  });
  const active=details.filter(x=>x.currentWeightPct!==null);
  const changes=details.filter(x=>x.material);
  const inc=changes.filter(x=>x.status==='increased'||x.status==='new').length;
  const dec=changes.filter(x=>x.status==='decreased'||x.status==='removed').length;
  let status='stable';
  if(inc&&dec)status='mixed';else if(inc)status='increased';else if(dec)status='decreased';
  const numericChanges=details.filter(x=>Number.isFinite(Number(x.deltaPP)));
  const largest=[...numericChanges].sort((a,b)=>Math.abs(Number(b.deltaPP))-Math.abs(Number(a.deltaPP)))[0]||null;
  const activeWeights=active.map(x=>x.currentWeightPct).filter(Number.isFinite);
  const row={
   symbol,currentFundCount:active.length,previousFundCount:details.filter(x=>x.previousWeightPct!==null).length,
   averageWeightPct:activeWeights.length?round(avg(activeWeights),2):null,
   largestWeightPct:activeWeights.length?round(Math.max(...activeWeights),2):null,
   largestChangePP:largest?round(largest.deltaPP,2):null,
   materialChanges:changes.length,status,label:fundLabel(status),tone:fundTone(status),details
  };
  if(row.currentFundCount>0||row.materialChanges>0)rows.push(row);
  for(const d of changes){
   alerts.push({
    id:symbol+':'+d.fundCode+':'+d.status,symbol,fundCode:d.fundCode,fundName:d.fundName,
    status:d.status,label:d.label,tone:d.tone,currentWeightPct:d.currentWeightPct,
    previousWeightPct:d.previousWeightPct,deltaPP:d.deltaPP,reportDate:d.reportDate,
    priority:(d.status==='new'||d.status==='removed'?100:Math.abs(Number(d.deltaPP)||0))
   });
  }
 }
 rows.sort((a,b)=>b.materialChanges-a.materialChanges||Math.abs(Number(b.largestChangePP)||0)-Math.abs(Number(a.largestChangePP)||0)||b.currentFundCount-a.currentFundCount||a.symbol.localeCompare(b.symbol));
 alerts.sort((a,b)=>b.priority-a.priority||a.symbol.localeCompare(b.symbol)||a.fundCode.localeCompare(b.fundCode));
 const latestHoldings=latest.holdings||[];
 const reportDates=latestHoldings.map(x=>String(x?.reportDate||'')).filter(Boolean).sort();
 const uniqueFunds=new Set(latestHoldings.map(x=>String(x?.fundCode||x?.fundId||'')).filter(Boolean));
 return{
  status:'ok',source:'FMARKET',sourceRole:'DISCLOSED_FUND_CONTEXT',asOf:String(latest.asOf),
  reportDate:reportDates.length?reportDates[reportDates.length-1]:null,
  generatedAt:latest.generatedAt||history?.generatedAt||null,
  lastChangedAsOf,previousAsOf:previous?String(previous.asOf):null,
  comparisonMode:'LAST_MEANINGFUL_HOLDING_CHANGE',
  snapshotCount:ordered.length,funds:uniqueFunds.size,holdingRows:latestHoldings.length,
  symbols:current.size,changedSymbols:rows.filter(x=>x.materialChanges>0).length,
  materialChanges:alerts.length,thresholdPP:FUND_CHANGE_THRESHOLD_PP,signature,
  rows,alerts:alerts.slice(0,60)
 };
}
function loadFundMonitor(historyPath=FUND_HISTORY_PATH){
 try{return buildFundMonitor(JSON.parse(fs.readFileSync(historyPath,'utf8')));}
 catch(error){return{status:'unavailable',source:'FMARKET',reason:'Không đọc được dữ liệu quỹ',error:String(error?.message||error).slice(0,180)};}
}
function vnDay(value){
 const d=new Date(value);if(!Number.isFinite(d.getTime()))return'';
 return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(d);
}
function viDate(value){
 const d=new Date(value);if(!Number.isFinite(d.getTime()))return'';
 return new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit'}).format(d);
}
function viTime(value){
 const d=new Date(value);if(!Number.isFinite(d.getTime()))return'';
 return new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',hour12:false}).format(d);
}
function level(score){return RISK_V2.level(score);}
function trend(current,previous,comparisonLabel='',previousSourceTime=null){
 if(previous===null||previous===undefined)return{label:'Mới bắt đầu ghi nhận',delta:null,direction:'flat',previousScore:null,previousSourceTime:null,comparisonLabel:'Chưa có mốc dữ liệu trước'};
 const delta=round((Number(current)||0)-(Number(previous)||0),1);
 let label='Ít thay đổi',direction='flat';
 if(delta>=8){label='Tăng nhanh';direction='up';}
 else if(delta>=3){label='Đang tăng';direction='up';}
 else if(delta<=-8){label='Hạ nhanh';direction='down';}
 else if(delta<=-3){label='Đang hạ';direction='down';}
 return{label,delta,direction,previousScore:round(previous,1),previousSourceTime,comparisonLabel};
}
function liveRows(quotes,strategy){
 const sourceTime=quotes.latestSourceTime||quotes.sourceTime||null;
 const day=vnDay(sourceTime);
 const rows=[];
 for(const [symbol,q] of Object.entries(quotes.quotes||{})){
  const s=(strategy.symbols||{})[symbol];
  const price=n(q?.price),change=n(q?.changePct);
  if(!s||q?.status==='retained'||!price||change===null)continue;
  if(s.cadence!=='LIVE_15M'||String(s.barDate||'')!==day)continue;
  const c=s.current||{};
  rows.push({
   symbol,q,s,price,change,
   volume:n(q.volume)||0,
   reference:n(q.reference)||price,
   rangePct:(n(q.high)!==null&&n(q.low)!==null&&(n(q.reference)||price)>0)?Math.max(0,(n(q.high)-n(q.low))/(n(q.reference)||price)*100):0,
   atrPct:n(c.atr14)!==null&&price>0?n(c.atr14)/price*100:0,
   volumeRatio:n(c.volumeRatio20)||0,
   cmf:n(c.cmf20),
   sma20:n(c.sma20),
   sma50:n(c.sma50)
  });
 }
 return{rows,sourceTime,day};
}
function sectorRows(rows,calibration=null,sourceTime=null){
 return RISK_V2.sectorRowsV2(rows,calibration,sourceTime);
}
function stockRisk(r){
 const loss=0.35*scale(-r.change,0,5);
 const selling=r.change<0?0.20*scale(r.volumeRatio,0.8,2.5):0;
 const vol=0.15*scale(r.rangePct,1,5);
 const trendPenalty=(r.sma20&&r.price<r.sma20?10:0)+(r.sma50&&r.price<r.sma50?10:0);
 const flow=r.cmf!==null&&r.cmf<-0.1?0.10*scale(-r.cmf,0.1,0.4):0;
 const score=clamp(loss+selling+vol+trendPenalty+flow);
 const reasons=[];
 if(r.change<=-2)reasons.push('Giảm mạnh trong phiên');
 if(r.change<0&&r.volumeRatio>=1.2)reasons.push('Khối lượng cao khi giá giảm');
 if(r.rangePct>=3)reasons.push('Biên độ trong phiên lớn');
 if(r.sma20&&r.price<r.sma20)reasons.push('Giá dưới trung bình 20 phiên');
 if(r.sma50&&r.price<r.sma50)reasons.push('Giá dưới trung bình 50 phiên');
 if(r.cmf!==null&&r.cmf<-0.1)reasons.push('Áp lực dòng tiền nghiêng về bán');
 return{symbol:r.symbol,score:round(score,1),level:level(score),changePct:round(r.change,2),volumeRatio:round(r.volumeRatio,2),rangePct:round(r.rangePct,2),atrPct:round(r.atrPct,2),reasons:reasons.slice(0,3)};
}
function componentScores(rows,sectors,sourceTime=null,marketCalibration=null){
 const raw=RISK_V2.rawComponents(rows,sectors,sourceTime,marketCalibration?.fragilityContext||{});
 return RISK_V2.detailsForComponents(RISK_V2.calibratedComponents(raw,marketCalibration));
}
function overallFromComponents(components,marketCalibration=null){
 return RISK_V2.overallFromComponents(components,marketCalibration);
}
function contributionRows(components,previousPoint){
 return RISK_V2.contributionRows(components,previousPoint);
}
function historicalRow(bars,idx,symbol){
 if(idx<50)return null;
 const bar=bars[idx],prev=bars[idx-1];
 const price=n(bar.close),reference=n(prev.close);
 if(!price||!reference)return null;
 const range=(n(bar.high)!==null&&n(bar.low)!==null)?Math.max(0,(n(bar.high)-n(bar.low))/reference*100):0;
 const atrValues=[];
 for(let i=Math.max(1,idx-13);i<=idx;i++){
  const b=bars[i],p=bars[i-1],hi=n(b.high),lo=n(b.low),pc=n(p.close);
  if(hi===null||lo===null||pc===null)continue;
  atrValues.push(Math.max(hi-lo,Math.abs(hi-pc),Math.abs(lo-pc)));
 }
 const window20=bars.slice(Math.max(0,idx-19),idx+1);
 const volAvg=avg(window20.map(x=>x.volume));
 let mfv=0,volSum=0;
 for(const b of window20){
  const hi=n(b.high),lo=n(b.low),cl=n(b.close),vol=n(b.volume)||0;
  if(hi===null||lo===null||cl===null)continue;
  const mult=hi===lo?0:((cl-lo)-(hi-cl))/(hi-lo);
  mfv+=mult*vol;volSum+=vol;
 }
 return{
  symbol,price,reference,change:(price/reference-1)*100,volume:n(bar.volume)||0,
  rangePct:range,atrPct:price>0?avg(atrValues)/price*100:0,
  volumeRatio:volAvg>0?(n(bar.volume)||0)/volAvg:0,cmf:volSum>0?mfv/volSum:null,
  sma20:avg(window20.map(x=>x.close)),
  sma50:avg(bars.slice(idx-49,idx+1).map(x=>x.close))
 };
}
function buildHistoricalBaseline(marketDir,symbols,currentDay,marketCalibration=null){
 const rows=[];let baselineDate='';
 for(const symbol of symbols){
  try{
   const data=JSON.parse(fs.readFileSync(path.join(marketDir,'history',symbol+'.json'),'utf8'));
   const bars=Array.isArray(data.bars)?data.bars:[];
   let idx=-1;
   for(let i=bars.length-1;i>=0;i--){if(String(bars[i]?.time||'')<String(currentDay)){idx=i;break;}}
   if(idx<0)continue;
   const row=historicalRow(bars,idx,symbol);if(!row)continue;
   rows.push(row);if(!baselineDate||String(bars[idx].time)>baselineDate)baselineDate=String(bars[idx].time);
  }catch{}
 }
 if(rows.length<Math.ceil(Math.max(1,symbols.length)*.85)||!baselineDate)return null;
 const sameDateRows=rows.filter(r=>{
  try{
   const data=JSON.parse(fs.readFileSync(path.join(marketDir,'history',r.symbol+'.json'),'utf8'));
   return (data.bars||[]).some(b=>String(b.time)===baselineDate);
  }catch{return false;}
 });
 const useRows=sameDateRows.length>=Math.ceil(symbols.length*.80)?sameDateRows:rows;
 const sourceTime=baselineDate+'T14:45:00+07:00';
 const sectors=sectorRows(useRows,null,sourceTime),components=componentScores(useRows,sectors,sourceTime,marketCalibration),overall=overallFromComponents(components,marketCalibration);
 return{
  sourceTime:sourceTime,sourceDate:baselineDate,score:overall.score,level:overall.level.key,
  components:Object.fromEntries(Object.entries(components).map(([k,v])=>[k,v.score])),
  basis:'previous-session-close',coverage:useRows.length
 };
}
function alertSpec(id,title,component,enter,exit,evidence){
 return{id,title,score:component.score,enter,exit,evidence};
}
function buildAlerts(components,overall,previous,sourceTime){
 const prevMap=new Map((previous?.alerts||[]).map(a=>[a.id,a]));
 const specs=[
  {id:'market-high',title:'Rủi ro thị trường đang cao',score:overall.score,enter:85,exit:78,evidence:`Điểm rủi ro chung hiện là ${overall.score}/100.`},
  alertSpec('breadth','Số mã giảm đang lan rộng',components.breadth,85,75,components.breadth.detail),
  alertSpec('volatility','Biến động đang ở vùng bất thường',components.volatility,85,75,components.volatility.detail),
  alertSpec('liquidity','Thanh khoản và áp lực bán đang xấu đi',components.liquidity,85,75,components.liquidity.detail),
  alertSpec('contagion','Nhiều nhóm ngành đang đồng biến theo chiều xấu',components.contagion,85,75,components.contagion.detail),
  alertSpec('concentration','Giao dịch tập trung trong lúc độ rộng suy yếu',components.concentration,90,80,components.concentration.detail)
 ];
 const previousScores={
  'market-high':n(previous?.overall?.score),
  breadth:n(previous?.components?.breadth?.score),
  volatility:n(previous?.components?.volatility?.score),
  liquidity:n(previous?.components?.liquidity?.score),
  contagion:n(previous?.components?.contagion?.score),
  concentration:n(previous?.components?.concentration?.score)
 };
 const alerts=[];
 for(const s of specs){
  const old=prevMap.get(s.id);
  const prevScore=previousScores[s.id];
  const immediate=Math.min(100,s.enter+10);
  const confirmed=Number(s.score)>=immediate||(Number(s.score)>=s.enter&&prevScore!==null&&Number(prevScore)>=s.enter);
  const active=old?Number(s.score)>=s.exit:confirmed;
  if(!active)continue;
  alerts.push({id:s.id,title:s.title,score:round(s.score,1),level:level(s.score),startedAt:old?.startedAt||sourceTime,lastSeen:sourceTime,evidence:s.evidence});
 }
 return alerts.sort((a,b)=>b.score-a.score);
}
function buildSectorAlerts(sectors,previous,sourceTime){
 const prevMap=new Map((previous?.alerts||[]).map(a=>[a.id,a])),alerts=[];
 const previousSectorScores=new Map((previous?.sectors||[]).map(s=>[s.id,n(s.score)]));
 for(const s of sectors||[]){
  if(!s.alertEligible||!Number.isFinite(Number(s.threshold)))continue;
  const id='sector-'+s.id,old=prevMap.get(id),enter=Number(s.threshold),exit=Number(s.exitThreshold??(enter-7.5));
  const prevScore=previousSectorScores.get(s.id);
  const immediate=Math.min(100,enter+10);
  const confirmed=Number(s.score)>=immediate||(Number(s.score)>=enter&&prevScore!==undefined&&prevScore!==null&&Number(prevScore)>=enter);
  const active=old?Number(s.score)>=exit:confirmed;if(!active)continue;
  const aboveThreshold=Number(s.score)>=enter;
  const bt=s.backtest||{},lift=Number(bt.precisionLift),precision=Number(bt.precision),base=Number(bt.baseRate);
  const evidence=[
   'Điểm ngành '+round(s.score,1)+'/100; ngưỡng căng thẳng lịch sử '+round(enter,1)+'/100',
   round(s.declinePct,1)+'% mã trong ngành đang giảm',
   'thay đổi trung vị '+(Number(s.medianChangePct)>0?'+':'')+round(s.medianChangePct,2)+'%'
  ];
  if(bt.continuationValidated&&Number.isFinite(lift)&&Number.isFinite(precision)&&Number.isFinite(base))evidence.push('Backtest T+3: '+round(precision*100,1)+'% so với nền '+round(base*100,1)+'%; lift '+round(lift,2)+'x');
  alerts.push({
   id,title:s.label+(aboveThreshold?' chạm ngưỡng căng thẳng lịch sử':' vẫn trong vùng cảnh báo'),score:round(s.score,1),
   level:{key:Number(s.score)>=enter+10?'high':'watch',label:Number(s.score)>=enter+10?'Cao':'Cần theo dõi',tone:Number(s.score)>=enter+10?'red':'yellow'},
   startedAt:old?.startedAt||sourceTime,lastSeen:sourceTime,evidence:evidence.join('. '),
   sectorId:s.id,threshold:round(enter,1),backtestValidated:true,continuationValidated:bt.continuationValidated===true
  });
 }
 return alerts;
}
function alertHistory(previous,alerts,sourceTime){
 const history=Array.isArray(previous?.alertHistory)?previous.alertHistory.filter(Boolean):[];
 const old=new Map((previous?.alerts||[]).map(x=>[x.id,x])),now=new Map(alerts.map(x=>[x.id,x]));
 for(const a of alerts)if(!old.has(a.id))history.push({id:a.id,title:a.title,type:'Bắt đầu',time:sourceTime,score:a.score,level:a.level});
 for(const a of previous?.alerts||[])if(!now.has(a.id))history.push({id:a.id,title:a.title,type:'Đã hạ',time:sourceTime,score:a.score,level:level(0)});
 return history.slice(-60);
}
function buildRiskSnapshot(quotes,strategy,previous=null,generatedAt=new Date().toISOString(),baselinePoint=null,fundMonitor=null,sectorCalibration=null,marketCalibration=null){
 if(!quotes||quotes.status!=='ok')throw new Error('quotes snapshot is not ok');
 if(!strategy||strategy.status!=='ok')throw new Error('strategy snapshot is not ok');
 const latest=quotes.latestSourceTime||quotes.sourceTime||null;
 if(!latest||String(strategy.sourceTime||'')!==String(latest))throw new Error('risk inputs are not aligned');
 const {rows,sourceTime,day}=liveRows(quotes,strategy);
 const expected=Math.max(1,Number(quotes.expected)||Object.keys(quotes.quotes||{}).length);
 if(rows.length<Math.ceil(expected*.90))throw new Error(`risk live coverage below 90%: ${rows.length}/${expected}`);
 const rawSectors=sectorRows(rows,sectorCalibration,sourceTime),components=componentScores(rows,rawSectors,sourceTime,marketCalibration),overall=overallFromComponents(components,marketCalibration);
 let oldTimeline=Array.isArray(previous?.timeline)?previous.timeline.filter(x=>x&&x.sourceTime):[];
 const hasDifferent=oldTimeline.some(x=>String(x.sourceTime)!==String(sourceTime));
 if(!hasDifferent&&baselinePoint?.sourceTime&&String(baselinePoint.sourceTime)!==String(sourceTime))oldTimeline=[baselinePoint,...oldTimeline];
 const previousPoint=[...oldTimeline].reverse().find(x=>String(x.sourceTime)!==String(sourceTime))||null;
 let comparisonLabel='Chưa có mốc dữ liệu trước';
 if(previousPoint){
  comparisonLabel=vnDay(previousPoint.sourceTime)===day?'So với mốc '+viTime(previousPoint.sourceTime):'So với cuối phiên '+viDate(previousPoint.sourceTime);
 }
 const timeline=[...oldTimeline.filter(x=>String(x.sourceTime)!==String(sourceTime)),{
  sourceTime,sourceDate:day,score:overall.score,level:overall.level.key,
  components:Object.fromEntries(Object.entries(components).map(([k,v])=>[k,v.score])),basis:'live'
 }].slice(-120);
 const topRisk=rows.map(stockRisk).sort((a,b)=>b.score-a.score||a.symbol.localeCompare(b.symbol)).slice(0,15);
 const sectorAlerts=buildSectorAlerts(rawSectors,previous,sourceTime);
 const activeSectorIds=new Set(sectorAlerts.map(x=>x.sectorId));
 const sectors=rawSectors.map(s=>({
  ...s,
  alertActive:activeSectorIds.has(s.id),
  nearThreshold:s.alertEligible&&!activeSectorIds.has(s.id)&&Number(s.score)>=Math.max(0,Number(s.threshold)-10)
 })).sort((a,b)=>{
  const ar=a.alertActive?3:a.nearThreshold?2:1,br=b.alertActive?3:b.nearThreshold?2:1;
  return br-ar||Number(b.score)-Number(a.score);
 });
 const alerts=[...buildAlerts(components,overall,previous,sourceTime),...sectorAlerts].sort((a,b)=>b.score-a.score);
 const breadthStats=components.breadth.stats;
 const contributions=contributionRows(components,previousPoint);
 const tr=trend(overall.score,previousPoint?.score,comparisonLabel,previousPoint?.sourceTime||null);
 const previousClosePoint=[...oldTimeline].reverse().find(x=>x?.sourceTime&&vnDay(x.sourceTime)!==day)||null;
 const sessionTr=trend(
  overall.score,
  previousClosePoint?.score,
  previousClosePoint?'So với cuối phiên '+viDate(previousClosePoint.sourceTime):'Chưa có cuối phiên trước',
  previousClosePoint?.sourceTime||null
 );
 return{
  version:VERSION,methodVersion:METHOD_VERSION,status:'ok',generatedAt,sourceTime,sourceDate:day,
  coverage:{quotes:rows.length,expected,strategyLive:rows.length,sectors:sectors.length},
  overall,trend:tr,sessionTrend:sessionTr,components,contributions,sectors,alerts,alertHistory:alertHistory(previous,alerts,sourceTime),topRisk,timeline,
  fundMonitor:fundMonitor||previous?.fundMonitor||{status:'unavailable',source:'FMARKET',reason:'Chưa có dữ liệu quỹ'},
  sectorCalibration:sectorCalibration?{version:sectorCalibration.version,status:sectorCalibration.status,forSession:sectorCalibration.forSession,validatedSectors:sectorCalibration.validatedSectors,continuationValidatedSectors:sectorCalibration.continuationValidatedSectors,totalSectors:sectorCalibration.totalSectors,methodology:sectorCalibration.methodology}:null,
  marketCalibration:marketCalibration?{version:marketCalibration.version,status:marketCalibration.status,forSession:marketCalibration.forSession,samples:marketCalibration.samples,trainingSamples:marketCalibration.trainingSamples,fragilityContext:marketCalibration.fragilityContext,backtest:marketCalibration.backtest}:null,
  marketCounts:{advancing:rows.filter(r=>r.change>0).length,declining:rows.filter(r=>r.change<0).length,unchanged:rows.filter(r=>r.change===0).length,...breadthStats},
  breadthGroups:{
   advancing:rows.filter(r=>r.change>0).sort((a,b)=>b.change-a.change).map(r=>({symbol:r.symbol,changePct:round(r.change,2),price:round(r.price,2),volumeRatio:round(r.volumeRatio,2)})),
   declining:rows.filter(r=>r.change<0).sort((a,b)=>a.change-b.change).map(r=>({symbol:r.symbol,changePct:round(r.change,2),price:round(r.price,2),volumeRatio:round(r.volumeRatio,2)})),
   unchanged:rows.filter(r=>r.change===0).sort((a,b)=>a.symbol.localeCompare(b.symbol)).map(r=>({symbol:r.symbol,changePct:0,price:round(r.price,2),volumeRatio:round(r.volumeRatio,2)}))
  },
  methodology:{
   weights:WEIGHTS,
   description:'Điểm 0-100 là thước đo căng thẳng tương đối với lịch sử. Dữ liệu trong phiên được điều chỉnh theo thời gian giao dịch trước khi so sánh.',
   scope:'HOSE Core + Liquid có dữ liệu trực tiếp',
   comparison:'So sánh ngắn hạn dùng mốc cập nhật trước; mốc đầu ngày dùng cuối phiên giao dịch trước.',
   calibration:'Các thành phần được xếp theo phân phối lịch sử; mức đồng biến ngành dùng tương quan downside lịch sử. Tập trung giao dịch chỉ làm tăng rủi ro khi độ rộng thị trường cùng suy yếu.',
   alertRule:'Cảnh báo chỉ bật khi điểm vào vùng cao và chỉ tắt sau khi hạ xuống mức an toàn hơn. Cảnh báo trạng thái và bằng chứng giảm tiếp 3 phiên được đánh giá riêng.'
  }
 };
}
function main(){
 const out=path.resolve(process.argv[2]||'');
 if(!process.argv[2])throw new Error('Usage: node build_risk_monitor.cjs <market-dir>');
 const read=name=>JSON.parse(fs.readFileSync(path.join(out,name),'utf8'));
 const quotes=read('quotes.json'),strategy=read('strategy-indicators.json');
 let previous=null;try{previous=read('risk-monitor.json');}catch{}
 let sectorCalibration=null;try{sectorCalibration=read('sector-risk-calibration.json');}catch{}
 let marketCalibration=null;try{marketCalibration=read('market-risk-calibration.json');}catch{}
 if(!marketCalibration||marketCalibration.status!=='ok'||String(marketCalibration.forSession||'')!==String(vnDay(quotes.latestSourceTime||quotes.sourceTime||'')))throw new Error('market risk calibration is unavailable or stale');
 const fundMonitor=loadFundMonitor();
 const latest=quotes.latestSourceTime||quotes.sourceTime||null,day=vnDay(latest);
 const reusable=previous&&previous.status==='ok'&&String(previous.sourceTime||'')===String(latest||'')&&previous.methodVersion===METHOD_VERSION&&Array.isArray(previous.contributions)&&previous.trend&&Object.prototype.hasOwnProperty.call(previous.trend,'comparisonLabel')&&String(previous.fundMonitor?.signature||'')===String(fundMonitor?.signature||'')&&String(previous.sectorCalibration?.version||'')===String(sectorCalibration?.version||'')&&String(previous.sectorCalibration?.forSession||'')===String(sectorCalibration?.forSession||'')&&String(previous.marketCalibration?.version||'')===String(marketCalibration?.version||'')&&String(previous.marketCalibration?.forSession||'')===String(marketCalibration?.forSession||'');
 if(reusable){
  console.log(JSON.stringify({status:previous.status,score:previous.overall?.score,level:previous.overall?.level?.label,coverage:previous.coverage,sourceTime:previous.sourceTime,trend:previous.trend,alerts:(previous.alerts||[]).length,timeline:(previous.timeline||[]).length,reused:true}));
  return;
 }
 const compatiblePrevious=previous?.methodVersion===METHOD_VERSION?previous:null;
 const oldTimeline=Array.isArray(compatiblePrevious?.timeline)?compatiblePrevious.timeline:[];
 const needsBaseline=!oldTimeline.some(x=>x?.sourceTime&&String(x.sourceTime)!==String(latest));
 const symbols=Object.entries(quotes.quotes||{}).filter(([,q])=>q?.status!=='retained').map(([s])=>s);
 const baseline=needsBaseline?buildHistoricalBaseline(out,symbols,day,marketCalibration):null;
 const snapshot=buildRiskSnapshot(quotes,strategy,compatiblePrevious,new Date().toISOString(),baseline,fundMonitor,sectorCalibration,marketCalibration);
 fs.writeFileSync(path.join(out,'risk-monitor.json'),JSON.stringify(snapshot));
 console.log(JSON.stringify({status:snapshot.status,score:snapshot.overall.score,level:snapshot.overall.level.label,coverage:snapshot.coverage,sourceTime:snapshot.sourceTime,trend:snapshot.trend,alerts:snapshot.alerts.length,timeline:snapshot.timeline.length,funds:snapshot.fundMonitor?.funds||0,fundSymbols:snapshot.fundMonitor?.symbols||0,fundChanges:snapshot.fundMonitor?.materialChanges||0,validatedSectors:snapshot.sectorCalibration?.validatedSectors||0,sectorAlerts:(snapshot.sectors||[]).filter(x=>x.alertActive).length}));
}
if(require.main===module)main();
module.exports={buildRiskSnapshot,buildHistoricalBaseline,buildFundMonitor,loadFundMonitor,componentScores,stockRisk,sectorRows,buildSectorAlerts,level,trend,scale,median,overallFromComponents,contributionRows,WEIGHTS,SECTORS};
