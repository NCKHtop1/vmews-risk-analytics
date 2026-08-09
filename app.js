const $ = (id) => document.getElementById(id);
const fmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
let currentRange = '5y';
let latestPayload = null;

const RESEARCH = {
  classifier_auc: [
    { model: 'ANFIS', auc: 0.970 },
    { model: 'Multilayer Perceptron', auc: 0.922 },
    { model: 'Logistic Regression', auc: 0.883 },
    { model: 'Simple Logistic', auc: 0.880 }
  ],
  stress_test: [
    { days_ahead: 20, accuracy: 0.95 },
    { days_ahead: 61, accuracy: 0.92 },
    { days_ahead: 122, accuracy: 0.88 },
    { days_ahead: 245, accuracy: 0.83 }
  ]
};

const SECTORS = [
  {sector:'Banking',mean:0.000949,stdev:0.044039,skewness:-0.246833},
  {sector:'Real Estate',mean:-0.000282,stdev:0.041610,skewness:-0.632678},
  {sector:'Information Technology',mean:0.001628,stdev:0.063230,skewness:8.538121},
  {sector:'Oil and Gas',mean:0.001113,stdev:0.038877,skewness:1.249546},
  {sector:'Financial Services',mean:-0.000553,stdev:0.0460779,skewness:-0.036501},
  {sector:'Industrial Services',mean:0.000696,stdev:0.039215,skewness:-0.479662},
  {sector:'Chemicals',mean:-0.000763,stdev:0.043455,skewness:-1.091906},
  {sector:'Minerals',mean:0.001188,stdev:0.047219,skewness:-0.183827},
  {sector:'Food and Beverage',mean:0.001389,stdev:0.037246,skewness:-0.095582},
  {sector:'Building Materials',mean:0.000924,stdev:0.043128,skewness:-0.279964}
];

// Emergency-only fallback. The live path is /api and is powered by Vnstock v4 + KBS.
// This snapshot is deliberately labelled FALLBACK so it can never be confused with live data.
const FALLBACK_ROWS = [
  ['2026-06-29',1854.97],['2026-06-30',1860.01],['2026-07-01',1867.21],['2026-07-02',1866.35],
  ['2026-07-03',1862.08],['2026-07-06',1843.50],['2026-07-07',1848.25],['2026-07-08',1853.70],
  ['2026-07-09',1840.70],['2026-07-10',1828.34],['2026-07-13',1800.54],['2026-07-14',1806.63],
  ['2026-07-15',1782.12],['2026-07-16',1804.24],['2026-07-17',1787.45],['2026-07-20',1743.51],
  ['2026-07-21',1730.56],['2026-07-22',1668.53],['2026-07-23',1699.38],['2026-07-24',1686.11],
  ['2026-07-27',1669.01],['2026-07-28',1680.62]
].map(([date,close]) => ({date,open:close,high:close,low:close,close,volume:0}));

const clamp = (x, a=0, b=1) => Math.max(a, Math.min(b, x));
const mean = a => a.length ? a.reduce((s,x)=>s+x,0)/a.length : 0;
const sd = a => {
  if(a.length < 2) return 0;
  const m = mean(a);
  return Math.sqrt(a.reduce((s,x)=>s+(x-m)**2,0)/(a.length-1));
};
const pct = x => `${(x*100).toFixed(2)}%`;

function returns(rows){
  const out=[];
  for(let i=1;i<rows.length;i++){
    const a=rows[i-1].close,b=rows[i].close;
    out.push(a>0&&b>0?Math.log(b/a):0);
  }
  return out;
}
function rollingVol(rows,w=20){ return sd(returns(rows).slice(-w))*Math.sqrt(252); }
function drawdown(rows,w=60){
  const x=rows.slice(-w).map(r=>r.close).filter(v=>v>0);
  if(!x.length) return 0;
  const p=Math.max(...x), l=x.at(-1);
  return p ? l/p-1 : 0;
}
function momentum(rows,w=20){
  const x=rows.slice(-(w+1));
  return x.length>=2 ? x.at(-1).close/x[0].close-1 : 0;
}
function percentileRank(v,h){
  const x=h.filter(Number.isFinite);
  return x.length ? x.filter(a=>a<=v).length/x.length : .5;
}
function volPercentile(rows){
  if(rows.length<30) return .5;
  const vs=[];
  for(let i=21;i<=rows.length;i++) vs.push(rollingVol(rows.slice(0,i),20));
  return percentileRank(vs.at(-1),vs.slice(-252));
}
function anomaly(rows){
  const r=returns(rows);
  if(r.length<21) return {z:0,score:0};
  const h=r.slice(-21,-1), last=r.at(-1), s=sd(h), m=mean(h), z=s?Math.abs((last-m)/s):0;
  return {z,score:clamp(z/4)};
}
function riskForSlice(rows){
  const vol=rollingVol(rows), volP=volPercentile(rows), dd=drawdown(rows), mom=momentum(rows), an=anomaly(rows);
  const vp=clamp((volP-.35)/.65), dp=clamp(Math.abs(Math.min(dd,0))/.20), mp=clamp(Math.abs(Math.min(mom,0))/.15), ap=an.score;
  return {
    score:100*(.35*vp+.25*dp+.20*mp+.20*ap),vol,dd,mom,anomaly:an.z,
    drivers:{volPressure:vp,ddPressure:dp,momPressure:mp,anomalyPressure:ap}
  };
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
  const m=new Map();
  for(const q of rows||[]){
    const date=String(q.date||q.time||'').slice(0,10), close=Number(q.close);
    if(!date||!Number.isFinite(close)||close<=0) continue;
    m.set(date,{date,open:Number(q.open)||close,high:Number(q.high)||close,low:Number(q.low)||close,close,volume:Number(q.volume)||0});
  }
  return [...m.values()].sort((a,b)=>a.date.localeCompare(b.date));
}

async function fetchMarket(range=currentRange){
  try{
    const r=await fetch(`/api?range=${encodeURIComponent(range)}&_=${Date.now()}`,{cache:'no-store'});
    const payload=await r.json();
    if(!r.ok) throw new Error(payload?.message||`API ${r.status}`);
    const rows=cleanRows(payload.rows);
    if(rows.length<10) throw new Error('Vnstock returned too few VNINDEX rows');
    return {...payload,rows,isFallback:false};
  }catch(err){
    console.error('Vnstock live API unavailable:',err);
    return {
      source:'Emergency static snapshot',provider:'fallback',asOf:FALLBACK_ROWS.at(-1).date,
      rows:FALLBACK_ROWS,isFallback:true,error:String(err?.message||err)
    };
  }
}

function setupCanvas(c){
  if(!c) return null;
  const r=c.getBoundingClientRect(),d=Math.max(1,Math.min(2,devicePixelRatio||1));
  const w=Math.max(220,Math.floor(r.width||c.parentElement?.clientWidth||600));
  const h=Math.max(120,Math.floor(r.height||c.parentElement?.clientHeight||300));
  c.width=w*d;c.height=h*d;
  const ctx=c.getContext('2d');ctx.setTransform(d,0,0,d,0,0);
  return{ctx,w,h};
}
function lineChart(c,pts,o={}){
  const sc=setupCanvas(c);if(!sc||!pts.length)return;
  const{ctx,w,h}=sc;ctx.clearRect(0,0,w,h);
  const p={l:10,r:50,t:10,b:26},vals=pts.map(x=>x.y).filter(Number.isFinite);
  let min=Math.min(...vals),max=Math.max(...vals);if(min===max){min--;max++}const e=(max-min)*.06;min-=e;max+=e;
  const X=i=>p.l+(w-p.l-p.r)*(i/Math.max(1,pts.length-1)),Y=v=>p.t+(h-p.t-p.b)*(1-(v-min)/(max-min));
  ctx.font='10px ui-monospace,Consolas,monospace';ctx.fillStyle='#6f879f';ctx.strokeStyle='#14283b';ctx.lineWidth=1;
  for(let i=0;i<4;i++){const y=p.t+(h-p.t-p.b)*i/3;ctx.beginPath();ctx.moveTo(p.l,y);ctx.lineTo(w-p.r,y);ctx.stroke();ctx.fillText(fmt.format(max-(max-min)*i/3),w-p.r+7,y+3)}
  if(o.fill){const g=ctx.createLinearGradient(0,p.t,0,h-p.b);g.addColorStop(0,'rgba(71,215,255,.18)');g.addColorStop(1,'rgba(71,215,255,0)');ctx.beginPath();pts.forEach((q,i)=>i?ctx.lineTo(X(i),Y(q.y)):ctx.moveTo(X(i),Y(q.y)));ctx.lineTo(X(pts.length-1),h-p.b);ctx.lineTo(X(0),h-p.b);ctx.closePath();ctx.fillStyle=g;ctx.fill()}
  ctx.beginPath();pts.forEach((q,i)=>i?ctx.lineTo(X(i),Y(q.y)):ctx.moveTo(X(i),Y(q.y)));ctx.strokeStyle=o.color||'#47d7ff';ctx.lineWidth=1.7;ctx.stroke();
  if(o.stress)for(const s of o.stress){if(!s||s.i<0||s.i>=pts.length)continue;ctx.beginPath();ctx.arc(X(s.i),Y(pts[s.i].y),3.2,0,Math.PI*2);ctx.fillStyle='#ffca63';ctx.fill()}
  const ticks=Math.min(6,pts.length);ctx.fillStyle='#677f98';for(let t=0;t<ticks;t++){const i=Math.round((pts.length-1)*t/Math.max(1,ticks-1));ctx.fillText(pts[i].x,X(i)-25,h-7)}
}
function miniLine(c,pts){
  const sc=setupCanvas(c);if(!sc||pts.length<2)return;const{ctx,w,h}=sc;ctx.clearRect(0,0,w,h);
  const vals=pts.map(p=>p.y),min=Math.min(...vals),max=Math.max(...vals),rng=max-min||1,X=i=>w*i/(pts.length-1),Y=v=>8+(h-16)*(1-(v-min)/rng);
  ctx.beginPath();pts.forEach((p,i)=>i?ctx.lineTo(X(i),Y(p.y)):ctx.moveTo(X(i),Y(p.y)));ctx.strokeStyle='#47d7ff';ctx.lineWidth=1.5;ctx.stroke();
}
function horizontalBars(c,items){
  const sc=setupCanvas(c);if(!sc||!items.length)return;const{ctx,w,h}=sc;ctx.clearRect(0,0,w,h);
  const max=Math.max(...items.map(x=>x.value))*1.08,left=Math.min(160,w*.38),right=40,top=12,row=(h-24)/items.length;ctx.font='10px system-ui';
  items.forEach((it,i)=>{const y=top+i*row+row*.18,bh=row*.55,bw=(w-left-right)*(it.value/max);ctx.fillStyle='#8298ad';ctx.fillText(it.label,6,y+bh*.75);ctx.fillStyle=i===0?'rgba(255,202,99,.78)':'rgba(71,215,255,.58)';ctx.fillRect(left,y,bw,bh);ctx.fillStyle='#9bb1c5';ctx.fillText(`${it.value.toFixed(2)}%`,left+bw+7,y+bh*.75)});
}
function sliceForDisplay(rows,r){
  if(r==='1y')return rows.slice(-260);
  if(r==='5y')return rows.slice(-1260);
  if(rows.length>1800){const step=Math.ceil(rows.length/1600);return rows.filter((_,i)=>i%step===0||i===rows.length-1)}
  return rows;
}
function renderMarketCharts(rows,r){
  const d=sliceForDisplay(rows,r),pts=d.map(x=>({x:x.date,y:x.close})),stress=[];
  const start=Math.max(25,d.length-360);
  for(let i=start;i<d.length;i++){
    if(i<d.length-80&&i%5!==0)continue;
    const rr=riskForSlice(d.slice(0,i+1));if(rr.score>=65)stress.push({i});
  }
  lineChart($('marketChart'),pts,{fill:true,stress});miniLine($('miniChart'),pts.slice(-80));
}
function setDelta(el,c){if(!el)return;el.textContent=`${c>=0?'+':''}${c.toFixed(2)}%`;el.classList.remove('pos','neg','neutral-text');el.classList.add(c>0?'pos':c<0?'neg':'neutral-text')}
function renderKPIs(p){
  const rows=p.rows,last=rows.at(-1),prev=rows.at(-2)||last,change=(last.close/prev.close-1)*100,r=riskForSlice(rows),s=stateForScore(r.score),price=fmt.format(last.close);
  $('heroPrice').textContent=price;$('kpiPrice').textContent=price;setDelta($('heroChange'),change);
  $('kpiChange').textContent=`${change>=0?'+':''}${change.toFixed(2)}%`;$('kpiChange').className=`chip ${change>=0?'ok':'danger'}`;
  $('heroRisk').textContent=r.score.toFixed(0);$('kpiRisk').textContent=r.score.toFixed(0);$('kpiRiskState').textContent=s.label;$('kpiRiskState').className=`chip ${s.cls}`;
  $('heroVol').textContent=pct(r.vol);$('kpiVol').textContent=pct(r.vol);$('heroDD').textContent=pct(r.dd);$('heroDate').textContent=last.date;$('kpiAnomaly').textContent=`${r.anomaly.toFixed(2)}σ`;
  $('gaugeValue').textContent=r.score.toFixed(0);$('riskState').textContent=`${s.label} RISK`;$('riskLight').className=`risk-light ${s.light}`;$('riskGauge').style.setProperty('--score',`${r.score*3.6}deg`);
  const vals=[r.drivers.volPressure,r.drivers.ddPressure,r.drivers.momPressure,r.drivers.anomalyPressure];[...$('driverList').querySelectorAll('b')].forEach((e,i)=>e.textContent=`${Math.round(vals[i]*100)}/100`);
  const badge=$('feedBadge');badge.textContent=p.isFallback?'FALLBACK':'VNSTOCK LIVE';badge.className=`status-badge ${p.isFallback?'fallback':'live'}`;
  $('feedNote').textContent=p.isFallback
    ? `Vnstock API unavailable. Emergency snapshot through ${last.date}. ${p.error||''}`
    : `${p.source||'Vnstock v4'} · ${p.provider||'KBS'} · latest available session ${last.date}`;
  $('footerFreshness').textContent=`Data freshness: ${last.date} · ${p.isFallback?'fallback':'Vnstock/KBS'}`;
  document.querySelectorAll('.trust-strip div:nth-child(2) span').forEach(el=>el.textContent='Vnstock v4 · KBS · VNINDEX');
}
function renderAlertRows(rows){
  const b=$('alertRows');b.innerHTML='';
  for(let i=rows.length-1;i>=Math.max(1,rows.length-8);i--){
    const r=riskForSlice(rows.slice(0,i+1)),s=stateForScore(r.score),prev=rows[i-1]||rows[i],ret=rows[i].close/prev.close-1,tr=document.createElement('tr');
    tr.innerHTML=`<td>${rows[i].date}</td><td>${fmt.format(rows[i].close)}</td><td class="${ret>=0?'pos':'neg'}">${ret>=0?'+':''}${pct(ret)}</td><td>${r.score.toFixed(0)}</td><td><span class="chip ${s.cls}">${s.label}</span></td><td>${compactReason(r)}</td>`;b.appendChild(tr);
  }
}
function renderResearch(){
  $('aucBars').innerHTML=RESEARCH.classifier_auc.map(x=>`<div class="bar-row"><span>${x.model}</span><div class="bar-track"><div class="bar-fill" style="width:${x.auc*100}%"></div></div><b>${x.auc.toFixed(3)}</b></div>`).join('');
  lineChart($('stressChart'),RESEARCH.stress_test.map(x=>({x:`${x.days_ahead}d`,y:x.accuracy*100})),{fill:true});
  const sorted=[...SECTORS].sort((a,b)=>b.stdev-a.stdev);horizontalBars($('sectorChart'),sorted.map(x=>({label:x.sector,value:x.stdev*100})));
  $('sectorRows').innerHTML=SECTORS.map(x=>`<tr><td>${x.sector}</td><td>${x.mean.toFixed(6)}</td><td>${x.stdev.toFixed(6)}</td><td>${x.skewness.toFixed(6)}</td></tr>`).join('');
}
async function loadMarket(r=currentRange,notify=false){
  if(notify)toast('Refreshing VNINDEX from Vnstock…');
  const p=await fetchMarket(r);latestPayload=p;renderKPIs(p);renderMarketCharts(p.rows,r);renderAlertRows(p.rows);
  if(notify)toast(p.isFallback?'Vnstock unavailable — fallback shown.':'Vnstock data refreshed.');
}
function toast(m){const e=$('toast');e.textContent=m;e.classList.add('show');clearTimeout(window.__toast);window.__toast=setTimeout(()=>e.classList.remove('show'),2400)}
function redraw(){if(latestPayload)renderMarketCharts(latestPayload.rows,currentRange);renderResearch()}

document.addEventListener('DOMContentLoaded',async()=>{
  renderResearch();
  try{await loadMarket();}catch(e){console.error(e);$('feedBadge').textContent='ERROR';$('feedNote').textContent='Unable to initialise market monitor.'}
  document.querySelectorAll('.range-btn').forEach(btn=>btn.addEventListener('click',async()=>{
    document.querySelectorAll('.range-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');currentRange=btn.dataset.range;await loadMarket(currentRange,true);
  }));
  $('refreshBtn')?.addEventListener('click',()=>loadMarket(currentRange,true));
  let timer;addEventListener('resize',()=>{clearTimeout(timer);timer=setTimeout(redraw,130)});
});
