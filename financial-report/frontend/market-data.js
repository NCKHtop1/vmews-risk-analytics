(function(){'use strict';
const source='https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/';
const pages=document.documentElement.dataset.hosting==='pages'?new URL('market/',location.href).href:null;
const stamp=v=>{const t=Date.parse(v||'');return Number.isFinite(t)&&t<=Date.now()+300000?t:null;};
function valid(data){return data&&typeof data==='object'&&['checkedAt','sourceTime','latestSourceTime','collectedAt','generatedAt'].every(k=>!data[k]||stamp(data[k])!==null);}
function revision(data){return Math.max(0,...['checkedAt','collectedAt','generatedAt','sourceTime','latestSourceTime'].map(k=>stamp(data[k])||0));}
async function read(base,file,signal,timeout){const r=await fetch(base+file+'?refresh='+Date.now().toString(36),{cache:'no-store',signal:signal?AbortSignal.any([signal,AbortSignal.timeout(timeout)]):AbortSignal.timeout(timeout)});if(!r.ok)throw Error('HTTP '+r.status);const data=await r.json();if(!valid(data))throw Error('Invalid snapshot timestamp');return data;}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function get(file,{signal,timeout=12000,hedgeMs=250}={}){
 // Raw publisher is the primary source. Pages is a true hedge: it starts only
 // when the primary is slow or fails, preventing duplicate multi-megabyte
 // downloads on every refresh while preserving fast failover.
 const bases=[...new Set([source,pages].filter(Boolean))];
 if(!bases.length)throw Error('No market snapshot source');
 const primaryCtl=new AbortController(),mirrorCtl=new AbortController();
 const combined=ctl=>signal?AbortSignal.any([signal,ctl.signal]):ctl.signal;
 let mirrorPromise=null,timer=null;
 const startMirror=()=>{
  if(mirrorPromise)return mirrorPromise;
  if(bases.length<2){mirrorPromise=Promise.reject(Error('No mirror snapshot source'));mirrorPromise.catch(()=>{});return mirrorPromise;}
  mirrorPromise=read(bases[1],file,combined(mirrorCtl),timeout);
  return mirrorPromise;
 };
 const primary=read(bases[0],file,combined(primaryCtl),timeout);
 const mirrorGate=new Promise((resolve,reject)=>{
  const launch=()=>startMirror().then(resolve,reject);
  timer=setTimeout(launch,Math.max(0,Number(hedgeMs)||0));
  primary.catch(()=>{if(timer){clearTimeout(timer);timer=null;}launch();});
 });
 try{
  const result=await Promise.any([primary,mirrorGate]);
  if(signal?.aborted)throw new DOMException('Aborted','AbortError');
  return result;
 }catch(error){
  if(signal?.aborted)throw new DOMException('Aborted','AbortError');
  throw Error('No valid market snapshot');
 }finally{
  if(timer)clearTimeout(timer);
  primaryCtl.abort();mirrorCtl.abort();
 }
}
function mergeQuotes(target,rows){for(const [symbol,q]of Object.entries(rows||{})){const t=stamp(q?.sourceTime),old=target[symbol],prior=stamp(old?.sourceTime);if(t!==null&&Number(q.price)>0&&(prior===null||!old||t>=prior))target[symbol]=q;}return target;}
const CORE_BUNDLE_FILES={quotes:'quotes.json',scanner:'technical-signals.json',strategy:'strategy-indicators.json',watch:'watch-today.json',risk:'risk-monitor.json'};
let committedBundle=null;
function bundleSource(data,key){return key==='quotes'?(data?.latestSourceTime||data?.sourceTime||null):(data?.sourceTime||null);}
async function getAlignedBundle(options={}){
 const rows=await Promise.all(Object.entries(CORE_BUNDLE_FILES).map(async([key,file])=>[key,await get(file,options)]));
 const bundle=Object.fromEntries(rows),sourceTime=bundleSource(bundle.quotes,'quotes');
 if(!sourceTime)throw Error('Market bundle sourceTime missing');
 const mismatched=Object.entries(bundle).filter(([key,data])=>String(bundleSource(data,key)||'')!==String(sourceTime)).map(([key])=>key);
 if(mismatched.length){const error=Error('Market bundle not aligned: '+mismatched.join(','));error.code='FINQUERY_BUNDLE_MISMATCH';error.sourceTime=sourceTime;error.mismatched=mismatched;throw error;}
 return{...bundle,sourceTime};
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
