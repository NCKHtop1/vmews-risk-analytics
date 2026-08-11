(()=>{
'use strict';
const SNAP='https://cdn.githubraw.com/NCKHtop1/vmews-risk-analytics/main/data/market-context.json';
const weights={technical:.30,analog:.25,market:.15,macro:.10,sentiment:.10,fundamental:.10};
let snapPromise=null;
const underlying=window.fetch.bind(window);
const loadSnap=()=>snapPromise||(snapPromise=underlying(`${SNAP}?t=${Date.now()}`,{cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null));
const valid=m=>m&&m.available!==false&&Number.isFinite(+m.score)&&m.date;
function aggregate(mods){let total=0,used=0;for(const[k,w]of Object.entries(weights)){const m=mods?.[k];if(m&&m.available!==false&&Number.isFinite(+m.score)){total+=w*(+m.score);used+=w}}return {score:used?total/used:50,confidence:used}}
function classify(x){const dd=+x.current?.dd60||0,weak=(+x.current?.mom20||0)<0||(+x.current?.trend50||0)<0;if(dd<=-.15)return ['ACTIVE_DRAWDOWN','GRAY','DRAWDOWN'];if(x.score>=70&&weak&&x.confidence>=.70)return['PRE_CRASH_RED','RED','HIGH'];if(x.score>=55&&weak&&x.confidence>=.55)return['PRE_CRASH_YELLOW','YELLOW','WATCH'];return['NORMAL','GREEN','CLEAR']}
function reasons(mods){const labels={technical:'Technical',analog:'Historical analog',market:'VNINDEX regime',macro:'Macro/cross-asset',sentiment:'News sentiment',fundamental:'Fundamentals'};return Object.entries(mods||{}).filter(([k,m])=>m&&m.available!==false&&Number.isFinite(+m.score)).map(([k,m])=>[+m.score,labels[k]||k]).sort((a,b)=>b[0]-a[0]).slice(0,4).map(([s,n])=>`${n} ${s.toFixed(0)}/100`)}
function applyItem(x,m){if(!x||!valid(m))return x;x.modules=x.modules||{};x.modules.market={...m,sourceNote:'Independent EOD market snapshot fallback'};const a=aggregate(x.modules);x.score=a.score;x.effectiveScore=a.score;x.confidence=a.confidence;const[p,c,s]=classify(x);x.phase=p;x.color=c;x.state=s;x.reasons=reasons(x.modules);return x}
async function patchPayload(p){const s=await loadSnap(),m=s?.market;if(!valid(m))return p;const generated=new Date(s.generatedAt||0),ageH=(Date.now()-generated.getTime())/36e5;if(!Number.isFinite(ageH)||ageH>168)return p;
  if(p?.market?.available===false||!valid(p?.market))p.market={...m,snapshotGeneratedAt:s.generatedAt,fallbackUsed:true};
  if(p?.mode==='scan'&&Array.isArray(p.ranking)){p.ranking=p.ranking.map(x=>applyItem(x,m)).sort((a,b)=>b.effectiveScore-a.effectiveScore);p.redList=p.ranking.filter(x=>x.color==='RED');p.yellowList=p.ranking.filter(x=>x.color==='YELLOW');p.greenList=p.ranking.filter(x=>x.color==='GREEN');p.activeDrawdown=p.ranking.filter(x=>x.phase==='ACTIVE_DRAWDOWN')}
  if(p?.mode==='detail')applyItem(p,m);
  p.marketContextAudit={fallbackUsed:true,snapshotGeneratedAt:s.generatedAt,ticker:m.ticker,source:m.source,provider:m.provider};return p;
}
window.fetch=async(input,init)=>{const raw=typeof input==='string'?input:(input&&input.url?input.url:String(input));const u=new URL(raw,location.href);const isApi=u.pathname==='/api/stocks2'||u.pathname==='/api/radar';const r=await underlying(input,init);if(!isApi||!r.ok)return r;try{const p=await r.clone().json();const patched=await patchPayload(p);return new Response(JSON.stringify(patched),{status:r.status,statusText:r.statusText,headers:r.headers})}catch{return r}};
window.__VMEWS_MARKET_SNAPSHOT__=SNAP;
})();
