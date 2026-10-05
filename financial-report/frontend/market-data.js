(function(){'use strict';
const source='https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/';
const pages=document.documentElement.dataset.hosting==='pages'?new URL('market/',location.href).href:null;
const stamp=v=>{const t=Date.parse(v||'');return Number.isFinite(t)&&t<=Date.now()+300000?t:null;};
function valid(data){return data&&typeof data==='object'&&['checkedAt','sourceTime','latestSourceTime','collectedAt','generatedAt'].every(k=>!data[k]||stamp(data[k])!==null);}
function revision(data){return Math.max(0,...['checkedAt','collectedAt','generatedAt','sourceTime','latestSourceTime'].map(k=>stamp(data[k])||0));}
async function read(base,file,signal,timeout){const r=await fetch(base+file+'?refresh='+Date.now().toString(36),{cache:'no-store',signal:signal?AbortSignal.any([signal,AbortSignal.timeout(timeout)]):AbortSignal.timeout(timeout)});if(!r.ok)throw Error('HTTP '+r.status);const data=await r.json();if(!valid(data))throw Error('Invalid snapshot timestamp');return data;}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function get(file,{signal,timeout=12000,hedgeMs=250}={}){
 // Raw publisher is normally the freshest copy, while Pages is a same-origin
 // safety mirror. Start both together, return the first valid copy quickly, and
 // keep only a short grace window to compare revisions. A hung mirror must never
 // hold an otherwise valid market snapshot until the full network timeout.
 const tasks=[...new Set([source,pages].filter(Boolean))].map(base=>read(base,file,signal,timeout));
 if(!tasks.length)throw Error('No market snapshot source');
 let first;
 try{first=await Promise.any(tasks);}catch{throw Error('No valid market snapshot');}
 if(signal?.aborted)throw new DOMException('Aborted','AbortError');
 const settled=await Promise.race([Promise.allSettled(tasks),delay(Math.max(0,Number(hedgeMs)||0)).then(()=>null)]);
 if(Array.isArray(settled)){
  const rows=settled.filter(x=>x.status==='fulfilled').map(x=>x.value).sort((a,b)=>revision(b)-revision(a));
  if(rows.length)return rows[0];
 }
 return first;
}
function mergeQuotes(target,rows){for(const [symbol,q]of Object.entries(rows||{})){const t=stamp(q?.sourceTime),old=target[symbol],prior=stamp(old?.sourceTime);if(t!==null&&Number(q.price)>0&&(prior===null||!old||t>=prior))target[symbol]=q;}return target;}
window.FinMarketData={get,stamp,valid,revision,mergeQuotes};
})();
