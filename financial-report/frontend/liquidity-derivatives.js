(function(){'use strict';
const $=id=>document.getElementById(id);
const SOURCE='https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/finquery-liquidity.json';
const nf=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2});
const fmt=(n,d=2)=>typeof n==='number'&&Number.isFinite(n)?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:d}).format(n):'—';
const esc=t=>String(t??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const dateVN=iso=>/^\d{4}-\d\d-\d\d$/.test(String(iso||''))?iso.slice(8,10)+'/'+iso.slice(5,7)+'/'+iso.slice(0,4):'—';
const monthVN=iso=>/^\d{4}-(0[1-9]|1[0-2])$/.test(String(iso||''))?iso.slice(5,7)+'/'+iso.slice(0,4):'—';
const safeURL=(url,hostname)=>{try{let u=new URL(url);return u.protocol==='https:'&&u.hostname===hostname?u.href:'';}catch{return'';}};
const state={payload:null,derivativeMode:'openInterest',loading:false};
const target=$('macro-liquidity-overview');
if(!target)return;
function miniLine(points,{unit='',title='',color='#2e74bb',width=640}={}){
 if(points.length<2)return'<div class="macro-no-chart">Chưa đủ dữ liệu để hiển thị.</div>';
 const values=points.map(p=>p.value),min=Math.min(...values),max=Math.max(...values),pad=Math.max((max-min)*.16,Math.abs(max)*.07,.03);
 const low=min-pad,high=max+pad,W=Math.max(250,Math.min(950,Math.floor(Number(width)||640))),compact=W<480;
 const H=232,L=49,R=22,T=18,B=39;
 const x=i=>L+(W-L-R)*i/(points.length-1),y=v=>T+(H-T-B)*(high-v)/(high-low);
 const grid=Array.from({length:4},(_,i)=>{const v=low+(high-low)*i/3,py=y(v);return'<line x1="'+L+'" y1="'+py+'" x2="'+(W-R)+'" y2="'+py+'" stroke="#e8edf4"/><text x="'+(L-7)+'" y="'+(py+4)+'" font-size="11" text-anchor="end" fill="#8491a4">'+fmt(v,1)+'</text>';}).join('');
 const line=points.map((p,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(p.value).toFixed(1)).join(' ');
 // Budget horizontal space for the actual rendered label text rather than
 // drawing five full dd/mm/yyyy labels inside a 300px chart.
 const labelWidth=compact?57:83,gap=compact?12:18;
 const limit=Math.max(2,Math.min(5,Math.floor((W-L-R+gap)/(labelWidth+gap))));
 const ticks=[...new Set(Array.from({length:limit},(_,i)=>Math.round(i*(points.length-1)/(limit-1))))];
 const labels=ticks.map(i=>{const p=points[i],full=dateVN(p.date),display=compact?full.slice(0,5):full;
  return'<text data-on-tick="'+i+'" x="'+x(i).toFixed(1)+'" y="'+(H-9)+'" text-anchor="'+(i===0?'start':i===points.length-1?'end':'middle')+'" font-size="'+(compact?10:11)+'" fill="#74869f">'+esc(display)+'<title>'+esc(full)+'</title></text>';
 }).join('');
 const circles=points.map((p,i)=>'<circle cx="'+x(i).toFixed(1)+'" cy="'+y(p.value).toFixed(1)+'" r="'+(i===points.length-1?4.8:3)+'" fill="'+color+'"><title>'+esc(dateVN(p.date)+' · '+fmt(p.value)+' '+unit)+'</title></circle>').join('');
 return'<svg viewBox="0 0 '+W+' '+H+'" class="macro-trend-svg money-on-trend" role="img" aria-label="'+esc(title)+'">'+grid+'<path d="'+line+'" stroke="'+color+'" stroke-width="2.8" stroke-linejoin="round" stroke-linecap="round" fill="none"/>'+circles+labels+'</svg>';
}
function vbmaSourceIcon(url,label){
 if(!url)return'';
 const svg='<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12m-5-5 5 5 5-5M5 17v3h14v-3"/></svg>';
 return'<a class="money-vbma-download" href="'+esc(url)+'" target="_blank" rel="noopener noreferrer" title="'+esc(label)+'" aria-label="'+esc(label)+'">'+svg+'</a>';
}
function monthBar(a,b,{unit='',color='#416eca',labelA='Tháng trước',labelB='Tháng này'}={}){
 const values=[a,b];if(values.some(x=>typeof x!=='number'||!Number.isFinite(x)||x<0))return'<div class="macro-no-chart">Không đủ số liệu đối chiếu.</div>';
 const max=Math.max(...values,1);
 const make=(val,label,opacity)=>'<div class="money-bar-item"><b>'+fmt(val,0)+'</b><div class="money-bar-track"><span style="width:'+Math.max(0,100*val/max)+'%;background:'+color+';opacity:'+opacity+'"></span></div><small>'+esc(label)+'</small></div>';
 return'<div class="money-bar-compare" aria-label="Đối chiếu theo tháng">'+make(a,labelA,'.43')+make(b,labelB,'1')+'</div><span class="money-bar-unit">'+esc(unit)+'</span>';
}
function cardHeader(label,value,unit,period){
 return'<div class="macro-viz-head"><div><span class="macro-viz-kicker">'+esc(period)+'</span><h4>'+esc(label)+'</h4></div><div class="money-main-num"><strong>'+esc(value)+'</strong><small>'+esc(unit)+'</small></div></div>';
}
function renderON(p){
 const host=$('money-on');if(!host)return;
 const on=p.interbank||{},points=(Array.isArray(on.observations)?on.observations:[]).filter(x=>/^\d{4}-\d\d-\d\d$/.test(x.date)&&typeof x.value==='number'&&Number.isFinite(x.value)&&x.value>=0&&x.value<50).sort((a,b)=>a.date.localeCompare(b.date));
 const last=points.at(-1),prev=points.at(-2);
 const origin=safeURL(on.source,'stockbiz.vn');
 const cross=safeURL(on.crossCheck,'dulieukinhte.com');
 const verified=['secondary_source_crosschecked','official_source'].includes(on.status);
 if(!last||!verified){host.innerHTML=cardHeader('Liên ngân hàng ON','—','%/năm','VND')+'<p class="money-empty">Chưa lấy được dữ liệu ON.</p>';return;}
 const difference=prev?last.value-prev.value:null;
 host.innerHTML=cardHeader('Liên ngân hàng ON',fmt(last.value),'%/năm',dateVN(last.date))+
 '<p class="money-card-caption">'+(difference===null?'':((difference>=0?'+':'')+fmt(difference)+' điểm % so với '+dateVN(prev.date)))+'</p>'+
 '<div class="money-chart">'+miniLine(points.slice(-25),{unit:'%/năm',title:'Lãi suất bình quân liên ngân hàng ON VND',color:'#326bbe',width:Math.max(250,host.clientWidth-36)})+'</div>'+
 '<div class="macro-viz-source"><span>Nguồn NHNN, đối chiếu qua bản tổng hợp</span>'+
 (origin?'<a href="'+esc(origin)+'" target="_blank" rel="noopener noreferrer">Lịch sử ON ↗</a>':'')+
 (cross?'<a href="'+esc(cross)+'" target="_blank" rel="noopener noreferrer">Đối chiếu ↗</a>':'')+'</div>';
}
function renderFutures(p){
 const root=$('money-futures');if(!root)return;
 const d=p.derivatives||{},months=Array.isArray(d.months)?d.months.slice().filter(m=>/^\d{4}-(0[1-9]|1[0-2])$/.test(m.month)).sort((a,b)=>a.month.localeCompare(b.month)):[];
 const source=safeURL(d.source,'www.gov.hnx.vn');
 const prev=months.at(-2),current=months.at(-1);
 if(!prev||!current){root.innerHTML='<p class="money-empty">Chưa có đủ hai tháng dữ liệu phái sinh.</p>';return;}
 const field=state.derivativeMode,choice=(symbol)=>({a:prev[symbol]?.[field],b:current[symbol]?.[field]});
 let cards=['vn30','vn100'].map((symbol,i)=>{
   const v=choice(symbol),label=symbol.toUpperCase();
   const delta=typeof v.a==='number'&&v.a>0&&typeof v.b==='number'?(v.b-v.a)/v.a*100:null;
   return'<article class="money-future-contract">'+cardHeader('HĐTL '+label,fmt(v.b,0),'hợp đồng',monthVN(current.month))+
    '<div class="money-delta">'+(delta===null?'Không có kỳ trước':((delta>=0?'+':'')+fmt(delta)+'% so với '+monthVN(prev.month)))+'</div>'+
    monthBar(v.a,v.b,{unit:field==='openInterest'?'OI cuối tháng':'KLGD bình quân/phiên',color:i===0?'#3b68c7':'#0b8877',labelA:monthVN(prev.month),labelB:monthVN(current.month)})+'</article>';
 }).join('');
 const buttons=[['openInterest','OI cuối tháng'],['avgVolume','KLGD bình quân/phiên']].map(([key,label])=>'<button type="button" data-derivative-mode="'+key+'" class="'+(key===field?'active':'')+'" aria-pressed="'+(key===field)+'">'+label+'</button>').join('');
 root.innerHTML='<div class="money-chart-menu" role="group" aria-label="Chọn chỉ tiêu chứng khoán phái sinh">'+buttons+'</div><div class="money-derivative-grid">'+cards+'</div>'+
 '<div class="macro-viz-source"><span>HNX · dữ liệu tổng hợp tháng '+esc(monthVN(current.month))+'</span>'+
 (source?'<a href="'+esc(source)+'" target="_blank" rel="noopener noreferrer">Báo cáo HNX ↗</a>':'')+'</div>';
}
function renderSwap(p){
 const host=$('money-swap');if(!host)return;const s=p.vbmaSwap||{},source=safeURL(s.source,'vbma.org.vn');
 const points=(Array.isArray(s.points)?s.points:[]).filter(x=>x.tenor&&typeof x.value==='number'&&Number.isFinite(x.value)&&Math.abs(x.value)<100000).slice(0,30);
 const enabled=s.status==='verified'&&s.unit&&/^\d{4}-\d\d-\d\d$/.test(s.asOf||'')&&points.length>=2;
 const link=vbmaSourceIcon(source,'Tải tệp dữ liệu USD/VND FX Swap từ VBMA');
 if(!enabled){
    host.innerHTML=cardHeader('USD/VND FX Swap','—','VBMA','Đường cong kỳ hạn')+
      '<p class="money-empty">Chưa có chuỗi FX Swap hợp lệ để vẽ.</p>'+(reason?'<p class="money-source-pending">'+esc(String(reason).replace(/^VBMA swap\s+/,''))+'</p>':'')+
      '<div class="macro-viz-source">'+link+'</div>';return;
 }
 const maxAbs=Math.max(...points.map(x=>Math.abs(x.value)),.01);
 const bars=points.map(x=>'<div class="money-swap-point"><small>'+esc(x.tenor)+'</small><div class="money-swap-track"><div style="height:'+Math.max(2,Math.abs(x.value)/maxAbs*100)+'%"></div></div><b>'+fmt(x.value,2)+'</b></div>').join('');
 host.innerHTML=cardHeader('USD/VND FX Swap',dateVN(s.asOf),s.unit,'VBMA')+'<div class="money-swap-chart" role="img" aria-label="USD VND FX Swap theo kỳ hạn">'+bars+'</div><div class="macro-viz-source"><span>'+esc(s.measurement||'Đường cong kỳ hạn')+'</span>'+link+'</div>';
}
function renderBondCurves(p){
 const host=$('money-vbma-curves');if(!host)return;
 const sources=[['fi_bond','FI Bond & CD'],['gov_bond','Lợi suất trái phiếu Chính phủ'],['short_benchmark','Repo ngắn hạn']];
 const data=p.vbmaCurves||{};
 host.innerHTML=sources.map(([key,title])=>{
  const s=data[key]||{},points=Array.isArray(s.points)?s.points.filter(x=>x.tenor&&Number.isFinite(x.value)):[];
  const url=safeURL(s.source||('https://vbma.org.vn/csv/markets/charts/vi/'+({fi_bond:'fi_bond_yield_curve',gov_bond:'government_bond_yield',short_benchmark:'short_term_benchmark_rate'}[key])+'.csv'),'vbma.org.vn');
  const link=vbmaSourceIcon(url,'Tải tệp dữ liệu '+title+' từ VBMA');
  const verified=s.status==='verified'&&s.licenseStatus==='approved'&&s.unit&&s.asOf&&points.length>=2;
  const reason=(p.sourceIssues||[]).find(x=>String(x).startsWith('VBMA '+key+' '));
  const visual=verified?'<div class="money-bond-chart">'+points.map(x=>'<div class="money-bond-point"><small>'+esc(x.tenor)+'</small><b>'+fmt(x.value,3)+'</b></div>').join('')+'</div>' :'<p class="money-source-pending">'+esc(reason?String(reason).replace(new RegExp('^VBMA '+key+'\\s+'),''):'Chưa có chuỗi kỳ hạn đã xác minh')+'</p>';
  return '<article class="macro-viz-card">'+cardHeader(title,verified?dateVN(s.asOf):'—',verified?s.unit:'VBMA','Đường cong kỳ hạn')+visual+'<div class="macro-viz-source">'+link+'</div></article>';
 }).join('');
}
function render(){
 const p=state.payload;if(!p)return;
 if($('money-source-stamp'))$('money-source-stamp').textContent='Cập nhật dữ liệu: '+dateVN(p.asOf);
 renderON(p);renderFutures(p);renderSwap(p);renderBondCurves(p);
}
async function load(){
 if(state.loading)return;state.loading=true;
 const btn=$('money-refresh');if(btn)btn.disabled=true;
 try{
  const resp=await fetch(SOURCE+'?v='+Math.floor(Date.now()/60000),{cache:'no-store',signal:AbortSignal.timeout(14000)});
  if(!resp.ok)throw Error('HTTP '+resp.status);
  const d=await resp.json();
  if(d.schemaVersion!==1||!d.interbank||!d.derivatives||!d.vbmaSwap)throw Error('Invalid schema');
  state.payload=d;render();
 }catch(error){
  if(!state.payload){for(const id of ['money-on','money-swap','money-vbma-curves']){const node=$(id);if(node)node.innerHTML='<p class="macro-no-chart">Nguồn tiền tệ đang gián đoạn; chưa nhận dữ liệu đã xác minh.</p>';}}
  if($('money-source-stamp'))$('money-source-stamp').textContent='Dữ liệu tạm gián đoạn';
 }finally{state.loading=false;if(btn)btn.disabled=false;}
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
window.FinLiquidityDerivatives={refresh:load,_test:{fmt,miniLine,monthBar,dateVN,monthVN,safeURL},setData:payload=>{state.payload=payload;render();}};
load();
})();