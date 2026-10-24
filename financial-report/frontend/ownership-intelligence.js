(function(){'use strict';
/* Ownership: sourced disclosures only, no inferred cost basis or insider alpha. */
const host=document.getElementById('market-ownership-content');
if(!host)return;
const SOURCE='https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/ownership-disclosures.json';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,d=0)=>Number.isFinite(v)?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:d}).format(v):'—';
const stamp=s=>{const d=Date.parse(s||'');return Number.isFinite(d)&&d<=Date.now()+300000&&d>0?d:null;};
function safeSource(u){try{const x=new URL(u);return x.protocol==='https:'&&/(^|\.)(hnx\.vn|hsx\.vn|ssc\.gov\.vn|vsd\.vn|vsd\.com\.vn)$/.test(x.hostname)?x.href:'';}catch{return'';}}
const TYPES={registered_buy:'Đăng ký mua',registered_sell:'Đăng ký bán',executed_buy:'Đã mua',executed_sell:'Đã bán',ownership_change:'Thay đổi sở hữu'};
const state={data:null,error:null,checked:false,symbol:''};
function verified(row){
 if(!row||!Object.hasOwn(TYPES,row.type)||!stamp(row.disclosedAt)||!safeSource(row.sourceUrl))return false;
 if(!/^[A-Z]{3}$/.test(row.symbol||''))return false;
 if(typeof row.person!=='string'||!row.person.trim()||typeof row.role!=='string')return false;
 if(!Number.isFinite(row.quantity)||row.quantity<0)return false;
 if(row.holdingsAfter!=null&&(!Number.isFinite(row.holdingsAfter)||row.holdingsAfter<0))return false;
 if(row.executedAt!=null&&!stamp(row.executedAt))return false;
 return true;
}
function selected(){return String(document.getElementById('ticker')?.value||'MBB').trim().toUpperCase();}
function render(){
 const symbol=selected();state.symbol=symbol;
 if(!state.data){
  host.innerHTML='<section class="ownership-empty"><strong>'+esc(symbol)+' · Sở hữu người nội bộ</strong><p>'+
   (state.error?'Nguồn hồ sơ giao dịch người nội bộ chưa sẵn sàng.':'Đang kiểm tra hồ sơ công bố chính thức.')+
   '</p><p>Chưa có dữ liệu được xác minh thì FinQuery không tự suy ra tỷ lệ nắm giữ, giá vốn hoặc tín hiệu mua bán.</p></section>';
  return;
 }
 const rows=state.data.events.filter(r=>verified(r)&&r.symbol===symbol).sort((a,b)=>stamp(b.disclosedAt)-stamp(a.disclosedAt)).slice(0,60);
 if(!rows.length){
  host.innerHTML='<section class="ownership-empty"><strong>'+esc(symbol)+' · Giao dịch nội bộ</strong><p>Chưa có bản ghi đã xác minh từ công bố của sở giao dịch/doanh nghiệp.</p><p>Tỷ lệ nắm giữ, giao dịch dự kiến và giao dịch đã thực hiện sẽ hiển thị riêng khi có chứng từ nguồn.</p></section>';return;
 }
 const header='<div class="ownership-heading"><strong>'+esc(symbol)+' · '+rows.length+' công bố</strong><small>Ưu tiên mốc ngày công bố, không thay bằng ngày thực hiện</small></div>';
 const trs=rows.map(r=>'<tr><td>'+esc(new Date(r.disclosedAt).toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}))+'</td><td><strong>'+esc(r.person)+'</strong><small>'+esc(r.role)+'</small></td>'+
 '<td>'+esc(TYPES[r.type])+(r.executedAt?'<small>Ngày giao dịch '+esc(new Date(r.executedAt).toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}))+'</small>':'')+'</td>'+
 '<td>'+fmt(r.quantity)+'</td><td>'+fmt(r.holdingsAfter)+'</td>'+
 '<td><a href="'+esc(safeSource(r.sourceUrl))+'" rel="noopener noreferrer" target="_blank" aria-label="Mở công bố nguồn '+esc(r.person)+'">Nguồn ↗</a></td></tr>').join('');
 host.innerHTML=header+'<div class="ownership-table-scroll"><table class="ownership-table"><thead><tr><th>Công bố</th><th>Người nội bộ</th><th>Loại giao dịch</th><th>Số lượng</th><th>Nắm giữ sau</th><th>Chứng từ</th></tr></thead><tbody>'+trs+'</tbody></table></div>'+
 '<p class="ownership-disclaimer">Giá trị sở hữu hiện tại ≠ lãi/lỗ đầu tư; thiếu giá vốn thì không tính lợi nhuận. Không phát tín hiệu Alpha từ sự kiện chưa kiểm định.</p>';
}
async function load(){
 try{
  const r=await fetch(SOURCE+'?v='+Math.floor(Date.now()/3600000),{cache:'no-store',signal:AbortSignal.timeout(10000)});
  if(!r.ok)throw Error('No verified ownership disclosures');
  const d=await r.json();
  if(d.schemaVersion!==1||d.status!=='verified'||!Array.isArray(d.events))throw Error('Invalid ownership data');
  state.data=d;state.error=null;
 }catch(e){state.error=e?.message||'unavailable';}finally{state.checked=true;render();}
}
document.addEventListener('finquery:symbol-change',render);
document.getElementById('ticker')?.addEventListener('change',render);
window.FinOwnership={refresh:()=>{if(!state.checked)return load();render();},setData:data=>{state.data=data;state.error=null;state.checked=true;render();},_test:{verified,safeSource}};
render();load();
})();