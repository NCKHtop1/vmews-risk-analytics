(function(){'use strict';
const $=id=>document.getElementById(id);
const SOURCE='https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/finquery-liquidity.json';
const nf=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2});
const fmt=(n,d=2)=>typeof n==='number'&&Number.isFinite(n)?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:d}).format(n):'—';
const esc=t=>String(t??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const dateVN=iso=>/^\d{4}-\d\d-\d\d$/.test(String(iso||''))?iso.slice(8,10)+'/'+iso.slice(5,7)+'/'+iso.slice(0,4):'—';
const monthVN=iso=>/^\d{4}-(0[1-9]|1[0-2])$/.test(String(iso||''))?iso.slice(5,7)+'/'+iso.slice(0,4):'—';
const safeURL=(url,hostname)=>{try{let u=new URL(url);return u.protocol==='https:'&&u.hostname===hostname?u.href:'';}catch{return'';}};
const state={payload:null,derivativeMode:'openInterest',loading:false,manual:[],canEditOn:false,onHistory:[],onRange:'1M',onYear:'all',onMonth:'all'};
const target=$('macro-liquidity-overview');
if(!target)return;
function miniLine(points,{unit='',title='',color='#2e74bb',width=640}={}){
 if(points.length<2)return'<div class="macro-no-chart">Chưa có dữ liệu.</div>';
 const values=points.map(p=>p.value),min=Math.min(...values),max=Math.max(...values),pad=Math.max((max-min)*.16,Math.abs(max)*.07,.03);
 const low=min-pad,high=max+pad,W=Math.max(250,Math.min(950,Math.floor(Number(width)||640))),compact=W<480;
 const H=232,L=49,R=22,T=18,B=39;
 const x=i=>L+(W-L-R)*i/(points.length-1),y=v=>T+(H-T-B)*(high-v)/(high-low);
 const grid=Array.from({length:4},(_,i)=>{const v=low+(high-low)*i/3,py=y(v);return'<line x1="'+L+'" y1="'+py+'" x2="'+(W-R)+'" y2="'+py+'" stroke="#e8edf4"/><text x="'+(L-7)+'" y="'+(py+4)+'" font-size="11" text-anchor="end" fill="#8491a4">'+fmt(v,1)+'</text>';}).join('');
 const line=points.map((p,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(p.value).toFixed(1)).join(' ');
 const labelWidth=compact?57:83,gap=compact?12:18;
 const limit=Math.max(2,Math.min(5,Math.floor((W-L-R+gap)/(labelWidth+gap))));
 const ticks=[...new Set(Array.from({length:limit},(_,i)=>Math.round(i*(points.length-1)/(limit-1))))];
 const labels=ticks.map(i=>{const p=points[i],full=dateVN(p.date),display=compact?full.slice(0,5):full;
  return'<text data-on-tick="'+i+'" x="'+x(i).toFixed(1)+'" y="'+(H-9)+'" text-anchor="'+(i===0?'start':i===points.length-1?'end':'middle')+'" font-size="'+(compact?10:11)+'" fill="#74869f">'+esc(display)+'</text>';
 }).join('');
 const exactRate=n=>new Intl.NumberFormat('vi-VN',{minimumFractionDigits:2,maximumFractionDigits:4}).format(n);
 const circles=points.map((p,i)=>'<circle data-on-point="'+i+'" data-on-date="'+esc(dateVN(p.date))+'" data-on-rate="'+esc(exactRate(p.value))+'" cx="'+x(i).toFixed(1)+'" cy="'+y(p.value).toFixed(1)+'" r="'+(i===points.length-1?4.8:3.1)+'" fill="'+esc(color)+'" aria-hidden="true"/>').join('');
 const guide='<line data-on-guide x1="0" x2="0" y1="'+T+'" y2="'+(H-B)+'" stroke="#90aedc" stroke-width="1.3" stroke-dasharray="4 4" pointer-events="none" visibility="hidden"/>';
 const focus='<circle data-on-focus cx="0" cy="0" r="7" fill="#fff" stroke="'+esc(color)+'" stroke-width="2.5" pointer-events="none" visibility="hidden"/>';
 return'<svg viewBox="0 0 '+W+' '+H+'" data-on-width="'+W+'" data-on-left="'+L+'" data-on-right="'+R+'" class="macro-trend-svg money-on-trend" role="img" tabindex="0" aria-label="'+esc(title+'. Di chuột, chạm hoặc dùng phím mũi tên để xem số liệu từng ngày.')+'">'+grid+'<path d="'+line+'" stroke="'+esc(color)+'" stroke-width="2.8" stroke-linejoin="round" stroke-linecap="round" fill="none"/>'+circles+guide+focus+labels+'</svg>';
}
// The tooltip reads only actual dated observations plotted in the SVG.
function bindONTooltip(){
 const host=$('money-on'),svg=host?.querySelector?.('svg.money-on-trend');
 if(!svg||typeof svg.addEventListener!=='function')return;
 const wrapper=svg.closest('.money-on-interactive'),tooltip=wrapper?.querySelector('.money-on-tooltip');
 const nodes=[...svg.querySelectorAll('[data-on-point]')],guide=svg.querySelector('[data-on-guide]'),focus=svg.querySelector('[data-on-focus]');
 if(!tooltip||!nodes.length)return;
 const width=Number(svg.getAttribute('data-on-width'))||640;
 const left=Number(svg.getAttribute('data-on-left'))||49,right=Number(svg.getAttribute('data-on-right'))||22;
 const hide=()=>{tooltip.hidden=true;guide?.setAttribute('visibility','hidden');focus?.setAttribute('visibility','hidden');};
 const nearest=clientX=>{
  const r=svg.getBoundingClientRect();
  if(!Number.isFinite(clientX)||!r.width)return nodes.length-1;
  const logical=(clientX-r.left)*width/r.width;
  return Math.max(0,Math.min(nodes.length-1,Math.round(((logical-left)/(width-left-right))*(nodes.length-1))));
 };
 const show=index=>{
  const i=Math.max(0,Math.min(nodes.length-1,index)),dot=nodes[i];
  if(!dot)return;
  const dt=dot.getAttribute('data-on-date'),rate=dot.getAttribute('data-on-rate');
  const cx=Number(dot.getAttribute('cx')),cy=Number(dot.getAttribute('cy'));
  const r=svg.getBoundingClientRect(),wr=wrapper.getBoundingClientRect();
  const px=r.left-wr.left+cx*r.width/width,py=r.top-wr.top+cy*r.height/232;
  const margin=Math.min(78,wr.width/2),below=py<67;
  tooltip.querySelector('[data-on-tooltip-date]').textContent=dt;
  tooltip.querySelector('[data-on-tooltip-rate]').textContent=rate;
  tooltip.style.left=Math.max(margin,Math.min(wr.width-margin,px))+'px';
  tooltip.style.top=(below?py+16:py-13)+'px';
  tooltip.classList.toggle('is-below',below);
  tooltip.hidden=false;
  guide?.setAttribute('x1',cx);guide?.setAttribute('x2',cx);
  guide?.setAttribute('visibility','visible');
  focus?.setAttribute('cx',cx);focus?.setAttribute('cy',cy);focus?.setAttribute('visibility','visible');
  svg.dataset.activePoint=String(i);
 };
 svg.addEventListener('pointermove',event=>{if(event.pointerType!=='touch')show(nearest(event.clientX));});
 svg.addEventListener('pointerdown',event=>{if(event.pointerType==='touch'||event.pointerType==='pen')show(nearest(event.clientX));});
 svg.addEventListener('click',event=>{if(Number.isFinite(event.clientX))show(nearest(event.clientX));});
 svg.addEventListener('pointerleave',event=>{if(event.pointerType!=='touch'&&event.pointerType!=='pen')hide();});
 svg.addEventListener('focus',()=>show(nodes.length-1));
 svg.addEventListener('blur',hide);
 svg.addEventListener('keydown',event=>{
  if(!['ArrowLeft','ArrowRight','Home','End','Escape'].includes(event.key))return;
  event.preventDefault();
  if(event.key==='Escape'){hide();return;}
  const i=Number.isInteger(Number(svg.dataset.activePoint))?Number(svg.dataset.activePoint):nodes.length-1;
  show(event.key==='Home'?0:event.key==='End'?nodes.length-1:i+(event.key==='ArrowLeft'?-1:1));
 });
}
function tenorCurve(points,{title='',unit='',color='#2e74bb',width=600}={}){
 const pts=(Array.isArray(points)?points:[]).filter(p=>p&&p.tenor&&Number.isFinite(p.value));
 if(pts.length<2)return'<div class="macro-no-chart">Chưa có dữ liệu.</div>';
 const W=Math.max(270,Math.min(900,Math.round(width||600))),H=226,L=52,R=22,T=20,B=38;
 const vals=pts.map(p=>p.value),min=Math.min(...vals),max=Math.max(...vals);
 const pad=Math.max((max-min)*.15,Math.abs(max)*.07,.05),lo=min-pad,hi=max+pad;
 const x=i=>L+(W-L-R)*i/(pts.length-1),y=v=>T+(H-T-B)*(hi-v)/(hi-lo);
 const grid=Array.from({length:4},(_,i)=>{
   const v=lo+(hi-lo)*i/3,py=y(v);
   return'<line x1="'+L+'" x2="'+(W-R)+'" y1="'+py.toFixed(1)+'" y2="'+py.toFixed(1)+'" stroke="'+(Math.abs(v)<.0001?'#b8cde5':'#e7edf5')+'"/>'+
    '<text x="'+(L-7)+'" y="'+(py+4).toFixed(1)+'" text-anchor="end" font-size="10" fill="#8191a4">'+esc(fmt(v,2))+'</text>';
 }).join('');
 const path=pts.map((p,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(p.value).toFixed(1)).join(' ');
 const budget=W<420?4:W<690?6:10,step=Math.max(1,Math.ceil((pts.length-1)/(budget-1)));
 const tickIndices=[...new Set([...pts.map((p,i)=>i).filter(i=>i%step===0),pts.length-1])];
 const labels=tickIndices.map(i=>'<text x="'+x(i).toFixed(1)+'" y="'+(H-9)+'" data-tenor-label="'+esc(pts[i].tenor)+'" text-anchor="'+(i===0?'start':i===pts.length-1?'end':'middle')+'" font-size="10" fill="#71859c">'+esc(pts[i].tenor)+'</text>').join('');
 const precise=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:6});
 const circles=pts.map((p,i)=>'<circle data-tenor-point="'+esc(p.tenor)+'" data-fq-point="'+i+'" data-fq-x="'+x(i).toFixed(1)+'" data-fq-y="'+y(p.value).toFixed(1)+'" data-fq-label="'+esc(p.tenor)+'" data-fq-series="'+esc(title||'Đường cong kỳ hạn')+'" data-fq-value="'+esc(precise.format(p.value))+'" data-fq-unit="'+esc(unit)+'" cx="'+x(i).toFixed(1)+'" cy="'+y(p.value).toFixed(1)+'" r="'+(i===pts.length-1?4.6:3.4)+'" fill="'+color+'" stroke="white" stroke-width="1"/>').join('');
 let zero='';
 if(lo<0&&hi>0){
  const py=y(0);zero='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+py.toFixed(1)+'" y2="'+py.toFixed(1)+'" stroke="#9eb0c9" stroke-dasharray="4 3" stroke-width="1.2"/>';
 }
 return'<svg class="money-tenor-curve" viewBox="0 0 '+W+' '+H+'" data-fq-inspect="tenor" data-fq-top="'+T+'" data-fq-bottom="'+(H-B)+'" data-fq-color="'+color+'" tabindex="0" role="img" aria-label="'+esc(title+' · '+pts.length+' kỳ hạn · '+unit)+'">'+grid+zero+
  '<path d="'+path+'" stroke="'+color+'" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'+circles+labels+'</svg>';
}
// Download exactly the verified curve shown on screen, never an unvalidated source file.
function curveDownloadButton(kind,title){
 const svg='<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12m-5-5 5 5 5-5M5 17v3h14v-3"/></svg>';
 return '<button type="button" class="money-vbma-download" data-download-curve="'+esc(kind)+'" title="'+esc('Tải CSV '+title)+'" aria-label="'+esc('Tải CSV '+title)+'">'+svg+'</button>';
}
function downloadCurveCsv(kind){
 const labels={swap:'Hoán đổi USD/VND',gov_bond:'Lợi suất trái phiếu Chính phủ',fi_bond:'Trái phiếu và chứng chỉ tiền gửi',short_benchmark:'Lãi suất tham chiếu ngắn hạn'};
 if(!Object.prototype.hasOwnProperty.call(labels,kind))return;
 const p=state.payload||{};
 const row=kind==='swap'?p.vbmaSwap:(p.vbmaCurves||p.curves||{})[kind];
 if(!row||!['verified','retained'].includes(row.status)||!Array.isArray(row.points)||
    (kind!=='swap'&&!['approved','source_attributed'].includes(row.licenseStatus))||
    !/^\d{4}-\d{2}-\d{2}$/.test(row.asOf||''))return;
 const points=row.points.filter(x=>x&&typeof x.tenor==='string'&&/^[\w -]{1,12}$/.test(x.tenor)&&typeof x.value==='number'&&Number.isFinite(x.value));
 if(points.length<2)return;
 const cell=x=>'"'+String(x??'').replace(/^[=+@]/,"'$&").replace(/"/g,'""')+'"';
 const csv=['date,indicator,tenor,value,unit',...points.map(x=>
   [cell(row.asOf),cell(labels[kind]),cell(x.tenor),String(x.value),cell(row.unit||'')].join(','))].join('\r\n')+'\r\n';
 const blob=new Blob(['\ufeff',csv],{type:'text/csv;charset=utf-8'});
 const url=URL.createObjectURL(blob);
 const link=document.createElement('a');
 link.href=url;link.download='finquery-'+kind+'-'+row.asOf+'.csv';
 document.body.appendChild(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function monthBar(a,b,{unit='',color='#416eca',labelA='Tháng trước',labelB='Tháng này'}={}){
 const values=[a,b];if(values.some(x=>typeof x!=='number'||!Number.isFinite(x)||x<0))return'<div class="macro-no-chart">Chưa có dữ liệu.</div>';
 const max=Math.max(...values,1);
 const make=(val,label,opacity)=>'<div class="money-bar-item"><b>'+fmt(val,0)+'</b><div class="money-bar-track"><span style="width:'+Math.max(0,100*val/max)+'%;background:'+color+';opacity:'+opacity+'"></span></div><small>'+esc(label)+'</small></div>';
 return'<div class="money-bar-compare" aria-label="Đối chiếu theo tháng">'+make(a,labelA,'.43')+make(b,labelB,'1')+'</div><span class="money-bar-unit">'+esc(unit)+'</span>';
}
function cardHeader(label,value,unit,period){
 const date=/^\d{2}\/\d{2}\/\d{4}$/.test(String(value||''));
 return'<div class="macro-viz-head money-card-head"><div><span class="macro-viz-kicker">'+esc(period)+'</span><h4>'+esc(label)+'</h4></div><div class="money-main-num'+(date?' money-asof':'')+'"><strong>'+esc(value)+'</strong><small>'+esc(unit)+'</small></div></div>';
}
function verifiedBondSpread(curve){
 if(!curve||curve.status!=='verified'||!['approved','source_attributed'].includes(curve.licenseStatus)||curve.unit!=='%/năm'||!/^(20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/.test(curve.asOf||''))return null;
 const dayStart=new Date(curve.asOf+'T00:00:00+07:00').getTime();
 if(!Number.isFinite(dayStart)||dayStart>Date.now())return null;
 const rates=new Map((curve.points||[]).filter(p=>p&&typeof p.value==='number'&&Number.isFinite(p.value)&&p.value>=0&&p.value<=25).map(p=>[String(p.tenor).toUpperCase(),p.value]));
 const a=rates.get('2Y'),b=rates.get('10Y');
 if(!Number.isFinite(a)||!Number.isFinite(b))return null;
 return {difference:b-a,asOf:curve.asOf};
}

function historyOnRows(data){
 if(data?.schemaVersion!==1||data.series!=='MMONVND'||data.baseDate!=='2025-01-01'||!Array.isArray(data.observations))return [];
 const start=Date.parse('2025-01-01T00:00:00Z');
 return data.observations.filter(x=>Array.isArray(x)&&Number.isInteger(x[0])&&Number.isInteger(x[1])&&x[0]>=0&&x[1]>=0&&x[1]<=2500)
 .map(x=>({date:new Date(start+x[0]*86400000).toISOString().slice(0,10),value:x[1]/100}));
}
function filterOnTimeline(points,range,year,month){
 if(year!=='all'||month!=='all')return points.filter(p=>(year==='all'||p.date.slice(0,4)===year)&&(month==='all'||p.date.slice(5,7)===month));
 if(range==='ALL'||!points.length)return points;
 const days={'1W':7,'1M':31,'3M':93,'6M':186,'1Y':366}[range]||31;
 const cutoff=new Date(Date.parse(points.at(-1).date+'T00:00:00Z')-(days-1)*86400000).toISOString().slice(0,10);
 return points.filter(p=>p.date>=cutoff);
}
function onFilters(points){
 const ranges=[['1W','1 tuần'],['1M','1 tháng'],['3M','3 tháng'],['6M','6 tháng'],['1Y','1 năm'],['ALL','Tất cả']];
 const range=ranges.map(([k,v])=>'<button type="button" data-on-range="'+k+'" aria-pressed="'+(state.onRange===k)+'">'+v+'</button>').join('');
 const years=[...new Set(points.map(p=>p.date.slice(0,4)))].sort().reverse();
 const yo='<option value="all">Mọi năm</option>'+years.map(y=>'<option value="'+y+'"'+(state.onYear===y?' selected':'')+'>'+y+'</option>').join('');
 const mo='<option value="all">Mọi tháng</option>'+Array.from({length:12},(_,i)=>{const m=String(i+1).padStart(2,'0');return'<option value="'+m+'"'+(state.onMonth===m?' selected':'')+'>Tháng '+(i+1)+'</option>';}).join('');
 return '<div class="on-timeline-controls"><div class="on-range-group">'+range+'</div><div class="on-date-group"><label>Năm <select data-on-filter="year" aria-label="Chọn năm ON">'+yo+'</select></label><label>Tháng <select data-on-filter="month" aria-label="Chọn tháng ON">'+mo+'</select></label></div></div>';
}
async function loadONHistory(){
 try{
  const r=await fetch('/financial-report/data/on-mmonvnd-history.json',{cache:'no-store',signal:AbortSignal.timeout(10000)});
  if(!r.ok)throw Error('History HTTP '+r.status);
  const items=historyOnRows(await r.json());
  if(items.length<400)throw Error('Insufficient history');
  state.onHistory=[...new Map(items.map(p=>[p.date,p])).values()].sort((a,b)=>a.date.localeCompare(b.date));
 }catch(e){console.warn('Historical ON unavailable',String(e?.message||e));}
 if(state.payload)renderON(state.payload);
}

function onEntryForm(){return state.canEditOn?'<form id="finquery-on-manual-form" style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:end"><label>Ngày<br><input name="date" type="date" required></label><label>ON (%/năm)<br><input name="value" type="number" min="0" max="25" step="0.0001" required placeholder="3.95"></label><button type="submit">Lưu ON</button><span id="finquery-on-entry-status" role="status"></span></form>':'';}
function renderON(p){
 const host=$('money-on');if(!host)return;
 const on=p.interbank||{},crawled=(Array.isArray(on.observations)?on.observations:[]).filter(x=>/^\d{4}-\d\d-\d\d$/.test(x.date)&&typeof x.value==='number'&&Number.isFinite(x.value)&&x.value>=0&&x.value<=25);
 const byDate=new Map();
 for(const x of state.onHistory)byDate.set(x.date,x);
 for(const x of crawled)byDate.set(x.date,x);
 for(const x of state.manual)if(/^\d{4}-\d\d-\d\d$/.test(x.date)&&Number.isFinite(x.value)&&x.value>=0&&x.value<=25)byDate.set(x.date,{date:x.date,value:x.value});
 const points=[...byDate.values()].sort((a,b)=>a.date.localeCompare(b.date));
 const displayed=filterOnTimeline(points,state.onRange,state.onYear,state.onMonth);
 const last=points.at(-1),prev=points.at(-2);
 const verified=['secondary_source_crosschecked','official_source'].includes(on.status);
 if(!last||(!verified&&!state.manual.length&&!state.onHistory.length)){host.innerHTML=cardHeader('Lãi suất qua đêm','—','%/năm','VND')+
  '<p class="money-source-pending">Chuỗi ON đang chờ cập nhật.</p>'+onEntryForm();return;}
 const difference=prev?last.value-prev.value:null;
 host.innerHTML=cardHeader('Lãi suất qua đêm',fmt(last.value),'%/năm',dateVN(last.date))+
 '<p class="money-card-caption">'+(difference===null?'':((difference>=0?'+':'')+fmt(difference)+' điểm % so với '+dateVN(prev.date)))+'</p>'+
 onFilters(points)+
 '<div class="money-chart money-on-interactive">'+miniLine(displayed,{unit:'%/năm',title:'Lãi suất bình quân liên ngân hàng ON VND',color:'#326bbe',width:Math.max(250,host.clientWidth-36)})+'<div class="money-on-tooltip" role="tooltip" hidden><span data-on-tooltip-date></span><strong><span data-on-tooltip-rate></span> <small>%/năm</small></strong></div></div>'+
 onEntryForm();
 bindONTooltip();
}
function renderFutures(p){
 const root=$('money-futures');if(!root)return;
 const d=p.derivatives||{},months=Array.isArray(d.months)?d.months.slice().filter(m=>/^\d{4}-(0[1-9]|1[0-2])$/.test(m.month)).sort((a,b)=>a.month.localeCompare(b.month)):[];
 const source=safeURL(d.source,'www.gov.hnx.vn');
 const prev=months.at(-2),current=months.at(-1);
 if(!prev||!current){root.innerHTML='<p class="money-source-pending">Báo cáo phái sinh theo tháng chưa có đủ hai kỳ được công bố để so sánh. Không giả định tháng trống bằng 0.</p>';return;}
 const field=state.derivativeMode,choice=(symbol)=>({a:prev[symbol]?.[field],b:current[symbol]?.[field]});
 let cards=['vn30','vn100'].map((symbol,i)=>{
   const v=choice(symbol),label=symbol.toUpperCase();
   const delta=typeof v.a==='number'&&v.a>0&&typeof v.b==='number'?(v.b-v.a)/v.a*100:null;
   return'<article class="money-future-contract">'+cardHeader('HĐTL '+label,fmt(v.b,0),'hợp đồng',monthVN(current.month))+
    '<div class="money-delta">'+(delta===null?'Không có kỳ trước':((delta>=0?'+':'')+fmt(delta)+'% so với '+monthVN(prev.month)))+'</div>'+
    monthBar(v.a,v.b,{unit:field==='openInterest'?'Vị thế mở cuối tháng':'Khối lượng bình quân/phiên',color:i===0?'#3b68c7':'#0b8877',labelA:monthVN(prev.month),labelB:monthVN(current.month)})+'</article>';
 }).join('');
 const buttons=[['openInterest','Vị thế mở cuối tháng'],['avgVolume','Khối lượng bình quân/phiên']].map(([key,label])=>'<button type="button" data-derivative-mode="'+key+'" class="'+(key===field?'active':'')+'" aria-pressed="'+(key===field)+'">'+label+'</button>').join('');
 root.innerHTML='<div class="money-chart-menu" role="group" aria-label="Chọn chỉ tiêu chứng khoán phái sinh">'+buttons+'</div><div class="money-derivative-grid">'+cards+'</div>'+
 ''+
 '';
}
function renderSwap(p){
 const host=$('money-swap');if(!host)return;
 const s=p.vbmaSwap||{},points=(Array.isArray(s.points)?s.points:[]).filter(x=>x.tenor&&typeof x.value==='number'&&Number.isFinite(x.value)&&Math.abs(x.value)<100000).slice(0,30);
 const enabled=['verified','retained'].includes(s.status)&&s.unit&&/^\d{4}-\d\d-\d\d$/.test(s.asOf||'')&&points.length>=2;
 if(!enabled){
   host.innerHTML=cardHeader('Hoán đổi USD/VND','—','','Kỳ hạn')+
     '<p class="money-empty-inline">Chưa có dữ liệu hợp lệ.</p>';
   return;
 }
 host.innerHTML=cardHeader('Hoán đổi USD/VND',dateVN(s.asOf),s.unit,'Kỳ hạn')+
   '<div class="money-curve" role="group" aria-label="Đường cong Hoán đổi USD/VND theo kỳ hạn">'+
   tenorCurve(points,{title:'Hoán đổi USD/VND',unit:s.unit,color:'#276bb7',width:Math.max(270,host.clientWidth-38)})+
   '</div><div class="macro-viz-source money-download-row">'+curveDownloadButton('swap','Hoán đổi USD/VND')+'</div>';
}
function renderBondCurves(p){
 const host=$('money-vbma-curves');if(!host)return;
 const sources=[['fi_bond','Trái phiếu và chứng chỉ tiền gửi'],['gov_bond','Lợi suất trái phiếu Chính phủ'],['short_benchmark','Lãi suất tham chiếu ngắn hạn']];
 const data=p.vbmaCurves||p.curves||{},spread=verifiedBondSpread(data.gov_bond),cards=[];
 if(spread)cards.push('<article class="macro-viz-card money-spread-card"><div class="macro-viz-head"><div><span class="macro-viz-kicker">ĐƯỜNG CONG LỢI SUẤT</span><h4>Chênh lệch 10Y – 2Y</h4></div><span class="macro-viz-period">'+esc(dateVN(spread.asOf))+'</span></div><div class="macro-viz-value"><strong>'+esc((spread.difference>0?'+':'')+fmt(spread.difference*100,1))+'</strong><span>điểm cơ bản</span></div></article>');
 for(const[key,title]of sources){
  const row=data[key]||{},points=Array.isArray(row.points)?row.points.filter(x=>x.tenor&&Number.isFinite(x.value)):[];
  const valid=['verified','retained'].includes(row.status)&&['approved','source_attributed'].includes(row.licenseStatus)&&
   row.unit&&/^\d{4}-\d\d-\d\d$/.test(row.asOf||'')&&points.length>=2;
  if(!valid)continue;
  cards.push('<article class="macro-viz-card">'+cardHeader(title,dateVN(row.asOf),row.unit,'Kỳ hạn')+
   '<div class="money-curve">'+tenorCurve(points,{title,unit:row.unit,color:'#28837a',
    width:Math.max(270,(host.clientWidth||960)/(window.innerWidth<950?1:3)-40)})+
   '</div><div class="macro-viz-source money-download-row">'+curveDownloadButton(key,title)+'</div></article>');
 }
 // Unsupported feeds stay in internal quality metadata, not in a large visible box.
 host.innerHTML=cards.length?cards.join(''):'<p class="money-empty-inline">Chưa có dữ liệu đường cong hợp lệ.</p>';
}
function render(){
 const p=state.payload;if(!p)return;
 if($('money-source-stamp'))$('money-source-stamp').textContent='Cập nhật '+dateVN(p.asOf)+
  ' · kiểm tra '+(p.lastCheckedAt?new Date(p.lastCheckedAt).toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'chưa xác định');
 renderON(p);renderFutures(p);renderSwap(p);renderBondCurves(p);
}
async function loadManualON(){
 try{
  const r=await fetch('/api/market/on-observations',{credentials:'same-origin',cache:'no-store'});
  if(!r.ok)return;
  const d=await r.json();
  state.canEditOn=d.canEdit===true;
  state.manual=Array.isArray(d.observations)?d.observations:[];
  if(state.payload)renderON(state.payload);
 }catch(e){console.warn('ON manual observations unavailable');}
}
document.addEventListener?.('click',event=>{
 const button=event.target.closest?.('[data-on-range]');
 if(button){state.onRange=button.dataset.onRange;state.onYear='all';state.onMonth='all';if(state.payload)renderON(state.payload);return;}
 const download=event.target.closest?.('[data-download-curve]');
 if(download)downloadCurveCsv(download.dataset.downloadCurve);
});
document.addEventListener?.('change',event=>{
 if(event.target?.dataset?.onFilter==='year')state.onYear=event.target.value;
 else if(event.target?.dataset?.onFilter==='month')state.onMonth=event.target.value;
 else return;
 if(state.payload)renderON(state.payload);
});
document.addEventListener?.('submit',async function(event){
 const form=event.target;if(form?.id!=='finquery-on-manual-form')return;
 event.preventDefault();if(!state.canEditOn)return;
 const note=$('finquery-on-entry-status');
 const date=form.elements.date.value,value=Number(form.elements.value.value);
 if(!date||!Number.isFinite(value)||value<0||value>25){if(note)note.textContent='Kiểm tra ngày và lãi suất.';return;}
 try{
  const r=await fetch('/api/market/on-observations',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({date,value})});
  if(!r.ok)throw Error((await r.json()).error||'Lưu không thành công');
  await loadManualON();
  const fresh=$('finquery-on-entry-status');if(fresh)fresh.textContent='Đã cập nhật biểu đồ.';
 }catch(e){if(note)note.textContent=e.message||'Không lưu được';}
});
async function load(){
 if(state.loading)return;state.loading=true;
 const btn=$('money-refresh');if(btn)btn.disabled=true;
 const mirror=typeof location==='object'&&location?.origin?
  (document.documentElement?.dataset?.hosting==='pages'?
   new URL('market/finquery-liquidity.json',location.href).href:
   new URL('/financial-report/market/finquery-liquidity.json',location.origin).href):SOURCE;
 const urls=[SOURCE,mirror];let failure=null;
 try{
  let received=null;
  for(const url of urls){
   try{
    const resp=await fetch(url+'?v='+Math.floor(Date.now()/60000),{
      cache:'no-store',signal:AbortSignal.timeout(10000)
    });
    if(!resp.ok)throw Error('HTTP '+resp.status);
    const d=await resp.json();
    if(d.schemaVersion!==1||!d.interbank||!d.derivatives||!d.vbmaSwap)
      throw Error('Invalid schema');
    const stamp=Date.parse(d.lastCheckedAt||d.publishedAt||'');
    if(!Number.isFinite(stamp)||stamp>Date.now()+300000)throw Error('Timestamp invalid');
    received=d;break;
   }catch(error){failure=error}
  }
  if(!received)throw failure||Error('Both verified market sources are unavailable');
  const previous=Date.parse(state.payload?.lastCheckedAt||state.payload?.publishedAt||'');
  const updated=Date.parse(received.lastCheckedAt||received.publishedAt||'');
  if(!Number.isFinite(previous)||updated>=previous)state.payload=received;
  render();
 }catch(error){
  if(!state.payload){
   const msg='<p class="macro-source-notice" role="status">Kết nối nguồn thanh khoản đang gián đoạn. Các chỉ tiêu không được thay bằng giá ước tính; chọn Cập nhật để thử lại.</p>';
   for(const id of ['money-on','money-swap','money-vbma-curves']){
    const el=$(id);if(el)el.innerHTML=msg;
   }
  }else{
   render();
   const stamp=$('money-source-stamp');if(stamp)stamp.textContent+=' · bản đã lưu';
  }
  console.warn('FinQuery liquidity: ',String(error?.message||error));
 }finally{state.loading=false;if(btn)btn.disabled=false}
}
[document.getElementById('macro-liquidity-overview'),document.getElementById('market-futures-workspace')].forEach(root=>root?.addEventListener('click',event=>{
 const button=event.target.closest?.('[data-derivative-mode]');
 if(!button)return;
 if(['openInterest','avgVolume'].includes(button.dataset.derivativeMode)){state.derivativeMode=button.dataset.derivativeMode;renderFutures(state.payload);}
}));
$('money-refresh')?.addEventListener('click',load);
const onHost=$('money-on');
if(onHost&&typeof ResizeObserver==='function'){
 let prior=0;
 new ResizeObserver(entries=>{const width=Math.round(entries[0]?.contentRect?.width||0);if(width&&Math.abs(width-prior)>12){prior=width;if(state.payload)renderON(state.payload);}}).observe(onHost);
}
window.FinLiquidityDerivatives={refresh:load,_test:{fmt,miniLine,tenorCurve,monthBar,dateVN,monthVN,safeURL,verifiedBondSpread,historyOnRows,filterOnTimeline},setData:payload=>{state.payload=payload;render();}};
load();loadManualON();loadONHistory();
})();