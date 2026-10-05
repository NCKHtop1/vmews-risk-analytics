'use strict';
const fs=require('fs'),path=require('path');

const VERSION='FINQUERY-RISK-1.1';
const METHOD_VERSION='FINQUERY-RISK-RULES-1.1';
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
const pct=v=>Math.round(clamp(v,0,1)*1000)/10;
const round=(v,d=1)=>{const p=10**d;return Math.round((Number(v)||0)*p)/p;};
const avg=values=>{const a=(values||[]).map(n).filter(Number.isFinite);return a.length?a.reduce((x,y)=>x+y,0)/a.length:0;};
function median(values){
 const a=(values||[]).map(n).filter(Number.isFinite).sort((x,y)=>x-y);
 if(!a.length)return 0;const m=Math.floor(a.length/2);return a.length%2?a[m]:(a[m-1]+a[m])/2;
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
function level(score){
 const s=Number(score)||0;
 if(s>=80)return{key:'very-high',label:'Rất cao',tone:'red'};
 if(s>=65)return{key:'high',label:'Cao',tone:'red'};
 if(s>=50)return{key:'rising',label:'Căng thẳng tăng',tone:'yellow'};
 if(s>=35)return{key:'watch',label:'Cần theo dõi',tone:'yellow'};
 return{key:'normal',label:'Bình thường',tone:'green'};
}
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
function sectorRows(rows){
 const by=new Map(rows.map(r=>[r.symbol,r]));
 return SECTORS.map(group=>{
  const members=group.symbols.map(s=>by.get(s)).filter(Boolean);
  if(members.length<2)return null;
  const declineShare=members.filter(r=>r.change<0).length/members.length;
  const medChange=median(members.map(r=>r.change));
  const medVolume=median(members.map(r=>r.volumeRatio));
  const score=clamp(
   0.65*scale(declineShare,0.40,0.85)+
   0.25*scale(-medChange,0,2.5)+
   0.10*scale(medVolume,0.8,1.8)
  );
  return{id:group.id,label:group.label,score:round(score,1),level:level(score),members:members.length,declinePct:pct(declineShare),medianChangePct:round(medChange,2),medianVolumeRatio:round(medVolume,2)};
 }).filter(Boolean).sort((a,b)=>b.score-a.score);
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
function componentScores(rows,sectors){
 const declines=rows.filter(r=>r.change<0),severe=rows.filter(r=>r.change<=-2);
 const declineShare=rows.length?declines.length/rows.length:0;
 const severeShare=rows.length?severe.length/rows.length:0;
 const medianChange=median(rows.map(r=>r.change));
 const breadth=clamp(
  0.55*scale(declineShare,0.40,0.85)+
  0.25*scale(severeShare,0.05,0.45)+
  0.20*scale(-medianChange,0,2.5)
 );

 const ranges=rows.map(r=>r.rangePct),atrs=rows.map(r=>r.atrPct);
 const medianRange=median(ranges),medianAtr=median(atrs);
 const bigRangeShare=rows.length?rows.filter(r=>r.rangePct>=3).length/rows.length:0;
 const volatility=clamp(
  0.45*scale(medianRange,1,4)+
  0.35*scale(medianAtr,1.5,5)+
  0.20*scale(bigRangeShare,0.10,0.50)
 );

 const medianDownVol=median(declines.map(r=>r.volumeRatio));
 const heavyDownShare=rows.length?rows.filter(r=>r.change<0&&r.volumeRatio>=1.2).length/rows.length:0;
 const negativeCmfShare=rows.length?rows.filter(r=>r.cmf!==null&&r.cmf<=-0.1).length/rows.length:0;
 const liquidity=clamp(
  0.45*scale(medianDownVol,0.8,2.0)+
  0.30*scale(heavyDownShare,0.15,0.55)+
  0.25*scale(negativeCmfShare,0.25,0.70)
 );

 const turnovers=rows.map(r=>Math.max(0,r.price*r.volume)).sort((a,b)=>b-a);
 const total=turnovers.reduce((a,b)=>a+b,0)||1;
 const top5=turnovers.slice(0,5).reduce((a,b)=>a+b,0)/total;
 const top10=turnovers.slice(0,10).reduce((a,b)=>a+b,0)/total;
 const concentration=clamp(0.70*scale(top5,0.18,0.45)+0.30*scale(top10,0.32,0.65));

 const stressed=sectors.filter(s=>s.score>=60).length,high=sectors.filter(s=>s.score>=75).length;
 const contagion=sectors.length?clamp(0.70*(stressed/sectors.length*100)+0.30*(high/sectors.length*100)):0;

 return{
  breadth:{label:'Mức giảm lan rộng',score:round(breadth,1),level:level(breadth),detail:`${pct(declineShare)}% số mã đang giảm; ${pct(severeShare)}% giảm từ 2% trở lên.`,stats:{declinePct:pct(declineShare),severeDeclinePct:pct(severeShare),medianChangePct:round(medianChange,2)}},
  volatility:{label:'Biến động giá',score:round(volatility,1),level:level(volatility),detail:`Biên độ trong phiên trung vị ${round(medianRange,2)}%; mức dao động 14 phiên/giá trung vị ${round(medianAtr,2)}%.`,stats:{medianRangePct:round(medianRange,2),medianAtrPct:round(medianAtr,2),bigRangePct:pct(bigRangeShare)}},
  liquidity:{label:'Áp lực giao dịch',score:round(liquidity,1),level:level(liquidity),detail:`Khối lượng/TB20 trung vị ở nhóm giảm ${round(medianDownVol,2)} lần; ${pct(heavyDownShare)}% số mã vừa giảm vừa có khối lượng cao.`,stats:{medianDownVolumeRatio:round(medianDownVol,2),heavyDownPct:pct(heavyDownShare),negativeCmfPct:pct(negativeCmfShare)}},
  concentration:{label:'Mức tập trung giao dịch',score:round(concentration,1),level:level(concentration),detail:`5 mã giao dịch lớn nhất chiếm ${pct(top5)}% giá trị ước tính; 10 mã lớn nhất chiếm ${pct(top10)}%.`,stats:{top5TurnoverPct:pct(top5),top10TurnoverPct:pct(top10)}},
  contagion:{label:'Lan rộng giữa các nhóm ngành',score:round(contagion,1),level:level(contagion),detail:`${stressed}/${sectors.length} nhóm ngành đang có mức căng thẳng từ 60 điểm trở lên.`,stats:{stressedSectors:stressed,highSectors:high,totalSectors:sectors.length}}
 };
}
function overallFromComponents(components){
 const base=Object.entries(WEIGHTS).reduce((sum,[key,w])=>sum+(components[key]?.score||0)*w,0);
 const highCount=Object.values(components).filter(x=>x.score>=65).length;
 const amplifier=highCount>=5?10:highCount===4?8:highCount===3?5:0;
 const total=round(clamp(base+amplifier),1);
 return{score:total,level:level(total),baseScore:round(base,1),systemWideAdd:amplifier};
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
function buildHistoricalBaseline(marketDir,symbols,currentDay){
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
 const sectors=sectorRows(useRows),components=componentScores(useRows,sectors),overall=overallFromComponents(components);
 return{
  sourceTime:baselineDate+'T07:45:00.000Z',sourceDate:baselineDate,score:overall.score,level:overall.level.key,
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
  {id:'market-high',title:'Rủi ro thị trường đang cao',score:overall.score,enter:65,exit:58,evidence:`Điểm rủi ro chung hiện là ${overall.score}/100.`},
  alertSpec('breadth','Số mã giảm đang lan rộng',components.breadth,65,55,components.breadth.detail),
  alertSpec('volatility','Biến động giá tăng mạnh',components.volatility,65,55,components.volatility.detail),
  alertSpec('liquidity','Áp lực bán đi kèm giao dịch lớn',components.liquidity,65,55,components.liquidity.detail),
  alertSpec('contagion','Sự suy yếu lan sang nhiều nhóm ngành',components.contagion,60,50,components.contagion.detail),
  alertSpec('concentration','Giao dịch đang tập trung vào ít mã',components.concentration,70,60,components.concentration.detail)
 ];
 const alerts=[];
 for(const s of specs){
  const old=prevMap.get(s.id),active=s.score>=(old?s.exit:s.enter);
  if(!active)continue;
  alerts.push({id:s.id,title:s.title,score:round(s.score,1),level:level(s.score),startedAt:old?.startedAt||sourceTime,lastSeen:sourceTime,evidence:s.evidence});
 }
 return alerts.sort((a,b)=>b.score-a.score);
}
function alertHistory(previous,alerts,sourceTime){
 const history=Array.isArray(previous?.alertHistory)?previous.alertHistory.filter(Boolean):[];
 const old=new Map((previous?.alerts||[]).map(x=>[x.id,x])),now=new Map(alerts.map(x=>[x.id,x]));
 for(const a of alerts)if(!old.has(a.id))history.push({id:a.id,title:a.title,type:'Bắt đầu',time:sourceTime,score:a.score,level:a.level});
 for(const a of previous?.alerts||[])if(!now.has(a.id))history.push({id:a.id,title:a.title,type:'Đã hạ',time:sourceTime,score:a.score,level:level(0)});
 return history.slice(-60);
}
function buildRiskSnapshot(quotes,strategy,previous=null,generatedAt=new Date().toISOString(),baselinePoint=null){
 if(!quotes||quotes.status!=='ok')throw new Error('quotes snapshot is not ok');
 if(!strategy||strategy.status!=='ok')throw new Error('strategy snapshot is not ok');
 const latest=quotes.latestSourceTime||quotes.sourceTime||null;
 if(!latest||String(strategy.sourceTime||'')!==String(latest))throw new Error('risk inputs are not aligned');
 const {rows,sourceTime,day}=liveRows(quotes,strategy);
 const expected=Math.max(1,Number(quotes.expected)||Object.keys(quotes.quotes||{}).length);
 if(rows.length<Math.ceil(expected*.90))throw new Error(`risk live coverage below 90%: ${rows.length}/${expected}`);
 const sectors=sectorRows(rows),components=componentScores(rows,sectors),overall=overallFromComponents(components);
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
 const alerts=buildAlerts(components,overall,previous,sourceTime);
 const breadthStats=components.breadth.stats;
 const contributions=contributionRows(components,previousPoint);
 const tr=trend(overall.score,previousPoint?.score,comparisonLabel,previousPoint?.sourceTime||null);
 return{
  version:VERSION,methodVersion:METHOD_VERSION,status:'ok',generatedAt,sourceTime,sourceDate:day,
  coverage:{quotes:rows.length,expected,strategyLive:rows.length,sectors:sectors.length},
  overall,trend:tr,components,contributions,sectors,alerts,alertHistory:alertHistory(previous,alerts,sourceTime),topRisk,timeline,
  marketCounts:{advancing:rows.filter(r=>r.change>0).length,declining:rows.filter(r=>r.change<0).length,unchanged:rows.filter(r=>r.change===0).length,...breadthStats},
  methodology:{
   weights:WEIGHTS,
   description:'Điểm 0-100 đo mức căng thẳng đang quan sát được trên nhóm HOSE Core + Liquid có dữ liệu trực tiếp, từ giá, khối lượng và mức lan rộng của biến động. Điểm này không phải xác suất thị trường sẽ giảm.',
   scope:'HOSE Core + Liquid có dữ liệu trực tiếp',
   comparison:'Mốc so sánh ưu tiên lần cập nhật liền trước. Khi chưa có lịch sử trong ngày, FinQuery dùng điểm cuối phiên giao dịch trước được dựng lại từ dữ liệu ngày.',
   alertRule:'Cảnh báo chỉ bật khi vượt ngưỡng vào và chỉ tắt khi hạ xuống dưới ngưỡng thoát để tránh đổi màu liên tục quanh một mốc.'
  }
 };
}
function main(){
 const out=path.resolve(process.argv[2]||'');
 if(!process.argv[2])throw new Error('Usage: node build_risk_monitor.cjs <market-dir>');
 const read=name=>JSON.parse(fs.readFileSync(path.join(out,name),'utf8'));
 const quotes=read('quotes.json'),strategy=read('strategy-indicators.json');
 let previous=null;try{previous=read('risk-monitor.json');}catch{}
 const latest=quotes.latestSourceTime||quotes.sourceTime||null,day=vnDay(latest);
 const oldTimeline=Array.isArray(previous?.timeline)?previous.timeline:[];
 const needsBaseline=!oldTimeline.some(x=>x?.sourceTime&&String(x.sourceTime)!==String(latest));
 const symbols=Object.entries(quotes.quotes||{}).filter(([,q])=>q?.status!=='retained').map(([s])=>s);
 const baseline=needsBaseline?buildHistoricalBaseline(out,symbols,day):null;
 const snapshot=buildRiskSnapshot(quotes,strategy,previous,new Date().toISOString(),baseline);
 fs.writeFileSync(path.join(out,'risk-monitor.json'),JSON.stringify(snapshot));
 console.log(JSON.stringify({status:snapshot.status,score:snapshot.overall.score,level:snapshot.overall.level.label,coverage:snapshot.coverage,sourceTime:snapshot.sourceTime,trend:snapshot.trend,alerts:snapshot.alerts.length,timeline:snapshot.timeline.length}));
}
if(require.main===module)main();
module.exports={buildRiskSnapshot,buildHistoricalBaseline,componentScores,stockRisk,sectorRows,level,trend,scale,median,overallFromComponents,contributionRows,WEIGHTS,SECTORS};
