(()=>{
'use strict';
const BANKS=new Set(['VCB','BID','CTG','MBB','TCB','VPB','ACB','HDB','STB','TPB','VIB','SHB']);
const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x));
const mean=a=>a.length?a.reduce((s,x)=>s+x,0)/a.length:null;
const ratio=x=>{x=Number(x);if(!Number.isFinite(x))return null;return Math.abs(x)>2?x/100:x};
function sectorScore(detail){
  const m=detail?.fundamentals||detail?.modules?.fundamental?.metrics||{},sym=String(detail?.symbol||'').toUpperCase(),bank=BANKS.has(sym),parts=[],used=[];
  const roe=ratio(m.roe),rev=ratio(m.revenueGrowth),margin=ratio(m.netMargin),pe=Number(m.pe),de=Number(m.debtToEquity);
  if(roe!=null){parts.push(clamp((.12-roe)/.18));used.push('ROE')}
  if(Number.isFinite(pe)&&pe>0){parts.push(clamp((pe-(bank?14:18))/(bank?24:30)));used.push('P/E')}
  if(rev!=null){parts.push(clamp((-rev)/.20));used.push('Revenue growth')}
  if(!bank){
    if(margin!=null){parts.push(clamp((.08-margin)/.15));used.push('Net margin')}
    if(Number.isFinite(de)){const dv=de>10?de/100:de;parts.push(clamp((dv-.7)/2));used.push('Debt/equity')}
  }
  return {score:parts.length?100*mean(parts):50,available:parts.length>0,metrics:m,sector:bank?'Bank':'Non-bank',features:used,note:bank?'Bank context excludes debt/equity and generic net-margin penalties; NPL, CAR and NIM are not used because dated source fields are unavailable.':'Sector-aware current fundamental snapshot.'};
}
function patch(){
  const R=window.VMEWSResearch;if(!R||R.__sectorPatched)return false;const base=R.run.bind(R);
  R.run=async(detail,onProgress)=>{
    const f=sectorScore(detail);detail.modules=detail.modules||{};detail.modules.fundamental=f;detail.fundamentals=f.metrics;
    const out=await base(detail,onProgress);out.fundamental=f;window.__VMEWS_SECTOR_FUNDAMENTAL__=f;return out;
  };
  R.__sectorPatched=true;return true;
}
if(!patch())window.addEventListener('DOMContentLoaded',()=>{let n=0;const t=setInterval(()=>{if(patch()||++n>50)clearInterval(t)},50)});
})();
