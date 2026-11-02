/* FINQUERY-PORTFOLIO-ADVISOR-UI-1.0 — read-only, completed-EOD model research.
 * Public inputs contain no user information. Never calls trade/order endpoints.
 */
(function(){
'use strict';
const root=document.getElementById('portfolio');
if(!root)return;
const $=id=>document.getElementById(id);
const RAW='https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/portfolio-advisor.json';
const PROFILE=new Set(['defensive','balanced','growth']);
const LABELS={breakout_volume:'Phá vỡ + thanh khoản',ema_adx:'EMA + ADX',macd_rsi:'MACD + RSI',momentum_recovery:'Động lượng hồi phục',bollinger_rebound:'Bollinger hồi phục'};
const ERRORS={SESSION_NOT_CLOSED:'Dữ liệu phiên chưa đóng. Hệ thống chỉ tính sau khi nến ngày hoàn tất.',
 STALE_EOD:'Bản giá cuối ngày chưa đủ mới; tạm ngừng tạo danh mục.',
 SOURCE_DATE_MISMATCH:'Ngày dữ liệu giá và rủi ro chưa đồng bộ.',
 INSUFFICIENT_COMPLETE_HISTORY:'Không đủ mã có lịch sử giá đầy đủ.',
 MARKET_STRESS_GATE:'Rủi ro thị trường đang cao. Chưa tạo đề xuất phân bổ cổ phiếu mới.',
 MARKET_SOURCE_QUALITY:'Dữ liệu thị trường chưa đủ độ phủ hoặc trạng thái rủi ro chưa hợp lệ.',
 NO_DIVERSIFIED_MODEL:'Chưa đủ tín hiệu hợp lệ để xây danh mục đa dạng.'};
const fmt=n=>Number.isFinite(Number(n))?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1}).format(Number(n)):'—';
const money=n=>Number.isFinite(Number(n))?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:0}).format(Number(n))+' đ':'—';
const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;' ,'"':'&quot;',"'":'&#39;'}[c]));
const state={data:null,profile:'balanced',frequency:'weekly',lastFetched:0,busy:false};
const status=(message)=>{$('advisor-status').textContent=message;};
const iso=string=>Number.isFinite(Date.parse(string||''))?new Date(string).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'short'}):'—';
function verified(x){
 if(!x||x.version!=='FINQUERY-PORTFOLIO-ADVISOR-RESEARCH-1.0'||!['BLOCKED','RESEARCH_ONLY'].includes(x.status))return false;
 if(x.publication!=='RESEARCH_ONLY'||x.orderExecutionEnabled!==false||x.personalizedRecommendation!==false)return false;
 if(!/^\d{4}-\d{2}-\d{2}$/.test(x.asOf||''))return false;
 if(!x.source||typeof x.source!=='object')return false;
 if(x.status==='RESEARCH_ONLY'&&x.quality?.completeEodOnly!==true)return false;
 return true;
}
function currentWeights(){
 try{
  const c=window.FinPortfolio?.context?.();
  if(!c?.ready||!c.snapshot||!Number.isFinite(c.snapshot.nav)||c.snapshot.nav<=0)return null;
  return new Map((c.snapshot.rows||[]).map(r=>[r.symbol,Number(r.weight)||0]));
 }catch{return null;}
}
function render(){
 const data=state.data;
 if(!data){$('advisor-summary').innerHTML='<p class="advisor-muted">Chưa có snapshot nghiên cứu. Dữ liệu được tạo sau khi hoàn tất phiên giao dịch.</p>';$('advisor-results').innerHTML='';return;}
 const gate=data.status==='RESEARCH_ONLY',m=gate?data.models?.[state.profile]:null;
 const date=safe(data.asOf),stamp=iso(data.generatedAt),code=safe(data.source?.marketRevision?.slice(0,8)||'—');
 $('advisor-meta').textContent='Phiên '+date+' · Xuất bản '+stamp+' · Mã dữ liệu '+code;
 const method=state.frequency==='weekly'?'thứ Sáu hoặc phiên cuối tuần':'phiên cuối tháng';
 const evalRow=data.researchEvaluation||{};
 const evidence=evalRow.status==='RESEARCH_PROXY_NOT_VALIDATED'?
  'Đã chạy '+fmt(evalRow.windows)+' khoảng kiểm định tiến về trước trên tập mã hiện có. Kết quả chỉ là proxy, chưa loại bỏ thiên lệch danh sách mã và điều chỉnh giá.':
  'Chưa đủ dữ liệu để kết luận hiệu quả ngoài mẫu của chiến lược.';
 if(!gate||!m||m.status!=='RESEARCH_ONLY'){
  const why=gate?(m?.why||ERRORS.NO_DIVERSIFIED_MODEL):(ERRORS[data.reason]||'Đang kiểm tra nguồn giá và tín hiệu.');
  $('advisor-summary').innerHTML='<div class="advisor-halted"><strong>Chưa đủ điều kiện đưa ra danh mục mô hình</strong><p>'+safe(why)+'</p><p>Giữ nguyên danh mục thực tế; không có thao tác mua/bán nào được tạo.</p></div>';
  $('advisor-results').innerHTML='';
  $('advisor-evidence').textContent=evidence;
  status('Tạm ngừng: '+why);
  return;
 }
 const cols=m.positions||[],cash=Number(m.cashPct),current=currentWeights();
 if(!cols.length||!Number.isFinite(cash)){status('Không đủ dữ liệu mô hình.');return;}
 const count=cols.length;
 const limit='Tối đa '+fmt(m.maxStockPct)+'%/mã và '+fmt(m.maxSectorPct)+'%/ngành';
 $('advisor-summary').innerHTML='<div class="advisor-metrics">'+
  '<div><small>TRẠNG THÁI</small><strong>Nghiên cứu</strong><span>Chưa xác nhận alpha</span></div>'+
  '<div><small>SỐ MÃ ĐỦ CHỌN</small><strong>'+count+'</strong><span>Chỉ gồm mã qua bộ lọc</span></div>'+
  '<div><small>TIỀN MẶT MÔ HÌNH</small><strong>'+fmt(cash)+'%</strong><span>Phần không phân bổ vẫn là tiền</span></div>'+
  '</div><p class="advisor-description">Đối chiếu theo dữ liệu cuối phiên, xem xét phân bổ vào '+method+'. '+limit+'. Không tự đặt lệnh hoặc thay đổi sổ giao dịch.</p>';
 const rows=cols.map(p=>{
  const symbol=String(p.symbol||''),valid=/^[A-Z0-9]{2,12}$/.test(symbol);
  if(!valid)return'';
  const actual=current?.get(symbol)||0;
  const delta=Number(p.weightPct)-actual;
  const gap=current?'<td class="'+(Math.abs(delta)<2?'advisor-neutral':'advisor-drift')+'">'+(delta>=0?'+':'')+fmt(delta)+' đ.%</td>':'<td>—</td>';
  const evidence=(p.matchedStrategies||[]).map(k=>LABELS[k]).filter(Boolean).slice(0,3).join(', ')||'—';
  return '<tr><td><button type="button" class="advisor-symbol" data-advisor-symbol="'+safe(symbol)+'">'+safe(symbol)+'</button></td>'+
   '<td>'+fmt(p.weightPct)+'%</td><td>'+fmt(p.volatility*100)+'%</td>'+
   '<td>'+safe(evidence)+'</td>'+gap+'</tr>';
 }).join('');
 $('advisor-results').innerHTML='<div class="portfolio-table-wrap"><table class="portfolio-table advisor-table"><thead><tr><th>Mã</th><th>Tỷ trọng mô hình</th><th>Biến động năm</th><th>Điều kiện khớp</th><th>Chênh với thực tế</th></tr></thead><tbody>'+rows+'</tbody></table></div>'+
  '<p class="advisor-note">Chênh lệch được tính theo tỷ trọng, không phải lệnh mua/bán. Biến động năm là số đo lịch sử, không phải mức lỗ tối đa.</p>';
 $('advisor-evidence').textContent=evidence;
 status('Bản nghiên cứu theo phiên '+data.asOf+' · Không phải xác suất sinh lời hoặc khuyến nghị cá nhân hóa.');
}
async function load(force=false){
 if(state.busy)return;
 if(!force&&state.data&&Date.now()-state.lastFetched<30*60000){render();return;}
 state.busy=true;const btn=$('advisor-refresh');if(btn)btn.disabled=true;
 status('Đang đối chiếu snapshot nghiên cứu…');
 try{
  const r=await fetch(RAW,{cache:'no-store',redirect:'follow',signal:AbortSignal.timeout(12000)});
  if(!r.ok)throw Error('Không lấy được bản nghiên cứu ('+r.status+').');
  const data=await r.json();
  if(!verified(data))throw Error('Cấu trúc dữ liệu chưa đạt kiểm tra.');
  const date=Date.parse(data.asOf+'T00:00:00Z');
  if(date>Date.now()+86400000||Date.now()-date>6*86400000)throw Error('Snapshot đã cũ; không hiển thị danh mục.');
  state.data=data;state.lastFetched=Date.now();render();
 }catch(error){
  state.data=null;render();
  status(String(error.message||'Dữ liệu Advisor chưa có. Hệ thống sẽ xuất bản sau EOD.'));
 }finally{state.busy=false;if(btn)btn.disabled=false;}
}
root.addEventListener('change',e=>{
 const p=e.target.closest?.('#advisor-profile'),c=e.target.closest?.('#advisor-frequency');
 if(p&&PROFILE.has(p.value)){state.profile=p.value;render();}
 if(c&&['weekly','monthly'].includes(c.value)){state.frequency=c.value;render();}
});
root.addEventListener('click',e=>{
 if(e.target.closest?.('#advisor-refresh')){void load(true);return;}
 const symbol=e.target.closest?.('[data-advisor-symbol]');
 if(symbol){
  const code=symbol.dataset.advisorSymbol;
  window.FinPlatformViews?.openAnalysis?.();
  window.FinancialMarket?.openChart?.(code);
  return;
 }
 const route=e.target.closest?.('[data-advisor-link]');
 if(!route)return;
 const dest=route.dataset.advisorLink;
 if(dest==='strategy')window.FinPlatformViews?.openStrategy?.();
 else if(dest==='risk')window.FinPlatformViews?.openRisk?.();
 else if(dest==='scanner'){
  window.FinPlatformViews?.openAnalysis?.();
  document.querySelector('[data-market-view="scanner"]')?.click();
 }
});
document.addEventListener('finquery:portfolio-advisor-open',()=>{void load();});
document.addEventListener('finquery:portfolio-render',()=>{if(state.data&&$('portfolio-tab-advisor')&&!$('portfolio-tab-advisor').hidden)render();});
window.FinPortfolioAdvisor={open:()=>load(),status:()=>state.data?.status||'NOT_PUBLISHED'};
})();
