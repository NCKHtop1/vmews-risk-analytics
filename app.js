const $ = (id) => document.getElementById(id);
const fmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
let currentRange = '5y';
let latestPayload = null;
let staticBenchmarks = null;
let staticSectors = null;

const clamp = (x, a=0, b=1) => Math.max(a, Math.min(b, x));
const mean = arr => arr.length ? arr.reduce((a,b)=>a+b,0)/arr.length : 0;
const sd = arr => {
  if (arr.length < 2) return 0;
  const m = mean(arr);
  return Math.sqrt(arr.reduce((s,x)=>s+(x-m)**2,0)/(arr.length-1));
};
const pct = x => `${(x*100).toFixed(2)}%`;

function returns(rows){
  const out=[];
  for(let i=1;i<rows.length;i++){
    const a=rows[i-1].close,b=rows[i].close;
    out.push(a>0 && b>0 ? Math.log(b/a) : 0);
  }
  return out;
}
function rollingVol(rows, window=20){ return sd(returns(rows).slice(-window))*Math.sqrt(252); }
function drawdown(rows, window=60){
  const x=rows.slice(-window).map(r=>r.close).filter(v=>v>0);
  if(!x.length) return 0;
  const peak=Math.max(...x), last=x[x.length-1];
  return peak ? last/peak-1 : 0;
}
function momentum(rows, window=20){
  const x=rows.slice(-(window+1));
  return x.length>=2 ? x[x.length-1].close/x[0].close-1 : 0;
}
function percentileRank(value, history){
  const valid=history.filter(Number.isFinite);
  return valid.length ? valid.filter(v=>v<=value).length/valid.length : .5;
}
function volPercentile(rows){
  if(rows.length<30) return .5;
  const vols=[];
  for(let i=21;i<=rows.length;i++) vols.push(rollingVol(rows.slice(0,i),20));
  return percentileRank(vols.at(-1), vols.slice(-252));
}
function anomaly(rows){
  const r=returns(rows);
  if(r.length<21) return {z:0,score:0};
  const hist=r.slice(-21,-1), last=r.at(-1), s=sd(hist), m=mean(hist);
  const z=s ? Math.abs((last-m)/s) : 0;
  return {z,score:clamp(z/4)};
}
function riskForSlice(rows){
  const vol=rollingVol(rows,20), volP=volPercentile(rows), dd=drawdown(rows,60), mom=momentum(rows,20), an=anomaly(rows);
  const volPressure=clamp((volP-.35)/.65), ddPressure=clamp(Math.abs(Math.min(dd,0))/.20), momPressure=clamp(Math.abs(Math.min(mom,0))/.15), anomalyPressure=an.score;
  const score=100*(.35*volPressure+.25*ddPressure+.20*momPressure+.20*anomalyPressure);
  return {score,vol,dd,mom,anomaly:an.z,drivers:{volPressure,ddPressure,momPressure,anomalyPressure}};
}
function stateForScore(s){
  if(s>=65) return {label:'HIGH',cls:'danger',light:'high'};
  if(s>=35) return {label:'WATCH',cls:'warn',light:'medium'};
  return {label:'LOW',cls:'ok',light:'low'};
}
function compactReason(r){
  const d=[];
  if(r.drivers.volPressure>.6)d.push('high volatility');
  if(r.drivers.ddPressure>.45)d.push('drawdown');
  if(r.drivers.momPressure>.45)d.push('negative momentum');
  if(r.drivers.anomalyPressure>.5)d.push('return anomaly');
  return d.length?d.join(', '):'normal conditions';
}
function cleanRows(rows){
  const byDate=new Map();
  for(const raw of rows||[]){
    const date=String(raw.date||'').slice(0,10), close=Number(raw.close);
    if(!date || !Number.isFinite(close) || close<=0) continue;
    byDate.set(date,{date,open:Number(raw.open)||close,high:Number(raw.high)||close,low:Number(raw.low)||close,close,volume:Number(raw.volume)||0});
  }
  return [...byDate.values()].sort((a,b)=>a.date.localeCompare(b.date));
}

async function fetchFallback(){
  const r=await fetch('./data/fallback-market.json',{cache:'no-store'});
  if(!r.ok) throw new Error('Fallback dataset unavailable');
  return r.json();
}
async function fetchMarket(range=currentRange){
  try{
    const r=await fetch(`/api/market?range=${encodeURIComponent(range)}`,{cache:'no-store'});
    if(!r.ok) throw new Error(`API ${r.status}`);
    const payload=await r.json(), rows=cleanRows(payload.rows);
    if(rows.length<10) throw new Error('Too few live rows');
    return {...payload,rows,isFallback:false};
  }catch(e){
    console.warn('Live feed failed; using fallback',e);
    const fb=await fetchFallback();
    return {...fb,rows:cleanRows(fb.rows),isFallback:true};
  }
}

// ---------- dependency-free canvas charts ----------
function setupCanvas(canvas){
  const rect=canvas.getBoundingClientRect();
  const dpr=Math.max(1,Math.min(2,window.devicePixelRatio||1));
  const w=Math.max(220,Math.floor(rect.width||canvas.parentElement.clientWidth||600));
  const h=Math.max(120,Math.floor(rect.height||canvas.parentElement.clientHeight||300));
  canvas.width=w*dpr; canvas.height=h*dpr;
  const ctx=canvas.getContext('2d'); ctx.setTransform(dpr,0,0,dpr,0,0);
  return {ctx,w,h};
}
function lineChart(canvas, points, opts={}){
  const {ctx,w,h}=setupCanvas(canvas); ctx.clearRect(0,0,w,h);
  if(!points.length) return;
  const pad={l:10,r:50,t:10,b:26};
  const vals=points.map(p=>p.y).filter(Number.isFinite); let min=Math.min(...vals),max=Math.max(...vals);
  if(min===max){min-=1;max+=1} const extra=(max-min)*.06; min-=extra;max+=extra;
  const X=i=>pad.l+(w-pad.l-pad.r)*(i/Math.max(1,points.length-1));
  const Y=v=>pad.t+(h-pad.t-pad.b)*(1-(v-min)/(max-min));
  ctx.font='10px ui-monospace, SFMono-Regular, Consolas, monospace'; ctx.fillStyle='#6f879f';ctx.strokeStyle='#14283b';ctx.lineWidth=1;
  for(let i=0;i<4;i++){const yy=pad.t+(h-pad.t-pad.b)*i/3;ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke();const v=max-(max-min)*i/3;ctx.fillText(fmt.format(v),w-pad.r+7,yy+3)}
  if(opts.fill){const g=ctx.createLinearGradient(0,pad.t,0,h-pad.b);g.addColorStop(0,'rgba(71,215,255,.18)');g.addColorStop(1,'rgba(71,215,255,0)');ctx.beginPath();points.forEach((p,i)=>{const x=X(i),y=Y(p.y);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.lineTo(X(points.length-1),h-pad.b);ctx.lineTo(X(0),h-pad.b);ctx.closePath();ctx.fillStyle=g;ctx.fill()}
  ctx.beginPath();points.forEach((p,i)=>{const x=X(i),y=Y(p.y);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.strokeStyle=opts.color||'#47d7ff';ctx.lineWidth=opts.width||1.7;ctx.stroke();
  if(opts.stress){for(const s of opts.stress){if(!s)continue;const i=s.i;if(i<0||i>=points.length)continue;ctx.beginPath();ctx.arc(X(i),Y(points[i].y),3.2,0,Math.PI*2);ctx.fillStyle='#ffca63';ctx.fill()}}
  const ticks=Math.min(6,points.length);ctx.fillStyle='#677f98';
  for(let t=0;t<ticks;t++){const i=Math.round((points.length-1)*t/Math.max(1,ticks-1));const label=points[i].x;ctx.fillText(label,X(i)-25,h-7)}
}
function miniLine(canvas, points){
  const {ctx,w,h}=setupCanvas(canvas);ctx.clearRect(0,0,w,h);if(points.length<2)return;
  const vals=points.map(p=>p.y),min=Math.min(...vals),max=Math.max(...vals),rng=max-min||1;
  const X=i=>w*i/(points.length-1),Y=v=>8+(h-16)*(1-(v-min)/rng);
  const g=ctx.createLinearGradient(0,0,0,h);g.addColorStop(0,'rgba(71,215,255,.14)');g.addColorStop(1,'rgba(71,215,255,0)');
  ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(X(i),Y(p.y)):ctx.moveTo(X(i),Y(p.y)));ctx.lineTo(w,h);ctx.lineTo(0,h);ctx.closePath();ctx.fillStyle=g;ctx.fill();
  ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(X(i),Y(p.y)):ctx.moveTo(X(i),Y(p.y)));ctx.strokeStyle='#47d7ff';ctx.lineWidth=1.5;ctx.stroke();
}
function horizontalBars(canvas, items){
  const {ctx,w,h}=setupCanvas(canvas);ctx.clearRect(0,0,w,h);if(!items.length)return;
  const max=Math.max(...items.map(x=>x.value))*1.08, left=Math.min(160,w*.38),right=40,top=12,row=(h-24)/items.length;
  ctx.font='10px ui-sans-serif, system-ui';
  items.forEach((it,i)=>{const y=top+i*row+row*.18,bh=row*.55,bw=(w-left-right)*(it.value/max);ctx.fillStyle='#8298ad';ctx.fillText(it.label,6,y+bh*.75);ctx.fillStyle=i===0?'rgba(255,202,99,.78)':'rgba(71,215,255,.58)';roundRect(ctx,left,y,bw,bh,5);ctx.fill();ctx.fillStyle='#9bb1c5';ctx.fillText(`${it.value.toFixed(2)}%`,left+bw+7,y+bh*.75)});
}
function roundRect(ctx,x,y,w,h,r){r=Math.min(r,w/2,h/2);ctx.beginPath();ctx.moveTo(x+r,y);ctx.arcTo(x+w,y,x+w,y+h,r);ctx.arcTo(x+w,y+h,x,y+h,r);ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);ctx.closePath()}

function sliceForDisplay(rows,range){
  if(range==='1y') return rows.slice(-260);
  if(range==='5y') return rows.slice(-1260);
  if(rows.length>2200){const step=Math.ceil(rows.length/1800);return rows.filter((_,i)=>i%step===0 || i===rows.length-1)}
  return rows;
}
function renderMarketCharts(rows,range){
  const display=sliceForDisplay(rows,range);
  const points=display.map(r=>({x:r.date,y:r.close})),stress=[];
  // Computing a full historical rolling score on thousands of rows would be expensive in the browser.
  // Use a 100-session stepping window for stress markers, then always include recent sessions.
  const start=Math.max(25,display.length-400);
  for(let i=start;i<display.length;i++){
    if(i<display.length-90 && i%5!==0) continue;
    const r=riskForSlice(display.slice(0,i+1)); if(r.score>=65) stress.push({i});
  }
  lineChart($('marketChart'),points,{fill:true,stress});
  miniLine($('miniChart'),points.slice(-80));
}

function setDelta(el,change){
  el.textContent=`${change>=0?'+':''}${change.toFixed(2)}%`;
  el.classList.remove('pos','neg','neutral-text'); el.classList.add(change>0?'pos':change<0?'neg':'neutral-text');
}
function renderKPIs(payload){
  const rows=payload.rows,last=rows.at(-1),prev=rows.at(-2)||last,change=(last.close/prev.close-1)*100,risk=riskForSlice(rows),state=stateForScore(risk.score),price=fmt.format(last.close);
  $('heroPrice').textContent=price;$('kpiPrice').textContent=price;setDelta($('heroChange'),change);
  $('kpiChange').textContent=`${change>=0?'+':''}${change.toFixed(2)}%`;$('kpiChange').className=`chip ${change>=0?'ok':'danger'}`;
  $('heroRisk').textContent=risk.score.toFixed(0);$('kpiRisk').textContent=risk.score.toFixed(0);$('kpiRiskState').textContent=state.label;$('kpiRiskState').className=`chip ${state.cls}`;
  $('heroVol').textContent=pct(risk.vol);$('kpiVol').textContent=pct(risk.vol);$('heroDD').textContent=pct(risk.dd);$('heroDate').textContent=last.date;$('kpiAnomaly').textContent=`${risk.anomaly.toFixed(2)}σ`;
  $('gaugeValue').textContent=risk.score.toFixed(0);$('riskState').textContent=`${state.label} RISK`;$('riskLight').className=`risk-light ${state.light}`;$('riskGauge').style.setProperty('--score',`${risk.score*3.6}deg`);
  const driverValues=[risk.drivers.volPressure,risk.drivers.ddPressure,risk.drivers.momPressure,risk.drivers.anomalyPressure];[...$('driverList').querySelectorAll('b')].forEach((el,i)=>el.textContent=`${Math.round(driverValues[i]*100)}/100`);
  $('feedBadge').textContent=payload.isFallback?'FALLBACK':'LIVE';$('feedBadge').className=`status-badge ${payload.isFallback?'fallback':'live'}`;
  const source=payload.source||'Market feed';$('feedNote').textContent=payload.isFallback?`Live feed unavailable. Showing fallback data through ${last.date}.`:`${source} · latest session ${last.date}`;
  $('footerFreshness').textContent=`Data freshness: ${last.date} · ${payload.isFallback?'fallback':'live adapter'}`;
}
function renderAlertRows(rows){
  const body=$('alertRows');body.innerHTML='';const start=Math.max(25,rows.length-8);
  for(let i=rows.length-1;i>=start;i--){
    const r=riskForSlice(rows.slice(0,i+1)),st=stateForScore(r.score),prev=rows[i-1]||rows[i],ret=rows[i].close/prev.close-1,tr=document.createElement('tr');
    tr.innerHTML=`<td>${rows[i].date}</td><td>${fmt.format(rows[i].close)}</td><td class="${ret>=0?'pos':'neg'}">${ret>=0?'+':''}${pct(ret)}</td><td>${r.score.toFixed(0)}</td><td><span class="chip ${st.cls}">${st.label}</span></td><td>${compactReason(r)}</td>`;body.appendChild(tr);
  }
}
async function renderStaticResearch(){
  const [b,s]=await Promise.all([fetch('./data/research-benchmarks.json').then(r=>r.json()),fetch('./data/sector-stats.json').then(r=>r.json())]);staticBenchmarks=b;staticSectors=s;
  $('aucBars').innerHTML=b.classifier_auc.map(x=>`<div class="bar-row"><span>${x.model}</span><div class="bar-track"><div class="bar-fill" style="width:${x.auc*100}%"></div></div><b>${x.auc.toFixed(3)}</b></div>`).join('');
  lineChart($('stressChart'),b.stress_test.map(x=>({x:`${x.days_ahead}d`,y:x.accuracy*100})),{fill:true});
  const sorted=[...s].sort((a,b)=>b.stdev-a.stdev);horizontalBars($('sectorChart'),sorted.map(x=>({label:x.sector,value:x.stdev*100})));
  $('sectorRows').innerHTML=s.map(x=>`<tr><td>${x.sector}</td><td>${x.mean.toFixed(6)}</td><td>${x.stdev.toFixed(6)}</td><td>${x.skewness.toFixed(6)}</td></tr>`).join('');
}
async function loadMarket(range=currentRange,notify=false){
  if(notify) toast('Refreshing market data…');const payload=await fetchMarket(range);latestPayload=payload;renderKPIs(payload);renderMarketCharts(payload.rows,range);renderAlertRows(payload.rows);if(notify)toast(payload.isFallback?'Live source unavailable — fallback loaded.':'Market data refreshed.');
}
function toast(msg){const el=$('toast');el.textContent=msg;el.classList.add('show');clearTimeout(window.__toast);window.__toast=setTimeout(()=>el.classList.remove('show'),2200)}
function redraw(){if(latestPayload)renderMarketCharts(latestPayload.rows,currentRange);if(staticBenchmarks)lineChart($('stressChart'),staticBenchmarks.stress_test.map(x=>({x:`${x.days_ahead}d`,y:x.accuracy*100})),{fill:true});if(staticSectors){const sorted=[...staticSectors].sort((a,b)=>b.stdev-a.stdev);horizontalBars($('sectorChart'),sorted.map(x=>({label:x.sector,value:x.stdev*100})))}}

document.addEventListener('DOMContentLoaded',async()=>{
  try{await renderStaticResearch()}catch(e){console.error(e);toast('Research visuals could not load.');}
  try{await loadMarket()}catch(e){console.error(e);$('feedBadge').textContent='ERROR';$('feedNote').textContent='Market data could not be loaded.';}
  document.querySelectorAll('.range-btn').forEach(btn=>btn.addEventListener('click',async()=>{document.querySelectorAll('.range-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');currentRange=btn.dataset.range;await loadMarket(currentRange,true)}));
  $('refreshBtn').addEventListener('click',()=>loadMarket(currentRange,true));
  let timer;window.addEventListener('resize',()=>{clearTimeout(timer);timer=setTimeout(redraw,120)});
});
