/* FinQuery Portfolio — transparent daily allocation review.
 * Pure computation, independent from DOM and the user's identity.
 */
(function(root,factory){
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 if(root)root.FinPortfolioPolicy=api;
})(typeof window==='object'?window:null,function(){'use strict';
 const PRESETS=Object.freeze({
  balanced:Object.freeze({id:'balanced',title:'Cân bằng',subtitle:'Phân tán vừa phải, giữ thanh khoản',cashPct:10,maxStockPct:30,sectorCapPct:45,driftPct:5,minTradeVnd:2000000,feeBps:15,sellTaxBps:10,lot:100}),
  equal:Object.freeze({id:'equal',title:'Chia đều',subtitle:'Phân bổ đồng đều trên các mã đang có',cashPct:5,maxStockPct:25,sectorCapPct:50,driftPct:4,minTradeVnd:1000000,feeBps:15,sellTaxBps:10,lot:100}),
  defensive:Object.freeze({id:'defensive',title:'Thận trọng',subtitle:'Giữ tiền mặt và giới hạn tập trung',cashPct:30,maxStockPct:20,sectorCapPct:35,driftPct:4,minTradeVnd:2000000,feeBps:15,sellTaxBps:10,lot:100}),
  focused:Object.freeze({id:'focused',title:'Tập trung có kiểm soát',subtitle:'Ít mã hơn, biên độ điều chỉnh rộng',cashPct:10,maxStockPct:40,sectorCapPct:65,driftPct:7,minTradeVnd:3000000,feeBps:15,sellTaxBps:10,lot:100})
 });
 const N=v=>Number.isFinite(Number(v))?Number(v):NaN;
 const clamp=(v,min,max)=>Math.min(max,Math.max(min,v));
 function normalize(input){
  const key=String(input?.preset||input?.id||'balanced');
  const base=PRESETS[key]||PRESETS.balanced;
  const cash=N(input?.cashPct??base.cashPct),drift=N(input?.driftPct??base.driftPct);
  return Object.freeze({...base,cashPct:Number.isFinite(cash)?clamp(Math.round(cash),0,50):base.cashPct,
   driftPct:Number.isFinite(drift)?clamp(Math.round(drift),2,15):base.driftPct});
 }
 function venueDate(sourceTime){
  const d=new Date(sourceTime||'');
  if(!Number.isFinite(d.getTime()))return null;
  const parts=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'})
   .formatToParts(d);
  const out=Object.fromEntries(parts.map(p=>[p.type,p.value]));
  return out.year+'-'+out.month+'-'+out.day;
 }
 function review(input){
  const cfg=normalize(input?.policy),book=input?.portfolio||{},rows=Array.isArray(book.rows)?book.rows:[];
  const generatedAt=input?.now??Date.now(),sourceTime=input?.sourceTime||null,day=venueDate(sourceTime);
  const hasPosition=rows.some(r=>N(r.quantity)>0);
  const base={policy:cfg,sourceDate:day,generatedAt:new Date(generatedAt).toISOString(),targets:[],
   trades:[],flags:[],blocked:false,why:null,driftMax:0,targetCashPct:100,asOf:sourceTime,
   estimatedCostVnd:0,estimatedBuyVnd:0,estimatedSellVnd:0,lot:cfg.lot};
  if(!hasPosition){base.why='Thêm cổ phiếu để lập kế hoạch phân bổ.';return base;}
  const nav=N(book.nav),cash=N(book.cash);
  if(!Number.isFinite(nav)||nav<=0||!Number.isFinite(cash)||cash<-.01||
     rows.some(r=>!(N(r.quantity)>0)||!Number.isFinite(N(r.value))||!(N(r.price)>0))){
   base.blocked=true;base.why='Thiếu giá hoặc NAV chưa hợp lệ. Kế hoạch tạm dừng.';return base;
  }
  if(!day){base.blocked=true;base.why='Chưa xác định được ngày dữ liệu giá.';return base;}
  const src=new Date(sourceTime).getTime();
  if(!Number.isFinite(src)||generatedAt-src>5*86400000||src-generatedAt>300000){
   base.blocked=true;base.why='Giá chưa đủ mới để lập kế hoạch. Cần đồng bộ phiên gần nhất.';return base;
  }
  // This is an observation by source session, not an automated trade or forecast.
  const filtered=rows.filter(r=>N(r.quantity)>0).map(r=>({...r,price:N(r.price),value:N(r.value),quantity:N(r.quantity)}));
  const baseWeight=Math.min((100-cfg.cashPct)/filtered.length,cfg.maxStockPct);
  const grouped=new Map();
  for(const h of filtered){
   const id=String(h.sectorId||('unknown:'+h.symbol));
   const g=grouped.get(id)||[];g.push(h);grouped.set(id,g);
  }
  const targets=[];
  for(const [sector,holders] of grouped){
   const groupTarget=Math.min(baseWeight*holders.length,cfg.sectorCapPct);
   const each=groupTarget/holders.length;
   for(const h of holders){
    const currentPct=100*h.value/nav;
    const driftPP=each-currentPct;
    targets.push({symbol:h.symbol,sectorId:sector,quantity:h.quantity,price:h.price,value:h.value,
     currentPct,targetPct:each,driftPP,deltaVnd:nav*driftPP/100});
   }
  }
  base.targets=targets.sort((a,b)=>Math.abs(b.driftPP)-Math.abs(a.driftPP));
  base.targetCashPct=clamp(100-targets.reduce((s,h)=>s+h.targetPct,0),0,100);
  base.driftMax=Math.max(0,...targets.map(h=>Math.abs(h.driftPP)));
  const estimate=(notional,side)=>notional*(cfg.feeBps+(side==='SELL'?cfg.sellTaxBps:0))/10000;
  const critical=base.targets.filter(t=>Math.abs(t.driftPP)>=cfg.driftPct&&Math.abs(t.deltaVnd)>=cfg.minTradeVnd);
  // Sell overweight positions first. Buys cannot spend projected reserve cash.
  let liquid=cash;
  const sells=critical.filter(t=>t.deltaVnd<0).sort((a,b)=>a.driftPP-b.driftPP);
  for(const t of sells){
   const qty=Math.min(Math.floor(Math.abs(t.deltaVnd)/t.price/cfg.lot)*cfg.lot,
                      Math.floor(t.quantity/cfg.lot)*cfg.lot);
   const gross=qty*t.price;
   if(qty<cfg.lot||gross<cfg.minTradeVnd)continue;
   const cost=estimate(gross,'SELL');
   liquid+=gross-cost;
   base.estimatedCostVnd+=cost;base.estimatedSellVnd+=gross;
   base.trades.push({symbol:t.symbol,side:'SELL',quantity:qty,price:t.price,
    grossVnd:gross,estimatedCostVnd:cost,netCashChangeVnd:gross-cost,
    currentPct:t.currentPct,targetPct:t.targetPct,driftPP:t.driftPP});
  }
  const cashReserve=nav*base.targetCashPct/100;
  let usable=Math.max(0,liquid-cashReserve);
  const buys=critical.filter(t=>t.deltaVnd>0).sort((a,b)=>b.deltaVnd-a.deltaVnd);
  for(const t of buys){
   const desiredQty=Math.floor(t.deltaVnd/t.price/cfg.lot)*cfg.lot;
   const budgetQty=Math.floor(usable/(t.price*(1+cfg.feeBps/10000))/cfg.lot)*cfg.lot;
   const qty=Math.min(desiredQty,budgetQty),gross=qty*t.price;
   if(qty<cfg.lot||gross<cfg.minTradeVnd)continue;
   const cost=estimate(gross,'BUY');
   if(gross+cost>usable+0.01)continue;
   usable-=gross+cost;
   base.estimatedCostVnd+=cost;base.estimatedBuyVnd+=gross;
   base.trades.push({symbol:t.symbol,side:'BUY',quantity:qty,price:t.price,
    grossVnd:gross,estimatedCostVnd:cost,netCashChangeVnd:-(gross+cost),
    currentPct:t.currentPct,targetPct:t.targetPct,driftPP:t.driftPP});
  }
  if(base.trades.length===0){
   base.why=critical.length?'Chênh lệch đã vượt ngưỡng nhưng chưa đủ điều kiện số tiền, lô hoặc tiền mặt.':
    'Phân bổ đang trong biên độ theo dõi. Chưa cần cân bằng lại.';
  }
  const balance=book.sectorAllocations||[];
  const excessive=balance.filter(s=>N(s.weight)>=cfg.sectorCapPct);
  if(excessive.length)base.flags.push('Nhóm ngành vượt mức theo dõi: '+excessive.map(s=>s.name).join(', '));
  if(rows.some(r=>!r.sectorId))base.flags.push('Một số mã chưa được xác định ngành.');
  if(!Number.isFinite(base.estimatedCostVnd)||base.trades.some(t=>!Number.isSafeInteger(t.quantity)||t.quantity<0)){
   base.blocked=true;base.trades=[];base.why='Không thể lượng hóa chi phí hợp lệ.';
  }
  return base;
 }
 return {PRESETS,normalize,venueDate,review};
});
