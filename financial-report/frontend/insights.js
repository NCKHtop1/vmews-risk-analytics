(function(){'use strict';
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const DATA_BASE=new URL('data/',location.href).href;
const state={symbol:'',events:[],reports:[],loaded:false,filter:'all',chart:null,updatedAt:null};
const EVENT_LABELS={agm:'ĐHĐCĐ',stock_dividend:'Cổ tức CP',cash_dividend:'Cổ tức tiền',dividend:'Cổ tức',rights:'Quyền',listing:'Niêm yết',earnings:'KQKD',other:'Sự kiện'};
const EVENT_MARKS={agm:'A',stock_dividend:'D',cash_dividend:'$',dividend:'D',rights:'R',listing:'L',earnings:'E',other:'•'};
const safeURL=value=>{try{const u=new URL(String(value||''));return u.protocol==='https:'?u.href:'';}catch{return'';}};
const date=value=>value&&Number.isFinite(Date.parse(value))?new Date(value+'T00:00:00+07:00').toLocaleDateString('vi-VN'):'—';
const money=value=>Number.isFinite(Number(value))?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:0}).format(Number(value))+' đ':'—';
async function read(name){const r=await fetch(DATA_BASE+name+'?v='+Math.floor(Date.now()/300000),{cache:'no-cache'});if(!r.ok)throw Error(name+' HTTP '+r.status);return r.json();}
function latestReports(){
 const rows=state.reports.filter(x=>x.symbol===state.symbol).sort((a,b)=>String(b.publishedAt).localeCompare(String(a.publishedAt)));
 const seen=new Set();return rows.filter(x=>{const k=String(x.broker||'').toUpperCase();if(seen.has(k))return false;seen.add(k);return true;});
}
function consensus(){
 const rows=latestReports(),targets=rows.map(x=>Number(x.targetPrice)).filter(Number.isFinite).sort((a,b)=>a-b);
 const median=targets.length?(targets.length%2?targets[(targets.length-1)/2]:(targets[targets.length/2-1]+targets[targets.length/2])/2):null;
 const ratings={};for(const r of rows){const k=String(r.recommendation||'Chưa có').toUpperCase();ratings[k]=(ratings[k]||0)+1;}
 return{brokers:rows.length,targetMedian:median,targetMin:targets[0]??null,targetMax:targets.at(-1)??null,ratings};
}
function rows(){
 const events=state.events.filter(x=>x.symbol===state.symbol).map(x=>({...x,_kind:'event',_date:x.date}));
 const reports=state.reports.filter(x=>x.symbol===state.symbol).map(x=>({...x,_kind:'research',_date:x.publishedAt}));
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
 const labels={exRightDate:'Ngày GDKHQ',recordDate:'Ngày đăng ký cuối cùng',payoutDate:'Ngày thanh toán',tradingDate:'Ngày giao dịch',ratio:'Tỷ lệ',entitlement:'Quyền hưởng',additionalShares:'CP bổ sung',totalSharesAfter:'Tổng CP sau thay đổi',revenuePlan2026BillionVnd:'Doanh thu kế hoạch 2026 (tỷ)',netProfitPlan2026BillionVnd:'LNST kế hoạch 2026 (tỷ)',stockDividend:'Cổ tức cổ phiếu',cashDividend:'Cổ tức tiền'};
 return Object.entries(obj||{}).map(([k,v])=>'<div><span>'+esc(labels[k]||k)+'</span><b>'+esc(typeof v==='number'?new Intl.NumberFormat('vi-VN').format(v):v)+'</b></div>').join('');
}
function open(id){
 const rawId=String(id||'').replace(/^(event|research):/,'');
 const item=state.events.find(x=>x.id===rawId)||state.reports.find(x=>x.id===rawId);if(!item)return;
 const dialog=$('insight-detail'),body=$('insight-detail-body');if(!dialog||!body)return;
 const isReport='broker'in item,source=safeURL(isReport?item.sourceUrl:item.source?.url),publisher=isReport?item.broker:item.source?.publisher;
 if(isReport){
  body.innerHTML='<div class="insight-detail-top"><div><span class="insight-kind research">BÁO CÁO CTCK · '+esc(item.broker)+'</span><h3>'+esc(state.symbol)+' · '+esc(item.title)+'</h3><p>'+esc(date(item.publishedAt))+'</p></div><div class="insight-rating">'+(item.recommendation?'<strong>'+esc(item.recommendation)+'</strong>':'')+(Number.isFinite(Number(item.targetPrice))?'<span>Giá mục tiêu '+money(item.targetPrice)+'</span>':'')+'</div></div><div class="insight-attribution">Khuyến nghị và giá mục tiêu là quan điểm của <b>'+esc(item.broker)+'</b>, không phải khuyến nghị của FinQuery.</div>'+(item.summary?'<section class="insight-detail-section"><h4>Tóm tắt FinQuery</h4><p>'+esc(item.summary)+'</p></section>':'')+section('Điểm chính',item.highlights)+section('Yếu tố hỗ trợ',item.catalysts)+section('Rủi ro cần theo dõi',item.risks)+(source?'<a class="insight-source-link" href="'+esc(source)+'" target="_blank" rel="noopener noreferrer">Xem báo cáo / trang nguồn '+esc(publisher||'')+' ↗</a>':'');
 }else{
  body.innerHTML='<div class="insight-detail-top"><div><span class="insight-kind event">'+esc(EVENT_LABELS[item.type]||'SỰ KIỆN')+'</span><h3>'+esc(state.symbol)+' · '+esc(item.title)+'</h3><p>'+esc(date(item.date))+'</p></div></div>'+(item.summary?'<section class="insight-detail-section"><h4>Nội dung</h4><p>'+esc(item.summary)+'</p></section>':'')+(item.details&&Object.keys(item.details).length?'<div class="insight-facts">'+detailRows(item.details)+'</div>':'')+(source?'<a class="insight-source-link" href="'+esc(source)+'" target="_blank" rel="noopener noreferrer">Xem nguồn '+esc(publisher||'')+' ↗</a>':'');
 }
 if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','');
}
function render(){
 const list=$('insight-list'),status=$('insight-status'),summary=$('insight-consensus');if(!list)return;
 const all=rows(),filtered=all.filter(x=>state.filter==='all'||x._kind===state.filter),events=all.filter(x=>x._kind==='event'),reports=all.filter(x=>x._kind==='research'),c=consensus();
 if(status)status.textContent=(state.loaded?'Đã đồng bộ':'Đang tải')+' · '+events.length+' sự kiện · '+reports.length+' báo cáo cho '+(state.symbol||'mã đang xem');
 if(summary)summary.innerHTML=c.brokers?'<span><b>'+c.brokers+'</b> CTCK gần nhất</span>'+(Number.isFinite(c.targetMedian)?'<span>Target trung vị <b>'+money(c.targetMedian)+'</b></span>':''):'<span>Chưa có báo cáo CTCK đã chuẩn hóa cho mã này.</span>';
 list.innerHTML=filtered.slice(0,18).map(x=>x._kind==='research'?'<button type="button" class="insight-card research" data-insight-open="research:'+esc(x.id)+'"><span class="insight-dot">'+esc(String(x.broker||'R').slice(0,4))+'</span><span class="insight-card-copy"><b>'+esc(x.broker)+' · '+esc(x.title)+'</b><small>'+esc(date(x.publishedAt))+(x.recommendation?' · '+esc(x.recommendation):'')+(Number.isFinite(Number(x.targetPrice))?' · Target '+money(x.targetPrice):'')+'</small></span><span class="insight-chevron">›</span></button>':'<button type="button" class="insight-card event" data-insight-open="event:'+esc(x.id)+'"><span class="insight-dot">'+esc(EVENT_MARKS[x.type]||'•')+'</span><span class="insight-card-copy"><b>'+esc(EVENT_LABELS[x.type]||'Sự kiện')+' · '+esc(x.title)+'</b><small>'+esc(date(x.date))+' · '+esc(x.source?.publisher||'Nguồn doanh nghiệp')</small></span><span class="insight-chevron">›</span></button>').join('')||'<div class="insight-empty">Chưa có sự kiện hoặc báo cáo nghiên cứu đã chuẩn hóa cho '+esc(state.symbol||'mã này')+'.</div>';
 document.querySelectorAll('[data-insight-filter]').forEach(b=>b.classList.toggle('active',b.dataset.insightFilter===state.filter));
 syncChart();
}
async function load(){
 try{
  const [e,r]=await Promise.all([read('corporate-events.json'),read('broker-research.json')]);
  state.events=Array.isArray(e.events)?e.events:[];state.reports=Array.isArray(r.reports)?r.reports:[];state.updatedAt=[e.updatedAt,r.updatedAt].filter(Boolean).sort().at(-1)||null;state.loaded=true;
 }catch(error){state.loaded=false;console.warn('FinInsights:',error);}
 render();
}
function select(symbol){state.symbol=String(symbol||'').toUpperCase();render();}
function attachChart(chart){state.chart=chart;syncChart();}
function context(){
 const eventRows=state.events.filter(x=>x.symbol===state.symbol).sort((a,b)=>String(b.date).localeCompare(String(a.date))).slice(0,10);
 const reportRows=state.reports.filter(x=>x.symbol===state.symbol).sort((a,b)=>String(b.publishedAt).localeCompare(String(a.publishedAt))).slice(0,8);
 return{symbol:state.symbol,updatedAt:state.updatedAt,corporateEvents:eventRows,brokerResearch:reportRows.map(x=>({id:x.id,broker:x.broker,publishedAt:x.publishedAt,title:x.title,recommendation:x.recommendation||null,targetPrice:Number.isFinite(Number(x.targetPrice))?Number(x.targetPrice):null,currency:x.currency||'VND',summary:x.summary||'',highlights:(x.highlights||[]).slice(0,5),catalysts:(x.catalysts||[]).slice(0,5),risks:(x.risks||[]).slice(0,5),sourceUrl:x.sourceUrl})),consensus:consensus()};
}
$('insight-filters')?.addEventListener('click',e=>{const b=e.target.closest('[data-insight-filter]');if(!b)return;state.filter=b.dataset.insightFilter;render();});
$('insight-list')?.addEventListener('click',e=>{const b=e.target.closest('[data-insight-open]');if(b)open(b.dataset.insightOpen);});
$('insight-detail-close')?.addEventListener('click',()=>$('insight-detail')?.close());
$('insight-detail')?.addEventListener('click',e=>{if(e.target===$('insight-detail'))$('insight-detail').close();});
window.FinInsights={select,attachChart,context,open,reload:load};
window.FinancialMarket?.registerInsights?.(window.FinInsights);
void load();
})();