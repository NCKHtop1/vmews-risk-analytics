const $ = id => document.getElementById(id);
const fmt = new Intl.NumberFormat('en-US',{maximumFractionDigits:2});
const pct = (x,d=2)=> Number.isFinite(Number(x)) ? `${(Number(x)*100).toFixed(d)}%` : '—';
const num = (x,d=2)=> Number.isFinite(Number(x)) ? Number(x).toFixed(d) : '—';
const clamp=(x,a=0,b=100)=>Math.max(a,Math.min(b,x));
let model=null, range='max', quoteTimer=null;

const INFO={
  liveQuote:['Live / latest quote','The live quote is fetched separately from the completed daily-bar model. During a trading session it can be newer than the model-as-of date. This separation prevents an incomplete intraday bar from being treated as a fully observed daily session.'],
  ewsScore:['EWS score (0–100)','Operational warning score built from six transparent pressures: volatility regime (25 pts), 60-day drawdown (20), negative 20-day momentum (15), MA50 trend break (15), negative-return shock (15), and volume-confirmed stress (10). State thresholds: LOW <32, WATCH 32–54, HIGH 55–74, CRITICAL ≥75.'],
  modelAsOf:['Model as-of date','The latest completed daily observation used by the EWS. This is intentionally different from the intraday quote. If this date becomes stale, Data Quality changes to REVIEW and the interface should not be interpreted as a current model signal.'],
  horizons:['Forward warning horizons','Each 5D, 20D and 60D warning combines the current structural EWS score with the historical stress rate among the 40 most similar past market states. The analog stress rate is evidence from history, not a guaranteed probability of a future crash.'],
  drivers:['Risk contributors','Each driver is normalized to a pressure from 0 to 100 using rolling market context. The contribution bar shows how many points that driver adds to the current EWS score. This makes the warning auditable rather than a black-box number.'],
  alerts:['Active alerts','An alert is emitted when a monitored driver crosses its operational pressure threshold. HIGH means the driver pressure is at least 75/100; WATCH means at least 45/100. Alerts explain what changed and how much it contributes to the aggregate risk score.'],
  analogs:['Historical analog engine','The engine standardizes six state variables and computes multivariate distance between today and older observations. The 40 nearest valid historical states are used to examine subsequent drawdowns over 5, 20 and 60 trading days.'],
  crashDiagnostic:['3.09σ diagnostic','This is a thesis-aligned realized tail-event diagnostic: the current 5-session log return is compared with mean minus 3.09 standard deviations. It identifies an extreme realized move; it is not itself a forward predictor.'],
  backtest:['Chronological holdout diagnostics','Eligible historical observations are split 70/30 in time order. The first 70% defines the alert threshold and the worst-5% forward drawdown threshold. Metrics are then measured only on the later 30%, reducing look-ahead bias.'],
  stress:['What-if stress lab','This client-side scenario tool approximates how current risk pressures could change under a hypothetical one-day price shock, volatility expansion and elevated volume. It is a sensitivity analysis, not a re-trained forecast.'],
  method:['Data and model governance','The system distinguishes source data, completed-session model inputs, live quote, operational EWS metrics, thesis-reported research benchmarks and scenario outputs. Data freshness and validation are surfaced explicitly to reduce silent model-risk.']
};

function stateFor(s){return s>=75?'CRITICAL':s>=55?'HIGH':s>=32?'WATCH':'LOW'}
function stateClass(s){return String(s||'').toLowerCase()}
function setText(id,v){const e=$(id);if(e)e.textContent=v}
function showError(msg){$('loadingOverlay').classList.add('hidden');$('errorBanner').hidden=false;setText('errorText',msg||'Unknown error');$('feedBadge').textContent='MODEL ERROR';$('feedBadge').className='badge danger';$('topDataBadge').textContent='MODEL ERROR';$('topDataBadge').className='badge danger'}

async function fetchJSON(url){const r=await fetch(url,{cache:'no-store'});const t=await r.text();let p;try{p=JSON.parse(t)}catch{throw new Error(`Invalid response (${r.status})`)}if(!r.ok)throw new Error(p.message||p.error||`HTTP ${r.status}`);return p}

async function loadModel(){
  $('errorBanner').hidden=true;$('loadingOverlay').classList.remove('hidden');
  try{model=await fetchJSON('/api/ews?mode=full');renderAll();$('loadingOverlay').classList.add('hidden');startQuoteRefresh()}
  catch(e){console.error(e);showError(e.message)}
}

async function refreshQuote(){
  if(!model)return;
  try{const p=await fetchJSON(`/api/ews?mode=quote&t=${Date.now()}`);if(p.quote){model.quote=p.quote;model.fetchedAt=p.fetchedAt||model.fetchedAt;renderQuote()}}
  catch(e){console.warn('Quote refresh failed',e)}
}
function startQuoteRefresh(){clearInterval(quoteTimer);quoteTimer=setInterval(refreshQuote,60000)}

function renderQuote(){
  const rows=model.rows||[], last=rows.at(-1)||{}, prev=rows.at(-2)||last;
  const q=model.quote||{}; const live=Number.isFinite(Number(q.last))?Number(q.last):Number(last.close);
  let ch=Number(q.percentChange); if(!Number.isFinite(ch)){const base=Number(prev.close)||Number(last.close);ch=base?((live/base)-1)*100:0}
  setText('livePrice',fmt.format(live));setText('liveChange',`${ch>=0?'+':''}${ch.toFixed(2)}%`);$('liveChange').className=`change ${ch>=0?'pos':'neg'}`;
  setText('quoteTime',q.time?String(q.time).replace('T',' ').slice(0,19):`EOD ${last.date||'—'}`);
  setText('fetchTime',`Fetched: ${new Date(model.fetchedAt).toLocaleString()}`);setText('footerSource',`Source: ${model.source} · ${model.provider}`)
}

function renderHeader(){
  const dq=model.dataQuality||{}, c=model.current||{}, risk=model.risk||{};
  setText('heroCoverage',`${dq.start||'—'} → ${dq.end||'—'} · ${fmt.format(dq.rows||0)} sessions`);setText('heroVersion',model.version||'—');
  const good=dq.status==='PASS';$('feedBadge').textContent=good?'VNSTOCK LIVE':'DATA REVIEW';$('feedBadge').className=`badge ${good?'live':'warn'}`;$('topDataBadge').textContent=good?'DATA PASS':'DATA REVIEW';$('topDataBadge').className=`badge ${good?'live':'warn'}`;
  setText('riskScore',Math.round(risk.score??c.score??0));setText('riskState',risk.state||stateFor(risk.score||0));setText('riskNarrative',risk.narrative||'—');setText('modelDate',c.date||dq.end||'—');setText('vol20',pct(c.vol20));setText('dd60',pct(c.dd60));setText('dqStatus',dq.status||'—');
  $('riskRing').style.setProperty('--risk-angle',`${clamp(risk.score||0)*3.6}deg`);$('riskRing').dataset.state=stateClass(risk.state);
  renderQuote();
}

function renderHorizons(){const root=$('horizonCards');root.innerHTML='';for(const h of model.risk?.horizons||[]){const el=document.createElement('article');el.className=`horizon-card card ${stateClass(h.state)}`;el.innerHTML=`<div class="horizon-top"><span>${h.days} TRADING DAYS</span><b>${h.state}</b></div><div class="horizon-score">${Math.round(h.score)}<small>/100</small></div><div class="horizon-detail"><span>Analog tail-stress rate</span><b>${pct(h.analogStressRate,1)}</b></div><div class="horizon-detail"><span>Tail drawdown threshold</span><b>${pct(h.tailThreshold,1)}</b></div><div class="horizon-detail"><span>Matched states</span><b>${h.analogs}</b></div>`;root.appendChild(el)}}

const DRIVER_META={volatility:['Volatility regime',25],drawdown:['60D drawdown',20],momentum:['20D momentum',15],trend:['MA50 trend break',15],shock:['Negative shock',15],volume:['Volume confirmation',10]};
function renderDrivers(){const root=$('driverBars');root.innerHTML='';const c=model.current||{};for(const [k,[label,maxPts]] of Object.entries(DRIVER_META)){const p=Number(c.pressures?.[k]||0),con=Number(c.contributions?.[k]||0);const row=document.createElement('div');row.className='driver-row';row.innerHTML=`<div class="driver-label"><span>${label}</span><b>${Math.round(p*100)}/100 · +${con.toFixed(1)} pts</b></div><div class="bar"><i style="width:${clamp(p*100)}%"></i></div><small>Max ${maxPts} pts</small>`;root.appendChild(row)}const sorted=Object.entries(c.contributions||{}).sort((a,b)=>b[1]-a[1]).slice(0,2).map(([k])=>DRIVER_META[k]?.[0]||k);$('driverSummary').innerHTML=`<b>Largest current contributors:</b> ${sorted.join(' and ')||'—'}.`}

function renderAlerts(){const list=$('alertList');list.innerHTML='';for(const a of model.risk?.alerts||[]){const el=document.createElement('article');el.className=`alert-item card ${stateClass(a.severity)}`;el.innerHTML=`<div class="alert-severity">${a.severity}</div><div><h3>${a.title}</h3><p>${a.description}</p><div class="alert-meta"><span>Pressure ${Math.round((a.pressure||0)*100)}/100</span><span>Contribution +${Number(a.contribution||0).toFixed(1)} pts</span></div></div>`;list.appendChild(el)}setText('playbookTitle',`${model.risk?.state||'—'} STATE CHECKLIST`);$('playbookList').innerHTML=(model.risk?.playbook||[]).map(x=>`<li>${x}</li>`).join('')}

function renderAnalogs(){const body=$('analogRows');body.innerHTML='';for(const a of model.analogs||[]){body.insertAdjacentHTML('beforeend',`<tr><td>${a.date}</td><td>${pct(a.similarity,1)}</td><td class="${a.forwardReturn20>=0?'pos':'neg'}">${pct(a.forwardReturn20,1)}</td><td class="neg">${pct(a.maxDrawdown20,1)}</td><td><span class="mini-badge ${a.stress?'danger':'neutral'}">${a.stress?'YES':'NO'}</span></td></tr>`)}const c=model.crashDiagnostic||{};setText('crashReturn',pct(c.currentReturn));setText('crashThreshold',pct(c.threshold));setText('sigmaDistance',`${num(c.sigmaDistance,2)}σ`);setText('crashTriggered',c.triggered?'TRIGGERED':'NOT TRIGGERED');$('crashTriggered').className=c.triggered?'neg':'pos'}

function renderBacktest(){const b=model.backtest||{};const metrics=[['ROC AUC',b.auc],['Precision',b.precision],['Recall',b.recall],['F1',b.f1],['Accuracy',b.accuracy],['Alert lift',b.lift]];$('metricGrid').innerHTML=metrics.map(([k,v])=>`<div><span>${k}</span><b>${Number.isFinite(Number(v))?(k==='Alert lift'?`${Number(v).toFixed(2)}×`:Number(v).toFixed(3)):'—'}</b></div>`).join('');setText('btSplit',`Calibration N=${b.trainN||0} · Holdout N=${b.testN||0} · Holdout starts ${b.splitDate||'—'} · 20D tail threshold ${pct(b.stressThreshold20,1)}`);const cm=b.confusion||{};$('confusion').innerHTML=`<div class="cm-axis">PREDICTED</div><div class="cm-grid"><div class="cm-head"></div><div class="cm-head">STRESS</div><div class="cm-head">NO STRESS</div><div class="cm-head side">ACTUAL STRESS</div><div class="cm-cell good">TP<br><b>${cm.tp??'—'}</b></div><div class="cm-cell bad">FN<br><b>${cm.fn??'—'}</b></div><div class="cm-head side">ACTUAL NORMAL</div><div class="cm-cell bad">FP<br><b>${cm.fp??'—'}</b></div><div class="cm-cell good">TN<br><b>${cm.tn??'—'}</b></div></div>`;const cal=$('calibrationBars');cal.innerHTML='';for(const x of b.calibration||[]){cal.insertAdjacentHTML('beforeend',`<div><span>${x.bucket}<small>n=${x.n}</small></span><div class="bar"><i style="width:${clamp((x.eventRate||0)*100)}%"></i></div><b>${pct(x.eventRate,1)}</b></div>`)}}

function renderQuality(){const d=model.dataQuality||{};const vals=[['Status',d.status],['Observations',fmt.format(d.rows||0)],['Coverage',`${d.start||'—'} → ${d.end||'—'}`],['Stale calendar days',d.staleCalendarDays],['Duplicates removed',d.duplicatesRemoved],['Invalid rows removed',d.invalidRemoved],['Large gaps',d.largeGaps]];$('qualityMetrics').innerHTML=vals.map(([k,v])=>`<div><span>${k}</span><b>${v??'—'}</b></div>`).join('')}

function setupCanvas(canvas){const r=canvas.getBoundingClientRect(),d=Math.min(2,window.devicePixelRatio||1),w=Math.max(320,Math.floor(r.width||800)),h=Math.max(260,Math.floor(r.height||380));canvas.width=w*d;canvas.height=h*d;const ctx=canvas.getContext('2d');ctx.setTransform(d,0,0,d,0,0);return{ctx,w,h}}
function renderChart(){if(!model)return;let rows=model.rows||[], scores=model.scoreHistory||[];const n=range==='1y'?260:range==='3y'?780:rows.length;rows=rows.slice(-n);const scoreMap=new Map(scores.map(x=>[x.date,x.score]));const pts=rows.map(r=>({date:r.date,close:r.close,score:scoreMap.get(r.date)}));const c=$('priceChart'),{ctx,w,h}=setupCanvas(c);ctx.clearRect(0,0,w,h);if(pts.length<2)return;const pad={l:14,r:48,t:16,b:28},cl=pts.map(x=>x.close),cmin=Math.min(...cl),cmax=Math.max(...cl),cr=cmax-cmin||1;const X=i=>pad.l+(w-pad.l-pad.r)*i/(pts.length-1),Yp=v=>pad.t+(h-pad.t-pad.b)*(1-(v-cmin)/cr),Yr=v=>pad.t+(h-pad.t-pad.b)*(1-v/100);ctx.strokeStyle='#17304a';ctx.lineWidth=1;ctx.font='10px ui-monospace';ctx.fillStyle='#70869d';for(let j=0;j<=4;j++){const y=pad.t+(h-pad.t-pad.b)*j/4;ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(w-pad.r,y);ctx.stroke();ctx.fillText(Math.round(cmax-cr*j/4),w-pad.r+6,y+3)}ctx.beginPath();pts.forEach((p,i)=>i?ctx.lineTo(X(i),Yp(p.close)):ctx.moveTo(X(i),Yp(p.close)));ctx.strokeStyle='#48d9ff';ctx.lineWidth=1.8;ctx.stroke();ctx.beginPath();let started=false;pts.forEach((p,i)=>{if(!Number.isFinite(Number(p.score)))return;started?ctx.lineTo(X(i),Yr(p.score)):ctx.moveTo(X(i),Yr(p.score));started=true});ctx.strokeStyle='#ffc95d';ctx.lineWidth=1.5;ctx.stroke();for(let i=0;i<pts.length;i++){const s=Number(pts[i].score);if(s>=55){ctx.beginPath();ctx.arc(X(i),Yr(s),2.7,0,Math.PI*2);ctx.fillStyle=s>=75?'#ff5d73':'#ffc95d';ctx.fill()}}const ticks=Math.min(6,pts.length);for(let t=0;t<ticks;t++){const i=Math.round((pts.length-1)*t/(ticks-1||1));ctx.fillStyle='#6b8197';ctx.fillText(pts[i].date,X(i)-26,h-7)}}

function stressScore(){if(!model)return;const c=model.current||{}, base=Number(model.risk?.score||0),shock=Number($('shockInput').value),vm=Number($('volMultInput').value),vz=Number($('volumeStressInput').value);setText('shockLabel',`${shock.toFixed(1)}%`);setText('volMultLabel',`${vm.toFixed(1)}×`);setText('volumeStressLabel',`+${vz.toFixed(2)}σ`);const existing=c.pressures||{};const shockP=Math.max(existing.shock||0,clamp((-shock/7)*100)/100);const volP=Math.max(existing.volatility||0,clamp(((vm-1)/1.2)*100)/100);const volumeP=Math.max(existing.volume||0,clamp((vz/4)*100)/100*Math.max(0,-shock/5));const ddP=Math.max(existing.drawdown||0,clamp(((Math.abs(Math.min(c.dd60||0,0))+Math.max(0,-shock/100))/.18)*100)/100);const momP=Math.max(existing.momentum||0,clamp(((Math.abs(Math.min(c.mom20||0,0))+Math.max(0,-shock/100))/.12)*100)/100);const trendP=Math.max(existing.trend||0,clamp(((Math.abs(Math.min(c.trendGap||0,0))+Math.max(0,-shock/100))/.10)*100)/100);const score=clamp(25*volP+20*ddP+15*momP+15*trendP+15*shockP+10*volumeP);const st=stateFor(score);setText('stressScore',Math.round(score));setText('stressState',st);setText('stressExplanation',`Scenario moves the operational EWS from ${Math.round(base)}/100 (${model.risk?.state}) to about ${Math.round(score)}/100 (${st}). The projection is driven by stressed volatility, price-shock, drawdown, trend and volume pressures.`);setText('currentStateChip',`CURRENT ${model.risk?.state} ${Math.round(base)}`);setText('stressStateChip',`STRESS ${st} ${Math.round(score)}`);$('stressStateChip').className=`state-chip ${stateClass(st)}`}

function renderAll(){renderHeader();renderHorizons();renderDrivers();renderAlerts();renderAnalogs();renderBacktest();renderQuality();renderChart();stressScore()}

function openInfo(key){const [t,b]=INFO[key]||['Information','No information available.'];setText('infoTitle',t);$('infoBody').innerHTML=`<p>${b}</p>`;$('infoDialog').showModal()}

document.addEventListener('DOMContentLoaded',()=>{
  setInterval(()=>setText('topClock',new Date().toLocaleString()),1000);
  document.addEventListener('click',e=>{const b=e.target.closest('[data-info]');if(b)openInfo(b.dataset.info);const r=e.target.closest('[data-range]');if(r){document.querySelectorAll('[data-range]').forEach(x=>x.classList.remove('active'));r.classList.add('active');range=r.dataset.range;renderChart()}});
  ['shockInput','volMultInput','volumeStressInput'].forEach(id=>$(id).addEventListener('input',stressScore));
  $('refreshBtn').addEventListener('click',loadModel);$('retryBtn').addEventListener('click',loadModel);
  let rt;window.addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(renderChart,120)});
  loadModel();
});
