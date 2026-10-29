(function(){'use strict';
const source='https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/';
// Authenticated same-origin mirror is available on Vercel as well as public Pages.
const pages=new URL(/\/financial-report\/frontend\//.test(location.pathname||'')?'../market/':'market/',location.href).href;
const stamp=v=>{const t=Date.parse(v||'');return Number.isFinite(t)&&t<=Date.now()+300000?t:null;};
function valid(data){return data&&typeof data==='object'&&['checkedAt','sourceTime','latestSourceTime','collectedAt','generatedAt'].every(k=>!data[k]||stamp(data[k])!==null);}
function revision(data){return Math.max(0,...['checkedAt','collectedAt','generatedAt','sourceTime','latestSourceTime'].map(k=>stamp(data[k])||0));}
async function read(base,file,signal,timeout){const r=await fetch(base+file+'?refresh='+Date.now().toString(36),{cache:'no-store',signal:signal?AbortSignal.any([signal,AbortSignal.timeout(timeout)]):AbortSignal.timeout(timeout)});if(!r.ok)throw Error('HTTP '+r.status);const data=await r.json();if(!valid(data))throw Error('Invalid snapshot timestamp');return data;}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function get(file,{signal,timeout=12000,hedgeMs=750}={}){
 // Publisher-first: the fastest successful response is not necessarily the freshest.
 const bases=[...new Set([source,pages].filter(Boolean))];
 if(!bases.length)throw Error('No market snapshot source');
 const primaryCtl=new AbortController(),mirrorCtl=new AbortController();
 const combined=ctl=>signal?AbortSignal.any([signal,ctl.signal]):ctl.signal;
 let mirrorPromise=null,hedgeTimer=null,deadlineTimer=null;
 const startMirror=()=>{
  if(mirrorPromise)return mirrorPromise;
  if(bases.length<2)throw Error('No mirror snapshot source');
  mirrorPromise=read(bases[1],file,combined(mirrorCtl),timeout);
  mirrorPromise.catch(()=>{});
  return mirrorPromise;
 };
 const primary=read(bases[0],file,combined(primaryCtl),timeout);
 const primaryBudget=Math.min(Math.max(100,Number(timeout)||12000),3500);
 const deadline=new Promise((_,reject)=>{deadlineTimer=setTimeout(()=>{
  primaryCtl.abort();reject(Error('Primary publisher timed out'));
 },primaryBudget);});
 if(bases.length>1)hedgeTimer=setTimeout(()=>{startMirror();},Math.max(0,Number(hedgeMs)||0));
 try{
  const snapshot=await Promise.race([primary,deadline]);
  if(signal?.aborted)throw new DOMException('Aborted','AbortError');
  return snapshot;
 }catch(error){
  if(signal?.aborted)throw new DOMException('Aborted','AbortError');
  try{
   const mirror=await startMirror();
   if(signal?.aborted)throw new DOMException('Aborted','AbortError');
   return mirror;
  }catch{
   if(signal?.aborted)throw new DOMException('Aborted','AbortError');
   throw Error('No valid market snapshot');
  }
 }finally{
  if(hedgeTimer!==null)clearTimeout(hedgeTimer);
  if(deadlineTimer!==null)clearTimeout(deadlineTimer);
  primaryCtl.abort();mirrorCtl.abort();
 }
}
function mergeQuotes(target,rows){for(const [symbol,q]of Object.entries(rows||{})){const t=stamp(q?.sourceTime),old=target[symbol],prior=stamp(old?.sourceTime);if(t!==null&&Number(q.price)>0&&(prior===null||!old||t>=prior))target[symbol]=q;}return target;}
const CORE_BUNDLE_FILES={quotes:'quotes.json',scanner:'technical-signals.json',strategy:'strategy-indicators.json',watch:'watch-today.json',risk:'risk-monitor.json'};
let committedBundle=null;
function bundleSource(data,key){return key==='quotes'?(data?.latestSourceTime||data?.sourceTime||null):(data?.sourceTime||null);}
async function getAlignedBundle({signal,timeout=12000,retries=2}={}){
 // Never mix files from independent origins or publisher revisions.
 const bases=[...new Set([source,pages].filter(Boolean))];
 const maxRawAttempts=Math.max(1,Math.min(3,Number(retries)||2));
 let lastError=null;
 for(let origin=0;origin<bases.length;origin++){
  const attempts=origin===0?maxRawAttempts:1;
  for(let attempt=0;attempt<attempts;attempt++){
   if(signal?.aborted)throw new DOMException('Aborted','AbortError');
   try{
    const rows=await Promise.all(Object.entries(CORE_BUNDLE_FILES).map(async([key,file])=>[
     key,await read(bases[origin],file,signal,timeout)
    ]));
    const bundle=Object.fromEntries(rows),sourceTime=bundleSource(bundle.quotes,'quotes');
    if(!sourceTime)throw Error('Market bundle sourceTime missing');
    const mismatched=Object.entries(bundle).filter(([key,data])=>
     String(bundleSource(data,key)||'')!==String(sourceTime)).map(([key])=>key);
    if(mismatched.length){
     const error=Error('Market bundle not aligned: '+mismatched.join(','));
     error.code='FINQUERY_BUNDLE_MISMATCH';error.sourceTime=sourceTime;
     error.mismatched=mismatched;throw error;
    }
    return{...bundle,sourceTime};
   }catch(error){
    if(signal?.aborted)throw new DOMException('Aborted','AbortError');
    lastError=error;
    if(origin===0&&attempt+1<attempts)await delay(250);
   }
  }
 }
 // Let the UI retain its last-known-good commit; never invent synchronized data.
 throw lastError||Error('No valid market snapshot');
}
function commitBundle(bundle){
 if(!bundle?.sourceTime)return committedBundle;
 const next=stamp(bundle.sourceTime),prior=stamp(committedBundle?.sourceTime);
 if(next===null)return committedBundle;
 if(prior!==null&&next<prior)return committedBundle;
 committedBundle=bundle;
 document.dispatchEvent(new CustomEvent('finquery:market-bundle',{detail:{sourceTime:bundle.sourceTime}}));
 return committedBundle;
}
function currentBundle(){return committedBundle;}
window.FinMarketData={get,stamp,valid,revision,mergeQuotes,getAlignedBundle,commitBundle,currentBundle};
})();
