(function(){'use strict';
/* Live-session futures quote board. Delayed polling, never pretend to stream ticks. */
const $=id=>document.getElementById(id);
const host=$('money-futures-live');
if(!host)return;
const SOURCE='https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/derivatives-live.json';
const nf=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2});
const fmt=(n,d=2)=>typeof n==='number'&&Number.isFinite(n)?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:d}).format(n):'—';
const esc=t=>String(t??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const validStamp=s=>{const t=Date.parse(s||'');return Number.isFinite(t)&&t>0&&t<=Date.now()+300000?t:null;};
const datetimeVN=s=>validStamp(s)?new Date(s).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'—';
const state={data:null,filter:'all',loading:false,failed:false,seenAt:null};
function marketOpen(now=Date.now()){
 const parts=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh',weekday:'short',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(new Date(now)).map(x=>[x.type,x.value]));
 if(['Sat','Sun'].includes(parts.weekday))return false;
 const min=Number(parts.hour)*60+Number(parts.minute);
 return (min>=525&&min<=690)||(min>=780&&min<=885);
}
function healthy(d){
 if(!d||d.schemaVersion!==1||d.status!=='ok'||d.exchange!=='HNX'||d.type!=='FUTURES_ONLY'||!Array.isArray(d.contracts))return false;
 if(!validStamp(d.collectedAt)||!validStamp(d.latestSourceTime))return false;
 return true;
}
function todayVN(now=Date.now()){
 const parts=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(now)).map(x=>[x.type,x.value]));
 return parts.year+'-'+parts.month+'-'+parts.day;
}
function contracts(d){
 if(!healthy(d))return[];
 return d.contracts.filter(c=>{
  if(!c||!/^VN(30|100)F2\d(0[1-9]|1[0-2])$/.test(c.symbol||''))return false;
  if(!/^20\d\d-\d\d-\d\d$/.test(c.expiry||'')||c.expiry<todayVN())return false;
  if(!/^41I[12][0-9A-HJ-NP-TV-W][1-9ABC]000$/.test(c.providerSymbol||''))return false;
  if((c.underlying!=='VN30'&&c.underlying!=='VN100')||c.market!=='HNX_FUTURES'||c.unit!=='points')return false;
  if(!validStamp(c.sourceTime)||typeof c.price!=='number'||!Number.isFinite(c.price)||c.price<=0||c.price>50000)return false;
  if(typeof c.reference!=='number'||!Number.isFinite(c.reference)||c.reference<=0)return false;
  if(typeof c.volume!=='number'||c.volume<0)return false;
  return true;
 }).sort((a,b)=>a.underlying.localeCompare(b.underlying)||a.expiry.localeCompare(b.expiry)).slice(0,24);
}
function statusFor(c,now=Date.now()){
 const age=(now-validStamp(c.sourceTime))/60000;
 if(marketOpen(now))return age<=10?'Giá trong phiên · có thể trễ':age<=45?'Chưa có khớp mới':'Dữ liệu chậm cập nhật';
 return 'Giá ghi nhận phiên gần nhất';
}
function change(c){
 const diff=typeof c.change==='number'&&Number.isFinite(c.change)?c.change:c.price-c.reference;
 const pct=(c.price/c.reference-1)*100;
 const tone=diff>0?'up':diff<0?'down':'flat';
 return '<span class="derivative-move '+tone+'">'+(diff>0?'+':'')+fmt(diff)+' · '+(pct>0?'+':'')+fmt(pct)+'%</span>';
}
function miniHistory(rows){
 const points=Array.isArray(rows)?rows.filter(p=>validStamp(p?.time)&&Number.isFinite(p?.price)&&p.price>0).slice(-40):[];
 if(points.length<2)return'<span class="derivative-spark-empty">Chưa đủ điểm giá</span>';
 const vals=points.map(p=>p.price),lo=Math.min(...vals),hi=Math.max(...vals),pad=Math.max((hi-lo)*.12,hi*.0005),min=lo-pad,max=hi+pad;
 const xy=(p,i)=>[(i/(points.length-1)*180).toFixed(1),(40-(p.price-min)/(max-min)*36-2).toFixed(1)];
 const path=points.map((p,i)=>(i?'L':'M')+xy(p,i).join(' ')).join(' ');
 return'<svg class="derivative-spark" viewBox="0 0 180 46" role="img" aria-label="Diễn biến giá theo các lần cập nhật từ nguồn"><path d="'+path+'" fill="none" stroke="#396fb6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
}
function render(){
 if(!state.data){host.innerHTML='<div class="derivative-head"><h4>Bảng giá hợp đồng tương lai</h4></div><p class="money-source-pending">'+(state.failed?'Chưa kết nối được nguồn giá phái sinh.':'Đang tải giá hợp đồng tương lai...')+'</p>';return;}
 const list=contracts(state.data),visible=list.filter(c=>state.filter==='all'||c.underlying===state.filter);
 const newest=list.map(x=>validStamp(x.sourceTime)).filter(Boolean).reduce((a,b)=>Math.max(a,b),0);
 const age=newest?(Date.now()-newest)/60000:Infinity;
 const badge=!list.length?'Chưa có hợp đồng':marketOpen()?(age<=10?'Theo dõi trong phiên':age<=45?'Giá chưa đổi':'Giá đang trễ'):'Ngoài giờ giao dịch';
 const actions=[['all','Tất cả'],['VN30','VN30F'],['VN100','VN100F']].map(([key,label])=>'<button type="button" data-futures-underlying="'+key+'" class="'+(state.filter===key?'active':'')+'" aria-pressed="'+(state.filter===key)+'">'+label+'</button>').join('');
 const cards=visible.map(c=>{
  const qty=n=>typeof n==='number'&&Number.isFinite(n)&&n>=0?fmt(n,0):'—';
  const cell=(label,value)=>'<div class="derivative-metric"><small>'+label+'</small><strong>'+value+'</strong></div>';
  return'<article class="derivative-live-contract">'+
   '<div class="derivative-contract-title"><div><strong>'+esc(c.symbol)+'</strong><small>Đáo hạn '+esc(c.expiry?.slice(8,10)+'/'+c.expiry?.slice(5,7)+'/'+c.expiry?.slice(0,4))+'</small></div><span class="derivative-time">'+esc(datetimeVN(c.sourceTime))+'</span></div>'+
   '<div class="derivative-last"><strong>'+fmt(c.price,2)+'</strong><small>điểm</small>'+change(c)+'</div>'+
   '<div class="derivative-spark-wrap">'+miniHistory(c.series)+'</div>'+
   '<div class="derivative-metrics">'+
   cell('Tham chiếu',fmt(c.reference))+
   cell('KLGD',qty(c.volume))+
   cell('OI',qty(c.openInterest))+
   cell('Cao / Thấp',fmt(c.high)+' / '+fmt(c.low))+
   cell('Dư mua 1',fmt(c.bid1)+' · '+qty(c.bidVol1))+
   cell('Dư bán 1',fmt(c.ask1)+' · '+qty(c.askVol1))+
   '</div><p class="derivative-contract-status">'+esc(statusFor(c))+'</p></article>';
 }).join('');
 host.innerHTML='<div class="derivative-head"><div><span class="macro-viz-kicker">HNX FUTURES · KBS</span><h4>Bảng giá hợp đồng tương lai</h4><p>'+esc(badge)+' · Giá gần nhất '+esc(newest?datetimeVN(new Date(newest).toISOString()):'—')+'</p></div><button type="button" class="money-refresh" data-futures-refresh>Làm mới giá</button></div>'+
 '<div class="derivative-filter" role="group" aria-label="Lọc hợp đồng tương lai">'+actions+'</div>'+
 (cards?'<div class="derivative-live-grid">'+cards+'</div>':'<p class="money-source-pending">Chưa có báo giá hợp đồng hợp lệ. Không thay bằng số OI tháng.</p>')+
 '<div class="macro-viz-source"><span>Nguồn KBS · cập nhật theo pipeline giá khoảng 5 phút khi thị trường giao dịch; không phải luồng tick thời gian thực.</span><a href="https://kbbuddywts.kbsec.com.vn/" target="_blank" rel="noopener noreferrer">Nguồn giá ↗</a></div>';
}
async function load(){
 if(state.loading)return;state.loading=true;
 try{
  const resp=await fetch(SOURCE+'?v='+Math.floor(Date.now()/60000),{cache:'no-store',signal:AbortSignal.timeout(10000)});
  if(!resp.ok)throw Error('HTTP '+resp.status);
  const d=await resp.json();
  if(!healthy(d))throw Error('Invalid futures source payload');
  const newer=validStamp(d.latestSourceTime)||0,old=validStamp(state.data?.latestSourceTime)||0;
  if(!state.data||newer>=old){state.data=d;state.failed=false;state.seenAt=Date.now();}
 }catch{state.failed=true;}finally{state.loading=false;render();}
}
host.addEventListener('click',event=>{
 const button=event.target.closest?.('button');
 if(!button)return;
 const key=button.dataset.futuresUnderlying;
 if(['all','VN30','VN100'].includes(key)){state.filter=key;render();return;}
 if(button.hasAttribute('data-futures-refresh'))load();
});
window.FinDerivativeQuotes={refresh:load,setData:data=>{state.data=data;state.failed=false;render();},_test:{healthy,contracts,statusFor,marketOpen,fmt,miniHistory}};
render();load();
setInterval(()=>{if(!document.hidden)load();},60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
})();
