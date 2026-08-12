(()=>{
'use strict';

const VERSION='VMEWS-LIVE-UI-6.0.1';
const ROOT='https://cdn.githubraw.com/NCKHtop1/vmews-risk-analytics/main/data';
const MARKET=`${ROOT}/market-scan.json`;
const TRACK=`${ROOT}/live-track/track-record.json`;
const INTEGRITY=`${ROOT}/live-track/integrity.json`;
const nativeFetch=window.fetch.bind(window);
let marketPromise=null;
let livePromise=null;
let lastTrack=null;

const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({
  '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
}[c]));
const pct=(x,d=1)=>Number.isFinite(+x)?`${(+x*100).toFixed(d)}%`:'N/A';
const num=(x,d=3)=>Number.isFinite(+x)?(+x).toFixed(d):'N/A';
function ordinal(x){
  const n=Math.max(0,Math.min(100,Math.round((+x||0)*100)));
  const mod100=n%100;
  const suffix=(mod100>=11&&mod100<=13)?'th':({1:'st',2:'nd',3:'rd'}[n%10]||'th');
  return `${n}${suffix} percentile`;
}
async function json(url){
  const r=await nativeFetch(`${url}?t=${Date.now()}`,{cache:'no-store'});
  if(!r.ok) throw Error(`${r.status} ${url}`);
  return r.json();
}
function market(){
  return marketPromise||(marketPromise=json(MARKET));
}
function live(){
  return livePromise||(livePromise=Promise.all([json(TRACK),json(INTEGRITY)])
    .then(([track,integrity])=>{lastTrack=track;return{track,integrity};})
    .catch(error=>({error:String(error)})));
}

function syntheticWatchlist(m,url){
  const parsed=new URL(url,location.href);
  const symbols=(parsed.searchParams.get('symbols')||'FPT,PNJ,VCB,HPG')
    .split(',').map(x=>x.trim().toUpperCase()).filter(Boolean).slice(0,8);
  const rows=m.monitorUniverse||m.ranking||[];
  const by=Object.fromEntries(rows.map(x=>[String(x.symbol||'').toUpperCase(),x]));
  const ranking=[];
  for(const symbol of symbols){
    const x=by[symbol];
    if(!x) continue;
    ranking.push({
      symbol,
      name:x.name||symbol,
      date:m.modelDate,
      close:x.close,
      ret5:x.ret5,
      score:x.score,
      color:x.status==='RED'?'RED':(x.status==='YELLOW'||x.status==='WATCH'?'YELLOW':'GREEN'),
      status:x.status,
      confidence:1,
      canonicalWatchlist:true,
      modules:{
        technical:{score:x.technicalScore,available:Number.isFinite(+x.technicalScore)},
        analog:{score:null,available:false,reason:'Single-name analog is not used to set Watchlist status.'},
        market:{score:null,available:false,reason:'Market-relative evidence follows the T-Day snapshot and is excluded when unavailable.'}
      },
      reasons:x.drivers||[]
    });
  }
  const mc=m.marketContext||{};
  const marketCard=mc.available?{
    available:true,score:0,technical:0,analog20:{rate:null},date:mc.vnindexModelDate,
    note:'Canonical market context is available in the T-Day snapshot.'
  }:{
    available:false,date:mc.vnindexModelDate,
    reason:'VNINDEX relative evidence is unavailable/excluded in the canonical T-Day snapshot.'
  };
  return{
    version:'VMEWS-WATCHLIST-6.0.0-CANONICAL-EOD',
    asOf:`${m.modelDate}T15:00:00+07:00`,
    modelDate:m.modelDate,
    requestedSymbols:symbols,
    scanned:ranking.length,
    market:marketCard,
    ranking,
    errors:symbols.filter(s=>!by[s]).map(symbol=>({symbol,error:'Outside current liquid/current canonical market-scan monitor universe'})),
    timeBasis:'LATEST_COMPLETED_EOD_ONLY',
    canonicalPolicy:m.policyVersion
  };
}

window.fetch=async(input,init)=>{
  const url=typeof input==='string'?input:(input?.url||'');
  if(url.includes('/api/stocks2')&&/[?&]mode=scan(?:&|$)/.test(url)){
    try{
      const m=await market();
      const body=syntheticWatchlist(m,url);
      return new Response(JSON.stringify(body),{
        status:200,
        headers:{'Content-Type':'application/json','X-VMEWS-Time-Basis':'LATEST_COMPLETED_EOD_ONLY'}
      });
    }catch(e){
      console.warn('VMEWS canonical watchlist fallback failed',e);
    }
  }
  return nativeFetch(input,init);
};

function css(){
  if(document.getElementById('liveV6Style')) return;
  const s=document.createElement('style');
  s.id='liveV6Style';
  s.textContent=`
    .liveGrid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:12px 0}
    .liveCard{border:1px solid var(--line);border-radius:8px;padding:11px;background:#09151f}
    .liveCard span,.liveCard small,.liveMetric span{display:block;color:var(--muted);font-size:11px}
    .liveCard b{display:block;font-size:18px;margin:4px 0}
    .liveCols{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
    .liveMetric{border:1px solid var(--line);border-radius:8px;padding:12px}
    .liveMetric h3{margin:3px 0 9px}
    .liveRows{display:grid;gap:5px}
    .liveRows div{display:flex;justify-content:space-between;gap:10px;border-top:1px solid var(--line);padding-top:5px}
    .livePass{color:var(--green)}.liveWait{color:var(--amber)}.liveWarn{color:var(--red)}
    @media(max-width:1000px){.liveGrid{grid-template-columns:1fr 1fr}.liveCols{grid-template-columns:1fr}}
    @media(max-width:600px){.liveGrid{grid-template-columns:1fr}}
  `;
  document.head.appendChild(s);
}

function ensureSection(){
  css();
  let section=document.getElementById('live');
  if(section) return section;
  const validation=document.getElementById('validation');
  const governance=document.getElementById('governance');
  section=document.createElement('section');
  section.id='live';
  section.className='section panel';
  section.innerHTML=`
    <div class="sectionHead"><div><div class="eyebrow">OUTCOMES ANALYSIS · POINT-IN-TIME CONTROL</div><h2>Live Model Monitor</h2></div><span id="liveMonitorStatus" class="status">Loading…</span></div>
    <p class="meta">The champion is frozen. Each aligned completed-EOD state is archived before its outcome is known; labels mature only after 20 later archived trading dates. Missing forward closes are marked unresolved rather than imputed. This section can downgrade confidence or trigger review, but never retrains or promotes a model automatically.</p>
    <div id="liveMonitorBody"></div>`;
  if(governance&&governance.parentNode) governance.parentNode.insertBefore(section,governance);
  else if(validation?.parentNode) validation.parentNode.insertBefore(section,validation.nextSibling);
  const nav=document.querySelector('header nav');
  if(nav&&!nav.querySelector('a[href="#live"]')){
    const a=document.createElement('a');
    a.href='#live';a.textContent='Live Monitor';
    const gov=nav.querySelector('a[href="#governance"]');
    nav.insertBefore(a,gov||null);
  }
  return section;
}

function displayRate(x){
  return Number.isFinite(+x)?pct(x):'Awaiting matured outcomes';
}

function renderLive(data){
  ensureSection();
  const status=document.getElementById('liveMonitorStatus');
  const root=document.getElementById('liveMonitorBody');
  if(!root) return;
  if(data.error){
    if(status){status.textContent='Monitor initializing';status.className='status';}
    root.innerHTML=`<div class="empty">Live monitor assets are being initialized. ${esc(data.error)}</div>`;
    return;
  }
  const t=data.track||{};
  const q=data.integrity||{};
  const td=t.tDayLiveTrack||{};
  const pl=t.pooledLiveTrack||{};
  const cal=t.calibrationLiveMonitor||{};
  const red=td.bySignalBand?.RED||{};
  const yellow=td.bySignalBand?.YELLOW||{};
  const aligned=q.sameCompletedEod===true;
  const integrityPass=q.status==='PASS';
  if(status){
    status.textContent=`${integrityPass?'PASS':'REVIEW'} · EOD ${q.marketModelDate||'—'}`;
    status.className=`status ${integrityPass?'ok':'loading'}`;
  }
  root.innerHTML=`
    <div class="liveGrid">
      <article class="liveCard"><span>Archived PIT snapshots</span><b>${t.archivedSnapshots||0}</b><small>${esc(t.trackingStarted||'Tracking starts with first aligned EOD')}</small></article>
      <article class="liveCard"><span>Current EOD integrity</span><b class="${aligned?'livePass':'liveWarn'}">${aligned?'ALIGNED':'NOT ALIGNED'}</b><small>Market ${esc(q.marketModelDate||'—')} · pooled ${esc(q.pooledModelDate||'—')}</small></article>
      <article class="liveCard"><span>Matured T-Day signals</span><b>${td.maturedSignals||0}</b><small>${td.pendingSignals||0} pending · fixed 20-session horizon</small></article>
      <article class="liveCard"><span>Matured pooled states</span><b>${pl.maturedStates||0}</b><small>${pl.pendingStates||0} pending</small></article>
      <article class="liveCard"><span>Live calibration</span><b class="${cal.stable?'livePass':'liveWait'}">${esc(cal.status||'BUILDING')}</b><small>No automatic probability promotion</small></article>
    </div>
    <div class="liveCols">
      <article class="liveMetric"><span>POINT-IN-TIME DATA QUALITY</span><h3>${integrityPass?'PASS · completed EOD only':'REVIEW REQUIRED'}</h3><div class="liveRows">
        <div><span>Market / pooled date</span><b>${aligned?'same EOD':'mismatch'}</b></div>
        <div><span>Market context</span><b>${esc(q.marketContextStatus||'—')}</b></div>
        <div><span>Neutral imputation</span><b>${q.marketContextImputed?'YES · FAIL':'NO'}</b></div>
        <div><span>Archive action</span><b>${esc(q.archiveStatus||'—')}</b></div>
        <div><span>Policy aligned</span><b>${q.policyAligned?'YES':'NO'}</b></div>
      </div></article>
      <article class="liveMetric"><span>T-DAY LIVE OUTCOMES</span><h3>${esc(td.status||'BUILDING')}</h3><div class="liveRows">
        <div><span>RED matured / event rate</span><b>${red.matured||0} / ${displayRate(red.eventRate)}</b></div>
        <div><span>YELLOW matured / event rate</span><b>${yellow.matured||0} / ${displayRate(yellow.eventRate)}</b></div>
        <div><span>All alerts event rate</span><b>${displayRate(td.combinedAlerts?.eventRate)}</b></div>
        <div><span>Eligible-state base rate</span><b>${displayRate(td.eligibleMarketBaseline?.eventRate)}</b></div>
        <div><span>Alert lift</span><b>${Number.isFinite(+td.combinedAlerts?.liftVsEligibleMarketStates)?(+td.combinedAlerts.liftVsEligibleMarketStates).toFixed(2)+'×':'Awaiting evidence'}</b></div>
      </div></article>
      <article class="liveMetric"><span>POOLED RANK + CALIBRATION</span><h3>${esc(pl.status||'BUILDING')}</h3><div class="liveRows">
        <div><span>Live PR-AUC / base</span><b>${num(pl.prAuc)} / ${displayRate(pl.baseRate)}</b></div>
        <div><span>Top-decile live event rate</span><b>${displayRate(pl.topDecile?.eventRate)}</b></div>
        <div><span>Top-decile live lift</span><b>${Number.isFinite(+pl.topDecile?.liftVsLiveBase)?(+pl.topDecile.liftVsLiveBase).toFixed(2)+'×':'Awaiting evidence'}</b></div>
        <div><span>Live Brier skill</span><b>${num(cal.brierSkill)}</b></div>
        <div><span>Live ECE</span><b>${num(cal.ece10)}</b></div>
      </div></article>
    </div>
    <p class="meta" style="margin-top:10px"><b>Interpretation:</b> no live performance metric is fabricated before outcomes mature. The first 20-session outcomes only become available after 20 later archived completed-EOD dates. A future live calibration PASS is review-eligible evidence only; model promotion remains manual.</p>`;
}

function inferredPublishers(items){
  const publishers=new Set();
  for(const item of items||[]){
    if(item.publisher){publishers.add(String(item.publisher).trim());continue;}
    const title=String(item.title||'');
    const i=title.lastIndexOf(' - ');
    if(i>0&&i<title.length-3) publishers.add(title.slice(i+3).trim());
  }
  return [...publishers].filter(Boolean);
}

function clarifyResearch(out){
  setTimeout(()=>{
    if(window.__VMEWS_LAST_RESEARCH__!==out) return;
    const riskRank=out?.currentRisk;

    const scoreRoot=document.getElementById('researchScore');
    if(scoreRoot&&Number.isFinite(+riskRank)){
      for(const card of scoreRoot.children){
        const label=card.querySelector('span');
        const value=card.querySelector('b');
        const note=card.querySelector('small');
        if(label?.textContent==='CURRENT RESEARCH RISK INDEX'){
          label.textContent='CURRENT RESEARCH RISK RANK';
          if(value) value.textContent=ordinal(riskRank);
          if(note) note.textContent='Validation-aware historical rank plus limited current context; not confidence or probability.';
        }
      }
    }

    const conclusion=document.getElementById('researchConclusion');
    if(conclusion&&Number.isFinite(+riskRank)){
      const firstCard=conclusion.querySelector('.conclusionGrid>div:first-child');
      if(firstCard){
        const label=firstCard.querySelector('span');
        const value=firstCard.querySelector('b');
        if(label) label.textContent='Current risk rank';
        if(value){
          const parts=(value.textContent||'').split('·');
          const band=(parts[1]||'').trim();
          value.textContent=ordinal(riskRank)+(band?` · ${band}`:'');
        }
      }
      const paragraph=conclusion.querySelector('p');
      if(paragraph){
        paragraph.textContent=(paragraph.textContent||'').replace(/Risk index\s+\d+\/100/i,`Risk rank ${ordinal(riskRank)}`);
      }
      if(!conclusion.querySelector('.clarityRankNote')){
        const note=document.createElement('small');
        note.className='clarityRankNote';
        note.textContent='Percentile/rank measures relative historical severity. Evidence sufficiency measures reliability. Neither is an absolute crash probability.';
        conclusion.appendChild(note);
      }
    }

    const keys=['structural','rf','anfis','regime','vae','lstm'];
    const modelCards=[...document.querySelectorAll('#modelGrid .metric')];
    modelCards.slice(0,6).forEach((card,i)=>{
      const note=card.querySelector('small');
      if(!note||/OOS reliability/i.test(note.textContent||'')) return;
      const weight=out.validation?.globalWeights?.[keys[i]]||0;
      note.textContent+=weight>0
        ?` · OOS reliability ACTIVE (${(weight*100).toFixed(0)}% rank weight)`
        :' · OOS reliability: NO incremental rank weight (0%)';
    });

    const news=out.news||{};
    const publisherCount=news.sourceCount||inferredPublishers(news.items).length;
    const newsMeta=document.getElementById('newsMeta');
    if(newsMeta){
      newsMeta.textContent=`${news.articleCount||0} unique headlines · ${publisherCount||0} publishers · headline-level event/NLP risk ${news.score==null?'N/A':Math.round(+news.score)+'/100'}`;
    }
    const newsCard=[...document.querySelectorAll('#moduleGrid .metric')].find(card=>card.querySelector('span')?.textContent==='News');
    if(newsCard){
      const note=newsCard.querySelector('small');
      const raw=out?.data?.rawNewsHeadlines||null;
      if(note){
        note.textContent=raw
          ?`${raw} raw headlines → ${news.articleCount||0} unique used`
          :`${news.articleCount||0} unique headlines used in research layer`;
      }
    }

    if(lastTrack){
      const pooledRoot=document.getElementById('pooledPredictiveLayer');
      if(pooledRoot&&!document.getElementById('pooledLiveOutcomeNote')){
        const liveNote=document.createElement('div');
        liveNote.id='pooledLiveOutcomeNote';
        liveNote.className='pooledNote';
        const pooled=lastTrack.pooledLiveTrack||{};
        const calibration=lastTrack.calibrationLiveMonitor||{};
        liveNote.innerHTML='<strong>Live outcomes:</strong> '
          +esc(pooled.status||'BUILDING')
          +' · matured pooled states '+String(pooled.maturedStates||0)
          +' · calibration '+esc(calibration.status||'BUILDING')
          +'. Live monitoring may downgrade evidence; promotion remains manual.';
        pooledRoot.appendChild(liveNote);
      }
    }
  },160);
}

function patchResearch(){
  const R=window.VMEWSResearch;
  if(!R||R.__liveV6Patched) return false;
  const base=R.run.bind(R);
  R.run=async(...args)=>{
    const out=await base(...args);
    clarifyResearch(out);
    return out;
  };
  R.__liveV6Patched=true;
  return true;
}

async function init(){
  ensureSection();
  renderLive(await live());
  if(!patchResearch()){
    let n=0;
    const timer=setInterval(()=>{
      if(patchResearch()||++n>150) clearInterval(timer);
    },30);
  }
}

if(document.readyState==='loading') window.addEventListener('DOMContentLoaded',init);
else init();
window.VMEWSLiveMonitor={version:VERSION,market,live,clarity:clarifyResearch};
})();
