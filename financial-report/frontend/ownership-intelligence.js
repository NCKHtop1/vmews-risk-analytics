(function(){'use strict';
const host=document.getElementById('market-ownership-content');
if(!host)return;
const ROOT='https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/';
const V2=ROOT+'ownership-intelligence-v2.json';
const FALLBACK=ROOT+'ownership-disclosures.json';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
const fmt=(v,d=0)=>Number.isFinite(Number(v))&&v!==null&&v!==undefined&&v!==''?Number(v).toLocaleString('vi-VN',{minimumFractionDigits:0,maximumFractionDigits:d}):'—';
const day=s=>{const t=Date.parse(s||'');return Number.isFinite(t)&&t<=Date.now()+300000&&t>0?new Date(t).toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'—'};
const stamp=s=>{const t=Date.parse(s||'');return Number.isFinite(t)&&t<=Date.now()+300000&&t>0?t:null};
function safeSource(raw,symbol){
 try{
  const u=new URL(raw);
  if(u.protocol!=='https:'||u.username||u.password)return'';
  const h=u.hostname.toLowerCase();
  if(/(^|\.)(hnx\.vn|hsx\.vn|ssc\.gov\.vn|vsd\.vn|vsd\.com\.vn)$/.test(h))return u.href;
  if(h==='kbbuddywts.kbsec.com.vn'&&u.pathname.startsWith('/iis-server/investment/stockinfo/'))return u.href;
  if(h==='iq.vietcap.com.vn'&&u.pathname.startsWith('/api/iq-insight-service/v1/events'))return u.href;
  if(symbol==='MBB'&&(h==='mbbank.com.vn'||h.endsWith('.mbbank.com.vn')))return u.href;
  return'';
 }catch{return''}
}
const TYPE={
 registered_buy:'Đăng ký mua',registered_sell:'Đăng ký bán',
 executed_buy:'Đã mua',executed_sell:'Đã bán',ownership_change:'Thay đổi sở hữu',
 reported_registration:'Thông báo giao dịch',reported_result:'Báo cáo kết quả'
};
const SIGNAL={
 TANG_KEM_THANH_KHOAN:['Tăng · KL cao','up'],
 GIAM_KEM_THANH_KHOAN:['Giảm · KL cao','down'],
 DI_NGANG:['Đi ngang','flat'],
 THEO_DOI:['Có biến động','watch'],
 CHO_DU_LIEU:['Chờ phiên','watch']
};
const state={data:null,error:null,checked:false,pending:null,legacy:false,lastAttempt:0};
function verified(r){
 if(!r||!Object.hasOwn(TYPE,r.type)||!stamp(r.disclosedAt)||!/^[A-Z]{3}$/.test(r.symbol||'')||!safeSource(r.sourceUrl,r.symbol))return false;
 if(typeof r.person!=='string'||!r.person.trim()||typeof r.role!=='string')return false;
 if(r.type.startsWith('executed_')&&(r.quantity==null||!Number.isSafeInteger(r.quantity)))return false;
 if(r.quantity!=null&&(!Number.isSafeInteger(r.quantity)||r.quantity<0))return false;
 if(r.holdingsAfter!=null&&(!Number.isSafeInteger(r.holdingsAfter)||r.holdingsAfter<0))return false;
 if(r.executedAt!=null&&!stamp(r.executedAt))return false;
 return true;
}
function selected(){return String(document.getElementById('ticker')?.value||'MBB').trim().toUpperCase()}
function validRows(d,symbol){
 const events=d?.schemaVersion===2?d.symbols?.[symbol]?.events:d?.events;
 if(!Array.isArray(events))return[];
 const seen=new Set();
 return events.filter(r=>r.symbol===symbol&&verified(r))
   .sort((a,b)=>stamp(b.disclosedAt)-stamp(a.disclosedAt))
   .filter(r=>{const k=r.id||[r.symbol,r.person,r.type,r.disclosedAt,r.title].join('|');if(seen.has(k))return false;seen.add(k);return true})
   .slice(0,90);
}
function sourceLink(url,symbol,label='Nguồn'){
 const href=safeSource(url,symbol);
 return href?'<a href="'+esc(href)+'" target="_blank" rel="noopener noreferrer">'+esc(label)+' ↗</a>':'';
}
function pct(v){if(v===null||v===undefined||!Number.isFinite(Number(v)))return'<span class="owner-missing">—</span>';
 const n=Number(v),tone=n>0?'owner-pos':n<0?'owner-neg':'owner-zero';
 return'<span class="'+tone+'">'+(n>0?'+':'')+fmt(n,2)+'%</span>';
}
function summarySection(symbol,profile){
 if(!profile)return'<div class="owner-overview"><section><h4>Cơ cấu sở hữu</h4><p>Chưa có số liệu đã đối chiếu.</p></section><section><h4>Cổ đông lớn</h4><p>Chưa có số liệu đã đối chiếu.</p></section><section><h4>Ban lãnh đạo</h4><p>Chưa có số liệu đã đối chiếu.</p></section></div>';
 const own=(profile.ownership||[]).filter(x=>x&&typeof x.name==='string'&&Number.isFinite(Number(x.percentage))&&x.percentage!==null);
 const holders=(profile.shareholders||[]).filter(x=>x&&typeof x.name==='string'&&Number.isFinite(Number(x.percentage))&&x.percentage!==null);
 const leaders=(profile.leaders||[]).filter(x=>x&&x.name&&x.role);
 const ownRows=own.map(x=>'<div class="owner-structure-row"><span>'+esc(x.name)+'</span><b>'+fmt(x.percentage,2)+'%</b></div>').join('')||'<p>Chưa có số liệu đã đối chiếu.</p>';
 const holderRows=holders.slice(0,6).map(x=>'<div class="owner-structure-row"><span>'+esc(x.name)+'</span><b>'+fmt(x.percentage,2)+'%</b></div>').join('')||'<p>Chưa có số liệu đã đối chiếu.</p>';
 const otherHolders=holders.length>6?'<details><summary>Xem thêm '+(holders.length-6)+' cổ đông</summary>'+holders.slice(6).map(x=>'<div class="owner-structure-row"><span>'+esc(x.name)+'</span><b>'+fmt(x.percentage,2)+'%</b></div>').join('')+'</details>':'';
 const leaderRows=leaders.slice(0,6).map(x=>'<div class="owner-structure-row"><span>'+esc(x.name)+'</span><small>'+esc(x.role)+'</small></div>').join('')||'<p>Chưa có danh sách đã đối chiếu.</p>';
 const otherLeaders=leaders.length>6?'<details><summary>Xem thêm '+(leaders.length-6)+' thành viên</summary>'+leaders.slice(6).map(x=>'<div class="owner-structure-row"><span>'+esc(x.name)+'</span><small>'+esc(x.role)+'</small></div>').join('')+'</details>':'';
 const latest=[profile.asOf,...own.map(x=>x.asOf),...holders.map(x=>x.asOf)].filter(Boolean).sort().at(-1)||null;
 const meta='<small class="owner-source">'+(latest?'Số liệu kỳ '+day(latest)+' · ':'')+sourceLink(profile.source,symbol,profile.sourceName||'Nguồn')+'</small>';
 return'<div class="owner-overview"><section><h4>Cơ cấu sở hữu</h4>'+ownRows+'</section>'+
 '<section><h4>Cổ đông lớn</h4>'+holderRows+otherHolders+'</section>'+
 '<section><h4>Ban lãnh đạo</h4>'+leaderRows+otherLeaders+'</section></div>'+meta;
}
function marketSignal(event){
 const r=event.reaction||{};
 if(r.status==='pending')return['Chờ phiên','watch'];
 if(!r.status||r.status==='unavailable')return['Chưa có giá','watch'];
 return SIGNAL[r.signal]||['Theo dõi','watch'];
}
function render(){
 const symbol=selected();
 if(!state.data){
  host.innerHTML='<section class="ownership-empty"><strong>'+esc(symbol)+' · Sở hữu và giao dịch</strong><p>'+(state.error?'Chưa tải được dữ liệu.':'Đang tải…')+'</p></section>';
  return;
 }
 const card=state.data?.schemaVersion===2?state.data.symbols?.[symbol]:null;
 const events=validRows(state.data,symbol);
 const head='<div class="ownership-section-title"><h4>'+esc(symbol)+' · Sở hữu, lãnh đạo và giao dịch</h4>'+
   '<small>'+('Cập nhật '+day(state.data?.checkedAt||state.data?.updatedAt))+'</small></div>';
 const summary=summarySection(symbol,card?.profile);
 const counts='<div class="owner-reaction-head"><h4>Giao dịch nội bộ &amp; phản ứng sau công bố</h4><small>'+events.length+' công bố</small></div>';
 if(!events.length){
   const code=card?.sourceStatus?.events;
   const message=code==='ok'?'Chưa có công bố giao dịch nội bộ trong 24 tháng gần đây.':
     code==='unavailable'||code==='not_checked'?'Đang bổ sung công bố giao dịch nội bộ.':
     'Chưa có công bố được đối chiếu.';
   host.innerHTML=head+summary+counts+'<section class="ownership-empty"><p>'+esc(message)+'</p></section>';
   return;
 }
 const list=events.map(r=>{
  const signal=marketSignal(r),re=r.reaction||{},ret=re.returnPct||{};
  const title=r.title&&r.title!==r.role?'<small>'+esc(r.title)+'</small>':'';
  const step=h=>pct(ret[String(h)]);
  const volume=re.volumeRatio3!=null?'KL '+fmt(re.volumeRatio3,2)+'×':''; 
  const kind=r.type.startsWith('registered_')?'Đã đăng ký':r.type.startsWith('executed_')?'Đã thực hiện':r.type==='reported_result'?'Báo cáo kết quả':'';
  const type='<strong>'+esc(TYPE[r.type])+'</strong>'+title;
  return'<tr><td class="owner-date">'+day(r.disclosedAt)+'</td>'+
   '<td><strong>'+esc(r.person)+'</strong><small>'+esc(r.role)+'</small></td>'+
   '<td>'+type+'</td><td class="owner-number">'+fmt(r.quantity)+'</td><td class="owner-number">'+fmt(r.holdingsAfter)+'</td>'+
   '<td>'+step(1)+'</td><td>'+step(3)+'</td><td>'+step(5)+'</td><td>'+step(10)+'</td>'+
   '<td><span class="owner-signal owner-signal-'+signal[1]+'">'+esc(signal[0])+'</span>'+
   (kind||volume?'<small>'+esc([kind,volume].filter(Boolean).join(' · '))+'</small>':'')+'</td>'+
   '<td>'+sourceLink(r.sourceUrl,r.symbol,r.sourcePublisher||'Nguồn')+'</td></tr>';
 }).join('');
 const table='<div class="ownership-table-scroll"><table class="ownership-table"><thead><tr>'+
 '<th>Công bố</th><th>Người/tổ chức</th><th>Giao dịch</th><th>Số lượng</th><th>Nắm giữ sau</th>'+
 '<th>T+1</th><th>T+3</th><th>T+5</th><th>T+10</th><th>Diễn biến</th><th>Nguồn</th>'+
 '</tr></thead><tbody>'+list+'</tbody></table></div>';
 host.innerHTML=head+summary+counts+table;
}
async function fetchBounded(url){
 const ctl=new AbortController();const timer=setTimeout(()=>ctl.abort(),12000);
 try{const r=await fetch(url+'?v='+Math.floor(Date.now()/3600000),{cache:'no-store',signal:ctl.signal});if(!r.ok)throw Error('HTTP '+r.status);return await r.json();}
 finally{clearTimeout(timer);}
}
async function load(){
 if(state.pending)return state.pending;
 state.lastAttempt=Date.now();
 state.pending=(async()=>{
  try{
   let next=null;
   try{const d=await fetchBounded(V2);if(d.schemaVersion===2&&d.symbols&&Object.keys(d.symbols).length===100)next=d;}catch(_){}
   if(!next){const d=await fetchBounded(FALLBACK);if(d.schemaVersion!==1||!Array.isArray(d.events))throw Error('No verified ownership');next=d;}
   state.data=next;state.error=null;state.legacy=next.schemaVersion===1;
  }catch(e){state.error=String(e?.message||'unavailable');}
  finally{state.checked=true;state.pending=null;render();}
 })();
 return state.pending;
}
document.addEventListener('finquery:symbol-change',render);
// app.js dispatches on window before updating the input; render on the next microtask.
window.addEventListener?.('finquery:symbol-change',()=>Promise.resolve().then(render));
document.getElementById('ticker')?.addEventListener('change',render);
window.FinOwnership={
 refresh:()=>{if(state.legacy&&Date.now()-state.lastAttempt>30000)return load();if(!state.checked)return load();render();return Promise.resolve();},
 setData:data=>{state.data=data;state.error=null;state.checked=true;render()},
 reload:()=>{state.checked=false;state.pending=null;return load()},
 _test:{verified,safeSource,validRows,marketSignal}
};
render();load();
})();
