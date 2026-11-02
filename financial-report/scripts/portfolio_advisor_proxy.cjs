'use strict';
/* Advisory shadow backtest. No historical universe reconstruction available:
 * point-in-time features, but present-day constituent membership / sector mapping.
 * These statistics MUST NOT certify alpha or expected future returns.
 */
const Core=require('./portfolio_advisor_core.cjs');
const VERSION='FINQUERY-PORTFOLIO-PROXY-1.0';
function calc(stocks,asOf,{windows=8,holdingSessions=20,minimumTurnoverVnd=3000000000}={}){
 const anchor=stocks.slice().sort((a,b)=>(b.bars?.length||0)-(a.bars?.length||0))[0];
 const days=(anchor?.bars||[]).map(b=>b.time).filter(d=>typeof d==='string'&&d<=asOf);
 if(days.length<260)return{version:VERSION,status:'INSUFFICIENT_HISTORY',windows:0};
 const index=new Map(stocks.map(x=>[x.symbol,new Map((x.bars||[]).map(b=>[b.time,b.close]))]));
 const rows=[];
 for(let w=windows;w>=1;w--){
  const fromIndex=days.length-1-w*holdingSessions;
  const toIndex=fromIndex+holdingSessions;
  if(fromIndex<210||toIndex>=days.length)continue;
  const from=days[fromIndex],to=days[toIndex];
  const {eligible}=Core.candidatesAt(stocks,from,{minimumTurnoverVnd});
  const model=Core.modelFor('balanced',eligible);
  if(model.status!=='RESEARCH_ONLY')continue;
  let gross=0,exposure=0,observed=0;
  for(const pos of model.positions){
   const map=index.get(pos.symbol);
   const before=map?.get(from),after=map?.get(to);
   if(!(before>0&&after>0)){observed=-1;break;}
   gross+=pos.weightPct/100*(after/before-1);
   exposure+=pos.weightPct/100;
   observed++;
  }
  if(observed!==model.positions.length)continue;
  const benchmark=[];
  for(const stock of stocks){
   const map=index.get(stock.symbol);
   const before=map?.get(from),after=map?.get(to);
   if(before>0&&after>0)benchmark.push(after/before-1);
  }
  if(benchmark.length<30)continue;
  const equal=benchmark.reduce((a,b)=>a+b,0)/benchmark.length;
  // Conservative roundtrip approximation: broker+slippage+sale tax ~60bp.
  const costRate=.006;
  const net=gross-costRate*exposure;
  rows.push({from,to,n:model.positions.length,exposure:Math.round(exposure*1000)/1000,
   modelNetPct:Math.round(net*10000)/100,equalUniverseNetPct:Math.round((equal-costRate)*10000)/100,
   transactionCostBps:60});
 }
 if(rows.length<4)return{version:VERSION,status:'INSUFFICIENT_EVALUATION',windows:rows.length};
 const mean=k=>rows.reduce((a,b)=>a+b[k],0)/rows.length;
 return{
  version:VERSION,status:'RESEARCH_PROXY_NOT_VALIDATED',
  windows:rows.length,holdingSessions,periods:rows,
  avgModelNetPct:Math.round(mean('modelNetPct')*100)/100,
  avgEqualUniverseNetPct:Math.round(mean('equalUniverseNetPct')*100)/100,
  notes:[
   'Historical window is forward-only from each signal date, no future bars in screening.',
   'Uses CURRENT listed symbol universe and current sector classification: survivorship bias.',
   'Corporate action / dividend adjustment and liquidity execution not independently certified.',
   'Fixed 60bp roundtrip assumption is illustrative; not a broker execution record.',
   'Evaluation is a research diagnostic, not an independent out-of-sample alpha proof.'
  ]
 };
}
module.exports={VERSION,calc};
