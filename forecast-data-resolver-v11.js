(()=>{'use strict';
const VERSION='VMEWS-FORECAST-RESOLVER-11.0.0';
const MIN_FORECAST_ROWS=520;
const nativeFetch=window.fetch.bind(window);
const detailCache=new Map();

function cleanSymbol(v){return String(v||'').toUpperCase().replace(/[^A-Z0-9]/g,'').slice(0,8)}
function validDetail(d,s){
  const h=d?.history;
  if(!Array.isArray(h)||h.length<MIN_FORECAST_ROWS)return false;
  if(s&&cleanSymbol(d?.symbol)!==s)return false;
  const last=h[h.length-1];
  return Boolean(last?.date&&Number.isFinite(Number(last?.close))&&Number(last.close)>0);
}
function cloneResponse(d,source,status=200){
  const body=JSON.stringify({...d,resolverClient:{version:VERSION,source,minForecastRows:MIN_FORECAST_ROWS}});
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
    const symbol=cleanSymbol(u.searchParams.get('symbol'));
    return symbol||null;
  }catch{return null}
}
async function fromMirror(symbol){
  if(detailCache.has(symbol))return detailCache.get(symbol);
  const u=new URL(`./data/hose-fallbacks/${encodeURIComponent(symbol)}.json`,location.href);
  const r=await nativeFetch(u.href,{cache:'no-store',credentials:'omit'});
  if(!r.ok)throw new Error(`CDN mirror HTTP ${r.status}`);
  const d=await r.json();
  if(!validDetail(d,symbol))throw new Error(`${symbol}: CDN mirror is not forecast-eligible`);
  detailCache.set(symbol,d);
  return d;
}

window.fetch=async function(input,init){
  const symbol=parseDetail(input);
  if(!symbol)return nativeFetch(input,init);
  let primary=null;
  try{
    primary=await nativeFetch(input,{...(init||{}),cache:'no-store'});
    if(primary.ok){
      try{
        const d=await primary.clone().json();
        if(validDetail(d,symbol)){
          detailCache.set(symbol,d);
          return primary;
        }
      }catch{}
    }
  }catch{}
  try{
    const d=await fromMirror(symbol);
    return cloneResponse(d,'IMMUTABLE_CDN_MIRROR');
  }catch(e){
    if(primary)return primary;
    return cloneResponse({error:'VMEWS_FORECAST_DATA_UNAVAILABLE',message:`${symbol}: không có nguồn EOD đạt chuẩn ${MIN_FORECAST_ROWS} phiên.`,retryable:true,resolverError:String(e?.message||e)},'UNRESOLVED',503);
  }
};

function hideIfUnavailable(selector,bad){
  const e=document.querySelector(selector);if(!e)return;
  const label=(e.querySelector('b')?.textContent||e.textContent||'').trim().toUpperCase();
  e.style.display=bad.some(x=>label.includes(x))?'none':'';
}
function enforceHonestUI(){
  hideIfUnavailable('#macro',['CHƯA CÓ','CHƯA ĐỦ','UNAVAILABLE']);
  hideIfUnavailable('#fund',['CHƯA CÓ','CHƯA ĐỦ','UNAVAILABLE']);
  hideIfUnavailable('#newsCard',['MẪU MỎNG','CHƯA ĐỦ','THIN','UNAVAILABLE']);
  const news=document.querySelector('#news'), summary=document.querySelector('#eventSummary');
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
window.VMEWSForecastResolver={version:VERSION,minForecastRows:MIN_FORECAST_ROWS,cache:detailCache};
})();
