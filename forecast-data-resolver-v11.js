(()=>{'use strict';
const VERSION='VMEWS-FORECAST-RESOLVER-11.2.0';
const MIN_FORECAST_ROWS=520;
const MAX_STALE_DAYS=7;
const RESEARCH_SNAPSHOT_SHA='71f12c862d759a1167ebf72cebd38c4eae0e19d1';
const CDN_ROOT='https://cdn.githubraw.com/NCKHtop1/vmews-risk-analytics';
const RESEARCH_URLS={
  sentiment:`${CDN_ROOT}/${RESEARCH_SNAPSHOT_SHA}/data/sentiment-v10.json`,
  event:`${CDN_ROOT}/${RESEARCH_SNAPSHOT_SHA}/data/news-event-study.json`
};
const PARAMS=new URLSearchParams(location.search);
const MODE=(PARAMS.get('resolver')||'cdn').toLowerCase();
const nativeFetch=window.fetch.bind(window);
const detailCache=new Map();
const marketCache={data:null};
const researchCache=new Map();

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
function validDetail(d,s,requireFresh=false){
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
  const body=JSON.stringify({...d,resolverClient:{version:VERSION,source,minForecastRows:MIN_FORECAST_ROWS,maxStaleDays:MAX_STALE_DAYS,mode:MODE,policy:'PINNED_CDN_FIRST',researchSnapshotSha:RESEARCH_SNAPSHOT_SHA}});
  return new Response(body,{status,headers:{'Content-Type':'application/json; charset=utf-8','X-VMEWS-Resolver':source}});
}
function inputUrl(input){try{return typeof input==='string'?input:String(input?.url||'')}catch{return''}}
function parseDetail(input){
  try{
    const raw=inputUrl(input);if(!raw)return null;
    const u=new URL(raw,location.href);
    if(!/^\/api\/(radar|stocks)$/.test(u.pathname))return null;
    if(u.searchParams.get('mode')!=='detail')return null;
    return cleanSymbol(u.searchParams.get('symbol'))||null;
  }catch{return null}
}
function matchesDataFile(input,name){
  try{return new RegExp(`/data/${name.replace('.','\\.')}(?:[?#]|$)`,'i').test(new URL(inputUrl(input),location.href).href)}catch{return false}
}
function isMarketScan(input){return matchesDataFile(input,'market-scan.json')}
function researchKind(input){
  if(matchesDataFile(input,'sentiment-v10.json'))return 'sentiment';
  if(matchesDataFile(input,'news-event-study.json'))return 'event';
  return null;
}
async function fetchJson(url,cacheMode='force-cache'){
  const r=await nativeFetch(url,{cache:cacheMode,credentials:'omit'});
  if(!r.ok)throw new Error(`CDN HTTP ${r.status}`);
  return r.json();
}
async function pinnedDetail(symbol){
  if(detailCache.has(symbol))return detailCache.get(symbol);
  const url=new URL(`./data/hose-fallbacks/${encodeURIComponent(symbol)}.json`,location.href).href;
  const d=await fetchJson(url,'force-cache');
  if(!validDetail(d,symbol,false))throw new Error(`${symbol}: pinned mirror is not forecast-eligible`);
  detailCache.set(symbol,d);return d;
}
async function pinnedMarketScan(){
  if(marketCache.data)return marketCache.data;
  const d=await fetchJson(new URL('./data/market-scan.json',location.href).href,'force-cache');
  if(!Array.isArray(d?.ranking))throw new Error('Pinned market scan invalid');
  marketCache.data=d;return d;
}
function validResearch(kind,d){
  if(kind==='sentiment')return /^VMEWS-SENTIMENT-/.test(String(d?.version||''))&&d?.symbols&&Object.keys(d.symbols).length>0;
  if(kind==='event')return /^VMEWS-NEWS-EVENT-STUDY-/.test(String(d?.version||''))&&Number(d?.events)>0&&d?.symbols&&Object.keys(d.symbols).length>0&&d?.rumorStudy;
  return false;
}
async function pinnedResearch(kind){
  if(researchCache.has(kind))return researchCache.get(kind);
  const d=await fetchJson(RESEARCH_URLS[kind],'force-cache');
  if(!validResearch(kind,d))throw new Error(`Pinned ${kind} research snapshot invalid`);
  researchCache.set(kind,d);return d;
}
async function liveApi(input,init,symbol){
  const r=await nativeFetch(input,{...(init||{}),cache:'no-store'});
  if(!r.ok)return r;
  try{
    const d=await r.clone().json();
    if(validDetail(d,symbol,true)){detailCache.set(symbol,d);return r}
  }catch{}
  throw new Error(`${symbol}: live API did not return a fresh eligible history`);
}

window.fetch=async function(input,init){
  const rk=researchKind(input);
  if(rk){
    try{return cloneResponse(await pinnedResearch(rk),rk==='event'?'PINNED_EVENT_INTELLIGENCE':'PINNED_FINANCIAL_SENTIMENT')}
    catch(e){
      return cloneResponse({symbols:{},error:'VMEWS_PINNED_RESEARCH_UNAVAILABLE',message:String(e?.message||e)},'UNRESOLVED_RESEARCH',503);
    }
  }
  if(isMarketScan(input)){
    try{return cloneResponse(await pinnedMarketScan(),'PINNED_MARKET_SCAN')}catch(e){
      if(MODE==='live'||MODE==='api')return nativeFetch(input,init);
      return cloneResponse({ranking:[],error:'VMEWS_PINNED_MARKET_SCAN_UNAVAILABLE',message:String(e?.message||e)},'UNRESOLVED_MARKET_SCAN',503);
    }
  }
  const symbol=parseDetail(input);
  if(!symbol)return nativeFetch(input,init);

  // Production default: same-commit CDN snapshot first. No Vercel/Yahoo wait path.
  if(MODE!=='api'&&MODE!=='live'){
    try{return cloneResponse(await pinnedDetail(symbol),'PINNED_CDN_DETAIL')}catch(e){
      try{return await liveApi(input,init,symbol)}catch{}
      return cloneResponse({error:'VMEWS_FORECAST_DATA_UNAVAILABLE',message:`${symbol}: không có lịch sử EOD đạt chuẩn ${MIN_FORECAST_ROWS} phiên.`,retryable:true,resolverError:String(e?.message||e)},'UNRESOLVED',503);
    }
  }

  // Explicit diagnostic/live mode: live API first, then deterministic pinned fallback.
  try{return await liveApi(input,init,symbol)}catch{}
  try{return cloneResponse(await pinnedDetail(symbol),'PINNED_CDN_FALLBACK')}catch(e){
    return cloneResponse({error:'VMEWS_FORECAST_DATA_UNAVAILABLE',message:`${symbol}: không có nguồn EOD đạt chuẩn ${MIN_FORECAST_ROWS} phiên.`,retryable:true,resolverError:String(e?.message||e)},'UNRESOLVED',503);
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
window.VMEWSForecastResolver={version:VERSION,minForecastRows:MIN_FORECAST_ROWS,maxStaleDays:MAX_STALE_DAYS,mode:MODE,policy:'PINNED_CDN_FIRST',querySymbol:QUERY_SYMBOL,researchSnapshotSha:RESEARCH_SNAPSHOT_SHA,cache:detailCache,researchCache};
})();
