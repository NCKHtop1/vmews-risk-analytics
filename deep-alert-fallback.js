(()=>{
'use strict';
const priorFetch=window.fetch.bind(window);
const BASE='https://cdn.githubraw.com/NCKHtop1/vmews-risk-analytics/main/data/deep-alerts';
function requestInfo(input){
  try{
    const raw=typeof input==='string'?input:(input&&input.url?input.url:String(input));
    const u=new URL(raw,location.href);
    return {u,symbol:String(u.searchParams.get('symbol')||'').toUpperCase().replace(/[^A-Z0-9]/g,'').slice(0,8)};
  }catch{return {u:null,symbol:''}}
}
async function staticDetail(symbol,init){
  if(!symbol)return null;
  try{
    const r=await priorFetch(`${BASE}/${encodeURIComponent(symbol)}.json?t=${Date.now()}`,{...init,cache:'no-store'});
    if(!r.ok)return null;
    const p=await r.json();
    p.warnings=[...(p.warnings||[]),'Primary API detail unavailable; CDN deep-alert cache supplied the price history.'];
    p.cdnFallback=true;
    return new Response(JSON.stringify(p),{status:200,headers:{'Content-Type':'application/json; charset=utf-8','X-VMEWS-Fallback':'deep-alert-cache'}});
  }catch{return null}
}
window.fetch=async(input,init)=>{
  const {u,symbol}=requestInfo(input);
  const isDetail=u&&u.pathname==='/api/stocks2'&&u.searchParams.get('mode')==='detail';
  if(!isDetail)return priorFetch(input,init);
  try{
    const r=await priorFetch(input,init);
    if(r.ok)return r;
    const fb=await staticDetail(symbol,init);
    return fb||r;
  }catch(e){
    const fb=await staticDetail(symbol,init);
    if(fb)return fb;
    throw e;
  }
};
window.__VMEWS_DEEP_ALERT_FALLBACK__=true;
})();
