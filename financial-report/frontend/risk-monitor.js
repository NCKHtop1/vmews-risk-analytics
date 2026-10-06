(function(){'use strict';
const $=id=>document.getElementById(id);
const state={data:null,loading:false,error:'',selectedFundSymbol:null,selectedSectorId:null,selectedBreadthGroup:null};
function updateNavBadge(){
 const badge=$('risk-nav-badge');if(!badge)return;
 const d=state.data||{},funds=d.fundMonitor||{};
 const sectorCount=(d.sectors||[]).filter(x=>x.alertActive===true).length;
 const fundChangeIsCurrent=String(funds.asOf||'')!==''&&String(funds.asOf||'')===String(funds.lastChangedAsOf||'');
 const fundCount=fundChangeIsCurrent?(Number(funds.changedSymbols)||0):0;
 const count=sectorCount+fundCount;
 badge.hidden=count<=0;badge.textContent=count>99?'99+':String(count);
 badge.title=sectorCount+' ngành đang cảnh báo · '+fundCount+' mã quỹ vừa thay đổi';
}
const COMPONENT_ORDER=['breadth','volatility','liquidity','contagion','concentration'];
const SECTOR_ORDER=['banking','securities','real-estate','steel','technology','retail','oil-gas','utilities','construction','seafood','chemicals','transport','insurance','consumer'];
const fmt=(v,d=1)=>Number.isFinite(Number(v))?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:d}).format(Number(v)):'—';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tone=v=>String(v||'green').replace(/[^a-z-]/g,'')||'green';
function time(value){
 const t=Date.parse(value||'');if(!Number.isFinite(t))return'—';
 return new Date(t).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
}
function shortTime(value,withDate=false){
 const t=Date.parse(value||'');if(!Number.isFinite(t))return'';
 return new Date(t).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:withDate?'2-digit':undefined,month:withDate?'2-digit':undefined,hour:'2-digit',minute:'2-digit'});
}
function dayKey(value){
 const t=Date.parse(value||'');if(!Number.isFinite(t))return'';
 return new Date(t).toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'});
}
function levelBadge(lvl){
 const x=lvl||{label:'—',tone:'green'};
 return '<span class="risk-status risk-'+tone(x.tone)+'"><i aria-hidden="true"></i>'+esc(x.label)+'</span>';
}
function summaryText(score){
 const s=Number(score)||0;
 if(s>=95)return'Rất cao so với lịch sử.';
 if(s>=85)return'Cao so với lịch sử.';
 if(s>=70)return'Cần theo dõi.';
 return'Bình thường.';
}
function renderTop(){
 const d=state.data;if(!d)return;
 $('risk-score').textContent=fmt(d.overall?.score,1)+' / 100';
 $('risk-level').innerHTML=levelBadge(d.overall?.level);
 $('risk-summary').textContent=summaryText(d.overall?.score);
 const tr=d.trend||{},trend=$('risk-trend'),detail=$('risk-trend-delta');
 if(tr.delta==null){
  trend.textContent=tr.label||'Mới bắt đầu ghi nhận';
  detail.textContent=tr.comparisonLabel||'Chưa có mốc dữ liệu trước.';
 }else{
  const sign=Number(tr.delta)>0?'+':'';
  trend.textContent=(tr.label||'Ít thay đổi')+' · '+sign+fmt(tr.delta,1)+' điểm';
  detail.textContent=fmt(d.overall?.score,1)+' / 100 hiện tại · '+fmt(tr.previousScore,1)+' / 100 ở mốc trước · '+(tr.comparisonLabel||'so với mốc trước');
 }
 const sessionTr=d.sessionTrend||{};
 const sessionTrend=$('risk-session-trend'),sessionDetail=$('risk-session-trend-delta');
 if(sessionTrend){
  if(sessionTr.delta==null){
   sessionTrend.textContent='—';
   if(sessionDetail)sessionDetail.textContent=sessionTr.comparisonLabel||'Chưa có cuối phiên trước';
  }else{
   const sign=Number(sessionTr.delta)>0?'+':'';
   sessionTrend.textContent=sign+fmt(sessionTr.delta,1)+' điểm';
   if(sessionDetail)sessionDetail.textContent=fmt(d.overall?.score,1)+' hiện tại · '+fmt(sessionTr.previousScore,1)+' cuối phiên trước';
  }
 }
 const cov=d.coverage||{};
 const coverageInline=$('risk-coverage-inline');
 if(coverageInline)coverageInline.textContent=fmt(cov.quotes,0)+'/'+fmt(cov.expected,0)+' live';
 $('risk-source-time').textContent='Dữ liệu đến '+time(d.sourceTime);
 const aligned=window.FinancialMarket?.context?.()?.quoteBundleSourceTime;
 const status=$('risk-source-status');
 if(status)status.textContent=aligned&&String(aligned)!==String(d.sourceTime)?'Đang chờ đồng bộ mốc dữ liệu mới':'Đã đồng bộ với dữ liệu thị trường';
}
function renderDriverChange(){
 const el=$('risk-driver-change');if(!el)return;
 const rows=(state.data?.contributions||[]).filter(x=>Number.isFinite(Number(x.change)));
 if(!rows.length){el.textContent='Chưa đủ mốc để so sánh từng nguyên nhân';return;}
 const up=[...rows].sort((a,b)=>(Number(b.pointChange)||0)-(Number(a.pointChange)||0))[0];
 const down=[...rows].sort((a,b)=>(Number(a.pointChange)||0)-(Number(b.pointChange)||0))[0];
 if((Number(up?.pointChange)||0)>0.2)el.textContent='Tăng mạnh nhất: '+up.label+' +'+fmt(up.pointChange,1)+' điểm';
 else if((Number(down?.pointChange)||0)<-0.2)el.textContent='Hạ mạnh nhất: '+down.label+' '+fmt(down.pointChange,1)+' điểm';
 else el.textContent='Các nguyên nhân thay đổi không đáng kể so với mốc trước';
}
function renderComponents(){
 const d=state.data,host=$('risk-components');if(!d||!host)return;
 host.innerHTML=COMPONENT_ORDER.map(key=>{
  const x=d.components?.[key];if(!x)return'';
  return '<article class="risk-component-card"><div class="risk-component-head"><span>'+esc(x.label)+'</span>'+levelBadge(x.level)+'</div><strong>'+fmt(x.score,1)+' / 100</strong><div class="risk-meter"><span class="risk-meter-fill risk-'+tone(x.level?.tone)+'" style="width:'+Math.max(0,Math.min(100,Number(x.score)||0))+'%"></span></div><p>'+esc(x.detail)+'</p></article>';
 }).join('');
}
function renderContributions(){
 const host=$('risk-contributions'),rows=state.data?.contributions||[];if(!host)return;
 if(!rows.length){host.innerHTML='<p class="risk-empty">Chưa có dữ liệu đóng góp.</p>';return;}
 host.innerHTML=rows.map(x=>{
  const delta=Number.isFinite(Number(x.pointChange))?((Number(x.pointChange)>0?'+':'')+fmt(x.pointChange,1)+' điểm so với mốc trước'):'Chưa có mốc so sánh';
  return '<div class="risk-contribution-row"><div class="risk-contribution-label"><strong>'+esc(x.label)+'</strong><small>Trọng số '+fmt(x.weight,0)+'% · '+esc(delta)+'</small></div><div class="risk-contribution-value"><div class="risk-contribution-track"><span class="risk-'+tone(x.level?.tone)+'" style="width:'+Math.max(2,Math.min(100,Number(x.score)||0))+'%"></span></div><b>'+fmt(x.points,1)+' / '+fmt((Number(x.weight)||0),0)+' điểm</b></div></div>';
 }).join('')+(Number(state.data?.overall?.systemWideAdd||0)>0?'<div class="risk-system-add"><span>Phần cộng thêm do nhiều nhóm cùng căng thẳng</span><strong>+'+fmt(state.data.overall.systemWideAdd,1)+' điểm</strong></div>':'');
}
function renderTimeline(){
 const d=state.data,host=$('risk-timeline');if(!d||!host)return;
 const rows=(d.timeline||[]).slice(-30);
 if(!rows.length){host.innerHTML='<p class="risk-empty">Chưa có mốc dữ liệu để vẽ diễn biến.</p>';return;}
 const W=780,H=250,L=48,R=22,T=18,B=42,innerW=W-L-R,innerH=H-T-B;
 const x=i=>L+(rows.length<=1?innerW/2:i/(rows.length-1)*innerW);
 const y=v=>T+(100-Math.max(0,Math.min(100,Number(v)||0)))/100*innerH;
 const pts=rows.map((r,i)=>x(i).toFixed(1)+','+y(r.score).toFixed(1)).join(' ');
 const grids=[0,25,50,70,85,95,100].map(v=>'<g><line x1="'+L+'" x2="'+(W-R)+'" y1="'+y(v)+'" y2="'+y(v)+'"/><text x="'+(L-10)+'" y="'+(y(v)+4)+'" text-anchor="end">'+v+'</text></g>').join('');
 const multipleDays=new Set(rows.map(r=>dayKey(r.sourceTime))).size>1;
 const step=Math.max(1,Math.ceil(rows.length/6));
 const labels=rows.map((r,i)=>{if(i%step!==0&&i!==rows.length-1)return'';return'<text x="'+x(i)+'" y="'+(H-10)+'" text-anchor="middle">'+esc(shortTime(r.sourceTime,multipleDays))+'</text>';}).join('');
 const dots=rows.map((r,i)=>{const lv=Number(r.score)>=85?'red':Number(r.score)>=70?'yellow':'green';return'<circle class="risk-line-dot risk-'+lv+'" cx="'+x(i)+'" cy="'+y(r.score)+'" r="'+(i===rows.length-1?5:3)+'"/>';}).join('');
 const zones='<rect class="risk-zone risk-zone-red" x="'+L+'" y="'+y(100)+'" width="'+innerW+'" height="'+(y(85)-y(100))+'"/><rect class="risk-zone risk-zone-yellow" x="'+L+'" y="'+y(85)+'" width="'+innerW+'" height="'+(y(70)-y(85))+'"/><rect class="risk-zone risk-zone-green" x="'+L+'" y="'+y(70)+'" width="'+innerW+'" height="'+(y(0)-y(70))+'"/>';
 const current=rows[rows.length-1];
 const currentLabel='<text class="risk-current-label" x="'+Math.min(W-R-4,x(rows.length-1)+8)+'" y="'+Math.max(T+12,y(current.score)-9)+'">'+fmt(current.score,1)+'/100</text>';
 host.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Diễn biến điểm rủi ro thị trường">'+zones+'<g class="risk-grid">'+grids+'</g><polyline class="risk-line" fill="none" points="'+pts+'"/>'+dots+currentLabel+'<g class="risk-axis-labels">'+labels+'</g></svg>';
}
function renderSectorDetail(id){
 const host=$('risk-sector-detail'),x=(state.data?.sectors||[]).find(s=>s.id===id);if(!host||!x){if(host)host.hidden=true;return;}
 state.selectedSectorId=id;host.hidden=false;
 const bt=x.backtest||{},validated=x.alertEligible===true;
 const threshold=Number.isFinite(Number(x.threshold))?fmt(x.threshold,1)+'/100':'Chưa đủ kiểm định';
 const members=(x.memberRows||[]).map(m=>'<button type="button" class="risk-sector-member '+(Number(m.changePct)<0?'price-down':Number(m.changePct)>0?'price-up':'price-flat')+'" data-risk-symbol="'+esc(m.symbol)+'"><strong>'+esc(m.symbol)+'</strong><span>'+(Number(m.changePct)>0?'+':'')+fmt(m.changePct,2)+'%</span><small>KL/TB20 '+fmt(m.volumeRatio,2)+'x</small></button>').join('');
 const continuation=bt.continuationValidated===true;
 const btHtml=validated?'<div class="risk-backtest-grid"><div><span>Ngưỡng cảnh báo ngành</span><strong>'+fmt(x.threshold,1)+'/100</strong></div><div><span>Độ lệch giữa các giai đoạn kiểm tra</span><strong>'+fmt(bt.thresholdSpread,1)+' điểm</strong></div><div><span>Tỷ lệ phiên chạm ngưỡng khi kiểm tra</span><strong>'+fmt(Number(bt.signalRate)*100,1)+'%</strong></div><div><span>Mức thay đổi cùng ngày khi chạm ngưỡng</span><strong>'+(Number(bt.medianCurrentReturnWhenSignalPct)>0?'+':'')+fmt(bt.medianCurrentReturnWhenSignalPct,2)+'%</strong></div><div><span>Giảm tiếp 3 phiên</span><strong>'+(continuation?'Đã có bằng chứng':'Chưa đủ bằng chứng')+'</strong></div><div><span>Số lần chạm ngưỡng đã kiểm tra</span><strong>'+fmt(bt.signals,0)+'</strong></div></div>':'';
 host.innerHTML='<div class="risk-detail-head"><div><span>CHI TIẾT NGÀNH</span><h3>'+esc(x.label)+'</h3></div><button type="button" id="risk-sector-detail-close">Đóng</button></div><div class="risk-sector-detail-summary"><div><span>Mã tăng</span><strong class="price-up">'+fmt(x.advancePct,1)+'%</strong></div><div><span>Mã giảm</span><strong class="price-down">'+fmt(x.declinePct,1)+'%</strong></div><div><span>Thay đổi trung vị</span><strong class="'+(Number(x.medianChangePct)<0?'price-down':Number(x.medianChangePct)>0?'price-up':'')+'">'+(Number(x.medianChangePct)>0?'+':'')+fmt(x.medianChangePct,2)+'%</strong></div><div><span>Ngưỡng cảnh báo</span><strong>'+threshold+'</strong></div></div>'+btHtml+'<h4>Các mã trong ngành</h4><div class="risk-sector-members">'+members+'</div>';
}
function renderSectors(){
 const d=state.data,host=$('risk-sectors'),status=$('risk-sector-calibration-status'),updated=$('risk-sector-updated');if(!d||!host)return;
 const cal=d.sectorCalibration||{};
 if(status)status.textContent=Number.isFinite(Number(cal.validatedSectors))?'Ngưỡng cảnh báo '+fmt(cal.validatedSectors,0)+' / '+fmt(cal.totalSectors,0)+' ngành':'';
 if(updated)updated.textContent='Cập nhật gần nhất: '+time(d.sourceTime);
 const rank=new Map(SECTOR_ORDER.map((id,i)=>[id,i]));
 const rows=[...(d.sectors||[])].sort((a,b)=>(rank.get(a.id)??999)-(rank.get(b.id)??999));
 host.innerHTML=rows.map(x=>{
  const change=Number(x.medianChangePct)||0;
  const direction=change>0.01?'up':change<-0.01?'down':'flat';
  const strength=Math.max(8,Math.min(100,Math.abs(change)/3*100));
  const threshold=x.alertActive?(x.aboveThreshold?' · CHẠM NGƯỠNG':' · CẢNH BÁO ĐANG GIỮ'):x.nearThreshold?' · TIỆM CẬN':'';
  const breadth=direction==='up'?fmt(x.advancePct,1)+'% mã tăng':direction==='down'?fmt(x.declinePct,1)+'% mã giảm':'Đi ngang';
  return '<button type="button" class="risk-sector-tile risk-sector-heat-cell risk-heat-'+direction+(x.alertActive?' risk-heat-threshold':'')+'" data-sector-id="'+esc(x.id)+'" style="--risk-heat:'+strength+'%"><div class="risk-sector-tile-head"><strong>'+esc(x.label)+'</strong><b class="'+(change>0?'price-up':change<0?'price-down':'price-flat')+'">'+(change>0?'+':'')+fmt(change,2)+'%</b></div><div class="risk-sector-heat-bar"><span></span></div><div class="risk-sector-heat-meta"><span>'+esc(breadth)+'</span><span>'+fmt(x.score,1)+'/100</span></div><small>'+((Number.isFinite(Number(x.threshold)))?'Ngưỡng '+fmt(x.threshold,1)+'/100':'')+threshold+'</small></button>';
 }).join('')||'<p class="risk-empty">Chưa đủ dữ liệu nhóm ngành.</p>';
 if(state.selectedSectorId&&rows.some(x=>x.id===state.selectedSectorId))renderSectorDetail(state.selectedSectorId);else{const detail=$('risk-sector-detail');if(detail)detail.hidden=true;}
}
function renderAlerts(){
 const d=state.data,host=$('risk-alerts'),history=$('risk-alert-history');if(!d||!host)return;
 const rows=d.alerts||[];
 host.innerHTML=rows.length?rows.map(x=>{
  return '<article class="risk-alert risk-'+tone(x.level?.tone)+'"><div class="risk-alert-title"><span class="risk-dot" aria-hidden="true"></span><strong>'+esc(x.title)+'</strong><b>'+fmt(x.score,1)+'/100</b></div><p>'+esc(x.evidence)+'</p><small>Bắt đầu '+time(x.startedAt)+' · cập nhật '+time(x.lastSeen)+'</small></article>';
 }).join(''):'<p class="risk-empty risk-empty-good">Chưa có cảnh báo đáng kể ở thời điểm này.</p>';
 if(history){
  const events=(d.alertHistory||[]).slice(-6).reverse();
  history.innerHTML=events.length?'<h4>Lịch sử gần đây</h4>'+events.map(x=>'<div><span>'+time(x.time)+'</span><strong>'+esc(x.title)+'</strong><small>'+esc(x.type)+'</small></div>').join(''):'';
 }
}
function renderTopStocks(){
 const d=state.data,body=$('risk-stock-rows');if(!d||!body)return;
 body.innerHTML=(d.topRisk||[]).slice(0,12).map(x=>'<tr><th><button type="button" data-risk-symbol="'+esc(x.symbol)+'">'+esc(x.symbol)+'</button></th><td>'+fmt(x.score,1)+' / 100</td><td class="'+(Number(x.changePct)<0?'price-down':Number(x.changePct)>0?'price-up':'price-flat')+'">'+(Number(x.changePct)>0?'+':'')+fmt(x.changePct,2)+'%</td><td>'+fmt(x.volumeRatio,2)+' lần</td><td>'+fmt(x.rangePct,2)+'%</td><td>'+esc((x.reasons||[]).join(' · ')||'Chưa có dấu hiệu nổi bật')+'</td></tr>').join('');
}
function renderBreadthDetail(group){
 const host=$('risk-breadth-detail'),groups=state.data?.breadthGroups||{};if(!host)return;
 const rows=Array.isArray(groups[group])?groups[group]:[];
 const labels={advancing:'Mã tăng',declining:'Mã giảm',unchanged:'Mã đứng giá'};
 state.selectedBreadthGroup=group;
 host.hidden=false;
 host.innerHTML='<div class="risk-detail-head"><div><span>ĐỘ RỘNG THỊ TRƯỜNG</span><h3>'+esc(labels[group]||'Danh sách mã')+' · '+fmt(rows.length,0)+'</h3></div><button type="button" id="risk-breadth-detail-close">Đóng</button></div><div class="risk-breadth-symbols">'+rows.map(x=>'<button type="button" data-risk-symbol="'+esc(x.symbol)+'"><strong>'+esc(x.symbol)+'</strong><span class="'+(Number(x.changePct)>0?'price-up':Number(x.changePct)<0?'price-down':'price-flat')+'">'+(Number(x.changePct)>0?'+':'')+fmt(x.changePct,2)+'%</span><small>KL/TB20 '+fmt(x.volumeRatio,2)+'x</small></button>').join('')+'</div>';
}
function renderBreadth(){
 const d=state.data,box=$('risk-market-counts'),strip=$('risk-breadth-strip'),detail=$('risk-breadth-detail');if(!d||!box)return;
 const c=d.marketCounts||{},up=Number(c.advancing)||0,down=Number(c.declining)||0,flat=Number(c.unchanged)||0,total=Math.max(1,up+down+flat);
 if(strip)strip.innerHTML='<span class="risk-breadth-up" style="width:'+(up/total*100).toFixed(2)+'%"></span><span class="risk-breadth-flat" style="width:'+(flat/total*100).toFixed(2)+'%"></span><span class="risk-breadth-down" style="width:'+(down/total*100).toFixed(2)+'%"></span>';
 box.innerHTML='<button type="button" data-breadth-group="advancing"><span>Tăng</span><strong>'+fmt(up,0)+'</strong><small>'+fmt(up/total*100,1)+'%</small></button><button type="button" data-breadth-group="declining"><span>Giảm</span><strong>'+fmt(down,0)+'</strong><small>'+fmt(down/total*100,1)+'%</small></button><button type="button" data-breadth-group="unchanged"><span>Đứng giá</span><strong>'+fmt(flat,0)+'</strong><small>'+fmt(flat/total*100,1)+'%</small></button><div><span>Thay đổi trung vị</span><strong class="'+(Number(c.medianChangePct)<0?'price-down':Number(c.medianChangePct)>0?'price-up':'')+'">'+(Number(c.medianChangePct)>0?'+':'')+fmt(c.medianChangePct,2)+'%</strong></div>';
 if(state.selectedBreadthGroup&&(d.breadthGroups||{})[state.selectedBreadthGroup])renderBreadthDetail(state.selectedBreadthGroup);else if(detail)detail.hidden=true;
}
function fundDeltaText(x){
 if(x.status==='new')return'Mới xuất hiện';
 if(x.status==='removed')return'Không còn trong top công bố';
 if(!Number.isFinite(Number(x.deltaPP)))return'Ít thay đổi';
 const n=Number(x.deltaPP);return Math.abs(n)<0.005?'Không đổi':(n>0?'+':'')+fmt(n,2)+' điểm %';
}
function renderFundDetail(symbol){
 const host=$('risk-fund-detail'),f=state.data?.fundMonitor||{},x=(f.rows||[]).find(r=>r.symbol===symbol);if(!host||!x){if(host)host.hidden=true;return;}
 state.selectedFundSymbol=symbol;host.hidden=false;
 const detail=(x.details||[]).map(y=>'<div class="risk-fund-detail-item"><div><strong>'+esc(y.fundCode||y.fundName)+'</strong><small>'+esc(y.fundName||'')+'</small></div><span class="risk-fund-state risk-fund-'+tone(y.tone)+'">'+esc(y.label)+'</span><b>'+(y.currentWeightPct==null?'—':fmt(y.currentWeightPct,2)+'%')+'</b><small>Trước: '+(y.previousWeightPct==null?'—':fmt(y.previousWeightPct,2)+'%')+(Number.isFinite(Number(y.deltaPP))?' · '+(Number(y.deltaPP)>0?'+':'')+fmt(y.deltaPP,2)+' điểm %':'')+(y.reportDate?' · công bố '+esc(y.reportDate):'')+(Number.isFinite(Number(y.navMomentum20Pct))?' · NAV 20P '+(Number(y.navMomentum20Pct)>0?'+':'')+fmt(y.navMomentum20Pct,2)+'%':'')+'</small></div>').join('');
 host.innerHTML='<div class="risk-detail-head"><div><span>CHI TIẾT QUỸ</span><h3>'+esc(symbol)+'</h3></div><button type="button" id="risk-fund-detail-close">Đóng</button></div><div class="risk-fund-detail-summary"><div><span>Số quỹ hiện tại</span><strong>'+fmt(x.currentFundCount,0)+'</strong></div><div><span>Quỹ lớn nhất</span><strong>'+(x.largestWeightPct==null?'—':fmt(x.largestWeightPct,2)+'%')+'</strong></div><div><span>Thay đổi lớn nhất</span><strong>'+(Number.isFinite(Number(x.largestChangePP))?((Number(x.largestChangePP)>0?'+':'')+fmt(x.largestChangePP,2)+' điểm %'):'—')+'</strong></div><div><span>Trạng thái</span><strong class="risk-fund-'+tone(x.tone)+'">'+esc(x.label)+'</strong></div></div><div class="risk-fund-detail-list">'+detail+'</div>';
}
function renderFunds(){
 const d=state.data,box=$('risk-fund-summary'),chart=$('risk-fund-chart'),asof=$('risk-fund-asof'),detail=$('risk-fund-detail');
 if(!box||!chart)return;
 const f=d?.fundMonitor||{};
 if(f.status!=='ok'){
  if(asof)asof.textContent='Chưa có dữ liệu quỹ';
  box.innerHTML='<p class="risk-empty">Chưa có dữ liệu quỹ đủ để so sánh.</p>';chart.innerHTML='';if(detail)detail.hidden=true;return;
 }
 if(asof)asof.textContent='Cập nhật nguồn '+esc(f.asOf||'—')+(f.lastChangedAsOf?' · danh mục đổi gần nhất '+esc(f.lastChangedAsOf):'')+(f.previousAsOf?' · so với '+esc(f.previousAsOf):'');
 box.innerHTML='<div><span>Quỹ có dữ liệu</span><strong>'+fmt(f.funds,0)+'</strong></div><div><span>Mã đang được nắm giữ</span><strong>'+fmt(f.symbols,0)+'</strong></div><div><span>Mã thay đổi đáng chú ý</span><strong>'+fmt(f.changedSymbols,0)+'</strong></div><div><span>Lượt thay đổi đáng chú ý</span><strong>'+fmt(f.materialChanges,0)+'</strong></div>';
 const rows=(f.rows||[]).filter(x=>Number(x.currentFundCount)>0).sort((a,b)=>b.currentFundCount-a.currentFundCount||b.materialChanges-a.materialChanges||a.symbol.localeCompare(b.symbol));
 const max=Math.max(1,...rows.map(x=>Number(x.currentFundCount)||0));
 chart.innerHTML='<div class="risk-fund-chart-head"><span>Mã</span><span>Số quỹ đang nắm giữ</span><span>Thay đổi gần nhất</span></div><div class="risk-fund-chart-body">'+rows.map(x=>{
  const width=Math.max(4,(Number(x.currentFundCount)||0)/max*100);
  const raw=Number(x.largestChangePP);const delta=Number.isFinite(raw)&&Math.abs(raw)>=0.005?((raw>0?'+':'')+fmt(raw,2)+' điểm %'):(x.status==='new'||x.status==='removed'?x.label:'Không đổi');
  return '<button type="button" class="risk-fund-bar risk-fund-'+tone(x.tone)+'" data-fund-symbol="'+esc(x.symbol)+'"><strong>'+esc(x.symbol)+'</strong><span class="risk-fund-bar-track"><i style="width:'+width+'%"></i><b>'+fmt(x.currentFundCount,0)+' quỹ</b></span><small>'+esc(delta)+'</small></button>';
 }).join('')+'</div>';
 if(state.selectedFundSymbol&&rows.some(x=>x.symbol===state.selectedFundSymbol))renderFundDetail(state.selectedFundSymbol);else if(detail)detail.hidden=true;
}
function render(){
 if(!state.data)return;
 renderTop();renderDriverChange();renderComponents();renderContributions();renderTimeline();renderSectors();renderAlerts();renderTopStocks();renderBreadth();renderFunds();updateNavBadge();
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
function setPlatformView(view,pushHash=true){
 const risk=$('risk-monitor'),strategy=$('strategy-builder'),intro=document.querySelector('.intro'),workspace=document.querySelector('.workspace');
 if(document.body.classList.contains('site-locked')&&view!=='analysis')view='analysis';
 if(risk)risk.hidden=view!=='risk';
 if(strategy)strategy.hidden=view!=='strategy';
 if(intro)intro.hidden=view!=='analysis';
 if(workspace)workspace.hidden=view!=='analysis';
 document.body.classList.toggle('risk-monitor-view',view==='risk');
 document.body.classList.toggle('strategy-lab-view',view==='strategy');
 document.querySelectorAll('.header nav a').forEach(a=>a.classList.toggle('active',a.dataset.platformView===view));
 if(pushHash){
  const hash=view==='risk'?'#risk-monitor':view==='strategy'?'#strategy-builder':'#market';
  if(location.hash!==hash)history.pushState(null,'',hash);
 }
 if(view==='risk')refresh();
 if(view==='strategy')window.FinStrategyBuilder?.refresh?.();
 window.scrollTo({top:0,behavior:'smooth'});
}
function showRisk(pushHash=true){setPlatformView('risk',pushHash);}
function showStrategy(pushHash=true){setPlatformView('strategy',pushHash);}
function showAnalysis(pushHash=false){setPlatformView('analysis',pushHash);}
function openSymbol(symbol){
 showAnalysis();
 const ticker=$('ticker');if(ticker)ticker.value=symbol;
 $('company-form')?.requestSubmit();
 setTimeout(()=>document.getElementById('market')?.scrollIntoView({behavior:'smooth',block:'start'}),50);
}
function bind(){
 document.querySelectorAll('.header nav a').forEach(a=>{
  if(a.dataset.platformView==='risk')a.addEventListener('click',e=>{e.preventDefault();showRisk();});
  else if(a.dataset.platformView==='strategy')a.addEventListener('click',e=>{e.preventDefault();showStrategy();});
  else a.addEventListener('click',()=>showAnalysis());
 });
 $('risk-refresh')?.addEventListener('click',refresh);
 $('risk-stock-rows')?.addEventListener('click',e=>{const b=e.target.closest('[data-risk-symbol]');if(b)openSymbol(b.dataset.riskSymbol);});
 $('risk-market-counts')?.addEventListener('click',e=>{const b=e.target.closest('[data-breadth-group]');if(b)renderBreadthDetail(b.dataset.breadthGroup);});
 $('risk-breadth-detail')?.addEventListener('click',e=>{const stock=e.target.closest('[data-risk-symbol]');if(stock){openSymbol(stock.dataset.riskSymbol);return;}if(e.target.closest('#risk-breadth-detail-close')){state.selectedBreadthGroup=null;$('risk-breadth-detail').hidden=true;}});
 $('risk-fund-chart')?.addEventListener('click',e=>{const b=e.target.closest('[data-fund-symbol]');if(b)renderFundDetail(b.dataset.fundSymbol);});
 $('risk-fund-detail')?.addEventListener('click',e=>{if(e.target.closest('#risk-fund-detail-close')){state.selectedFundSymbol=null;$('risk-fund-detail').hidden=true;}});
 $('risk-sectors')?.addEventListener('click',e=>{const b=e.target.closest('[data-sector-id]');if(b)renderSectorDetail(b.dataset.sectorId);});
 $('risk-sector-detail')?.addEventListener('click',e=>{const stock=e.target.closest('[data-risk-symbol]');if(stock){openSymbol(stock.dataset.riskSymbol);return;}if(e.target.closest('#risk-sector-detail-close')){state.selectedSectorId=null;$('risk-sector-detail').hidden=true;}});
 window.addEventListener('hashchange',()=>{if(location.hash==='#risk-monitor')showRisk(false);else if(location.hash==='#strategy-builder')showStrategy(false);else showAnalysis(false);});
 document.addEventListener('finquery:market-refresh',()=>{if(!$('risk-monitor')?.hidden)refresh();});
}
bind();
if(location.hash==='#risk-monitor')showRisk(false);
setInterval(()=>{if(!$('risk-monitor')?.hidden&&!document.hidden)refresh();},60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!$('risk-monitor')?.hidden)refresh();});
window.FinPlatformViews={openRisk:()=>showRisk(),openStrategy:()=>showStrategy(),openAnalysis:()=>showAnalysis()};
window.FinRiskMonitor={refresh,open:()=>showRisk(),close:showAnalysis,context:()=>state.data};
})();