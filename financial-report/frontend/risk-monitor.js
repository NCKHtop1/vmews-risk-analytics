(function(){'use strict';
const $=id=>document.getElementById(id);
const state={data:null,loading:false,error:''};
const COMPONENT_ORDER=['breadth','volatility','liquidity','concentration','contagion'];
const fmt=(v,d=1)=>Number.isFinite(Number(v))?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:d}).format(Number(v)):'—';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tone=v=>String(v||'green').replace(/[^a-z-]/g,'')||'green';
function time(value){
 const t=Date.parse(value||'');if(!Number.isFinite(t))return'—';
 return new Date(t).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
}
function shortTime(value){
 const t=Date.parse(value||'');if(!Number.isFinite(t))return'';
 return new Date(t).toLocaleTimeString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit'});
}
function levelBadge(lvl){
 const x=lvl||{label:'—',tone:'green'};
 return '<span class="risk-status risk-'+tone(x.tone)+'"><i aria-hidden="true"></i>'+esc(x.label)+'</span>';
}
function summaryText(score){
 const s=Number(score)||0;
 if(s>=80)return'Các dấu hiệu căng thẳng đang xuất hiện đồng thời trên nhiều mặt. Cần ưu tiên bảo toàn vị thế và theo dõi khả năng lan rộng.';
 if(s>=65)return'Rủi ro thị trường đang cao. Cần theo dõi sát mức giảm lan rộng, biến động và các nhóm ngành đang yếu.';
 if(s>=50)return'Mức căng thẳng đang tăng. Chưa phải trạng thái cao nhất nhưng cần theo dõi sát các cảnh báo đang bật.';
 if(s>=35)return'Thị trường có một số dấu hiệu cần theo dõi, nhưng áp lực chưa lan rộng trên toàn bộ hệ thống.';
 return'Các thước đo chính đang ở vùng bình thường. Chưa thấy dấu hiệu căng thẳng lan rộng ở thời điểm này.';
}
function renderTop(){
 const d=state.data;if(!d)return;
 $('risk-score').textContent=fmt(d.overall?.score,1);
 $('risk-level').innerHTML=levelBadge(d.overall?.level);
 $('risk-summary').textContent=summaryText(d.overall?.score);
 const tr=d.trend||{};
 $('risk-trend').textContent=tr.label||'Chưa đủ mốc so sánh';
 $('risk-trend-delta').textContent=tr.delta==null?'Sẽ rõ hơn sau các lần cập nhật tiếp theo':((tr.delta>0?'+':'')+fmt(tr.delta,1)+' điểm so với mốc trước');
 const cov=d.coverage||{};
 $('risk-coverage').textContent=fmt(cov.quotes,0)+' / '+fmt(cov.expected,0)+' mã';
 $('risk-coverage-note').textContent='Nhóm ngành đủ dữ liệu: '+fmt(cov.sectors,0);
 $('risk-source-time').textContent='Dữ liệu đến '+time(d.sourceTime);
 const aligned=window.FinancialMarket?.context?.()?.quoteBundleSourceTime;
 const status=$('risk-source-status');
 if(status)status.textContent=aligned&&String(aligned)!==String(d.sourceTime)?'Đang chờ đồng bộ mốc dữ liệu mới':'Đã đồng bộ với dữ liệu thị trường';
}
function renderComponents(){
 const d=state.data,host=$('risk-components');if(!d||!host)return;
 host.innerHTML=COMPONENT_ORDER.map(key=>{
  const x=d.components?.[key];if(!x)return'';
  return '<article class="risk-component-card"><div class="risk-component-head"><span>'+esc(x.label)+'</span>'+levelBadge(x.level)+'</div><strong>'+fmt(x.score,1)+'</strong><div class="risk-meter"><span class="risk-meter-fill risk-'+tone(x.level?.tone)+'" style="width:'+Math.max(0,Math.min(100,Number(x.score)||0))+'%"></span></div><p>'+esc(x.detail)+'</p></article>';
 }).join('');
}
function renderTimeline(){
 const d=state.data,host=$('risk-timeline');if(!d||!host)return;
 const rows=(d.timeline||[]).slice(-24);
 if(!rows.length){host.innerHTML='<p class="risk-empty">Chưa có mốc dữ liệu để vẽ diễn biến.</p>';return;}
 const W=760,H=230,L=46,R=18,T=16,B=34,innerW=W-L-R,innerH=H-T-B;
 const x=i=>L+(rows.length<=1?innerW/2:i/(rows.length-1)*innerW);
 const y=v=>T+(100-Math.max(0,Math.min(100,Number(v)||0)))/100*innerH;
 const pts=rows.map((r,i)=>x(i).toFixed(1)+','+y(r.score).toFixed(1)).join(' ');
 const grids=[0,25,50,75,100].map(v=>'<g><line x1="'+L+'" x2="'+(W-R)+'" y1="'+y(v)+'" y2="'+y(v)+'"/><text x="'+(L-10)+'" y="'+(y(v)+4)+'" text-anchor="end">'+v+'</text></g>').join('');
 const labels=rows.map((r,i)=>{if(rows.length>8&&i%Math.ceil(rows.length/6)!==0&&i!==rows.length-1)return'';return'<text x="'+x(i)+'" y="'+(H-9)+'" text-anchor="middle">'+esc(shortTime(r.sourceTime))+'</text>';}).join('');
 const dots=rows.map((r,i)=>{const lv=Number(r.score)>=65?'red':Number(r.score)>=35?'yellow':'green';return'<circle class="risk-line-dot risk-'+lv+'" cx="'+x(i)+'" cy="'+y(r.score)+'" r="'+(i===rows.length-1?5:3)+'"/>';}).join('');
 host.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Diễn biến điểm rủi ro thị trường"><g class="risk-grid">'+grids+'</g><polyline class="risk-line" fill="none" points="'+pts+'"/>'+dots+'<g class="risk-axis-labels">'+labels+'</g></svg>';
}
function renderSectors(){
 const d=state.data,host=$('risk-sectors');if(!d||!host)return;
 const rows=(d.sectors||[]).slice(0,14);
 host.innerHTML=rows.map(x=>'<div class="risk-sector-row"><div><strong>'+esc(x.label)+'</strong><small>'+fmt(x.declinePct,1)+'% mã giảm · thay đổi trung vị '+(Number(x.medianChangePct)>0?'+':'')+fmt(x.medianChangePct,2)+'%</small></div><div class="risk-sector-score"><span class="risk-bar"><i class="risk-'+tone(x.level?.tone)+'" style="width:'+Math.max(0,Math.min(100,Number(x.score)||0))+'%"></i></span><b>'+fmt(x.score,1)+'</b></div></div>').join('')||'<p class="risk-empty">Chưa đủ dữ liệu nhóm ngành.</p>';
}
function renderAlerts(){
 const d=state.data,host=$('risk-alerts');if(!d||!host)return;
 const rows=d.alerts||[];
 host.innerHTML=rows.length?rows.map(x=>'<article class="risk-alert risk-'+tone(x.level?.tone)+'"><div class="risk-alert-title"><span class="risk-dot" aria-hidden="true"></span><strong>'+esc(x.title)+'</strong><b>'+fmt(x.score,1)+'</b></div><p>'+esc(x.evidence)+'</p><small>Bắt đầu '+time(x.startedAt)+' · cập nhật '+time(x.lastSeen)+'</small></article>').join(''):'<p class="risk-empty risk-empty-good">Chưa có cảnh báo đáng kể ở thời điểm này.</p>';
}
function renderTopStocks(){
 const d=state.data,body=$('risk-stock-rows');if(!d||!body)return;
 body.innerHTML=(d.topRisk||[]).slice(0,12).map(x=>'<tr><th><button type="button" data-risk-symbol="'+esc(x.symbol)+'">'+esc(x.symbol)+'</button></th><td>'+fmt(x.score,1)+'</td><td class="'+(Number(x.changePct)<0?'price-down':Number(x.changePct)>0?'price-up':'price-flat')+'">'+(Number(x.changePct)>0?'+':'')+fmt(x.changePct,2)+'%</td><td>'+fmt(x.volumeRatio,2)+' lần</td><td>'+fmt(x.rangePct,2)+'%</td><td>'+esc((x.reasons||[]).join(' · ')||'Chưa có dấu hiệu nổi bật')+'</td></tr>').join('');
}
function renderBreadth(){
 const d=state.data,box=$('risk-market-counts');if(!d||!box)return;
 const c=d.marketCounts||{};
 box.innerHTML='<div><span>Tăng</span><strong>'+fmt(c.advancing,0)+'</strong></div><div><span>Giảm</span><strong>'+fmt(c.declining,0)+'</strong></div><div><span>Đứng giá</span><strong>'+fmt(c.unchanged,0)+'</strong></div><div><span>Thay đổi trung vị</span><strong class="'+(Number(c.medianChangePct)<0?'price-down':Number(c.medianChangePct)>0?'price-up':'')+'">'+(Number(c.medianChangePct)>0?'+':'')+fmt(c.medianChangePct,2)+'%</strong></div>';
}
function renderMethod(){
 const d=state.data;if(!d)return;
 const el=$('risk-method-note');if(el)el.textContent=d.methodology?.description||'';
 const el2=$('risk-alert-rule');if(el2)el2.textContent=d.methodology?.alertRule||'';
}
function render(){
 if(!state.data)return;
 renderTop();renderComponents();renderTimeline();renderSectors();renderAlerts();renderTopStocks();renderBreadth();renderMethod();
 const err=$('risk-error');if(err){err.hidden=true;err.textContent='';}
}
async function refresh(){
 if(state.loading)return;
 state.loading=true;
 const btn=$('risk-refresh');if(btn)btn.disabled=true;
 const status=$('risk-source-status');if(status)status.textContent='Đang cập nhật…';
 try{
  const data=await window.FinMarketData.get('risk-monitor.json',{timeout:10000});
  if(data?.status!=='ok'||!data.overall||!Number.isFinite(Number(data.overall.score)))throw Error('Dữ liệu giám sát chưa hợp lệ');
  state.data=data;state.error='';render();
 }catch(error){
  state.error=String(error?.message||error);
  const err=$('risk-error');if(err){err.hidden=false;err.textContent=state.data?'Chưa lấy được bản mới; đang giữ kết quả gần nhất.':'Chưa tải được dữ liệu giám sát rủi ro.';}
  if(status)status.textContent=state.data?'Đang giữ bản gần nhất':'Chưa có dữ liệu';
 }finally{state.loading=false;if(btn)btn.disabled=false;}
}
function showRisk(pushHash=true){
 const section=$('risk-monitor'),intro=document.querySelector('.intro'),workspace=document.querySelector('.workspace');
 if(!section)return;
 if(intro)intro.hidden=true;if(workspace)workspace.hidden=true;section.hidden=false;document.body.classList.add('risk-monitor-view');
 document.querySelectorAll('.header nav a').forEach(a=>a.classList.toggle('active',a.dataset.platformView==='risk'));
 if(pushHash&&location.hash!=='#risk-monitor')history.pushState(null,'','#risk-monitor');
 refresh();window.scrollTo({top:0,behavior:'smooth'});
}
function showAnalysis(){
 const section=$('risk-monitor'),intro=document.querySelector('.intro'),workspace=document.querySelector('.workspace');
 if(section)section.hidden=true;if(intro)intro.hidden=false;if(workspace)workspace.hidden=false;document.body.classList.remove('risk-monitor-view');
 document.querySelectorAll('.header nav a').forEach(a=>a.classList.remove('active'));
}
function openSymbol(symbol){
 showAnalysis();
 const ticker=$('ticker');if(ticker)ticker.value=symbol;
 $('company-form')?.requestSubmit();
 setTimeout(()=>document.getElementById('market')?.scrollIntoView({behavior:'smooth',block:'start'}),50);
}
function bind(){
 document.querySelectorAll('.header nav a').forEach(a=>{
  if(a.dataset.platformView==='risk')a.addEventListener('click',e=>{e.preventDefault();showRisk();});
  else a.addEventListener('click',()=>showAnalysis());
 });
 $('risk-refresh')?.addEventListener('click',refresh);
 $('risk-stock-rows')?.addEventListener('click',e=>{const b=e.target.closest('[data-risk-symbol]');if(b)openSymbol(b.dataset.riskSymbol);});
 window.addEventListener('hashchange',()=>{if(location.hash==='#risk-monitor')showRisk(false);else if(!location.hash.startsWith('#risk-monitor'))showAnalysis();});
 document.addEventListener('finquery:market-refresh',()=>{if(!$('risk-monitor')?.hidden)refresh();});
}
bind();
if(location.hash==='#risk-monitor')showRisk(false);
setInterval(()=>{if(!$('risk-monitor')?.hidden&&!document.hidden)refresh();},60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!$('risk-monitor')?.hidden)refresh();});
window.FinRiskMonitor={refresh,open:()=>showRisk(),close:showAnalysis,context:()=>state.data};
})();