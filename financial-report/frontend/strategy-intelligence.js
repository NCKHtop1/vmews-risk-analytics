(function(){
'use strict';
const $=id=>document.getElementById(id);
const C=window.FinStrategyIntelligenceCore;
const E=window.FinStrategyEngine;
if(!C||!E)return;
const state={model:null,selected:null,lastSourceTime:null,busy:false};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,d=0)=>Number.isFinite(Number(v))?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:d}).format(Number(v)):'—';
const pct=(v,d=1)=>Number.isFinite(Number(v))?fmt(v,d)+'%':'—';
function ctx(){
 const strategy=window.FinStrategyBuilder?.context?.()||{};
 const risk=window.FinRiskMonitor?.context?.()||window.FinMarketData?.currentBundle?.()?.risk||null;
 return{strategy,risk,snapshot:strategy.snapshot||window.FinMarketData?.currentBundle?.()?.strategy||null};
}
function sourceLabel(model){
 const t=model?.sourceTime||model?.snapshot?.sourceTime||model?.snapshot?.checkedAt;
 if(!t||!Number.isFinite(Date.parse(t)))return'Chưa đồng bộ';
 return new Date(t).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',day:'2-digit',month:'2-digit'});
}
function metric(label,value,sub=''){
 return '<div class="sai-metric"><span>'+esc(label)+'</span><strong>'+esc(value)+'</strong>'+(sub?'<small>'+esc(sub)+'</small>':'')+'</div>';
}
function strategyCard(x,rank){
 const symbols=(x.matchSymbols||[]).slice(0,5);
 return '<button type="button" class="sai-strategy-card" data-sai-strategy="'+esc(x.id)+'">'+
  '<div class="sai-rank">#'+rank+'</div><div class="sai-strategy-main"><div class="sai-strategy-line"><strong>'+esc(x.label)+'</strong><span class="sai-pill '+(x.score>=82?'good':x.score>=68?'watch':'muted')+'">'+esc(x.status)+'</span></div>'+
  '<small>'+esc(x.family)+' · '+esc(x.horizon)+' · Rủi ro '+esc(x.risk)+'</small>'+
  '<div class="sai-score-row"><span>Phù hợp hiện tại <b>'+fmt(x.score)+'/100</b></span><i><u style="width:'+Math.max(0,Math.min(100,x.score))+'%"></u></i></div>'+
  '<div class="sai-card-meta"><span>Regime '+fmt(x.regimeFit)+'</span><span>Xác nhận '+fmt(x.confirmation)+'</span><span>'+fmt(x.matchesCount)+' mã khớp</span></div>'+
  (symbols.length?'<div class="sai-symbol-chips">'+symbols.map(s=>'<em>'+esc(s)+'</em>').join('')+'</div>':'')+
  '</div></button>';
}
function renderRegime(model){
 const r=model.regime,host=$('sai-regime');if(!host)return;
 const m=r.metrics||{};
 host.innerHTML='<div class="sai-regime-head"><div><span>TRẠNG THÁI THỊ TRƯỜNG</span><h3>'+esc(r.label)+'</h3></div><strong>'+fmt(r.confidence)+'/100</strong></div>'+
 '<div class="sai-regime-grid">'+
 metric('Xu hướng tăng',pct(m.trendUp,0),'Tỷ lệ mã xác nhận')+
 metric('Động lượng',pct(m.momentum,0),'RSI/MACD đồng thuận')+
 metric('Độ rộng',pct(m.breadth,0),'Tỷ lệ mã tăng')+
 metric('Rủi ro',m.risk==null?'—':fmt(m.risk,1)+'/100','Risk Monitor')+
 '</div>';
}
function renderStrategies(model){
 const host=$('sai-top-strategies');if(!host)return;
 host.innerHTML=(model.ranking||[]).map((x,i)=>strategyCard(x,i+1)).join('')||'<div class="sai-empty">Chưa đủ dữ liệu để xếp hạng chiến lược.</div>';
}
function oppRow(x,i){
 const p=x.primary||{};
 const current=x.row?.current||{};
 return '<button type="button" class="sai-opp-row '+(state.selected===x.symbol?'active':'')+'" data-sai-symbol="'+esc(x.symbol)+'">'+
 '<span class="sai-opp-rank">'+(i+1)+'</span><strong>'+esc(x.symbol)+'</strong>'+
 '<span>'+esc(p.label||'—')+'</span><span>'+fmt(x.score)+'/100</span>'+
 '<span>'+fmt(current.volumeRatio20,2)+'x</span><span>'+fmt(x.riskScore,0)+'/100</span>'+
 '<em>'+esc(x.stance)+'</em></button>';
}
function renderOpportunities(model){
 const host=$('sai-opportunities');if(!host)return;
 const rows=(model.opportunities||[]).slice(0,25);
 if(!state.selected&&rows.length)state.selected=rows[0].symbol;
 host.innerHTML='<div class="sai-opp-head"><span>#</span><span>Mã</span><span>Chiến lược chính</span><span>Điểm</span><span>KL/TB20</span><span>Rủi ro</span><span>Đánh giá</span></div>'+
 (rows.length?rows.map(oppRow).join(''):'<div class="sai-empty">Snapshot hiện tại chưa có mã khớp nhóm chiến lược được xếp hạng.</div>');
}
function renderView(model){
 const host=$('sai-investment-view');if(!host)return;
 const v=C.investmentView(state.selected,model.opportunities,model.regime);
 if(!v.symbol){host.innerHTML='<div class="sai-empty">Chọn một mã trong bảng cơ hội.</div>';return;}
 const positives=(v.positives||[]).map(x=>'<li><i>+</i><span>'+esc(x)+'</span></li>').join('');
 const cautions=(v.cautions||[]).map(x=>'<li><i>!</i><span>'+esc(x)+'</span></li>').join('');
 const c=v.current||{};
 host.innerHTML='<div class="sai-view-head"><div><span>NHẬN ĐỊNH ĐỊNH LƯỢNG</span><h3>'+esc(v.symbol)+' · '+esc(v.stance)+'</h3><small>'+esc(v.primary?.label||'Chưa có chiến lược chính')+'</small></div><strong>'+fmt(v.score)+'/100</strong></div>'+
 '<div class="sai-view-market">'+
 metric('Giá',fmt(c.price,0)+' đ')+metric('RSI 14',fmt(c.rsi14,1))+metric('KL/TB20',fmt(c.volumeRatio20,2)+'x')+metric('Rủi ro',fmt(v.riskScore,0)+'/100')+
 '</div>'+
 '<div class="sai-evidence-grid"><section><h4>Yếu tố ủng hộ</h4><ul class="positive">'+positives+'</ul></section><section><h4>Điểm cần thận trọng</h4><ul class="caution">'+cautions+'</ul></section></div>'+
 '<div class="sai-invalidation"><span>ĐIỀU KIỆN MẤT HIỆU LỰC</span><p>'+esc(v.invalidation)+'</p></div>'+
 '<div class="sai-ai-actions"><button id="sai-open-symbol" type="button">Mở biểu đồ '+esc(v.symbol)+'</button><button id="sai-query-ai" type="button" class="primary">Phân tích sâu</button></div>';
}
function renderExecution(){
 const host=$('sai-vn-execution');if(!host)return;
 const x=C.executionProfile();
 host.innerHTML='<div class="sai-section-title"><div><span>GIẢ ĐỊNH GIAO DỊCH VIỆT NAM</span><h3>Execution profile · HOSE</h3></div></div>'+
 '<div class="sai-execution-grid">'+
 metric('Lô chẵn',fmt(x.boardLot)+' cp','Khối lượng làm tròn theo lô')+
 metric('Biên độ',pct(x.priceBandPct,0),'HOSE mặc định')+
 metric('Phí mô phỏng',pct(x.brokerFeePct,2),'Có thể cấu hình khi backtest')+
 metric('Thuế bán',pct(x.sellTaxPct,2),'Áp dụng phía bán')+
 metric('Slippage',pct(x.slippagePct,2),'Giả định mặc định')+
 metric('Thanh khoản',pct(x.maxAdvPct,0)+' ADV','Giới hạn quy mô lệnh')+
 '</div>';
}
function renderStatus(model){
 const el=$('sai-status');if(!el)return;
 el.textContent=(model.snapshot?.coverage||0)+' mã đủ dữ liệu · cập nhật '+sourceLabel(model);
}
function build(){
 const {strategy,risk,snapshot}=ctx();
 if(!snapshot?.symbols)return null;
 const ranked=C.rankStrategies(snapshot,risk,E);
 const opportunities=C.rankOpportunities(ranked.ranking,snapshot,risk);
 return{...ranked,opportunities,snapshot,risk,sourceTime:snapshot.sourceTime||snapshot.checkedAt||null};
}
function refresh(){
 if(state.busy)return;state.busy=true;
 try{
  const model=build();if(!model)return;
  state.model=model;
  if(state.selected&&!model.opportunities.some(x=>x.symbol===state.selected))state.selected=model.opportunities[0]?.symbol||null;
  renderStatus(model);renderRegime(model);renderStrategies(model);renderOpportunities(model);renderView(model);renderExecution();
 }finally{state.busy=false;}
}
function selectSymbol(symbol){
 state.selected=String(symbol||'').toUpperCase()||null;
 if(state.model){renderOpportunities(state.model);renderView(state.model);}
}
function loadPreset(id){
 const button=document.querySelector('[data-strategy-preset="'+CSS.escape(id)+'"]');
 if(button){button.click();document.getElementById('strategy-builder')?.scrollIntoView({behavior:'smooth',block:'start'});}
}
function openSymbol(symbol){
 const s=String(symbol||state.selected||'').toUpperCase();if(!s)return;
 window.FinPlatformViews?.openAnalysis?.();
 const ticker=$('ticker');if(ticker)ticker.value=s;
 $('company-form')?.requestSubmit();
 setTimeout(()=>document.getElementById('market')?.scrollIntoView({behavior:'smooth',block:'start'}),60);
}
function askAI(){
 if(!state.model||!state.selected||!window.FinQueryAI?.ask)return;
 const v=C.investmentView(state.selected,state.model.opportunities,state.model.regime);
 const q='Phân tích '+state.selected+' theo Strategy Intelligence hiện tại. Chiến lược chính: '+(v.primary?.label||'chưa có')+'. Điểm phù hợp: '+(v.score??'—')+'/100. Regime: '+state.model.regime.label+'. Hãy đối chiếu thêm giá, kỹ thuật, Forecast, Risk, tin doanh nghiệp và BCTC đang có trong FinQuery; nêu yếu tố ủng hộ, yếu tố phản biện, kịch bản tích cực, kịch bản mất hiệu lực và rủi ro. Không suy diễn số liệu thiếu.';
 window.FinQueryAI.ask(q,'deep');
}
function bind(){
 $('sai-top-strategies')?.addEventListener('click',e=>{const b=e.target.closest('[data-sai-strategy]');if(b)loadPreset(b.dataset.saiStrategy);});
 $('sai-opportunities')?.addEventListener('click',e=>{const b=e.target.closest('[data-sai-symbol]');if(b)selectSymbol(b.dataset.saiSymbol);});
 $('sai-investment-view')?.addEventListener('click',e=>{if(e.target.closest('#sai-open-symbol'))openSymbol();else if(e.target.closest('#sai-query-ai'))askAI();});
 document.addEventListener('finquery:market-bundle',refresh);
 document.addEventListener('finquery:market-refresh',refresh);
 window.addEventListener('hashchange',()=>{if(location.hash==='#strategy-builder')setTimeout(refresh,80);});
}
bind();setTimeout(refresh,1500);setInterval(()=>{if(!document.hidden&&location.hash==='#strategy-builder')refresh();},300000);
window.FinStrategyIntelligence={refresh,selectSymbol,context:()=>({selected:state.selected,model:state.model,execution:C.executionProfile()})};
})();