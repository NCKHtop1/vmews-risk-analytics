(function(){'use strict';
const $=id=>document.getElementById(id);
const BASE=document.documentElement.dataset.hosting==='pages'?new URL('market/',location.href).href:'https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/';
const ACCESS_HASH='0a0667865bc17f9d624bcf11088057bbab46336e7dae65f3d5366f4f7a18333e';
const state={data:null,unlocked:sessionStorage.getItem('finquery-technical-access')==='1',filter:'all',search:'',loading:false};
const fmt=(v,d=2)=>Number.isFinite(Number(v))?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:d}).format(Number(v)):'—';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time=s=>s&&Number.isFinite(Date.parse(s))?new Date(s).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'short'}):'—';
async function digest(text){const buf=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));return[...new Uint8Array(buf)].map(b=>b.toString(16).padStart(2,'0')).join('');}
async function fetchData(){const r=await fetch(BASE+'technical-signals.json?v='+Math.floor(Date.now()/60000),{cache:'no-cache',signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('HTTP '+r.status);const data=await r.json();if(!data?.symbols||!Array.isArray(data.matches))throw Error('Invalid scanner data');return data;}
function showGate(){
 const gate=$('technical-scanner-gate'),work=$('technical-scanner-workspace');
 if(gate){gate.hidden=state.unlocked;gate.style.display=state.unlocked?'none':'';}
 if(work){work.hidden=!state.unlocked;work.style.display=state.unlocked?'block':'none';}
}
function signalIds(row){return new Set((row.signals||[]).map(x=>x.id));}
function matchesFilter(row){
 if(state.filter==='all')return true;
 const ids=signalIds(row);
 if(state.filter==='volume')return ids.has('volume_spike')||ids.has('volume_elevated');
 return ids.has(state.filter);
}
function biasLabel(v){return v==='bullish'?'Nghiêng tăng':v==='bearish'?'Nghiêng giảm':v==='mixed'?'Hỗn hợp':'Theo dõi';}
function signalHTML(row){return(row.signals||[]).map(s=>'<span class="tech-tag tech-'+esc(s.direction)+'">'+esc(s.label)+'</span>').join('');}
function rows(){
 const q=state.search.trim().toUpperCase();
 return(state.data?.matches||[]).filter(matchesFilter).filter(row=>!q||row.symbol.includes(q)).sort((a,b)=>(b.priority||0)-(a.priority||0)||a.symbol.localeCompare(b.symbol));
}
function renderSummary(){
 const data=state.data;if(!data)return;
 const all=data.matches||[],count=id=>all.filter(r=>signalIds(r).has(id)).length;
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
 $('technical-scanner-status').textContent='Cập nhật '+time(state.data.checkedAt)+' · nguồn giá '+time(state.data.sourceTime)+' · '+fmt(state.data.coverage,0)+'/'+fmt(state.data.universe,0)+' mã đủ dữ liệu · '+list.length+' mã theo bộ lọc.';
 const body=$('technical-scanner-rows');
 body.innerHTML=list.map(row=>'<tr data-tech-symbol="'+esc(row.symbol)+'"><td><button type="button" class="tech-symbol" data-tech-open="'+esc(row.symbol)+'">'+esc(row.symbol)+'</button></td><td><span class="tech-bias '+esc(row.bias)+'">'+biasLabel(row.bias)+'</span><small>Ưu tiên '+fmt(row.priority,0)+'/100</small></td><td>'+fmt(row.price,0)+'<small>'+(Number(row.changePct)>=0?'+':'')+fmt(row.changePct)+'%</small></td><td>'+fmt(row.macd,2)+'<small>Signal '+fmt(row.macdSignal,2)+'</small></td><td>'+fmt(row.macdHistogram,2)+'<small>'+fmt(row.macdSpreadPct,3)+'% giá</small></td><td>'+fmt(row.rsi14,1)+'</td><td>'+fmt(row.volumeRatio20,2)+'x<small>'+fmt(row.volume,0)+' cp</small></td><td><div class="tech-tags">'+signalHTML(row)+'</div></td><td>'+time(row.sourceTime)+'</td></tr>').join('')||'<tr><td colspan="9"><div class="tech-empty">Không có mã nào khớp bộ lọc ở snapshot hiện tại.</div></td></tr>';
}
async function load(){
 if(!state.unlocked||state.loading)return;state.loading=true;
 try{$('technical-scanner-status').textContent='Đang tải scanner VN100…';state.data=await fetchData();render();}
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
$('technical-scanner-refresh')?.addEventListener('click',load);
$('technical-scanner-rows')?.addEventListener('click',e=>{const b=e.target.closest('[data-tech-open]');if(!b)return;const symbol=b.dataset.techOpen,ticker=$('ticker');if(ticker)ticker.value=symbol;$('company-form')?.requestSubmit();document.querySelector('[data-market-view="price"]')?.click();document.getElementById('market')?.scrollIntoView({behavior:'smooth',block:'start'});});
showGate();
if(state.unlocked)setTimeout(load,0);
setInterval(()=>{if(state.unlocked&&!document.hidden)load();},60000);
document.addEventListener('visibilitychange',()=>{if(state.unlocked&&!document.hidden)load();});
window.FinTechnicalScanner={open,refresh:load,context(){return state.unlocked&&state.data?{checkedAt:state.data.checkedAt,sourceTime:state.data.sourceTime,rules:state.data.rules,matches:(state.data.matches||[]).slice(0,30)}:null;}};
})();