(function(root){'use strict';
/* FinQuery Macro & ESG: visualizes verified source rows, never synthetic observations. */
const $=id=>document.getElementById(id);
const nf=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2});
const fmt=n=>typeof n==='number'&&Number.isFinite(n)?nf.format(n):'—';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const FEATURES=[
 {id:'pmi',key:'PMI',title:'PMI sản xuất',unit:'điểm',scale:1,threshold:50,color:'#3565d5',info:'Mốc 50 phân biệt mở rộng và thu hẹp'},
 {id:'money_supply',key:'M2 (tỷ VND)',title:'Cung tiền M2',unit:'triệu tỷ đồng',scale:1000000,color:'#009d87',info:'Số dư M2 công bố theo tháng'},
 {id:'credit_sector',key:'Tổng dư nợ',title:'Dư nợ tín dụng',unit:'triệu tỷ đồng',scale:1000000,color:'#7561c0',info:'Số dư theo thống kê tín dụng'},
 {id:'fdi',key:'FDI giải ngân (lũy kế năm) (tỷ USD)',title:'FDI giải ngân',unit:'tỷ USD',scale:1,color:'#c88932',info:'Lũy kế năm, bắt đầu lại từ tháng 1'}
];
const WORLD=[
 {id:'AG.LND.FRST.ZS',title:'Tỷ lệ diện tích rừng',unit:'% diện tích đất'},
 {id:'EG.FEC.RNEW.ZS',title:'Tiêu thụ năng lượng tái tạo',unit:'% năng lượng cuối cùng'},
 {id:'EG.ELC.RNEW.ZS',title:'Sản lượng điện tái tạo',unit:'% tổng sản lượng điện'},
 {id:'ER.PTD.TOTL.ZS',title:'Diện tích đất và biển được bảo vệ',unit:'% lãnh thổ'},
 {id:'SP.DYN.LE00.IN',title:'Tuổi thọ bình quân',unit:'năm'}
];
let countryId='AG.LND.FRST.ZS',corporateId='',companySymbol='';
function rank(period){
 const s=String(period??'').trim();
 let m=s.match(/^T(1[0-2]|[1-9])\s+(\d{4})$/i);if(m)return +m[2]*12+ +m[1]-1;
 m=s.match(/^Q([1-4])\s+(\d{4})$/i);if(m)return +m[2]*12+(+m[1]-1)*3+2;
 m=s.match(/^(\d{4})$/);if(m)return +m[1]*12+11;
 return null;
}
function series(ds,key,scale=1){
 if(!ds||!Array.isArray(ds.rows)||!(scale>0))return[];
 const first=(ds.columns||[])[0]||'Date';
 return ds.rows.map(r=>({label:String(r?.[first]??''),date:rank(r?.[first]),raw:r?.[key]}))
 .filter(p=>p.date!==null&&typeof p.raw==='number'&&Number.isFinite(p.raw))
 .sort((a,b)=>a.date-b.date)
 .map(p=>({label:p.label,rank:p.date,y:p.raw/scale}));
}
function httpsUrl(raw){try{const u=new URL(String(raw||''));return u.protocol==='https:'?u.href:'';}catch{return'';}}
function sourceLink(raw,label){
 const url=httpsUrl(raw);return url?'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc(label)+' ↗</a>':'<span>Nguồn chưa có đường dẫn xác minh</span>';
}
function plot(data,opts={}){
 const pts=data.slice(-(opts.limit||24));
 if(pts.length<2)return'<div class="macro-no-chart">Chưa đủ hai kỳ số liệu so sánh.</div>';
 let low=Math.min(...pts.map(p=>p.y)),high=Math.max(...pts.map(p=>p.y));
 if(typeof opts.threshold==='number'){low=Math.min(low,opts.threshold);high=Math.max(high,opts.threshold);}
 const range=Math.max(high-low,Math.abs(high)*.035,.1);low-=range*.1;high+=range*.14;
 const width=680,height=230,l=65,r=17,t=17,b=36,dy=high-low;
 const x=i=>l+(width-l-r)*i/(pts.length-1),y=v=>t+(height-t-b)*(high-v)/dy;
 const grid=[0,1/3,2/3,1].map(p=>{
  const val=low+dy*p,pos=y(val).toFixed(1);
  return'<line x1="'+l+'" y1="'+pos+'" x2="'+(width-r)+'" y2="'+pos+'" stroke="#e5edf7"/><text x="'+(l-9)+'" y="'+(Number(pos)+4)+'" text-anchor="end" fill="#8190a5" font-size="11">'+esc(fmt(val))+'</text>';
 }).join('');
 const color=/^#[0-9a-fA-F]{6}$/.test(opts.color||'')?opts.color:'#3565d5';
 const shape=pts.map((p,i)=>(i?'L':'M')+x(i).toFixed(1)+','+y(p.y).toFixed(1)).join(' ');
 const horizontal=[0,Math.floor((pts.length-1)/2),pts.length-1].map((i,j)=>'<text x="'+x(i).toFixed(1)+'" y="'+(height-10)+'" fill="#7688a0" font-size="11" text-anchor="'+(j===0?'start':j===2?'end':'middle')+'">'+esc(pts[i].label)+'</text>').join('');
 const threshold=typeof opts.threshold==='number'?'<line x1="'+l+'" y1="'+y(opts.threshold).toFixed(1)+'" x2="'+(width-r)+'" y2="'+y(opts.threshold).toFixed(1)+'" stroke="#bb8443" stroke-dasharray="5 5"/><text x="'+(width-r-4)+'" y="'+(y(opts.threshold)-6).toFixed(1)+'" text-anchor="end" font-size="11" fill="#aa763c">'+esc(opts.threshold)+'</text>':'';
 const tips=pts.map((p,i)=>'<circle cx="'+x(i).toFixed(1)+'" cy="'+y(p.y).toFixed(1)+'" r="9" fill="transparent"><title>'+esc(p.label+': '+fmt(p.y)+' '+(opts.unit||''))+'</title></circle>').join('');
 const last=pts.at(-1);
 return'<svg class="macro-trend-svg" viewBox="0 0 '+width+' '+height+'" role="img" aria-label="'+esc((opts.title||'Biểu đồ')+' · '+pts.length+' kỳ dữ liệu')+'">'+grid+threshold+'<path d="'+shape+'" fill="none" stroke="'+color+'" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/><circle cx="'+x(pts.length-1).toFixed(1)+'" cy="'+y(last.y).toFixed(1)+'" r="5" fill="'+color+'" stroke="white" stroke-width="2"/>'+tips+horizontal+'</svg>';
}
function renderMacro(data){
 const host=$('macro-overview');if(!host)return;
 const sources=data?.sources||[];
 host.innerHTML=FEATURES.map(c=>{
  const ds=data?.datasets?.[c.id],src=sources.find(s=>s.id===c.id);
  const allowed=ds?.status==='ok'&&ds.qualityStatus!=='warning'&&src?.status==='ok'&&src?.qualityStatus!=='warning';
  const pts=allowed?series(ds,c.key,c.scale):[];
  const last=pts.at(-1),earlier=pts.at(-2);
  const head='<div class="macro-viz-head"><div><span class="macro-viz-kicker">KINH TẾ VIỆT NAM</span><h4>'+esc(c.title)+'</h4></div>'+(last?'<span class="macro-viz-period">'+esc(last.label)+'</span>':'')+'</div>';
  const link=sourceLink(src?.url,'VBMA');
  if(pts.length<2)return'<article class="macro-viz-card">'+head+'<div class="macro-no-chart">Chưa có chuỗi được xác minh để vẽ biểu đồ.</div><div class="macro-viz-source">'+link+'<span>Trạng thái: '+esc(src?.qualityStatus||src?.status||'không rõ')+'</span></div></article>';
  let context='';
  if(c.id==='pmi')context=last.y>=50?'Trên mốc 50 · sản xuất đang mở rộng':'Dưới mốc 50 · sản xuất đang thu hẹp';
  else if(c.id==='fdi')context='Lũy kế trong năm · không diễn giải thành tăng trưởng tháng';
  else context='So với '+esc(earlier.label)+': '+(last.y>=earlier.y?'+':'')+esc(fmt(last.y-earlier.y))+' '+esc(c.unit);
  return'<article class="macro-viz-card">'+head+'<div class="macro-viz-value"><strong>'+esc(fmt(last.y))+'</strong><span>'+esc(c.unit)+'</span></div><p class="macro-viz-comment">'+context+'</p><div class="macro-viz-plot">'+plot(pts,{title:c.title,unit:c.unit,color:c.color,threshold:c.threshold})+'</div><div class="macro-viz-source">'+link+'<span>'+esc(c.info)+' · kỳ '+esc(last.label)+'</span></div></article>';
 }).join('');
 const checkDate=new Date(data?.checkedAt);
 const freshness=$('macro-data-freshness');
 if(freshness)freshness.textContent=Number.isNaN(checkDate.getTime())?'Chưa rõ thời điểm nguồn':'Bản kiểm tra '+checkDate.toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'})+' · không phải giá trực tiếp';
}

function renderCountry(data){
 const ds=data?.datasets?.esg_world_bank,body=$('macro-country-chart'),foot=$('macro-country-source'),select=$('macro-country-metric');
 if(!body||!select||!foot)return;
 const choices=WORLD.filter(m=>series(ds,m.id).length>=2);
 if(!choices.length||!['ok','cached','retained'].includes(ds?.status)||ds?.qualityStatus==='warning'){
  select.innerHTML='<option>Chưa có chuỗi đủ điều kiện</option>';select.disabled=true;
  body.innerHTML='<div class="macro-no-chart">Không có chuỗi ESG quốc gia đã kiểm tra để vẽ.</div>';
  foot.textContent='Nguồn World Bank ESG hiện chưa sẵn sàng.';return;
 }
 select.disabled=false;
 const selected=select.value;
 if(choices.some(x=>x.id===selected))countryId=selected;
 if(!choices.some(x=>x.id===countryId))countryId=choices[0].id;
 select.innerHTML=choices.map(m=>'<option value="'+esc(m.id)+'"'+(m.id===countryId?' selected':'')+'>'+esc(m.title)+'</option>').join('');
 select.value=countryId;
 const metric=choices.find(m=>m.id===countryId);
 const pts=series(ds,metric.id),latest=pts.at(-1);
 body.innerHTML='<div class="macro-viz-value"><strong>'+esc(fmt(latest.y))+'</strong><span>'+esc(metric.unit)+'</span></div><p class="macro-viz-comment">Kỳ công bố gần nhất: '+esc(latest.label)+' · các kỳ không có số liệu được để trống</p><div class="macro-viz-plot">'+plot(pts,{title:metric.title,unit:metric.unit,color:'#158c83',limit:24})+'</div>';
 const source=(data.sources||[]).find(s=>s.id==='esg_world_bank');
 foot.innerHTML=sourceLink(source?.url,'World Bank ESG')+'<span>Kỳ quan sát '+esc(latest.label)+' · không đồng nghĩa cập nhật năm hiện tại</span>';
}
function corporateRows(esg,symbol){
 const company=esg?.companies?.[symbol];
 const approved=Array.isArray(company?.canonicalMetrics)?company.canonicalMetrics:[];
 return approved.filter(m=>m&&m.metricId&&typeof m.value==='number'&&Number.isFinite(m.value)&&Number.isInteger(Number(m.year))&&m.year>=2000&&m.year<=2100&&httpsUrl(m.sourceUrl));
}
function renderCorporate(esg,symbol){
 const body=$('macro-company-chart'),foot=$('macro-company-source'),select=$('macro-company-metric'),title=$('macro-company-symbol');
 if(!body||!foot||!select)return;
 const key=String(symbol||'').toUpperCase(),company=esg?.companies?.[key];
 if(title)title.textContent='DOANH NGHIỆP · '+(key||'CHƯA CHỌN');
 const rows=corporateRows(esg,key),groups=new Map();
 for(const m of rows){
  if(!groups.has(m.metricId))groups.set(m.metricId,[]);
  const list=groups.get(m.metricId);
  if(!list.some(x=>String(x.year)===String(m.year)&&x.unit===m.unit))list.push(m);
 }
 const ids=[...groups.keys()];
 if(key!==companySymbol){companySymbol=key;corporateId='';}
 if(!ids.length){
  select.disabled=true;select.innerHTML='<option value="">Chưa có KPI đủ điều kiện</option>';
  body.innerHTML='<div class="macro-no-chart"><b>'+esc(key)+'</b> chưa có KPI ESG định lượng đã chuẩn hóa. Không tự tạo điểm tổng hợp hoặc suy đoán xu hướng.</div>';
  const doc=(company?.documents||[]).find(d=>httpsUrl(d.url));
  foot.innerHTML=doc?sourceLink(doc.url,'Công bố doanh nghiệp'):'<span>Chưa có công bố KPI đủ chuẩn liên kết.</span>';
  return;
 }
 select.disabled=false;
 const selected=select.value;
 if(groups.has(selected))corporateId=selected;
 if(!groups.has(corporateId)){
  corporateId=groups.has('green_credit')?'green_credit':ids.sort((a,b)=>groups.get(b).length-groups.get(a).length)[0];
 }
 select.innerHTML=[...groups.keys()].map(id=>{
  const m=groups.get(id)[0];
  return'<option value="'+esc(id)+'"'+(id===corporateId?' selected':'')+'>'+esc(m.label||id)+'</option>';
 }).join('');
 select.value=corporateId;
 const records=groups.get(corporateId).slice().sort((a,b)=>Number(b.year)-Number(a.year));
 const latestRaw=records[0],unitRaw=latestRaw.unit||'';
 const sameUnit=records.filter(m=>(m.unit||'')===unitRaw).sort((a,b)=>Number(a.year)-Number(b.year));
 const points=sameUnit.map(m=>({label:String(m.year),rank:Number(m.year)*12+11,y:m.value}));
 const last=points.at(-1),prev=points.at(-2),unit={
  'billion VND':'tỷ đồng','million VND':'triệu đồng',hours:'giờ',kWh:'kWh',m3:'m³'
 }[unitRaw]||unitRaw||'đơn vị gốc';
 const latestValue='<div class="macro-viz-value"><strong>'+esc(fmt(last.y))+'</strong><span>'+esc(unit)+'</span></div>';
 const info='<p class="macro-viz-comment">'+esc(latestRaw.label||latestRaw.metricId)+' · kỳ công bố '+esc(last.label)+'</p>';
 let visual=latestValue+info;
 if(points.length>=2){
  const delta=last.y-prev.y;
  visual+='<p class="macro-viz-comparison">So với '+esc(prev.label)+': '+(delta>0?'+':'')+esc(fmt(delta))+' '+esc(unitRaw==='%'?'điểm phần trăm':unit)+'</p>';
  visual+='<div class="macro-viz-plot">'+plot(points,{title:latestRaw.label||corporateId,unit,color:'#7561c0',limit:16})+'</div>';
 }else{
  visual+='<div class="macro-single-year"><span class="macro-single-dot" aria-hidden="true"></span><strong>Mới có dữ liệu năm '+esc(last.label)+'</strong><small>Chưa đủ hai năm cùng chỉ tiêu, cùng đơn vị để kết luận xu hướng.</small></div>';
 }
 body.innerHTML=visual;
 foot.innerHTML=sourceLink(latestRaw.sourceUrl,'Công bố gốc '+key)+'<span>'+esc(points.length)+' năm so sánh được · không có điểm ESG tổng hợp tự tính</span>';
}
function renderEsg(data,esg,symbol){
 renderCountry(data);
 renderCorporate(esg,symbol);
}
function render(data,esg,symbol){
 renderMacro(data);
 renderEsg(data,esg,symbol);
}
root.FinMacroDashboard={render,renderEsg,series,plot,corporateRows,rank,features:FEATURES.map(x=>x.id)};
})(window);
