(function(){'use strict';
const source='https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/';
const pages=document.documentElement.dataset.hosting==='pages'?new URL('market/',location.href).href:null;
const stamp=v=>{const t=Date.parse(v||'');return Number.isFinite(t)&&t<=Date.now()+300000?t:null;};
function valid(data){return data&&typeof data==='object'&&['checkedAt','sourceTime','latestSourceTime','collectedAt','generatedAt'].every(k=>!data[k]||stamp(data[k])!==null);}
function revision(data){return Math.max(0,...['checkedAt','collectedAt','generatedAt','sourceTime','latestSourceTime'].map(k=>stamp(data[k])||0));}
async function read(base,file,signal,timeout){const r=await fetch(base+file+'?refresh='+Date.now().toString(36),{cache:'no-store',signal:signal?AbortSignal.any([signal,AbortSignal.timeout(timeout)]):AbortSignal.timeout(timeout)});if(!r.ok)throw Error('HTTP '+r.status);const data=await r.json();if(!valid(data))throw Error('Invalid snapshot timestamp');return data;}
async function get(file,{signal,timeout=12000}={}){
 // Read the publisher directly; a successful HTTP response from Pages may still
 // contain an old deployment. Compare both copies, including future-time guards.
 const results=await Promise.allSettled([...new Set([source,pages].filter(Boolean))].map(base=>read(base,file,signal,timeout)));
 if(signal?.aborted)throw new DOMException('Aborted','AbortError');
 const rows=results.filter(x=>x.status==='fulfilled').map(x=>x.value).sort((a,b)=>revision(b)-revision(a));
 if(!rows.length)throw Error('No valid market snapshot');return rows[0];
}
function mergeQuotes(target,rows){for(const [symbol,q]of Object.entries(rows||{})){const t=stamp(q?.sourceTime),old=target[symbol],prior=stamp(old?.sourceTime);if(t!==null&&Number(q.price)>0&&(prior===null||!old||t>=prior))target[symbol]=q;}return target;}
window.FinMarketData={get,stamp,valid,revision,mergeQuotes};
})();
