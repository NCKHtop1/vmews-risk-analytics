(function(){'use strict';
/* Use issuer/exchange announcements, not inferred trades or portfolio holdings. */
const host=document.getElementById('market-ownership-content');
if(!host)return;
const SOURCE='https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/ownership-disclosures.json';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,d=0)=>Number.isFinite(v)?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:d}).format(v):'—';
const stamp=s=>{const d=Date.parse(s||'');return Number.isFinite(d)&&d<=Date.now()+300000&&d>0?d:null;};
function safeSource(u,symbol){
 try{
  const x=new URL(u);
  if(x.protocol!=='https:'||x.username||x.password)return'';
  const h=x.hostname.toLowerCase();
  const regulator=/(^|\.)(hnx\.vn|hsx\.vn|ssc\.gov\.vn|vsd\.vn|vsd\.com\.vn)$/.test(h);
  const mbIssuer=symbol==='MBB'&&(h==='mbbank.com.vn'||h.endsWith('.mbbank.com.vn'));
  return regulator||mbIssuer?x.href:'';
 }catch{return'';}
}
const TYPES={
 registered_buy:'Đăng ký mua',registered_sell:'Đăng ký bán',
 executed_buy:'Đã mua',executed_sell:'Đã bán',
 ownership_change:'Thay đổi sở hữu',
 reported_registration:'Thông báo giao dịch',
 reported_result:'Báo cáo kết quả'
};
const state={data:null,error:null,checked:false,symbol:''};
function verified(row){
 if(!row||!Object.hasOwn(TYPES,row.type)||!stamp(row.disclosedAt))return false;
 if(!/^[A-Z]{3}$/.test(row.symbol||'')||!safeSource(row.sourceUrl,row.symbol))return false;
 if(typeof row.person!=='string'||!row.person.trim()||typeof row.role!=='string')return false;
 const isDocumentOnly=row.type==='reported_registration'||row.type==='reported_result';
 if(isDocumentOnly){
  if(row.quantity!==null&&row.quantity!==undefined&&(!Number.isSafeInteger(row.quantity)||row.quantity<0))return false;
 }else if(!Number.isSafeInteger(row.quantity)||row.quantity<0)return false;
 if(row.holdingsAfter!=null&&(!Number.isSafeInteger(row.holdingsAfter)||row.holdingsAfter<0))return false;
 if(row.executedAt!=null&&!stamp(row.executedAt))return false;
 if(row.title!=null&&(typeof row.title!=='string'||row.title.length>300))return false;
 return true;
}
function selected(){return String(document.getElementById('ticker')?.value||'MBB').trim().toUpperCase();}
function validRows(data,symbol){
 if(data?.schemaVersion!==1||data?.status!=='verified'||!Array.isArray(data.events))return[];
 const found=data.events.filter(r=>r.symbol===symbol&&verified(r))
   .sort((a,b)=>stamp(b.disclosedAt)-stamp(a.disclosedAt));
 const seen=new Set();
 return found.filter(r=>{
  const key=r.id||[r.symbol,r.person,r.type,r.disclosedAt,r.sourceUrl].join('|');
  if(seen.has(key))return false;
  seen.add(key);return true;
 }).slice(0,60);
}
function render(){
 const symbol=selected();state.symbol=symbol;
 if(!state.data){
  host.innerHTML='<section class="ownership-empty"><strong>'+esc(symbol)+' · Giao dịch người nội bộ</strong><p>'+
   (state.error?'Chưa tải được dữ liệu.':'Đang tải…')+'</p></section>';
  return;
 }
 const rows=validRows(state.data,symbol);
 if(!rows.length){
  host.innerHTML='<section class="ownership-empty"><strong>'+esc(symbol)+' · Giao dịch người nội bộ</strong><p>Chưa có công bố được đối chiếu.</p></section>';return;
 }
 const header='<div class="ownership-heading"><strong>'+esc(symbol)+' · '+rows.length+' công bố</strong></div>';
 const trs=rows.map(r=>{
  const desc=String(r.title||r.role||'').trim();
  const role=String(r.role||'').trim();
  const detail=desc&&desc!==role?desc:role;
  const source=safeSource(r.sourceUrl,r.symbol);
  return '<tr><td>'+esc(new Date(r.disclosedAt).toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}))+'</td>'+
   '<td><strong>'+esc(r.person)+'</strong>'+(role?'<small>'+esc(role)+'</small>':'')+'</td>'+
   '<td>'+esc(TYPES[r.type])+(detail?'<small>'+esc(detail)+'</small>':'')+
   (r.executedAt?'<small>Ngày giao dịch '+esc(new Date(r.executedAt).toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}))+'</small>':'')+'</td>'+
   '<td>'+fmt(r.quantity)+'</td><td>'+fmt(r.holdingsAfter)+'</td>'+
   '<td><a href="'+esc(source)+'" rel="noopener noreferrer" target="_blank" aria-label="Mở công bố nguồn '+esc(r.person)+'">Nguồn ↗</a></td></tr>';
 }).join('');
 host.innerHTML=header+'<div class="ownership-table-scroll"><table class="ownership-table"><thead><tr>'+
  '<th>Công bố</th><th>Người/tổ chức</th><th>Nội dung</th><th>Số lượng</th><th>Nắm giữ sau</th><th>Nguồn</th>'+
  '</tr></thead><tbody>'+trs+'</tbody></table></div>';
}
async function load(){
 try{
  const r=await fetch(SOURCE+'?v='+Math.floor(Date.now()/3600000),{cache:'no-store',signal:AbortSignal.timeout(10000)});
  if(!r.ok)throw Error('Missing ownership data');
  const d=await r.json();
  if(d.schemaVersion!==1||d.status!=='verified'||!Array.isArray(d.events))throw Error('Invalid ownership data');
  state.data=d;state.error=null;
 }catch(e){state.error=e?.message||'unavailable';}finally{state.checked=true;render();}
}
document.addEventListener('finquery:symbol-change',render);
document.getElementById('ticker')?.addEventListener('change',render);
window.FinOwnership={refresh:()=>{if(!state.checked)return load();render();},setData:data=>{state.data=data;state.error=null;state.checked=true;render();},_test:{verified,safeSource,validRows}};
render();load();
})();
