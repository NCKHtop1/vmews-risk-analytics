'use strict';
const fs=require('fs');
const path=require('path');
const assert=require('assert');

const ROOT=path.resolve(__dirname,'..');
const MIN=520;
const MAX_STALE_DAYS=7;
const REQUIRED=['FPT','FRT','PNJ','VCB','HPG','MBB'];
const read=p=>JSON.parse(fs.readFileSync(path.join(ROOT,p),'utf8'));
const html=fs.readFileSync(path.join(ROOT,'forecast-final.html'),'utf8');
const resolver=fs.readFileSync(path.join(ROOT,'forecast-data-resolver-v11.js'),'utf8');

assert(html.includes('./forecast-data-resolver-v11.js'),'forecast resolver missing from production page');
assert(html.indexOf('./forecast-data-resolver-v11.js')<html.indexOf('./forecast-final-v10.js'),'resolver must load before forecast runtime');
assert(resolver.includes('MIN_FORECAST_ROWS=520'),'resolver minimum history contract drift');
assert(resolver.includes('MAX_STALE_DAYS=7'),'resolver freshness contract drift');
assert(resolver.includes("get('resolver')==='cdn'"),'forced CDN test mode missing');
assert(resolver.includes('DAILY_CDN_MIRROR'),'daily CDN mirror path missing');
assert(resolver.includes('PINNED_CDN_MIRROR'),'pinned audit mirror path missing');

const manifest=read('data/hose-fallbacks/manifest.json');
assert.equal(manifest.version,'VMEWS-HOSE-RESOLVER-1.1.0','resolver manifest is not V1.1');
assert(manifest.hoseReference>=250,`HOSE universe too small: ${manifest.hoseReference}`);
assert(manifest.routeCoverageRatio>=0.999,`route coverage ${manifest.routeCoverageRatio}`);
assert.equal((manifest.unresolved||[]).length,0,'unresolved HOSE symbols remain');
assert.equal(manifest.forecastMinRows,MIN,'forecast minimum row contract drift');
assert(manifest.cacheHistoryRows>=MIN,'mirror history window cannot support forecast');

function staleDays(date){
  const t=Date.parse(`${date}T23:59:59+07:00`);
  return Number.isFinite(t)?Math.max(0,(Date.now()-t)/86400000):Infinity;
}
function validateFile(sym,requireEligible=false){
  const fp=path.join(ROOT,'data','hose-fallbacks',`${sym}.json`);
  assert(fs.existsSync(fp),`${sym}: CDN mirror missing`);
  const d=JSON.parse(fs.readFileSync(fp,'utf8'));
  assert.equal(d.symbol,sym,`${sym}: symbol mismatch`);
  assert.equal(d.mode,'detail',`${sym}: wrong payload mode`);
  const h=d.history||[];
  assert(h.length>0,`${sym}: empty history`);
  let prev='';
  const dates=new Set();
  for(const [i,r] of h.entries()){
    assert(typeof r.date==='string'&&r.date>prev,`${sym}: non-monotonic date at ${i}`);
    assert(!dates.has(r.date),`${sym}: duplicate date ${r.date}`);
    dates.add(r.date); prev=r.date;
    const close=Number(r.close);
    assert(Number.isFinite(close)&&close>0,`${sym}: invalid close ${r.date}`);
    if(r.open!=null)assert(Number.isFinite(Number(r.open))&&Number(r.open)>0,`${sym}: invalid open ${r.date}`);
    if(r.high!=null)assert(Number.isFinite(Number(r.high))&&Number(r.high)>0,`${sym}: invalid high ${r.date}`);
    if(r.low!=null)assert(Number.isFinite(Number(r.low))&&Number(r.low)>0,`${sym}: invalid low ${r.date}`);
    if(r.volume!=null)assert(Number.isFinite(Number(r.volume))&&Number(r.volume)>=0,`${sym}: invalid volume ${r.date}`);
  }
  assert.equal(d.modelAsOf,h[h.length-1].date,`${sym}: modelAsOf not last completed EOD`);
  const dq=d.dataQuality||{};
  if(requireEligible||dq.forecastEligible===true){
    assert(h.length>=MIN,`${sym}: forecast eligible but mirror has only ${h.length}`);
    assert(dq.totalSourceRows>=MIN,`${sym}: source history below ${MIN}`);
    assert(staleDays(h[h.length-1].date)<=MAX_STALE_DAYS,`${sym}: stale forecast mirror ${h[h.length-1].date}`);
  }
  // Guard against fake padding: no repeated dates and no repeated final bar injected to hit MIN.
  if(h.length>=MIN){
    const tail=h.slice(-10).map(r=>`${r.date}|${r.close}|${r.volume??''}`);
    assert(new Set(tail).size===tail.length,`${sym}: suspicious repeated tail bars`);
  }
  return {rows:h.length,eligible:dq.forecastEligible===true,sourceRows:dq.totalSourceRows||h.length,route:d.resolver?.route||'',modelAsOf:d.modelAsOf};
}

const required={};
for(const sym of REQUIRED){
  assert(manifest.routes?.[sym],`${sym}: route absent from manifest`);
  const route=manifest.routes[sym];
  const expect=Boolean(route.forecastEligible);
  required[sym]=validateFile(sym,expect);
  if((route.rows||0)>=MIN){
    assert(required[sym].eligible,`${sym}: >=${MIN} source rows but forecastEligible=false`);
    assert(required[sym].rows>=MIN,`${sym}: CDN mirror truncated below ${MIN}`);
  }
}

let checked=0,eligible=0;
for(const [sym,route] of Object.entries(manifest.routes||{})){
  const z=validateFile(sym,Boolean(route.forecastEligible));
  checked++;
  if(z.eligible)eligible++;
}
assert.equal(checked,manifest.resolved,'manifest/file count mismatch');
assert.equal(eligible,manifest.forecastEligibleCount,'forecast-eligible count mismatch');

console.log(JSON.stringify({status:'PASS',manifestVersion:manifest.version,hose:manifest.hoseReference,checked,eligible,required},null,2));
