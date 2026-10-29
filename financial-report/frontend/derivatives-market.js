(function(){'use strict';
/* Public HNX futures terminal: point-priced contracts, never synthetic candles. */
const $=id=>document.getElementById(id),host=$('money-futures-live');
if(!host)return;
const SOURCE='https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/derivatives-live.json';
const esc=t=>String(t??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const fmt=(n,d=2)=>typeof n==='number'&&Number.isFinite(n)?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:d}).format(n):'—';
const validStamp=s=>{const v=Date.parse(s||'');return Number.isFinite(v)&&v>0&&v<=Date.now()+300000?v:null;};
const datetimeVN=s=>validStamp(s)?new Date(s).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'—';
function todayVN(now=Date.now()){
 const p=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(now)).map(x=>[x.type,x.value]));
 return p.year+'-'+p.month+'-'+p.day;
}
function marketOpen(now=Date.now()){
 const p=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh',weekday:'short',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(new Date(now)).map(x=>[x.type,x.value]));
 if(['Sat','Sun'].includes(p.weekday))return false;
 const minute=Number(p.hour)*60+Number(p.minute);
 return (minute>=525&&minute<=690)||(minute>=780&&minute<=885);
}
const state={data:null,filter:'all',selected:null,loading:false,failed:false,lastAttempt:0};
function healthy(d){
 return!!(d&&d.schemaVersion===1&&d.status==='ok'&&d.exchange==='HNX'&&d.type==='FUTURES_ONLY'&&
  Array.isArray(d.contracts)&&validStamp(d.collectedAt)&&validStamp(d.latestSourceTime));
}
function contracts(d){
 if(!healthy(d))return[];
 return d.contracts.filter(c=>
  c&&/^VN(30|100)F2\d(0[1-9]|1[0-2])$/.test(c.symbol||'')&&
  /^41I[12][0-9A-HJ-NP-TV-W][1-9ABC]000$/.test(c.providerSymbol||'')&&
  ['VN30','VN100'].includes(c.underlying)&&c.market==='HNX_FUTURES'&&c.unit==='points'&&
  /^\d{4}-\d\d-\d\d$/.test(c.expiry||'')&&c.expiry>=todayVN()&&
  validStamp(c.sourceTime)&&Number.isFinite(c.price)&&c.price>0&&c.price<=50000&&
  Number.isFinite(c.reference)&&c.reference>0&&Number.isFinite(c.volume)&&c.volume>=0
 ).sort((a,b)=>(a.underlying==='VN30'?0:1)-(b.underlying==='VN30'?0:1)||a.expiry.localeCompare(b.expiry)).slice(0,24);
}
function withAliases(list){
 const counts={VN30:0,VN100:0};
 return list.map(c=>{let ix=counts[c.underlying]++;return {...c,alias:c.underlying+'F'+(['1M','2M','1Q','2Q'][ix]||('T'+(ix+1))) };});
}
function statusFor(c,now=Date.now()){
 const source=validStamp(c.sourceTime);const age=source?(now-source)/60000:Infinity;
 if(marketOpen(now))return age<=10?'Trong phiên':age<=45?'Chưa có khớp mới':'Dữ liệu chậm cập nhật';
 return 'Giá ghi nhận phiên gần nhất';
}
function miniHistory(rows){
 const data=Array.isArray(rows)?rows.filter(p=>validStamp(p?.time)&&Number.isFinite(p?.price)&&p.price>0).sort((a,b)=>Date.parse(a.time)-Date.parse(b.time)).slice(-100):[];
 if(data.length<2)return'<div class="derivative-spark-empty">Chưa đủ quan sát giá có thời điểm nguồn để vẽ diễn biến.</div>';
 const vals=data.map(x=>x.price),lo=Math.min(...vals),hi=Math.max(...vals),pad=Math.max((hi-lo)*.15,hi*.0005);
 const y=v=>64-(v-(lo-pad))/(hi-lo+2*pad)*55;
 const x=i=>8+i/(data.length-1)*624;
 const path=data.map((p,i)=>(i?'L':'M')+x(i).toFixed(1)+','+y(p.price).toFixed(1)).join(' ');
 const precise=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:4});
 const dots=data.map((p,i)=>'<circle data-fq-point="'+i+'" data-fq-x="'+x(i).toFixed(1)+'" data-fq-y="'+y(p.price).toFixed(1)+'" data-fq-label="'+esc(datetimeVN(p.time))+'" data-fq-series="Giá hợp đồng" data-fq-value="'+esc(precise.format(p.price))+'" data-fq-unit="điểm" cx="'+x(i).toFixed(1)+'" cy="'+y(p.price).toFixed(1)+'" r="2.8" fill="#2966bb"/>').join('');
 return '<svg class="derivative-spark derivative-spark-wide" viewBox="0 0 640 80" data-fq-inspect="intraday" data-fq-top="4" data-fq-bottom="70" data-fq-color="#2966bb" tabindex="0" role="img" aria-label="Diễn biến giá hợp đồng"><path d="'+path+'" fill="none" stroke="#2966bb" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'+dots+'</svg>';
}
function diff(c){return Number.isFinite(c.change)?c.change:c.price-c.reference;}
function move(c){const change=diff(c),pct=(c.price/c.reference-1)*100;
 return '<span class="derivative-move '+(change>0?'up':change<0?'down':'flat')+'">'+(change>0?'+':'')+fmt(change)+' · '+(pct>0?'+':'')+fmt(pct)+'%</span>';
}
function render(){
 if(!state.data){host.innerHTML='<div class="derivative-head"><h4>Bảng giá VN30F / VN100F</h4></div><p class="money-source-pending">'+(state.failed?'Chưa tải được dữ liệu.':'Đang tải dữ liệu…')+'</p>';return;}
 const all=withAliases(contracts(state.data)),subset=all.filter(c=>state.filter==='all'||c.underlying===state.filter);
 if(!all.some(c=>c.symbol===state.selected))state.selected=all[0]?.symbol||null;
 const c=all.find(x=>x.symbol===state.selected);
 const sourceAge=validStamp(state.data.latestSourceTime);
 const fresh=sourceAge?Math.round((Date.now()-sourceAge)/60000):null;
 const stale=marketOpen()&&fresh!==null&&fresh>15;
 const badge=marketOpen()?(stale?'Giá chậm cập nhật':'Trong giờ giao dịch'):'Ngoài giờ giao dịch';
 const choice=[['all','Tất cả'],['VN30','VN30F'],['VN100','VN100F']].map(([id,label])=>'<button type="button" data-futures-underlying="'+id+'" class="'+(state.filter===id?'active':'')+'" aria-pressed="'+(state.filter===id)+'">'+label+'</button>').join('');
 const selector=all.map(x=>'<option value="'+esc(x.symbol)+'" '+(x.symbol===state.selected?'selected':'')+'>'+esc(x.alias)+' · '+esc(x.symbol)+' · '+esc(x.expiry)+'</option>').join('');
 const pricePanel=c?'<div class="derivative-focus-head"><div><strong>'+esc(c.alias)+' <span>'+esc(c.symbol)+'</span></strong><small>Đáo hạn '+esc(c.expiry)+' · '+esc(statusFor(c))+'</small></div><div class="derivative-focus-price"><strong>'+fmt(c.price)+'</strong><small>điểm</small>'+move(c)+'</div></div>'+
 '<div class="derivative-focus-metrics"><span>Tham chiếu <b>'+fmt(c.reference)+'</b></span><span>Khối lượng <b>'+fmt(c.volume,0)+'</b></span><span>Vị thế mở <b>'+fmt(c.openInterest,0)+'</b></span><span>Cao / Thấp <b>'+fmt(c.high)+' / '+fmt(c.low)+'</b></span></div>'+
 '<div class="derivative-chart-wrap">'+miniHistory(c.series)+'</div>'+
 ''
 :'<p class="money-source-pending">Chưa có dữ liệu.</p>';
 const headers=['Mã / Kỳ hạn','Giá','Thay đổi','Khối lượng','Vị thế mở','Dư mua 1','Dư bán 1'];
 const rows=subset.map(x=>{
  const selected=x.symbol===state.selected;
  const cls='derivative-live-contract'+(selected?' active':'');
  return '<tr class="'+cls+'" data-futures-symbol="'+esc(x.symbol)+'" aria-selected="'+selected+'">'+
  '<td class="derivative-contract-title"><button type="button" data-futures-select="'+esc(x.symbol)+'"><strong>'+esc(x.symbol)+'</strong><small>'+esc(x.alias)+' · '+esc(x.expiry)+'</small></button></td>'+
  '<td class="derivative-last"><strong>'+fmt(x.price)+'</strong></td><td>'+move(x)+'</td><td>'+fmt(x.volume,0)+'</td><td>'+fmt(x.openInterest,0)+'</td>'+
  '<td>'+fmt(x.bid1)+' <small>('+fmt(x.bidVol1,0)+')</small></td><td>'+fmt(x.ask1)+' <small>('+fmt(x.askVol1,0)+')</small></td>'+
  '</tr>';
 }).join('');
 host.innerHTML='<div class="derivative-head"><div><span class="macro-viz-kicker">HỢP ĐỒNG TƯƠNG LAI</span><h4>Bảng giá hợp đồng tương lai</h4><p>'+esc(badge)+' · Giá lúc '+esc(datetimeVN(state.data.latestSourceTime))+'</p></div><button type="button" class="money-refresh" data-futures-refresh>Làm mới</button></div>'+
 '<div class="derivative-filter" role="group" aria-label="Lọc chỉ số hợp đồng">'+choice+'</div>'+
 '<div class="derivative-focus-select"><label for="futures-contract-select">Chọn hợp đồng</label><select id="futures-contract-select" aria-label="Chọn hợp đồng tương lai">'+selector+'</select></div>'+
 '<section class="derivative-focus" aria-label="Chi tiết giá và biểu đồ hợp đồng">'+pricePanel+'</section>'+
 '<div class="derivative-board-scroll"><table class="derivative-board-table"><thead><tr>'+headers.map(x=>'<th>'+esc(x)+'</th>').join('')+'</tr></thead><tbody>'+
 (rows||'<tr><td colspan="7">Không có hợp đồng phù hợp bộ lọc.</td></tr>')+'</tbody></table></div>';
}
async function load(){
 if(state.loading)return;state.loading=true;state.lastAttempt=Date.now();
 try{
  const resp=await fetch(SOURCE+'?v='+Math.floor(Date.now()/60000),{cache:'no-store',signal:AbortSignal.timeout(12000)});
  if(!resp.ok)throw Error('HTTP '+resp.status);
  const data=await resp.json();if(!healthy(data))throw Error('Invalid futures snapshot');
  const current=validStamp(state.data?.latestSourceTime)||0,next=validStamp(data.latestSourceTime)||0;
  if(!state.data||next>=current){state.data=data;state.failed=false;}
 }catch{state.failed=true;}finally{state.loading=false;render();}
}
host.addEventListener('click',e=>{
 const b=e.target.closest?.('button');if(!b)return;
 const group=b.dataset.futuresUnderlying;
 if(['all','VN30','VN100'].includes(group)){state.filter=group;render();return;}
 const sym=b.dataset.futuresSelect;if(sym){state.selected=sym;render();return;}
 if(b.hasAttribute('data-futures-refresh'))load();
});
host.addEventListener('change',e=>{if(e.target.id==='futures-contract-select'){state.selected=e.target.value;render();}});
window.FinDerivativeQuotes={refresh:load,setData:data=>{state.data=data;state.failed=false;render();},_test:{healthy,contracts,statusFor,marketOpen,fmt,miniHistory,withAliases}};
render();load();
setInterval(()=>{if(!document.hidden)load();},60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
})();