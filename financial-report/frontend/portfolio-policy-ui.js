/* FinQuery Portfolio: account-scoped template selection and daily rebalancing review. */
(()=>{'use strict';
const root=document.getElementById('portfolio'),P=window.FinPortfolio,Q=window.FinPortfolioPolicy;
if(!root||!P||!Q)return;
const el=id=>document.getElementById(id),fmt=n=>Number.isFinite(n)?Math.round(n).toLocaleString('vi-VN')+' đ':'—',
pct=n=>Number.isFinite(n)?(n>0?'+':'')+n.toFixed(1)+'%':'—';
const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state={policy:Q.normalize({preset:'balanced'}),loaded:false,saved:false,dirty:false,busy:false,revision:0};
function showTemplates(){
 const html=Object.values(Q.PRESETS).map((p,i)=>{
  const selected=p.id===state.policy.id;
  return '<article class="portfolio-template'+(selected?' is-selected':'')+'"><span class="portfolio-template-tag">MẪU '+String(i+1).padStart(2,'0')+'</span>'+
   '<h3>'+safe(p.title)+'</h3><p>'+safe(p.subtitle)+'</p>'+
   '<div class="portfolio-template-facts"><span>Tiền '+p.cashPct+'%</span><span>Mã ≤'+p.maxStockPct+'%</span><span>Lệch '+p.driftPct+'đ%</span></div>'+
   '<button type="button" data-portfolio-preset="'+safe(p.id)+'" aria-pressed="'+selected+'">'+(selected?'Đang chọn':'Chọn mẫu')+'</button></article>';
 }).join('');
 el('portfolio-setup-templates').innerHTML=html;
 el('portfolio-policy-cards').innerHTML=html;
}
function controls(){
 const p=state.policy;
 el('portfolio-cash-target').value=String(p.cashPct);
 el('portfolio-drift').value=String(p.driftPct);
 el('portfolio-cash-target-label').textContent=p.cashPct+'%';
 el('portfolio-drift-label').textContent=p.driftPct+' điểm %';
 el('portfolio-policy-stamp').textContent=state.dirty?'Có thay đổi chưa lưu':state.saved?'Đã lưu theo tài khoản':state.loaded?'Chưa lưu kế hoạch':'Đang tải kế hoạch…';
 el('portfolio-policy-save').disabled=!state.loaded||state.busy;
 showTemplates();
}
async function api(method,body){
 const r=await fetch('/api/user/portfolio-policy',{method,credentials:'same-origin',cache:'no-store',
  headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(15000)});
 const data=await r.json();if(!r.ok)throw Object.assign(Error(data.error||'Lỗi đồng bộ kế hoạch.'),{code:data.code});return data;
}
async function load(){
 if(state.loaded||state.busy)return;
 state.busy=true;
 try{
  const r=await api('GET');
  if(r.policy){
   const p=r.policy;
   state.saved=true;state.revision=Number(p.revision)||0;
   if(!state.dirty)state.policy=Q.normalize({preset:p.preset,cashPct:p.cash_pct,driftPct:p.drift_pct});
  }
  state.loaded=true;
 }catch(_){
  el('portfolio-policy-stamp').textContent='Chưa kết nối kế hoạch';
 }finally{state.busy=false;controls();render();}
}
async function save(){
 if(!state.loaded||state.busy)return;
 state.busy=true;controls();
 try{
  const p=state.policy;
  const r=await api('PUT',{preset:p.id,cashPct:p.cashPct,driftPct:p.driftPct,revision:state.revision});
  state.revision=Number(r.policy.revision);
  state.saved=true;state.dirty=false;
  el('portfolio-policy-stamp').textContent='Đã lưu theo tài khoản';
 }catch(e){
  if(e.code==='POLICY_CONFLICT'){state.loaded=false;state.saved=false;}
  el('portfolio-policy-stamp').textContent=e.message;
 }finally{state.busy=false;controls();render();}
}
function getBook(){
 const context=P.context(),snap=context?.snapshot;
 if(!context?.ready||!snap)return null;
 const sectors=new Map();
 for(const sec of context.sectors||[])for(const row of sec.memberRows||[])sectors.set(row.symbol,sec.id);
 const stocks=context.rotation?.stocks||{};
 const rows=snap.rows.map(r=>({...r,sectorId:sectors.get(r.symbol)||stocks[r.symbol]?.sectorId||null}));
 return {portfolio:{...snap,rows},sourceTime:context.quoteTime};
}
function render(){
 const book=getBook();
 if(!book)return;
 const count=book.portfolio.rows.length,hasPositions=count>0;
 root.classList.toggle('portfolio-no-positions',!hasPositions);
 el('portfolio-onboarding').hidden=hasPositions;
 el('portfolio-plan-preview').hidden=!hasPositions;
 const report=Q.review({portfolio:book.portfolio,policy:state.policy,sourceTime:book.sourceTime,now:Date.now()});
 const eligible=state.saved&&!state.dirty&&!report.blocked;
 const label=!hasPositions?'Chưa có mã':!state.saved?'Chưa lưu mẫu':state.dirty?'Chưa lưu thay đổi':
  report.blocked?'Cần đồng bộ':report.trades.length?report.trades.length+' phương án':'Chưa cần đổi';
 el('portfolio-plan-status').textContent=label;
 el('portfolio-plan-status').classList.toggle('has-actions',eligible&&report.trades.length>0);
 el('portfolio-plan-date').textContent=report.sourceDate?'Dữ liệu phiên '+report.sourceDate+' · tự rà soát khi có giá mới':'Chưa có ngày dữ liệu';
 el('portfolio-plan-summary').innerHTML='<div><span>MẪU PHÂN BỔ</span><strong>'+safe(state.policy.title)+'</strong></div>'+
  '<div><span>ĐỘ LỆCH LỚN NHẤT</span><strong>'+(!report.blocked&&hasPositions?pct(report.driftMax):'—')+'</strong></div>'+
  '<div><span>TRẠNG THÁI PHIÊN</span><strong>'+safe(label)+'</strong></div>';
 el('portfolio-target-rows').innerHTML=report.targets.length?report.targets.map(t=>
  '<tr><td><button type="button" class="portfolio-symbol" data-portfolio-symbol="'+safe(t.symbol)+'">'+safe(t.symbol)+'</button></td>'+
  '<td>'+pct(t.currentPct)+'</td><td>'+pct(t.targetPct)+'</td><td>'+pct(t.driftPP)+'</td>'+
  '<td>'+safe(Math.abs(t.driftPP)>=state.policy.driftPct?'Vượt ngưỡng':'Theo dõi')+'</td></tr>').join(''):
  '<tr><td colspan="5" class="portfolio-empty">Nhập cổ phiếu để xem mục tiêu phân bổ.</td></tr>';
 if(!hasPositions||!eligible){
  el('portfolio-plan-result').innerHTML='<p class="portfolio-plan-message">'+safe(!hasPositions?'Chọn mẫu, nạp vốn rồi ghi nhận vị thế để bắt đầu.':
   report.blocked?report.why:!state.saved?'Chọn và lưu một mẫu để bật đánh giá theo phiên.':'Lưu cấu hình mới để đánh giá.')+'</p>';
  return;
 }
 const metrics='<div class="portfolio-review-metrics"><div><small>TIỀN MẶT MỤC TIÊU</small><strong>'+pct(report.targetCashPct)+'</strong></div>'+
  '<div><small>ĐỘ LỆCH CAO NHẤT</small><strong>'+pct(report.driftMax)+'</strong></div>'+
  '<div><small>CHI PHÍ DỰ KIẾN</small><strong>'+fmt(report.estimatedCostVnd)+'</strong></div></div>';
 const cards=report.trades.length?'<div class="portfolio-review-trades">'+report.trades.slice(0,8).map(t=>
  '<article class="portfolio-review-trade"><div><span class="portfolio-review-side'+(t.side==='SELL'?' sell':'')+'">'+
  (t.side==='SELL'?'GIẢM':'BỔ SUNG')+'</span><strong>'+safe(t.symbol)+' · '+pct(t.currentPct)+' → '+pct(t.targetPct)+'</strong></div>'+
  '<div class="portfolio-review-value">'+t.quantity.toLocaleString('vi-VN')+' cp · '+fmt(t.grossVnd)+'</div>'+
  '<p>Giá '+fmt(t.price)+'/cp · Chi phí ước tính '+fmt(t.estimatedCostVnd)+'</p></article>').join('')+'</div>':
  '<p class="portfolio-plan-message">'+safe(report.why||'Trong ngưỡng mục tiêu, chưa cần điều chỉnh.')+'</p>';
 const reserveNote=report.targetCashPct>state.policy.cashPct+0.1?'<p class="portfolio-plan-message">Tiền mặt mục tiêu cao hơn mức chọn do giới hạn tỷ trọng mã hoặc ngành đang áp dụng.</p>':'';
 el('portfolio-plan-result').innerHTML=metrics+cards+reserveNote+
  (report.flags.length?'<p class="portfolio-plan-message">'+safe(report.flags.join(' · '))+'</p>':'');
}
function select(id){
 if(!Q.PRESETS[id])return;
 state.policy=Q.normalize({preset:id});
 state.dirty=true;controls();render();P.setTab('plan');
}
root.addEventListener('click',e=>{
 const b=e.target.closest('[data-portfolio-preset]');if(b){select(b.dataset.portfolioPreset);return;}
 if(e.target.closest('#portfolio-start-deposit')){
  el('portfolio-add').click();el('portfolio-type').value='DEPOSIT';
  el('portfolio-type').dispatchEvent(new Event('change'));
 }
});
for(const id of ['portfolio-cash-target','portfolio-drift']){
 el(id).addEventListener('input',()=>{
  const c=Number(el('portfolio-cash-target').value),d=Number(el('portfolio-drift').value);
  state.policy=Q.normalize({preset:state.policy.id,cashPct:c,driftPct:d});
  state.dirty=true;controls();render();
 });
}
el('portfolio-policy-save').addEventListener('click',save);
document.addEventListener('finquery:portfolio-plan-open',()=>{void load();render();});
document.addEventListener('finquery:portfolio-render',render);
controls();
if(!root.hidden)void load();
})();