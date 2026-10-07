(function(root,factory){
 const api=factory();
 if(typeof module!=='undefined'&&module.exports)module.exports=api;
 root.FinStrategyIntelligenceCore=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const VERSION='FINQUERY-STRATEGY-INTELLIGENCE-1.0';
 const STRATEGIES={
  breakout_volume:{label:'Breakout + Volume',family:'Breakout',horizon:'5–20 phiên',risk:'Trung bình',regime:{UPTREND_STRONG:96,UPTREND_FRAGILE:82,SIDEWAYS:52,DOWNTREND:30,STRESS:20}},
  ema_adx:{label:'EMA Trend + ADX',family:'Xu hướng',horizon:'10–30 phiên',risk:'Trung bình',regime:{UPTREND_STRONG:94,UPTREND_FRAGILE:86,SIDEWAYS:48,DOWNTREND:34,STRESS:20}},
  macd_rsi:{label:'MACD + RSI xác nhận',family:'Động lượng',horizon:'5–15 phiên',risk:'Trung bình',regime:{UPTREND_STRONG:88,UPTREND_FRAGILE:82,SIDEWAYS:66,DOWNTREND:42,STRESS:30}},
  momentum_recovery:{label:'Momentum hồi phục',family:'Hồi phục',horizon:'3–12 phiên',risk:'Trung bình–cao',regime:{UPTREND_STRONG:78,UPTREND_FRAGILE:84,SIDEWAYS:74,DOWNTREND:56,STRESS:36}},
  bollinger_rebound:{label:'Bollinger Rebound',family:'Mean reversion',horizon:'2–10 phiên',risk:'Trung bình–cao',regime:{UPTREND_STRONG:38,UPTREND_FRAGILE:48,SIDEWAYS:86,DOWNTREND:70,STRESS:45}}
 };
 const DEFAULT_EXECUTION=Object.freeze({
  exchange:'HOSE',boardLot:100,priceBandPct:7,sellTaxPct:0.1,settlement:'T+2',
  brokerFeePct:0.15,slippagePct:0.10,maxPositionPct:20,maxAdvPct:5,initialCapital:1000000000
 });
 const REGIME_LABELS={
  UPTREND_STRONG:'Tăng rõ · độ rộng xác nhận',
  UPTREND_FRAGILE:'Nghiêng tăng · cần chọn lọc',
  SIDEWAYS:'Đi ngang · phân hóa',
  DOWNTREND:'Nghiêng giảm',
  STRESS:'Rủi ro cao'
 };
 const finite=v=>Number.isFinite(Number(v))?Number(v):null;
 const clamp=(v,a=0,b=100)=>Math.max(a,Math.min(b,Number(v)||0));
 const mean=a=>{const x=a.filter(Number.isFinite);return x.length?x.reduce((s,v)=>s+v,0)/x.length:null;};
 const liveRows=snapshot=>Object.values(snapshot?.symbols||{}).filter(r=>{
  const c=r?.current||{},price=finite(c.price);
  return price!==null&&price>0&&String(r?.tier||'').toUpperCase()!=='DISCOVERY'&&String(r?.cadence||'').toUpperCase()!=='EOD';
 });
 const ratio=(rows,fn)=>rows.length?rows.filter(fn).length/rows.length*100:null;
 function inferRegime(snapshot,risk){
  const rows=liveRows(snapshot),counts=risk?.marketCounts||{};
  const trendUp=ratio(rows,r=>finite(r.current?.price)>finite(r.current?.sma20)&&finite(r.current?.ema20)>finite(r.current?.ema50));
  const trendDown=ratio(rows,r=>finite(r.current?.price)<finite(r.current?.sma20)&&finite(r.current?.ema20)<finite(r.current?.ema50));
  const momentum=ratio(rows,r=>(finite(r.current?.rsi14)??0)>=50&&(finite(r.current?.macdHistogram)??0)>=0);
  const volume=ratio(rows,r=>(finite(r.current?.volumeRatio20)??0)>=1.05);
  const total=(finite(counts.advancing)||0)+(finite(counts.declining)||0)+(finite(counts.unchanged)||0);
  const breadth=total>0?(finite(counts.advancing)||0)/total*100:ratio(rows,r=>(finite(r.current?.changePct)||0)>0);
  const riskScore=finite(risk?.overall?.score);
  const atrPct=mean(rows.map(r=>{const p=finite(r.current?.price),a=finite(r.current?.atr14);return p&&a!==null?a/p*100:null;}));
  const up=mean([trendUp,momentum,breadth])??50,down=mean([trendDown,breadth===null?null:100-breadth])??50;
  let id='SIDEWAYS';
  if((riskScore??0)>=85&&((breadth??50)<45||(trendUp??50)<45))id='STRESS';
  else if((trendUp??0)>=60&&(momentum??0)>=55&&(breadth??0)>=55&&(riskScore??0)<75)id='UPTREND_STRONG';
  else if((trendUp??0)>=52&&(breadth??0)>=45&&(riskScore??0)<85)id='UPTREND_FRAGILE';
  else if((trendUp??100)<=38&&(breadth??100)<=42&&down>=55)id='DOWNTREND';
  const separation=Math.abs(up-down);
  const agreement=[trendUp,momentum,breadth].filter(Number.isFinite);
  const dispersion=agreement.length?Math.max(...agreement)-Math.min(...agreement):45;
  const confidence=clamp(58+separation*.32-dispersion*.14+Math.min(10,rows.length/15),50,94);
  return{
   id,label:REGIME_LABELS[id],confidence:Math.round(confidence),coverage:rows.length,
   metrics:{trendUp:trendUp===null?null:Math.round(trendUp),momentum:momentum===null?null:Math.round(momentum),breadth:breadth===null?null:Math.round(breadth),volume:volume===null?null:Math.round(volume),risk:riskScore,atrPct:atrPct===null?null:Number(atrPct.toFixed(2))}
  };
 }
 function conditionStrength(row,id){
  const c=row?.current||{},price=finite(c.price),sma20=finite(c.sma20),ema9=finite(c.ema9),ema20=finite(c.ema20),ema50=finite(c.ema50);
  const rsi=finite(c.rsi14),hist=finite(c.macdHistogram),adx=finite(c.adx14),vol=finite(c.volumeRatio20),roc=finite(c.roc10),pctB=finite(c.bbPctB);
  const pct=(a,b)=>a!==null&&b&&b!==0?(a/b-1)*100:null;
  let s=60;
  if(id==='breakout_volume')s=mean([clamp(55+(pct(price,sma20)||0)*5,45,100),clamp(50+((vol??1)-1)*42,40,100),clamp(55+(roc??0)*5,40,100)])??60;
  else if(id==='ema_adx')s=mean([clamp(58+(pct(ema9,ema20)||0)*8,45,100),clamp(58+(pct(ema20,ema50)||0)*6,45,100),clamp(45+((adx??20)-20)*2.4,35,100)])??60;
  else if(id==='macd_rsi')s=mean([clamp(60+(hist??0)*8,45,100),clamp(55+((rsi??50)-50)*1.6,40,100)])??60;
  else if(id==='momentum_recovery')s=mean([clamp(70-Math.abs((rsi??40)-45)*1.4,40,95),clamp(62+(hist??0)*8,40,100)])??60;
  else if(id==='bollinger_rebound')s=mean([clamp(92-(pctB??.05)*160,45,100),clamp(90-Math.abs((rsi??30)-30)*2,40,100)])??60;
  return Math.round(clamp(s));
 }
 function selectivityScore(matches,total){
  if(!matches||!total)return 0;
  const p=matches/total*100;
  if(p<=3)return 78;
  if(p<=10)return 96;
  if(p<=20)return 86;
  if(p<=35)return 70;
  return 55;
 }
 function strategyRiskPenalty(id,riskScore){
  const r=Math.max(0,(finite(riskScore)??50)-65);
  const factor=id==='breakout_volume'||id==='ema_adx'?0.42:id==='macd_rsi'?0.34:id==='momentum_recovery'?0.28:0.22;
  return r*factor;
 }
 function rankStrategies(snapshot,risk,engine){
  const regime=inferRegime(snapshot,risk),rows=liveRows(snapshot),total=Math.max(1,rows.length),riskScore=regime.metrics.risk;
  const ranking=Object.entries(STRATEGIES).map(([id,meta])=>{
   const preset=engine?.PRESETS?.[id];
   const matches=preset&&engine?.scan?engine.scan(snapshot,preset).filter(r=>String(r?.tier||'').toUpperCase()!=='DISCOVERY'):[];
   const strengths=matches.map(r=>conditionStrength(r,id));
   const confirmation=mean(strengths)??0,selectivity=selectivityScore(matches.length,total),regimeFit=meta.regime[regime.id]??50;
   let score=regimeFit*.55+confirmation*.27+selectivity*.18-strategyRiskPenalty(id,riskScore);
   if(!matches.length)score=Math.min(score,regimeFit*.58);
   score=Math.round(clamp(score));
   const status=score>=82?'Phù hợp cao':score>=68?'Đáng theo dõi':score>=52?'Trung tính':'Thấp';
   return{id,...meta,score,status,regimeFit,confirmation:Math.round(confirmation),selectivity,matchesCount:matches.length,matchSymbols:matches.map(x=>x.symbol),matches};
  }).sort((a,b)=>b.score-a.score||b.matchesCount-a.matchesCount);
  return{regime,ranking};
 }
 function stockRiskMap(risk){
  return new Map((risk?.topRisk||[]).map(x=>[String(x.symbol||'').toUpperCase(),finite(x.score)]));
 }
 function rankOpportunities(ranking,snapshot,risk){
  const map=new Map(),riskMap=stockRiskMap(risk),globalRisk=finite(risk?.overall?.score)??50;
  for(const s of (ranking||[]).slice(0,5)){
   for(const row of s.matches||[]){
    const symbol=String(row?.symbol||'').toUpperCase();if(!symbol)continue;
    const tier=String(row?.tier||'').toUpperCase(),tierScore=tier==='CORE'?94:tier==='LIQUID'?82:64;
    const strength=conditionStrength(row,s.id),stockRisk=riskMap.get(symbol)??globalRisk;
    const riskPenalty=Math.max(0,stockRisk-65)*.34;
    const contribution=clamp(s.score*.48+strength*.34+tierScore*.18-riskPenalty);
    const x=map.get(symbol)||{symbol,row,strategies:[],scores:[],riskScore:stockRisk};
    x.strategies.push({id:s.id,label:s.label,score:s.score,strength});
    x.scores.push(contribution);x.riskScore=stockRisk;map.set(symbol,x);
   }
  }
  return [...map.values()].map(x=>{
   x.strategies.sort((a,b)=>b.score-a.score||b.strength-a.strength);
   const base=Math.max(...x.scores),consensusBonus=Math.min(9,Math.max(0,x.strategies.length-1)*3);
   x.score=Math.round(clamp(base+consensusBonus));
   x.primary=x.strategies[0];
   x.stance=x.riskScore>=85?'Thận trọng':x.score>=82?'Tích cực có điều kiện':x.score>=68?'Đáng theo dõi':'Theo dõi';
   return x;
  }).sort((a,b)=>b.score-a.score||a.symbol.localeCompare(b.symbol));
 }
 function money(v){return Number.isFinite(v)?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:0}).format(v):'—';}
 function investmentView(symbol,opportunities,regime){
  const x=(opportunities||[]).find(o=>o.symbol===String(symbol||'').toUpperCase());
  if(!x)return{symbol:String(symbol||'').toUpperCase(),stance:'Chưa có tín hiệu',score:null,positives:[],cautions:['Mã chưa khớp các chiến lược đang được xếp hạng ở snapshot hiện tại.'],invalidation:'Chưa có điều kiện vô hiệu để theo dõi.',primary:null};
  const c=x.row?.current||{},positives=[],cautions=[],primary=x.primary?.id;
  positives.push('Khớp '+x.primary.label+' với mức xác nhận '+x.primary.strength+'/100.');
  if(regime?.label)positives.push('Trạng thái thị trường: '+regime.label+'.');
  if((finite(c.volumeRatio20)??0)>=1.2)positives.push('Thanh khoản xác nhận: '+Number(c.volumeRatio20).toFixed(2)+'x trung bình 20 phiên.');
  if((finite(c.rsi14)??0)>=50&&finite(c.rsi14)<=70)positives.push('RSI duy trì vùng động lượng tích cực mà chưa quá nóng.');
  if(x.strategies.length>1)positives.push(x.strategies.length+' chiến lược độc lập cùng khớp mã này.');
  if(x.riskScore>=70)cautions.push('Điểm rủi ro hiện tại '+Math.round(x.riskScore)+'/100 cần được kiểm soát khi vào vị thế.');
  const rsi=finite(c.rsi14);if(rsi!==null&&rsi>72)cautions.push('RSI '+rsi.toFixed(1)+' cho thấy động lượng ngắn hạn đã cao.');
  const vol=finite(c.volumeRatio20);if(vol!==null&&vol<1)cautions.push('Thanh khoản dưới trung bình 20 phiên, mức xác nhận chưa mạnh.');
  const price=finite(c.price),sma20=finite(c.sma20);
  if(price&&sma20){const d=(price/sma20-1)*100;if(d>8)cautions.push('Giá đang cao hơn SMA20 '+d.toFixed(1)+'%, biên an toàn cho điểm vào mới giảm.');}
  if(!cautions.length)cautions.push('Theo dõi biến động giá và thanh khoản khi tín hiệu mới hình thành.');
  let invalidation='Tín hiệu mất hiệu lực khi các điều kiện chiến lược không còn đồng thời thỏa mãn.';
  if(primary==='breakout_volume')invalidation='Theo dõi mất hiệu lực khi giá đóng cửa xuống dưới SMA20'+(sma20?' ('+money(sma20)+' đ)':'')+' hoặc KL/TB20 giảm dưới 1,0x.';
  else if(primary==='ema_adx')invalidation='Theo dõi mất hiệu lực khi EMA20 không còn cao hơn EMA50 hoặc ADX suy yếu dưới 20.';
  else if(primary==='macd_rsi')invalidation='Theo dõi mất hiệu lực khi MACD mất xác nhận tăng hoặc RSI quay xuống dưới 50.';
  else if(primary==='momentum_recovery')invalidation='Theo dõi mất hiệu lực khi RSI quay lại dưới vùng 30 hoặc MACD histogram trở lại âm.';
  else if(primary==='bollinger_rebound')invalidation='Theo dõi mất hiệu lực khi giá tiếp tục bám dải Bollinger dưới mà không xuất hiện tín hiệu hồi phục.';
  return{symbol:x.symbol,stance:x.stance,score:x.score,positives,cautions,invalidation,primary:x.primary,riskScore:x.riskScore,strategies:x.strategies,current:c};
 }
 function tickSize(price){
  const p=finite(price);if(p===null||p<=0)return 10;
  if(p<10000)return 10;if(p<50000)return 50;return 100;
 }
 function roundPrice(price,mode='nearest'){
  const p=finite(price);if(p===null)return null;const t=tickSize(p),q=p/t;
  const n=mode==='floor'?Math.floor(q):mode==='ceil'?Math.ceil(q):Math.round(q);
  return n*t;
 }
 function priceBand(reference){
  const r=finite(reference);if(r===null||r<=0)return{floor:null,ceiling:null};
  return{floor:roundPrice(r*(1-DEFAULT_EXECUTION.priceBandPct/100),'ceil'),ceiling:roundPrice(r*(1+DEFAULT_EXECUTION.priceBandPct/100),'floor')};
 }
 function normalizeOrderQuantity(qty){
  const q=Math.max(0,Math.floor(finite(qty)||0));return Math.floor(q/DEFAULT_EXECUTION.boardLot)*DEFAULT_EXECUTION.boardLot;
 }
 function executionProfile(overrides={}){
  const x={...DEFAULT_EXECUTION,...overrides};
  for(const k of ['brokerFeePct','slippagePct','maxPositionPct','maxAdvPct','initialCapital'])if(finite(x[k])!==null)x[k]=finite(x[k]);
  return x;
 }
 return{VERSION,STRATEGIES,DEFAULT_EXECUTION,REGIME_LABELS,liveRows,inferRegime,conditionStrength,rankStrategies,rankOpportunities,investmentView,tickSize,roundPrice,priceBand,normalizeOrderQuantity,executionProfile,clamp};
});