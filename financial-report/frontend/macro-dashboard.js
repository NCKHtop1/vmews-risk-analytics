(function(root){'use strict';
/* FinQuery Macro & ESG: visualizes verified source rows, never synthetic observations. */
const $=id=>document.getElementById(id);
const nf=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2});
const fmt=n=>typeof n==='number'&&Number.isFinite(n)?nf.format(n):'—';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const FEATURES=[
 {id:'pmi',key:'PMI',title:'PMI sản xuất',unit:'điểm',scale:1,threshold:50,color:'#3565d5',info:'Mốc 50 phân biệt mở rộng và thu hẹp'},
 {id:'gdp_growth',key:'Tốc độ tăng trưởng GDP thực tế',title:'Tăng trưởng GDP thực tế',unit:'% YoY',scale:1,color:'#20795d',info:'Tổng GDP theo quý, không gộp các ngành có điểm ngoại lệ'},
 {id:'money_supply',key:'M2 (tỷ VND)',title:'Cung tiền M2',unit:'nghìn tỷ đồng',scale:1000,color:'#009d87',info:'Số dư M2 công bố theo tháng'},
 {id:'credit_sector',key:'Tổng dư nợ',title:'Dư nợ tín dụng',unit:'nghìn tỷ đồng',scale:1000,color:'#7561c0',info:'Số dư theo thống kê tín dụng'},
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
 .filter(p=>p.date!==null&&typeof p.raw==='number'&&Number.isFinite(p.raw) &&
 // A quality warning in another GDP sector must not blank the verified
 // aggregate; values beyond ±20% remain quarantined, never interpolated.
 (!(ds?.title||'').toLowerCase().includes('gdp')||p.raw>=-20&&p.raw<=20))
 .sort((a,b)=>a.date-b.date)
 .map(p=>({label:p.label,rank:p.date,y:p.raw/scale}));
}
function httpsUrl(raw){try{const u=new URL(String(raw||''));return u.protocol==='https:'?u.href:'';}catch{return'';}}
// Source URLs stay in the verified data model; the public dashboard does not render them.
function sourceLink(){return '';}

function plot(data,opts={}){
 const pts=data.slice(-(opts.limit||24));
 if(pts.length<2)return'<div class="macro-no-chart">Chuỗi này chưa có hai kỳ công bố hợp lệ để vẽ xu hướng.</div>';
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
 const exact=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:6});
 const tips=pts.map((p,i)=>'<circle data-fq-point="'+i+'" data-fq-x="'+x(i).toFixed(1)+'" data-fq-y="'+y(p.y).toFixed(1)+'" data-fq-label="'+esc(p.label)+'" data-fq-series="'+esc(opts.title||'Biểu đồ')+'" data-fq-value="'+esc(exact.format(p.y))+'" data-fq-unit="'+esc(opts.unit||'')+'" cx="'+x(i).toFixed(1)+'" cy="'+y(p.y).toFixed(1)+'" r="3.2" fill="'+color+'"/>').join('');
 const last=pts.at(-1);
 return'<svg class="macro-trend-svg" viewBox="0 0 '+width+' '+height+'" data-fq-inspect="line" data-fq-top="'+t+'" data-fq-bottom="'+(height-b)+'" data-fq-color="'+color+'" tabindex="0" role="img" aria-label="'+esc((opts.title||'Biểu đồ')+' · '+pts.length+' kỳ dữ liệu')+'">'+grid+threshold+'<path d="'+shape+'" fill="none" stroke="'+color+'" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/><circle cx="'+x(pts.length-1).toFixed(1)+'" cy="'+y(last.y).toFixed(1)+'" r="5" fill="'+color+'" stroke="white" stroke-width="2"/>'+tips+horizontal+'</svg>';
}
function renderMacro(data){
 const host=$('macro-overview');if(!host)return;
 const sources=data?.sources||[];
 if(!data?.datasets||!FEATURES.some(feature=>data.datasets[feature.id])){
  host.innerHTML='<article class="macro-viz-card macro-state-full" role="status"><h4>Đang kiểm tra dữ liệu vĩ mô</h4><p>Dữ liệu vĩ mô chưa kết nối được. Thử Cập nhật; ESG doanh nghiệp vẫn hoạt động độc lập nếu có dữ liệu.</p></article>';
  return;
 }
 host.innerHTML=FEATURES.filter(c=>data?.datasets?.[c.id]).map(c=>{
  const ds=data?.datasets?.[c.id],src=sources.find(s=>s.id===c.id);
  const qualityNotice=ds?.qualityStatus==='warning'||src?.qualityStatus==='warning';
  // Quality is assessed per metric rather than suppressing every time-series
  // when only a separate GDP sector contains a suspicious observation.
  const allowed=!!ds&&['ok','cached','retained'].includes(ds.status)&&
    (!src||['ok','cached','retained','error'].includes(src.status));
  const pts=allowed?series(ds,c.key,c.scale):[];
  const last=pts.at(-1),earlier=pts.at(-2);
  // FDI is cumulative within each calendar year. Connecting December to
  // January would misrepresent the accounting reset as a sudden downturn.
  const drawn=c.id==='fdi'&&last?pts.filter(p=>p.label.endsWith(last.label.slice(-4))):pts;
  const head='<div class="macro-viz-head"><div><span class="macro-viz-kicker">KINH TẾ VIỆT NAM</span><h4>'+esc(c.title)+'</h4></div>'+(last?'<span class="macro-viz-period">'+esc(last.label)+'</span>':'')+'</div>';
  const link=sourceLink(src?.url,'Nguồn');
  if(pts.length<2){
    const issue='Chưa đủ số liệu hợp lệ để vẽ xu hướng.';
    return'<article class="macro-viz-card">'+head+
      (last?'<div class="macro-viz-value"><strong>'+esc(fmt(last.y))+'</strong><span>'+esc(c.unit)+'</span></div><p class="macro-viz-comment">Mốc công bố '+esc(last.label)+' · chưa đủ hai kỳ để vẽ đường.</p>':
      '<div class="macro-source-notice" role="status">'+issue+'</div>')+
      '<div class="macro-viz-source">'+link+'</div></article>';
  }
  let context='';
  if(c.id==='pmi')context=last.y>=50?'Trên mốc 50 · sản xuất đang mở rộng':'Dưới mốc 50 · sản xuất đang thu hẹp';
  else if(c.id==='fdi')context='';
  else context='So với '+esc(earlier.label)+': '+(last.y>=earlier.y?'+':'')+esc(fmt(last.y-earlier.y))+' '+esc(c.unit);
  const retained=ds?.status==='retained'||src?.status==='retained'||src?.status==='error';
  return'<article class="macro-viz-card">'+head+(retained?'<span class="macro-quiet-note">Kỳ công bố gần nhất</span>':'')+
    (qualityNotice?'<span class="macro-quiet-note" title="Một số kỳ công bố có cảnh báo chất lượng, cần xác minh thêm">Một số kỳ cần xác minh</span>':'')+'<div class="macro-viz-value"><strong>'+esc(fmt(last.y))+'</strong><span>'+esc(c.unit)+'</span></div><p class="macro-viz-comment">'+context+'</p><div class="macro-viz-plot">'+plot(drawn,{title:c.title,unit:c.unit,color:c.color,threshold:c.threshold})+'</div><div class="macro-viz-source">'+link+'</div></article>';
 }).join('');
 const checkDate=new Date(data?.checkedAt);
 const freshness=$('macro-data-freshness');
 if(freshness)freshness.textContent=Number.isNaN(checkDate.getTime())?'—':checkDate.toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'});
}

function renderCountry(data){
 const ds=data?.datasets?.esg_world_bank,body=$('macro-country-chart'),foot=$('macro-country-source'),select=$('macro-country-metric');
 if(!body||!select||!foot)return;
 const choices=WORLD.filter(m=>series(ds,m.id).length>=2);
 if(!choices.length||!['ok','cached','retained'].includes(ds?.status)){
  select.innerHTML='<option value="">Chờ dữ liệu</option>';select.disabled=true;
  const message=ds?.qualityStatus==='warning'?'Chuỗi ESG quốc gia đang được đối chiếu chất lượng.':
   !ds?'Chưa tải được ESG quốc gia. Các số liệu doanh nghiệp, nếu có, vẫn được hiển thị độc lập.':
   'Chưa tìm thấy ít nhất hai năm quan sát hợp lệ cho các chỉ tiêu ESG đã chọn.';
  body.innerHTML='<div class="macro-source-notice" role="status">'+message+'</div>';
  foot.innerHTML=sourceLink((data?.sources||[]).find(s=>s.id==='esg_world_bank')?.url,'Nguồn World Bank');return;
 }
 select.disabled=false;
 const selected=select.value;
 if(choices.some(x=>x.id===selected))countryId=selected;
 if(!choices.some(x=>x.id===countryId))countryId=choices[0].id;
 select.innerHTML=choices.map(m=>'<option value="'+esc(m.id)+'"'+(m.id===countryId?' selected':'')+'>'+esc(m.title)+'</option>').join('');
 select.value=countryId;
 const metric=choices.find(m=>m.id===countryId);
 const pts=series(ds,metric.id),latest=pts.at(-1);
 body.innerHTML='<div class="macro-viz-value"><strong>'+esc(fmt(latest.y))+'</strong><span>'+esc(metric.unit)+'</span></div><p class="macro-viz-comment">Năm công bố '+esc(latest.label)+' · không đồng nghĩa dữ liệu năm hiện tại</p>'+
  (ds.status==='retained'?'<div class="macro-source-notice">Đang sử dụng kỳ công bố đã lưu; chưa nhận bản mới.</div>':'')+
  '<div class="macro-viz-plot">'+plot(pts,{title:metric.title,unit:metric.unit,color:'#158c83',limit:24})+'</div>';
 const source=(data.sources||[]).find(s=>s.id==='esg_world_bank');
 foot.innerHTML=sourceLink(source?.url,'Ngân hàng Thế giới');
}
function corporateRows(esg,symbol){
 const company=esg?.companies?.[symbol];
 const approved=Array.isArray(company?.canonicalMetrics)?company.canonicalMetrics:[];
 return approved.filter(m=>{
  if(!m||!m.metricId||typeof m.value!=='number'||!Number.isFinite(m.value)||
     !Number.isInteger(Number(m.year))||m.year<2000||m.year>2100||!httpsUrl(m.sourceUrl))return false;
  // Reject obviously mis-scaled VND rows (e.g. raw "2000 tỷ VND" parsed
  // as 0.000002 billion VND). Do not silently transform uncertain disclosures.
  if(m.unit==='billion VND'&&m.value>0&&m.value<.001){
    const raw=Number(String(m.rawValue||'').replace(/[^0-9.,]/g,'').replace(/\./g,'').replace(',','.'));
    if(Number.isFinite(raw)&&raw>=1)return false;
  }
  if(m.metricId.endsWith('_pct')&&(m.value<0||m.value>100))return false;
  return true;
 });
}
function renderCorporate(esg,symbol){
 const body=$('macro-company-chart'),foot=$('macro-company-source'),select=$('macro-company-metric'),title=$('macro-company-symbol');
 if(!body||!foot||!select)return;
 const key=String(symbol||'').toUpperCase(),company=esg?.companies?.[key];
 if(title)title.textContent='DOANH NGHIỆP · '+(key||'CHƯA CHỌN');
 const rows=corporateRows(esg,key),groups=new Map();
 const rejected=Math.max(0,(company?.canonicalMetrics?.length||0)-rows.length);
 for(const m of rows){
  if(!groups.has(m.metricId))groups.set(m.metricId,[]);
  const list=groups.get(m.metricId);
  if(!list.some(x=>String(x.year)===String(m.year)&&x.unit===m.unit))list.push(m);
 }
 const ids=[...groups.keys()];
 if(key!==companySymbol){companySymbol=key;corporateId='';}
 if(!ids.length){
  select.disabled=true;select.innerHTML='<option value="">Chưa có KPI đủ điều kiện</option>';
  const docs=(company?.documents||[]).filter(d=>httpsUrl(d.url));
  const processed=docs.filter(d=>d.processedAt).length;
  const found=docs.length;
  const candidates=docs.slice().sort((a,b)=>(Number(b.year)||0)-(Number(a.year)||0)).slice(0,3);
  const external=(company?.externalAssessments||[]).filter(x=>httpsUrl(x.sourceUrl)).slice(0,2);
  const title=company?.name||key||'Doanh nghiệp';
  const message=!esg?'Dữ liệu ESG đang gián đoạn. Chưa thể kết luận doanh nghiệp không công bố thông tin.':
   !company?'Chưa tra cứu được hồ sơ ESG cho mã này trong danh mục VN100.':
   found?'Đã ghi nhận '+found+' hồ sơ công bố ('+processed+' hồ sơ xử lý). Đang đối chiếu số định lượng và năm báo cáo; dữ liệu chưa xác minh không được đưa vào biểu đồ.':
   'Đang cập nhật hồ sơ công bố và danh mục báo cáo của doanh nghiệp. Chưa có hồ sơ đủ điều kiện trong lần thu thập này; không suy ra doanh nghiệp không có hoạt động ESG.';
  const links=candidates.map(d=>sourceLink(d.url,
   (d.type==='annual_report'?'Báo cáo thường niên':d.type==='sustainability_report'?'Báo cáo phát triển bền vững':'Tài liệu công bố')+
   (d.year?' '+d.year:'')
  )).join(' · ');
  const index=key&&/^[A-Z]{3}$/.test(key)?
   sourceLink('https://24hmoney.vn/stock/'+key.toLowerCase()+'/report','Danh mục công bố của '+key):'';
  body.innerHTML='<div class="macro-esg-disclosure" role="status"><strong>'+esc(title)+'</strong><p>'+message+'</p>'+
    (links?'<div class="macro-disclosure-links"><strong>Hồ sơ hiện có</strong> · '+links+'</div>':'')+
    (external.length?'<small>Đã có '+external.length+' đánh giá từ nguồn ngoài; không quy đổi thành điểm ESG tổng hợp.</small>':'')+
    (rejected?'<small>'+rejected+' dòng KPI nghi sai đơn vị hoặc vượt giới hạn đã bị giữ lại để đối chiếu.</small>':'')+
    '<small>KPI chưa kiểm chứng được giữ trống; không nội suy số liệu hoặc xếp hạng giả.</small></div>';
  foot.innerHTML=found?sourceLink(candidates[0]?.url,'Mở tài liệu nguồn'):index;
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
  visual+='<div class="macro-single-year"><span class="macro-single-dot" aria-hidden="true"></span><strong>Năm '+esc(last.label)+'</strong></div>';
 }
 body.innerHTML=visual;
 foot.innerHTML=sourceLink(latestRaw.sourceUrl,'Công bố gốc');
}
function renderEsg(data,esg,symbol){
 const coverage=$('macro-esg-coverage');
 if(coverage){
  const companies=Object.values(esg?.companies||{}),withKpi=companies.filter(c=>
   Array.isArray(c.canonicalMetrics)&&c.canonicalMetrics.some(r=>typeof r.value==='number'&&Number.isFinite(r.value)&&httpsUrl(r.sourceUrl))).length;
  const withDocs=companies.filter(c=>(c.documents||[]).some(d=>httpsUrl(d.url))).length;
  const documentedWithoutKpi=companies.filter(c=>(c.documents||[]).some(d=>httpsUrl(d.url))&&
    !corporateRows(esg,c.symbol).length).length;
  const searching=companies.filter(c=>!corporateRows(esg,c.symbol).length&&
    !(c.documents||[]).some(d=>httpsUrl(d.url))).length;
  const last=esg?.checkedAt?new Date(esg.checkedAt):null;
  const lastCheck=last&&Number.isFinite(+last)?last.toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'chưa rõ';
  coverage.textContent=esg?'VN100 · '+companies.length+' doanh nghiệp · '+withDocs+' có tài liệu ESG · '+withKpi+' có KPI chuẩn hóa':'Dữ liệu ESG doanh nghiệp đang kết nối.';
  coverage.title=esg?'Chi tiết dữ liệu ESG: '+documentedWithoutKpi+' có tài liệu nhưng chưa có KPI · '+searching+' chưa có hồ sơ phù hợp · kiểm tra '+lastCheck:'';
 }
 renderCountry(data);
 renderCorporate(esg,symbol);
} 
function render(data,esg,symbol){
 renderMacro(data);
 renderEsg(data,esg,symbol);
}
root.FinMacroDashboard={render,renderEsg,series,plot,corporateRows,rank,features:FEATURES.map(x=>x.id)};
})(window);
