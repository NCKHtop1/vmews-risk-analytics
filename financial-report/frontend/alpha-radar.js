(function(){'use strict';
/* Alpha Radar is a consumer of masked, backend-generated events ONLY. */
const root=document.getElementById('alpha-radar-panel');if(!root)return;
const SOURCE='https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/alpha-radar.json';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtDate=s=>Number.isFinite(Date.parse(s||''))?new Date(s).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'—';
const fresh=s=>{const t=Date.parse(s||'');return Number.isFinite(t)&&t<=Date.now()+300000&&t>0;};
const state={data:null,loading:false,failed:false,notify:false,seen:new Set()};
function valid(d){
 return !!(d&&d.schemaVersion===1&&d.status==='verified'&&d.privateRulesIncluded===false&&
  Array.isArray(d.alerts)&&fresh(d.sourceTime)&&['HOSE_CORE_LIQUID'].includes(d.scope));
}
function render(){
 const status=$('alpha-radar-status'),board=$('alpha-radar-list');if(!status||!board)return;
 if(!state.data){
  status.textContent=state.failed?'Nguồn Alpha riêng tư chưa được cấu hình hoặc chưa có dữ liệu phiên hợp lệ.':'Đang kiểm tra phiên quét Alpha...';
  board.innerHTML='<p class="alpha-empty">Khi backend có dữ liệu được xác minh, hệ thống sẽ hiển thị các mã đang tiệm cận hoặc đã khớp Alpha mà không lộ công thức.</p>';return;
 }
 const d=state.data,age=(Date.now()-Date.parse(d.sourceTime))/60000;
 const stale=age>25&&new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date()).replace(':','')>='0900';
 status.textContent='Quan sát thị trường '+fmtDate(d.sourceTime)+(stale?' · Dữ liệu không còn mới trong phiên':'')+' · '+d.alerts.length+' sự kiện mới';
 const alerts=d.alerts.filter(x=>x&&/^ALPHA[_-]\d{2,3}$/.test(x.alphaId)&&/^[A-Z]{3}$/.test(x.symbol)&&['confirmed','preparing'].includes(x.stage)&&fresh(x.sourceTime)&&typeof x.id==='string').slice(0,100);
 board.innerHTML=alerts.map(x=>'<article class="alpha-signal-row"><div><strong>'+esc(x.alphaId)+'</strong><span>'+esc(x.symbol)+'</span></div><div><b class="'+(x.stage==='confirmed'?'confirmed':'preparing')+'">'+(x.stage==='confirmed'?'Đã xác nhận':'Tiệm cận điều kiện')+'</b><small>'+esc(fmtDate(x.sourceTime))+'</small></div></article>').join('')||
 '<p class="alpha-empty">Không có tín hiệu Alpha mới tại thời điểm nguồn hiện tại.</p>';
}
function notify(data){
 if(!state.notify||!('Notification'in window)||Notification.permission!=='granted')return;
 for(const x of data.alerts||[]){
  if(x.stage!=='confirmed'||state.seen.has(x.id))continue;
  try{new Notification('FinQuery · '+x.alphaId,{body:x.symbol+' vừa được backend xác nhận lúc '+fmtDate(x.sourceTime)});}catch{}
  state.seen.add(x.id);
 }
 try{localStorage.setItem('finquery-alpha-seen-v1',JSON.stringify([...state.seen].slice(-100)));}catch{}
}
async function load(){
 if(state.loading)return;state.loading=true;
 try{
  const r=await fetch(SOURCE+'?v='+Math.floor(Date.now()/300000),{cache:'no-store',signal:AbortSignal.timeout(10000)});
  if(!r.ok)throw Error('Alpha feed not yet configured');
  const d=await r.json();if(!valid(d))throw Error('Invalid masked Alpha feed');
  const old=Date.parse(state.data?.sourceTime||'')||0,next=Date.parse(d.sourceTime)||0;
  if(!state.data||next>old){state.data=d;state.failed=false;notify(d);}
 }catch{state.failed=true;}finally{state.loading=false;render();}
}
try{const prior=JSON.parse(localStorage.getItem('finquery-alpha-seen-v1')||'[]');if(Array.isArray(prior))state.seen=new Set(prior.slice(-100).filter(s=>typeof s==='string'));}catch{}
$('alpha-radar-refresh')?.addEventListener('click',load);
$('alpha-radar-notifications')?.addEventListener('click',async()=>{
 if(!('Notification'in window)){$('alpha-radar-status').textContent='Trình duyệt chưa hỗ trợ thông báo.';return;}
 const p=await Notification.requestPermission();
 state.notify=p==='granted';
 $('alpha-radar-notifications').textContent=state.notify?'Thông báo khi đang mở: bật':'Bật thông báo';
});
window.FinAlphaRadar={refresh:load,setData:data=>{state.data=data;state.failed=false;render();},_test:{valid}};
render();load();
setInterval(()=>{if(!document.hidden)load();},300000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
})();