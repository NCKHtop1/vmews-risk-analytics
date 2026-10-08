(function(){'use strict';
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const DATA_BASE=new URL('data/',location.href).href;
const state={symbol:'',events:[],reports:[],plans:[],loaded:false,filter:'all',chart:null,updatedAt:null,health:null,eventHealth:null,planHealth:null,researchFilter:'all',eventFilter:'all',compactExpanded:false,researchExpanded:false,eventExpanded:false};
const EVENT_LABELS={agm:'ĐHĐCĐ',egm:'ĐHĐCĐ bất thường',stock_dividend:'Cổ tức CP',cash_dividend:'Cổ tức tiền',dividend:'Cổ tức',bonus_share:'Thưởng CP',rights:'Quyền',rights_issue:'Quyền mua',listing:'Niêm yết',delisting:'Hủy niêm yết',earnings:'KQKD',esop:'ESOP',private_placement:'Phát hành riêng lẻ',buyback:'Mua CP quỹ',shareholder_vote:'Lấy ý kiến CĐ',other:'Sự kiện'};
const EVENT_MARKS={agm:'A',egm:'A',stock_dividend:'S',cash_dividend:'D',dividend:'D',bonus_share:'B',rights:'R',rights_issue:'R',listing:'L',delisting:'X',earnings:'KQ',esop:'E',private_placement:'P',buyback:'T',shareholder_vote:'V',other:'•'};
const RATING_GROUPS=[
 {id:'buy',label:'MUA',match:/MUA|BUY|TĂNG TỶ TRỌNG|OVERWEIGHT|STRONG BUY/i},
 {id:'positive',label:'KHẢ QUAN',match:/KHẢ QUAN|OUTPERFORM/i},
 {id:'neutral',label:'TRUNG LẬP',match:/TRUNG LẬP|NẮM GIỮ|HOLD|MARKET PERFORM|NEUTRAL/i},
 {id:'negative',label:'KÉM KHẢ QUAN',match:/KÉM KHẢ QUAN|GIẢM TỶ TRỌNG|UNDERPERFORM|REDUCE/i},
 {id:'sell',label:'BÁN',match:/BÁN|SELL/i}
];
const safeURL=value=>{try{const u=new URL(String(value||''));return /^https?:$/.test(u.protocol)?u.href:'';}catch{return'';}};
const date=value=>value&&Number.isFinite(Date.parse(value))?new Date(value+'T00:00:00+07:00').toLocaleDateString('vi-VN'):'—';
const money=value=>Number.isFinite(Number(value))?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:0}).format(Number(value))+' đ':'—';
const pct=value=>Number.isFinite(Number(value))?(Number(value)>=0?'+':'')+Number(value).toLocaleString('vi-VN',{maximumFractionDigits:1})+'%':'—';
async function read(name){const r=await fetch(DATA_BASE+name+'?v='+Math.floor(Date.now()/300000),{cache:'no-cache'});if(!r.ok)throw Error(name+' HTTP '+r.status);return r.json();}
function symbolEvents(){return state.events.filter(x=>x.symbol===state.symbol).sort((a,b)=>String(b.date).localeCompare(String(a.date)));}
function symbolReports(){return state.reports.filter(x=>x.symbol===state.symbol).sort((a,b)=>String(b.publishedAt).localeCompare(String(a.publishedAt)));}
function symbolPlans(){return state.plans.filter(x=>x.symbol===state.symbol).sort((a,b)=>(Number(b.year)||0)-(Number(a.year)||0));}
function latestReports(){
 const rows=symbolReports(),seen=new Set();return rows.filter(x=>{const k=String(x.broker||'').toUpperCase();if(seen.has(k))return false;seen.add(k);return true;});
}
function ratingGroup(value){
 const raw=String(value||'').trim();if(!raw)return'other';
 return RATING_GROUPS.find(x=>x.match.test(raw))?.id||'other';
}
function consensus(){
 const rows=latestReports(),targets=rows.map(x=>Number(x.targetPrice)).filter(Number.isFinite).sort((a,b)=>a-b);
 const median=targets.length?(targets.length%2?targets[(targets.length-1)/2]:(targets[targets.length/2-1]+targets[targets.length/2])/2):null;
 const ratings={};for(const r of rows){const k=ratingGroup(r.recommendation);ratings[k]=(ratings[k]||0)+1;}
 return{brokers:rows.length,targetMedian:median,targetMin:targets[0]??null,targetMax:targets.at(-1)??null,targets:targets.length,ratings,latest:rows};
}
function rows(){
 const events=symbolEvents().map(x=>({...x,_kind:'event',_date:x.date}));
 const reports=symbolReports().map(x=>({...x,_kind:'research',_date:x.publishedAt}));
 return [...events,...reports].sort((a,b)=>String(b._date).localeCompare(String(a._date)));
}
function markerItems(){
 return rows().map(x=>x._kind==='research'?{
  id:'research:'+x.id,date:x.publishedAt,kind:'research',label:String(x.broker||'R').slice(0,4).toUpperCase(),title:(x.broker||'CTCK')+' · '+x.title,tone:'research'
 }:{
  id:'event:'+x.id,date:x.date,kind:'event',label:EVENT_MARKS[x.type]||'•',title:(EVENT_LABELS[x.type]||'Sự kiện')+' · '+x.title,tone:x.type||'event'
 });
}
function syncChart(){state.chart?.setInsights?.(markerItems(),open);}
function section(title,items){
 if(!Array.isArray(items)||!items.length)return'';
 return '<section class="insight-detail-section"><h4>'+esc(title)+'</h4><ul>'+items.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul></section>';
}
function detailRows(obj){
 const labels={exRightDate:'Ngày GDKHQ',recordDate:'Ngày đăng ký cuối cùng',payoutDate:'Ngày thanh toán',paymentDate:'Ngày thanh toán',meetingDate:'Ngày họp',tradingDate:'Ngày giao dịch',ratio:'Tỷ lệ',ratioText:'Tỷ lệ',entitlement:'Quyền hưởng',cashAmount:'Tiền/cp',stockRate:'Tỷ lệ cổ phiếu',additionalShares:'CP bổ sung',totalSharesAfter:'Tổng CP sau thay đổi',revenuePlan2026BillionVnd:'Doanh thu kế hoạch 2026 (tỷ)',netProfitPlan2026BillionVnd:'LNST kế hoạch 2026 (tỷ)',stockDividend:'Cổ tức cổ phiếu',cashDividend:'Cổ tức tiền'};
 return Object.entries(obj||{}).map(([k,v])=>'<div><span>'+esc(labels[k]||k)+'</span><b>'+esc(typeof v==='number'?new Intl.NumberFormat('vi-VN').format(v):v)+'</b></div>').join('');
}
function open(id){
 const rawId=String(id||'').replace(/^(event|research):/,'');
 const item=state.events.find(x=>x.id===rawId)||state.reports.find(x=>x.id===rawId);if(!item)return;
 const dialog=$('insight-detail'),body=$('insight-detail-body');if(!dialog||!body)return;
 const isReport='broker'in item,source=safeURL(isReport?item.sourceUrl:item.source?.url),publisher=isReport?item.broker:item.source?.publisher;
 if(isReport){
  const quote=window.FinancialMarket?.context?.().quote||{},up=Number.isFinite(Number(item.targetPrice))&&Number.isFinite(Number(quote.price))&&Number(quote.price)>0?(Number(item.targetPrice)/Number(quote.price)-1)*100:null;
  body.innerHTML='<div class="insight-detail-top"><div><span class="insight-kind research">BÁO CÁO CTCK · '+esc(item.broker)+'</span><h3>'+esc(state.symbol)+' · '+esc(item.title)+'</h3><p>'+esc(date(item.publishedAt))+'</p></div><div class="insight-rating">'+(item.recommendation?'<strong>'+esc(item.recommendation)+'</strong>':'')+(Number.isFinite(Number(item.targetPrice))?'<span>Giá mục tiêu '+money(item.targetPrice)+(Number.isFinite(up)?' · '+pct(up):'')+'</span>':'')+'</div></div><div class="insight-attribution">Khuyến nghị và giá mục tiêu là quan điểm của <b>'+esc(item.broker)+'</b>, không phải khuyến nghị của FinQuery.</div>'+(item.summary?'<section class="insight-detail-section"><h4>Tóm tắt FinQuery</h4><p>'+esc(item.summary)+'</p></section>':'')+section('Điểm chính',item.highlights)+section('Yếu tố hỗ trợ',item.catalysts)+section('Rủi ro cần theo dõi',item.risks)+(source?'<a class="insight-source-link" href="'+esc(source)+'" target="_blank" rel="noopener noreferrer">Xem báo cáo / trang nguồn '+esc(publisher||'')+' ↗</a>':'');
 }else{
  body.innerHTML='<div class="insight-detail-top"><div><span class="insight-kind event">'+esc(EVENT_LABELS[item.type]||'SỰ KIỆN')+'</span><h3>'+esc(state.symbol)+' · '+esc(item.title)+'</h3><p>'+esc(date(item.date))+'</p></div></div>'+(item.summary?'<section class="insight-detail-section"><h4>Nội dung</h4><p>'+esc(item.summary)+'</p></section>':'')+(item.details&&Object.keys(item.details).length?'<div class="insight-facts">'+detailRows(item.details)+'</div>':'')+(source?'<a class="insight-source-link" href="'+esc(source)+'" target="_blank" rel="noopener noreferrer">Xem nguồn '+esc(publisher||'')+' ↗</a>':'');
 }
 if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','');
}
function compactCard(x){
 return x._kind==='research'
 ?'<button type="button" class="insight-card research" data-insight-open="research:'+esc(x.id)+'"><span class="insight-dot">'+esc(String(x.broker||'R').slice(0,4))+'</span><span class="insight-card-copy"><b>'+esc(x.broker)+' · '+esc(x.title)+'</b><small>'+esc(date(x.publishedAt))+(x.recommendation?' · '+esc(x.recommendation):'')+(Number.isFinite(Number(x.targetPrice))?' · Target '+money(x.targetPrice):'')+'</small></span><span class="insight-chevron">›</span></button>'
 :'<button type="button" class="insight-card event" data-insight-open="event:'+esc(x.id)+'"><span class="insight-dot">'+esc(EVENT_MARKS[x.type]||'•')+'</span><span class="insight-card-copy"><b>'+esc(EVENT_LABELS[x.type]||'Sự kiện')+' · '+esc(x.title)+'</b><small>'+esc(date(x.date))+' · '+esc(x.source?.publisher||'Nguồn doanh nghiệp')+'</small></span><span class="insight-chevron">›</span></button>';
}
function renderCompact(){
 const list=$('insight-list'),status=$('insight-status'),summary=$('insight-consensus');if(!list)return;
 const all=rows(),filtered=all.filter(x=>state.filter==='all'||x._kind===state.filter),events=all.filter(x=>x._kind==='event'),reports=all.filter(x=>x._kind==='research'),c=consensus();
 if(status){const coverage=state.health&&Number.isFinite(state.health.sourcesTotal)?' · '+(state.health.sourcesReachable||0)+'/'+state.health.sourcesTotal+' nguồn research truy cập được':'';status.textContent=(state.loaded?'Đã đồng bộ':'Đang tải')+' · '+events.length+' sự kiện · '+reports.length+' báo cáo cho '+(state.symbol||'mã đang xem')+coverage;}
 if(summary)summary.innerHTML=c.brokers?'<span><b>'+c.brokers+'</b> CTCK gần nhất</span>'+(Number.isFinite(c.targetMedian)?'<span>Target trung vị <b>'+money(c.targetMedian)+'</b></span><span>Khoảng target <b>'+money(c.targetMin)+'–'+money(c.targetMax)+'</b></span>':''):'<span>Chưa có báo cáo CTCK đã chuẩn hóa cho mã này.</span>';
 if(!state.compactExpanded){
  list.innerHTML='<button type="button" class="insight-summary-toggle" data-insight-expand="more"><span><b>Sự kiện doanh nghiệp</b><small>'+events.length+' sự kiện đã chuẩn hóa</small></span><span><b>Báo cáo CTCK</b><small>'+reports.length+' báo cáo · '+c.brokers+' CTCK gần nhất</small></span><i class="clean-chevron down" aria-hidden="true"></i></button>';
 }else{
  list.innerHTML=(filtered.map(compactCard).join('')||'<div class="insight-empty">Chưa có sự kiện hoặc báo cáo nghiên cứu đã chuẩn hóa cho '+esc(state.symbol||'mã này')+'.</div>')+(filtered.length?'<button type="button" class="insight-more-toggle" data-insight-expand="less">Thu gọn <span class="clean-chevron up" aria-hidden="true"></span></button>':'');
 }
 document.querySelectorAll('[data-insight-filter]').forEach(b=>b.classList.toggle('active',b.dataset.insightFilter===state.filter));
}
function ratingLabel(group){return RATING_GROUPS.find(x=>x.id===group)?.label||'KHÁC';}
function renderRatingDistribution(c){
 const host=$('idea-rating-distribution'),total=$('idea-rating-total');if(!host)return;
 const n=Math.max(1,c.brokers),keys=[...RATING_GROUPS.map(x=>x.id),'other'];
 host.innerHTML=keys.filter(k=>(c.ratings[k]||0)>0).map(k=>{const count=c.ratings[k]||0,p=Math.round(count*100/n);return '<button type="button" data-idea-rating="'+esc(k)+'"><span><b>'+esc(ratingLabel(k))+'</b><small>'+count+' báo cáo</small></span><em>'+p+'%</em><i><u style="width:'+p+'%"></u></i></button>';}).join('')||'<div class="idea-empty">Chưa đủ dữ liệu rating.</div>';
 if(total)total.textContent=c.brokers?c.brokers+' CTCK':'';
}
function renderTargetZone(c,price){
 const host=$('idea-target-zone');if(!host)return;
 if(!c.targets){host.innerHTML='<div class="idea-empty">Chưa đủ giá mục tiêu để tạo vùng đồng thuận.</div>';return;}
 const vals=[c.targetMin,c.targetMax,price].filter(Number.isFinite),min=Math.min(...vals),max=Math.max(...vals),span=Math.max(1,max-min),pos=v=>((v-min)/span*100).toFixed(1);
 host.innerHTML='<div class="target-axis"><div class="target-range" style="left:'+pos(c.targetMin)+'%;width:'+(Number(pos(c.targetMax))-Number(pos(c.targetMin))).toFixed(1)+'%"></div>'+(Number.isFinite(price)?'<span class="target-now" style="left:'+pos(price)+'%"><i></i><b>'+money(price)+'</b><small>Giá hiện tại</small></span>':'')+'<span class="target-mid" style="left:'+pos(c.targetMedian)+'%"><i></i><b>'+money(c.targetMedian)+'</b><small>Trung vị</small></span></div><div class="target-minmax"><span>'+money(c.targetMin)+'</span><span>'+money(c.targetMax)+'</span></div>';
}
function renderDashboard(){
 const title=$('idea-title');if(!title)return;
 const reports=symbolReports(),events=symbolEvents(),plans=symbolPlans(),c=consensus(),quote=window.FinancialMarket?.context?.().quote||{},price=Number(quote.price),change=Number(quote.changePct);
 title.textContent='Investment Ideas · '+(state.symbol||'—');if($('idea-symbol-title'))$('idea-symbol-title').textContent=(state.symbol||'—')+' · Báo cáo phân tích';
 const badge=$('idea-consensus-badge');const dominant=Object.entries(c.ratings).sort((a,b)=>b[1]-a[1])[0]?.[0];
 if(badge){badge.textContent=c.brokers?('Đồng thuận: '+ratingLabel(dominant)):'Chưa có đồng thuận';badge.dataset.rating=dominant||'none';}
 const healthParts=[];if(state.health?.sourcesTotal)healthParts.push((state.health.sourcesReachable||0)+'/'+state.health.sourcesTotal+' nguồn research');if(state.eventHealth?.sourcesTotal)healthParts.push((state.eventHealth.sourcesReachable||0)+'/'+state.eventHealth.sourcesTotal+' nguồn event');if(state.health?.symbolsTotal)healthParts.push((state.health.symbolsCovered||0)+'/'+state.health.symbolsTotal+' mã có research');
 if($('idea-health'))$('idea-health').textContent='Đã đồng bộ '+reports.length+' báo cáo · '+events.length+' sự kiện'+(healthParts.length?' · '+healthParts.join(' · '):'');
 if($('idea-meta'))$('idea-meta').innerHTML='<span><b>'+c.brokers+'</b> CTCK</span><span><b>'+reports.length+'</b> báo cáo</span><span><b>'+events.length+'</b> sự kiện</span><span><b>'+plans.length+'</b> chỉ tiêu kế hoạch</span><span>Cập nhật <b>'+esc(state.updatedAt?new Date(state.updatedAt).toLocaleDateString('vi-VN'):'—')+'</b></span>';
 const latestPlanYear=Math.max(0,...plans.map(x=>Number(x.year)||0)),latestPlans=plans.filter(x=>Number(x.year)===latestPlanYear),planLabels={revenue:'Doanh thu',pretaxProfit:'LNTT',netProfit:'LNST'};
 if($('idea-plan-year'))$('idea-plan-year').textContent=latestPlanYear?String(latestPlanYear):'';
 if($('idea-plan-list'))$('idea-plan-list').innerHTML=latestPlans.length?latestPlans.map(p=>'<a class="idea-plan-row" href="'+esc(p.sourceUrl||'#')+'" target="_blank" rel="noopener noreferrer"><span><b>'+esc(planLabels[p.metric]||p.metric)+'</b><small>Kế hoạch '+(Number.isFinite(Number(p.plan))?fmt(Number(p.plan),1):'—')+' · Thực hiện '+(Number.isFinite(Number(p.actual))?fmt(Number(p.actual),1):'—')+'</small></span><strong>'+esc(Number.isFinite(Number(p.completionPct))?Number(p.completionPct).toLocaleString('vi-VN',{maximumFractionDigits:1})+'%':'—')+'</strong></a>').join(''):'<div class="idea-empty">Chưa có dữ liệu kế hoạch năm.</div>';
 if($('idea-price'))$('idea-price').textContent=Number.isFinite(price)?money(price):'—';if($('idea-price-change')){$('idea-price-change').textContent=Number.isFinite(change)?pct(change):'';$('idea-price-change').className=change>0?'positive':change<0?'negative':'';}
 if($('idea-target'))$('idea-target').textContent=Number.isFinite(c.targetMedian)?money(c.targetMedian):'—';
 const upside=Number.isFinite(price)&&price>0&&Number.isFinite(c.targetMedian)?(c.targetMedian/price-1)*100:null;if($('idea-upside')){$('idea-upside').textContent=Number.isFinite(upside)?'Upside kỳ vọng '+pct(upside):'';$('idea-upside').className=upside>0?'positive':upside<0?'negative':'';}
 if($('idea-target-range'))$('idea-target-range').textContent=c.targets?money(c.targetMin)+' – '+money(c.targetMax):'—';if($('idea-target-count'))$('idea-target-count').textContent=c.targets?c.targets+' target gần nhất':'';
 renderRatingDistribution(c);renderTargetZone(c,Number.isFinite(price)?price:null);
 const researchFilters=[{id:'all',label:'Tất cả ('+reports.length+')'},...RATING_GROUPS.map(g=>({id:g.id,label:g.label+' ('+reports.filter(r=>ratingGroup(r.recommendation)===g.id).length+')'})),{id:'other',label:'Khác ('+reports.filter(r=>ratingGroup(r.recommendation)==='other').length+')'}];
 if($('idea-research-filters'))$('idea-research-filters').innerHTML=researchFilters.filter(x=>!/(0)/.test(x.label)||x.id==='all').map(x=>'<button type="button" class="'+(state.researchFilter===x.id?'active':'')+'" data-idea-research-filter="'+esc(x.id)+'">'+esc(x.label)+'</button>').join('');
 const shownReports=reports.filter(r=>state.researchFilter==='all'||ratingGroup(r.recommendation)===state.researchFilter),reportPreview=shownReports.slice(0,state.researchExpanded?shownReports.length:4);if($('idea-report-count'))$('idea-report-count').textContent=shownReports.length+' báo cáo';
 if($('idea-report-list'))$('idea-report-list').innerHTML=reportPreview.map(r=>'<button type="button" class="idea-report-item" data-insight-open="research:'+esc(r.id)+'"><div class="idea-report-top"><span>'+esc(r.broker)+'</span>'+(r.recommendation?'<em data-rating="'+esc(ratingGroup(r.recommendation))+'">'+esc(r.recommendation)+'</em>':'')+'</div><b>'+esc(r.symbol)+' · '+esc(r.title)+'</b><small>'+esc(date(r.publishedAt))+(Number.isFinite(Number(r.targetPrice))?' · '+money(r.targetPrice):'')+'</small>'+(r.summary?'<p>'+esc(r.summary)+'</p>':'')+'<u>Xem chi tiết ›</u></button>').join('')+(shownReports.length>4?'<button type="button" class="idea-more-toggle" data-idea-research-expand="'+(state.researchExpanded?'less':'more')+'">'+(state.researchExpanded?'Thu gọn':'Xem thêm '+(shownReports.length-reportPreview.length)+' báo cáo')+' <span class="clean-chevron '+(state.researchExpanded?'up':'down')+'" aria-hidden="true"></span></button>':'')||'<div class="idea-empty">Không có báo cáo phù hợp bộ lọc.</div>';
 const types=[...new Set(events.map(e=>e.type))];if($('idea-event-filters'))$('idea-event-filters').innerHTML=[{id:'all',label:'Tất cả ('+events.length+')'},...types.map(t=>({id:t,label:(EVENT_LABELS[t]||t)+' ('+events.filter(e=>e.type===t).length+')'}))].map(x=>'<button type="button" class="'+(state.eventFilter===x.id?'active':'')+'" data-idea-event-filter="'+esc(x.id)+'">'+esc(x.label)+'</button>').join('');
 const shownEvents=events.filter(e=>state.eventFilter==='all'||e.type===state.eventFilter),eventPreview=shownEvents.slice(0,state.eventExpanded?shownEvents.length:6);if($('idea-event-count'))$('idea-event-count').textContent=shownEvents.length+' sự kiện';
 if($('idea-event-list'))$('idea-event-list').innerHTML=eventPreview.map(e=>'<button type="button" class="idea-event-item" data-insight-open="event:'+esc(e.id)+'"><span class="idea-event-mark '+esc(e.type||'other')+'">'+esc(EVENT_MARKS[e.type]||'•')+'</span><span><b>'+esc(EVENT_LABELS[e.type]||'Sự kiện')+' · '+esc(e.title)+'</b><small>'+esc(date(e.date))+' · '+esc(e.source?.publisher||'Nguồn công bố')+'</small>'+(e.summary?'<p>'+esc(e.summary)+'</p>':'')+'</span><i>›</i></button>').join('')+(shownEvents.length>6?'<button type="button" class="idea-more-toggle wide" data-idea-event-expand="'+(state.eventExpanded?'less':'more')+'">'+(state.eventExpanded?'Thu gọn':'Xem thêm '+(shownEvents.length-eventPreview.length)+' sự kiện')+' <span class="clean-chevron '+(state.eventExpanded?'up':'down')+'" aria-hidden="true"></span></button>':'')||'<div class="idea-empty">Chưa có sự kiện phù hợp bộ lọc.</div>';
}
function render(){renderCompact();renderDashboard();syncChart();}
async function load(){
 try{
  const [e,r,h,eh,p,ph]=await Promise.all([read('corporate-events.json'),read('broker-research.json'),read('insights-status.json').catch(()=>null),read('event-status.json').catch(()=>null),read('business-plans.json').catch(()=>({items:[]})),read('business-plan-status.json').catch(()=>null)]);
  state.events=Array.isArray(e.events)?e.events:[];state.reports=Array.isArray(r.reports)?r.reports:[];state.plans=Array.isArray(p.items)?p.items:[];state.health=h;state.eventHealth=eh;state.planHealth=ph;state.updatedAt=[e.updatedAt,r.updatedAt,p?.updatedAt,h?.checkedAt,eh?.checkedAt,ph?.checkedAt].filter(Boolean).sort().at(-1)||null;state.loaded=true;
 }catch(error){state.loaded=false;console.warn('FinInsights:',error);}
 render();
}
function select(symbol){state.symbol=String(symbol||'').toUpperCase();state.researchFilter='all';state.eventFilter='all';state.compactExpanded=false;state.researchExpanded=false;state.eventExpanded=false;render();}
function attachChart(chart){state.chart=chart;syncChart();}
function context(){
 const eventRows=symbolEvents().slice(0,12),reportRows=symbolReports().slice(0,10),planRows=symbolPlans().slice(0,12);
 return{symbol:state.symbol,updatedAt:state.updatedAt,corporateEvents:eventRows,businessPlans:planRows,brokerResearch:reportRows.map(x=>({id:x.id,broker:x.broker,brokerName:x.brokerName||x.broker,publishedAt:x.publishedAt,title:x.title,recommendation:x.recommendation||null,targetPrice:Number.isFinite(Number(x.targetPrice))?Number(x.targetPrice):null,currency:x.currency||'VND',summary:x.summary||'',highlights:(x.highlights||[]).slice(0,5),catalysts:(x.catalysts||[]).slice(0,5),risks:(x.risks||[]).slice(0,5),sourceUrl:x.sourceUrl})),consensus:consensus(),sourceHealth:state.health?.sources||[],eventSourceHealth:state.eventHealth?.sources||[],planSourceHealth:state.planHealth?.sources||[]};
}
$('insight-filters')?.addEventListener('click',e=>{const b=e.target.closest('[data-insight-filter]');if(!b)return;state.filter=b.dataset.insightFilter;state.compactExpanded=false;render();});
$('insight-list')?.addEventListener('click',e=>{const b=e.target.closest('[data-insight-open]');if(b){open(b.dataset.insightOpen);return;}const more=e.target.closest('[data-insight-expand]');if(more){state.compactExpanded=more.dataset.insightExpand==='more';renderCompact();}});
$('idea-rating-distribution')?.addEventListener('click',e=>{const b=e.target.closest('[data-idea-rating]');if(!b)return;state.researchFilter=b.dataset.ideaRating;renderDashboard();});
$('idea-research-filters')?.addEventListener('click',e=>{const b=e.target.closest('[data-idea-research-filter]');if(!b)return;state.researchFilter=b.dataset.ideaResearchFilter;state.researchExpanded=false;renderDashboard();});
$('idea-event-filters')?.addEventListener('click',e=>{const b=e.target.closest('[data-idea-event-filter]');if(!b)return;state.eventFilter=b.dataset.ideaEventFilter;state.eventExpanded=false;renderDashboard();});
$('idea-report-list')?.addEventListener('click',e=>{const b=e.target.closest('[data-insight-open]');if(b){open(b.dataset.insightOpen);return;}const more=e.target.closest('[data-idea-research-expand]');if(more){state.researchExpanded=more.dataset.ideaResearchExpand==='more';renderDashboard();}});
$('idea-event-list')?.addEventListener('click',e=>{const b=e.target.closest('[data-insight-open]');if(b){open(b.dataset.insightOpen);return;}const more=e.target.closest('[data-idea-event-expand]');if(more){state.eventExpanded=more.dataset.ideaEventExpand==='more';renderDashboard();}});
$('insight-detail-close')?.addEventListener('click',()=>$('insight-detail')?.close());
$('insight-detail')?.addEventListener('click',e=>{if(e.target===$('insight-detail'))$('insight-detail').close();});
window.FinInsights={select,attachChart,context,open,reload:load};
window.FinancialMarket?.registerInsights?.(window.FinInsights);
void load();
})();