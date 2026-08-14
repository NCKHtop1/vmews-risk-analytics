(()=>{'use strict';
const VERSION='VMEWS-FORECAST-RESOLVER-11.0.4';
const MIN_FORECAST_ROWS=520;
const MAX_STALE_DAYS=7;
const MAIN='https://cdn.githubraw.com/NCKHtop1/vmews-risk-analytics/main';
const PARAMS=new URLSearchParams(location.search);
const FORCE_CDN=PARAMS.get('resolver')==='cdn';
const nativeFetch=window.fetch.bind(window);
const detailCache=new Map();

function cleanSymbol(v){return String(v||'').toUpperCase().replace(/[^A-Z0-9]/g,'').slice(0,8)}
const QUERY_SYMBOL=cleanSymbol(PARAMS.get('symbol'));
if(QUERY_SYMBOL){
  const input=document.querySelector('#symbol');
  if(input){input.value=QUERY_SYMBOL;input.setAttribute('value',QUERY_SYMBOL)}
}
function ageDays(date){
  const t=Date.parse(`${date}T23:59:59+07:00`);
  return Number.isFinite(t)?Math.max(0,(Date.now()-t)/86400000):Infinity;
}
function validDetail(d,s,requireFresh=true){
  const h=d?.history;
  if(!Array.isArray(h)||h.length<MIN_FORECAST_ROWS)return false;
  if(s&&cleanSymbol(d?.symbol)!==s)return false;
  let prev='';
  for(const row of h){
    if(!row?.date||row.date<=prev||!Number.isFinite(Number(row.close))||Number(row.close)<=0)return false;
    prev=row.date;
  }
  if(requireFresh&&ageDays(h[h.length-1].date)>MAX_STALE_DAYS)return false;
  return true;
}
function cloneResponse(d,source,status=200){
  const body=JSON.stringify({...d,resolverClient:{version:VERSION,source,minForecastRows:MIN_FORECAST_ROWS,maxStaleDays:MAX_STALE_DAYS,forcedCdn:FORCE_CDN}});
  return new Response(body,{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-VMEWS-Resolver':source}});
}
function parseDetail(input){
  try{
    const raw=typeof input==='string'?input:input?.url;
    if(!raw)return null;
    const u=new URL(raw,location.href);
    if(!/vmews-risk-analytics-sojd\.vercel\.app$/i.test(u.hostname))return null;
    if(!/^\/api\/(radar|stocks)$/.test(u.pathname))return null;
    if(u.searchParams.get('mode')!=='detail')return null;
    return cleanSymbol(u.searchParams.get('symbol'))||null;
  }catch{return null}
}
async function fetchMirror(url,symbol,source){
  const r=await nativeFetch(url,{cache:'no-store',credentials:'omit'});
  if(!r.ok)throw new Error(`${source} HTTP ${r.status}`);
  const d=await r.json();
  if(!validDetail(d,symbol,true))throw new Error(`${symbol}: ${source} is stale or not forecast-eligible`);
  detailCache.set(symbol,d);
  return {data:d,source};
}
async function fromMirror(symbol){
  if(detailCache.has(symbol))return {data:detailCache.get(symbol),source:'MEMORY_CACHE'};
  const live=`${MAIN}/data/hose-fallbacks/${encodeURIComponent(symbol)}.json?t=${Date.now()}`;
  try{return await fetchMirror(live,symbol,'DAILY_CDN_MIRROR')}catch{}
  const pinned=new URL(`./data/hose-fallbacks/${encodeURIComponent(symbol)}.json`,location.href).href;
  return fetchMirror(pinned,symbol,'PINNED_CDN_MIRROR');
}

window.fetch=async function(input,init){
  const symbol=parseDetail(input);
  if(!symbol)return nativeFetch(input,init);
  let primary=null;
  if(!FORCE_CDN){
    try{
      primary=await nativeFetch(input,{...(init||{}),cache:'no-store'});
      if(primary.ok){
        try{
          const d=await primary.clone().json();
          if(validDetail(d,symbol,true)){
            detailCache.set(symbol,d);
            return primary;
          }
        }catch{}
      }
    }catch{}
  }
  try{
    const m=await fromMirror(symbol);
    return cloneResponse(m.data,FORCE_CDN?`FORCED_${m.source}`:m.source);
  }catch(e){
    if(primary)return primary;
    return cloneResponse({error:'VMEWS_FORECAST_DATA_UNAVAILABLE',message:`${symbol}: không có nguồn EOD tươi và đạt chuẩn ${MIN_FORECAST_ROWS} phiên.`,retryable:true,resolverError:String(e?.message||e)},'UNRESOLVED',503);
  }
};

function hideIfUnavailable(selector,bad){
  const e=document.querySelector(selector);if(!e)return;
  const text=(e.textContent||'').trim().toUpperCase();
  e.style.display=bad.some(x=>text.includes(x))?'none':'';
}
function enforceHonestUI(){
  hideIfUnavailable('#market',['CHƯA CÓ','CHƯA ĐỦ','UNAVAILABLE']);
  hideIfUnavailable('#macro',['CHƯA CÓ','CHƯA ĐỦ','UNAVAILABLE']);
  hideIfUnavailable('#fund',['CHƯA CÓ','CHƯA ĐỦ','UNAVAILABLE']);
  hideIfUnavailable('#newsCard',['MẪU MỎNG','CHƯA ĐỦ','THIN','UNAVAILABLE']);
  const news=document.querySelector('#news'),summary=document.querySelector('#eventSummary');
  const panel=news?.closest('.panel');
  if(panel){
    const nt=(news?.textContent||'').toLowerCase();
    const st=(summary?.textContent||'').toLowerCase();
    const noNews=nt.includes('không đủ tin')||nt.trim()==='—';
    const noStudy=st.includes('chưa đủ mẫu')||st.trim()==='—';
    panel.style.display=(noNews&&noStudy)?'none':'';
  }
}
const observer=new MutationObserver(()=>enforceHonestUI());
addEventListener('DOMContentLoaded',()=>{
  enforceHonestUI();
  observer.observe(document.body,{childList:true,subtree:true,characterData:true});
});
window.VMEWSForecastResolver={version:VERSION,minForecastRows:MIN_FORECAST_ROWS,maxStaleDays:MAX_STALE_DAYS,forceCdn:FORCE_CDN,querySymbol:QUERY_SYMBOL,cache:detailCache};
})();
