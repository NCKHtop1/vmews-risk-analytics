(function(){'use strict';
const $=id=>document.getElementById(id);
const BASE=document.documentElement.dataset.hosting==='pages'?new URL('market/',location.href).href:'https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/';
const ACCESS_HASH='0a0667865bc17f9d624bcf11088057bbab46336e7dae65f3d5366f4f7a18333e';
const state={data:null,evidence:null,evidenceLoadedAt:0,unlocked:sessionStorage.getItem('finquery-technical-access')==='1',filter:'all',universeFilter:'all',search:'',loading:false,marketSourceTime:null,retryTimer:null};
const fmt=(v,d=2)=>Number.isFinite(Number(v))?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:d}).format(Number(v)):'—';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time=s=>s&&Number.isFinite(Date.parse(s))?new Date(s).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'short'}):'—';
async function digest(text){const buf=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));return[...new Uint8Array(buf)].map(b=>b.toString(16).padStart(2,'0')).join('');}
async function fetchData(){const bundle=window.FinMarketData.currentBundle?.(),bundled=bundle?.scanner,bundleAligned=bundled&&(!state.marketSourceTime||String(bundled.sourceTime||'')===String(state.marketSourceTime));const scannerPromise=bundleAligned?Promise.resolve(bundled):window.FinMarketData.get('technical-signals.json');const evidenceFresh=state.evidence&&Date.now()-state.evidenceLoadedAt<3600000;const evidencePromise=evidenceFresh?Promise.resolve(state.evidence):window.FinMarketData.get('technical-evidence.json');const [scanner,evidence]=await Promise.allSettled([scannerPromise,evidencePromise]);const data=scanner.status==='fulfilled'?scanner.value:null;if(!data?.symbols||!Array.isArray(data.matches))throw Error('Invalid scanner data');if(evidence.status==='fulfilled'){state.evidence=evidence.value;state.evidenceLoadedAt=Date.now();}return data;}
function showGate(){
 const gate=$('technical-scanner-gate'),work=$('technical-scanner-workspace');
 if(gate){gate.hidden=state.unlocked;gate.style.display=state.unlocked?'none':'';}
 if(work){work.hidden=!state.unlocked;work.style.display=state.unlocked?'block':'none';}
}
function signalIds(row){return new Set((row.signals||[]).map(x=>x.id));}
function matchesUniverse(row){return state.universeFilter==='all'||String(row.tier||'CORE').toUpperCase()===state.universeFilter;}
function sourceLabel(row){return row.cadence==='EOD'?'EOD '+esc(row.barDate||'—'):time(row.sourceTime);}
function matchesFilter(row){
 if(state.filter==='all')return true;
 const ids=signalIds(row);
 if(state.filter==='volume')return ids.has('volume_spike')||ids.has('volume_elevated');
 return ids.has(state.filter);
}
function biasLabel(v){return v==='bullish'?'Nghiêng tăng':v==='bearish'?'Nghiêng giảm':v==='mixed'?'Hỗn hợp':'Theo dõi';}
function evidenceFor(row){const source=state.evidence?.signals||{},ids=(row.signals||[]).map(x=>x.id),candidates=ids.map(id=>source[id]).filter(Boolean);if(!candidates.length)return null;return candidates.sort((a,b)=>{const ad=Number.isFinite(Number(a?.horizons?.['3']?.directionalHitRate))?1:0,bd=Number.isFinite(Number(b?.horizons?.['3']?.directionalHitRate))?1:0;return bd-ad||(b.sample||0)-(a.sample||0);})[0];}
function evidenceHTML(row){const e=evidenceFor(row),h=e?.horizons?.['3']||e?.horizons?.[3];if(!e||!h)return '<span class="tech-priority-help">Điểm rule heuristic · không phải xác suất</span>';const hit=Number(h.directionalHitRate),lift=Number(h.liftVsBaseline),n=Number(h.n||e.sample||0);return '<span class="tech-priority-help">Điểm rule heuristic · không phải xác suất</span><span class="tech-evidence"><strong>EOD proxy T+3</strong> · n='+fmt(n,0)+(Number.isFinite(hit)?' · hit '+fmt(hit*100,1)+'%':'')+(Number.isFinite(lift)?' · lift '+(lift>=0?'+':'')+fmt(lift*100,1)+'đ%':'')+'</span>';}
function signalHTML(row){return(row.signals||[]).map(s=>'<span class="tech-tag tech-'+esc(s.direction)+'">'+esc(s.label)+'</span>').join('');}
function symbolHTML(row){return row.tier==='DISCOVERY'?'<span class="tech-symbol tech-symbol-static">'+esc(row.symbol)+'</span>':'<button type="button" class="tech-symbol" data-tech-open="'+esc(row.symbol)+'">'+esc(row.symbol)+'</button>';}
function rows(){
 const q=state.search.trim().toUpperCase();
 return(state.data?.matches||[]).filter(matchesUniverse).filter(matchesFilter).filter(row=>!q||row.symbol.includes(q)).sort((a,b)=>(b.priority||0)-(a.priority||0)||a.symbol.localeCompare(b.symbol));
}
function renderSummary(){
 const data=state.data;if(!data)return;
 const all=(data.matches||[]).filter(matchesUniverse),count=id=>all.filter(r=>signalIds(r).has(id)).length;
 $('technical-scanner-summary').innerHTML=[
  ['Mã khớp rule',all.length],['MACD cắt ↑',count('macd_cross_up')],['MACD cắt ↓',count('macd_cross_down')],
  ['Sắp cắt ↑',count('macd_near_up')],['Sắp cắt ↓',count('macd_near_down')],
  ['RSI ≤ 30',count('rsi_oversold')],['RSI ≥ 70',count('rsi_overbought')],['Volume ≥ 1,5x',count('volume_spike')]
 ].map(x=>'<div><span>'+esc(x[0])+'</span><strong>'+fmt(x[1],0)+'</strong></div>').join('');
}
function render(){
 if(!state.data)return;
 renderSummary();
 const list=rows();
 const aligned=!state.marketSourceTime||String(state.marketSourceTime)===String(state.data.sourceTime),live=Number(state.data.liveCoverage||0),liveUniverse=Number(state.data.liveUniverse||0),discovery=Number(state.data.discoveryCoverage||0);$('technical-scanner-status').textContent='Cập nhật '+time(state.data.checkedAt)+' · Trong phiên '+fmt(live,0)+'/'+fmt(liveUniverse,0)+' · Discovery EOD '+fmt(discovery,0)+' · tổng '+fmt(state.data.coverage,0)+'/'+fmt(state.data.universe,0)+' mã đủ dữ liệu · '+list.length+' mã theo bộ lọc.'+(aligned?'':' · ⚠ Scanner live chưa đồng bộ với giá mới nhất; tín hiệu live chỉ dùng để tham khảo.');
 const body=$('technical-scanner-rows');
 body.innerHTML=list.map(row=>'<tr data-tech-symbol="'+esc(row.symbol)+'"><td>'+symbolHTML(row)+'<small class="universe-tier universe-tier-'+esc(String(row.tier||'CORE').toLowerCase())+'">'+esc(row.tier||'CORE')+' · '+esc(row.cadence==='EOD'?'EOD':'TRONG PHIÊN')+'</small></td><td><span class="tech-bias '+esc(row.bias)+'">'+biasLabel(row.bias)+'</span><small>Rule priority '+fmt(row.priority,0)+'/100</small>'+evidenceHTML(row)+'</td><td>'+fmt(row.price,0)+'<small>'+(Number(row.changePct)>=0?'+':'')+fmt(row.changePct)+'%</small></td><td>'+fmt(row.macd,2)+'<small>Signal '+fmt(row.macdSignal,2)+'</small></td><td>'+fmt(row.macdHistogram,2)+'<small>'+fmt(row.macdSpreadPct,3)+'% giá</small></td><td>'+fmt(row.rsi14,1)+'</td><td>'+fmt(row.volumeRatio20,2)+'x<small>'+fmt(row.volume,0)+' cp</small></td><td><div class="tech-tags">'+signalHTML(row)+'</div></td><td>'+sourceLabel(row)+'</td></tr>').join('')||'<tr><td colspan="9"><div class="tech-empty">Không có mã nào khớp bộ lọc ở snapshot hiện tại.</div></td></tr>';
}
async function load(){
 if(!state.unlocked||state.loading)return;state.loading=true;
 try{
  $('technical-scanner-status').textContent='Đang tải scanner HOSE…';
  const data=await fetchData(),expected=state.marketSourceTime;
  if(expected&&String(data.sourceTime||'')!==String(expected)){
   if(state.data)render();
   $('technical-scanner-status').textContent=(state.data?'Đang giữ snapshot Scanner gần nhất · ':'')+'Đang đồng bộ với snapshot giá mới nhất…';
   clearTimeout(state.retryTimer);state.retryTimer=setTimeout(()=>{if(Date.parse(data.sourceTime||0)>Date.parse(expected||0))window.FinancialMarket?.refresh?.();load();},1200);
   return;
  }
  state.data=data;render();
 }
 catch(e){$('technical-scanner-status').textContent='Chưa tải được technical scanner. Dữ liệu chart/giá vẫn hoạt động độc lập.';}
 finally{state.loading=false;}
}
async function unlock(code){
 if(await digest(String(code||'').trim())!==ACCESS_HASH){$('technical-scanner-error').textContent='Mã truy cập không đúng.';return false;}
 state.unlocked=true;sessionStorage.setItem('finquery-technical-access','1');$('technical-scanner-error').textContent='';showGate();await load();return true;
}
function open(){showGate();if(state.unlocked)load();}
$('technical-scanner-unlock-form')?.addEventListener('submit',e=>{e.preventDefault();unlock($('technical-scanner-access-code').value);});
$('technical-scanner-filters')?.addEventListener('click',e=>{const b=e.target.closest('[data-tech-filter]');if(!b)return;state.filter=b.dataset.techFilter;document.querySelectorAll('[data-tech-filter]').forEach(x=>x.classList.toggle('active',x===b));render();});
$('technical-scanner-search')?.addEventListener('input',e=>{state.search=e.target.value;render();});
$('technical-scanner-universe')?.addEventListener('change',e=>{state.universeFilter=e.target.value;render();});
$('technical-scanner-refresh')?.addEventListener('click',load);
$('technical-scanner-rows')?.addEventListener('click',e=>{const b=e.target.closest('[data-tech-open]');if(!b)return;const symbol=b.dataset.techOpen,row=state.data?.symbols?.[symbol];if(row?.tier&&row.tier!=='CORE'){const url=new URL('../forecast-final.html',location.href);url.searchParams.set('symbol',symbol);window.open(url.href,'_blank','noopener');return;}const ticker=$('ticker');if(ticker)ticker.value=symbol;$('company-form')?.requestSubmit();document.querySelector('[data-market-view="price"]')?.click();document.getElementById('market')?.scrollIntoView({behavior:'smooth',block:'start'});});
showGate();
if(state.unlocked)setTimeout(load,0);
setInterval(()=>{if(state.unlocked&&!document.hidden)load();},300000);
document.addEventListener('visibilitychange',()=>{if(state.unlocked&&!document.hidden)load();});
window.FinTechnicalScanner={open,refresh:load,setMarketSourceTime(value){const next=value||null,changed=String(next||'')!==String(state.marketSourceTime||'');state.marketSourceTime=next;if(changed)load();else if(state.data)render();},allContext(){return{unlocked:state.unlocked,checkedAt:state.data?.checkedAt||null,sourceTime:state.data?.sourceTime||null,symbols:state.unlocked?(state.data?.symbols||{}):{},evidence:state.evidence||null};},context(){if(!state.unlocked||!state.data)return null;const symbol=String(document.getElementById('ticker')?.value||'').trim().toUpperCase(),selected=state.data.symbols?.[symbol]||null,aligned=selected?.cadence==='EOD'?false:(!state.marketSourceTime||String(state.marketSourceTime)===String(state.data.sourceTime));return{checkedAt:state.data.checkedAt,sourceTime:state.data.sourceTime,rules:state.data.rules,current:aligned?(state.data.symbols?.[symbol]||null):null,retainedCurrent:!aligned?(state.data.symbols?.[symbol]||null):null,evidence:selected?evidenceFor(selected):null,matches:aligned?(state.data.matches||[]).filter(x=>x.cadence!=='EOD').slice(0,30):[],aligned,liveCoverage:state.data.liveCoverage,discoveryCoverage:state.data.discoveryCoverage};}};
})();