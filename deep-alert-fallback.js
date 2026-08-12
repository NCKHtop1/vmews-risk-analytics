(()=>{
'use strict';
const priorFetch=window.fetch.bind(window);
const ALERT_BASE='https://cdn.githubraw.com/NCKHtop1/vmews-risk-analytics/main/data/deep-alerts';
const HOSE_BASE='https://cdn.githubraw.com/NCKHtop1/vmews-risk-analytics/main/data/hose-fallbacks';
function requestInfo(input){try{const raw=typeof input==='string'?input:(input&&input.url?input.url:String(input)),u=new URL(raw,location.href);return{u,symbol:String(u.searchParams.get('symbol')||'').toUpperCase().replace(/[^A-Z0-9]/g,'').slice(0,8)}}catch{return{u:null,symbol:''}}}
async function staticFrom(base,symbol,init,label){if(!symbol)return null;try{const r=await priorFetch(`${base}/${encodeURIComponent(symbol)}.json?t=${Date.now()}`,{...init,cache:'no-store'});if(!r.ok)return null;const p=await r.json();p.warnings=[...(p.warnings||[]),`Primary API detail unavailable; ${label} supplied the price history.`];p.cdnFallback=true;p.cdnFallbackLayer=label;return new Response(JSON.stringify(p),{status:200,headers:{'Content-Type':'application/json; charset=utf-8','X-VMEWS-Fallback':label}})}catch{return null}}
async function staticDetail(symbol,init){return await staticFrom(ALERT_BASE,symbol,init,'deep-alert-cache')||await staticFrom(HOSE_BASE,symbol,init,'hose-universal-cache')}
async function captureDetail(response){try{const p=await response.clone().json();if(p?.mode==='detail'&&p?.symbol){window.__VMEWS_LAST_DETAIL__=p;if(window.VMEWSInvestorChart?.render)window.VMEWSInvestorChart.render(p)}}catch{}}
window.fetch=async(input,init)=>{const {u,symbol}=requestInfo(input),isDetail=u&&u.pathname==='/api/stocks2'&&u.searchParams.get('mode')==='detail';if(!isDetail)return priorFetch(input,init);let result=null;try{const r=await priorFetch(input,init);if(r.ok)result=r;else result=await staticDetail(symbol,init)||r}catch(e){result=await staticDetail(symbol,init);if(!result)throw e}if(result?.ok)captureDetail(result);return result};
window.__VMEWS_DEEP_ALERT_FALLBACK__=true;
if(!window.__VMEWS_INVESTOR_CHART_V2_LOADER__){window.__VMEWS_INVESTOR_CHART_V2_LOADER__=true;const s=document.createElement('script');s.src=new URL('./investor-chart-v2.js',location.href).href;s.async=false;s.onload=()=>{if(window.__VMEWS_LAST_DETAIL__&&window.VMEWSInvestorChart?.render)window.VMEWSInvestorChart.render(window.__VMEWS_LAST_DETAIL__)};document.head.appendChild(s)}
})();
