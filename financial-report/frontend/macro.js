(function(){'use strict';
const $=id=>document.getElementById(id);
const RAW='https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/';
const LOCAL=document.documentElement.dataset.hosting==='pages'?
  new URL('market/',location.href).href:new URL('/financial-report/market/',location.origin).href;
const BASE=document.documentElement.dataset.hosting==='pages'?LOCAL:RAW;
// Concurrently verify both publishers: a fast mirrored snapshot can be stale.
const ROOTS=[...new Set([RAW,LOCAL])];
const state={data:null,rawMacro:null,esg:null,symbol:'',active:'pmi',metric:'',
 countryMetric:'AG.LND.FRST.ZS',companyMetric:'',unlocked:true,
 sourceStatus:{macro:'loading',esg:'loading'},loading:false};
const fmt=v=>typeof v==='number'&&Number.isFinite(v)?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2}).format(v):String(v??'—');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
async function fetchVerifiedFile(file,validator,timeout=12000){
 const revision=Math.floor(Date.now()/60000);
 const results=await Promise.allSettled(ROOTS.map(async root=>{
  const r=await fetch(root+file+'?v='+revision,{
   cache:'no-store',signal:AbortSignal.timeout(timeout)
  });
  if(!r.ok)throw Error('HTTP '+r.status);
  const payload=await r.json();
  const stamp=Date.parse(payload?.checkedAt||'');
  if(!Number.isFinite(stamp)||stamp>Date.now()+300000||!validator(payload))
   throw Error('Snapshot/source metadata invalid');
  return {payload,stamp,origin:root};
 }));
 const valid=results.filter(r=>r.status==='fulfilled').map(r=>r.value)
  .sort((a,b)=>b.stamp-a.stamp);
 if(valid.length)return valid[0].payload;
 const errors=results.map(r=>r.status==='rejected'?String(r.reason?.message||r.reason):'').filter(Boolean);
 throw Error(file+' không tải được từ nguồn chính và dự phòng: '+errors.join('; ').slice(0,230));
}
const fetchMacro=()=>fetchVerifiedFile('macro.json',d=>d?.datasets&&
 Object.keys(d.datasets).length>0&&d.status!=='error',11000);
const fetchCompanyEsg=()=>fetchVerifiedFile('company-esg.json',d=>
 d?.companies&&typeof d.companies==='object'&&Object.keys(d.companies).length>0&&d.status!=='error',15000);
function periodLabel(value){return periodRank(value)!==null;}
function periodRank(value){
 const s=String(value||'').trim();
 let m=s.match(/^T(1[0-2]|[1-9])\s+(\d{4})$/i);if(m)return Number(m[2])*12+Number(m[1])-1;
 m=s.match(/^Q([1-4])\s+(\d{4})$/i);if(m)return Number(m[2])*12+(Number(m[1])-1)*3+2;
 m=s.match(/^(\d{4})[-/](\d{1,2})$/);if(m&&Number(m[2])>=1&&Number(m[2])<=12)return Number(m[1])*12+Number(m[2])-1;
 m=s.match(/^(\d{4})$/);if(m)return Number(m[1])*12+11;
 return null;
}
function normalizeDataset(ds){
 const cols=ds.columns||[],first=cols[0],periodCols=cols.slice(1).filter(periodLabel),rows=ds.rows||[];
 if(first&&periodCols.length>=Math.max(3,Math.floor((cols.length-1)*.6))&&rows.length){
  const names=rows.map((r,i)=>String(r[first]??('Chỉ tiêu '+(i+1))).trim()).filter(Boolean),units=cols[1]==='- (2)'?rows.map(r=>r['- (2)']):[];
  const out=periodCols.sort((a,b)=>periodRank(a)-periodRank(b)).map(p=>{const row={Date:p};rows.forEach((r,i)=>{const name=names[i]||('Chỉ tiêu '+(i+1));if(typeof r[p]==='number')row[name]=r[p];});return row;});
  const metrics=[...new Set(out.flatMap(r=>Object.keys(r).filter(k=>k!=='Date'&&typeof r[k]==='number')))];
  return {...ds,columns:['Date',...metrics],numericColumns:metrics,rows:out,orientation:'time-columns',units:Object.fromEntries(names.map((n,i)=>[n,units[i]||'']))};
 }
 const timed=first?rows.map(row=>({row,rank:periodRank(row[first])})).filter(x=>x.rank!==null):[];
 if(timed.length>=3){
  const sorted=timed.sort((a,b)=>a.rank-b.rank).map(x=>x.row);
  return {...ds,rows:sorted,orientation:'time-rows'};
 }
 return {...ds,orientation:'time-rows'};
}
let manuallySelectedCompany='';
function currentSymbol(){
 return String(manuallySelectedCompany||new URL(location.href).searchParams.get('symbol')||
  $('ticker')?.value||'FPT').trim().toUpperCase();
}
function renderCompanyPicker(){
 const select=$('macro-company-ticker');
 if(!select||!state.esg)return;
 const records=Object.entries(state.esg.companies||{}).sort(([a],[b])=>a.localeCompare(b));
 const selected=state.symbol;
 select.innerHTML=records.map(([symbol,c])=>{
  const trusted=window.FinMacroDashboard?.corporateRows?.(state.esg,symbol)||[];
  const docs=(c.documents||[]).filter(d=>/^https:\/\//.test(String(d.url||''))).length;
  const suffix=trusted.length?' · KPI '+trusted.length:docs?' · '+docs+' tài liệu':' · đang tìm nguồn';
  return '<option value="'+esc(symbol)+'"'+(symbol===selected?' selected':'')+'>'+esc(symbol+suffix)+'</option>';
 }).join('');
 if(records.some(([key])=>key===selected))select.value=selected;
}

function corporateDataset(esg,symbol){
 const company=esg?.companies?.[symbol];if(!company)return null;
 const years={},labels={},units={},pillars={};
 // Use the same quality gate in the macro Explorer and the main ESG card.
 const metricRows=window.FinMacroDashboard?.corporateRows?.(esg,symbol)||
   (Array.isArray(company.canonicalMetrics)?company.canonicalMetrics:[]);
 for(const row of metricRows){
  const year=Number(row.year),value=row.value;if(!Number.isFinite(year)||typeof value!=='number'||!Number.isFinite(value)||!row.metricId||!row.sourceUrl)continue;
  years[year]??={Year:year};years[year][row.metricId]=value;labels[row.metricId]=row.label||row.metricId;if(row.unit)units[row.metricId]=row.unit;if(row.pillar)pillars[row.metricId]=row.pillar;
 }
 const rows=Object.values(years).sort((a,b)=>a.Year-b.Year),metrics=[...new Set(rows.flatMap(r=>Object.keys(r).filter(k=>k!=='Year'&&Number.isFinite(r[k]))))];
 return{id:'company_esg_'+symbol,title:'ESG doanh nghiệp · '+symbol,source:'Công bố doanh nghiệp',status:'ok',companySymbol:symbol,columns:['Year',...metrics],numericColumns:metrics,metricLabels:labels,metricUnits:units,metricPillars:pillars,rows,allYears:true,metricTable:true};
}
function normalizePayload(data,esg,symbol){const datasets={};for(const[id,ds]of Object.entries(data.datasets||{}))datasets[id]=normalizeDataset({...ds,id});const corporate=corporateDataset(esg,symbol);if(corporate)datasets[corporate.id]=normalizeDataset(corporate);return{...data,datasets};}
function firstColumn(ds){return(ds.columns||[])[0]||'Date';}
function latestRow(ds){const rows=ds.rows||[];for(let i=rows.length-1;i>=0;i--){if(Object.values(rows[i]||{}).some(v=>v!==null&&v!==''))return rows[i];}return null;}
function latestMetricPoint(ds,key){const rows=(ds?.rows||[]).slice().reverse();for(const row of rows){const value=row?.[key];if(typeof value==='number'&&Number.isFinite(value))return{year:row[firstColumn(ds)],value};}return null;}
function displayTitle(value){return String(value||'').replace(/\bVBMA\b/gi,'').replace(/\s{2,}/g,' ').trim()||'Dữ liệu';}
function renderTabs(){const box=$('macro-tabs'),sets=state.data?.datasets||{};box.innerHTML=Object.entries(sets).map(([id,ds])=>'<button type="button" data-macro-tab="'+esc(id)+'" class="'+(id===state.active?'active':'')+'">'+esc(displayTitle(ds.title||id))+'</button>').join('');}
function metricLabel(ds,key){return ds?.metricLabels?.[key]||key;}
function metricUnit(ds,key){return ds?.metricUnits?.[key]||ds?.units?.[key]||'';}
function metricOptions(){
 const ds=state.data?.datasets?.[state.active],select=$('macro-metric');
 if(!ds||!select)return;
 const metrics=(ds.numericColumns||[]).filter(k=>chartPoints(ds,k).length>0)
  .sort((a,b)=>chartPoints(ds,b).length-chartPoints(ds,a).length);
 select.innerHTML=metrics.length?metrics.map(x=>'<option value="'+esc(x)+'">'+
   esc(metricLabel(ds,x))+(x!==metricLabel(ds,x)?' · '+esc(x):'')+'</option>').join(''):
  '<option value="">Chưa có KPI định lượng</option>';
 select.disabled=!metrics.length;
 if(!metrics.includes(state.metric))state.metric=metrics[0]||'';
 select.value=state.metric;
}
function renderKpis(){
 const ds=state.data?.datasets?.[state.active],box=$('macro-kpis');if(!ds){box.innerHTML='';return;}
 const cols=(ds.numericColumns||[]).slice(0,4);
 if(ds.companySymbol){
  box.innerHTML=cols.map(k=>{const p=latestMetricPoint(ds,k),unit=metricUnit(ds,k);return'<div class="macro-kpi"><span>'+esc(metricLabel(ds,k))+'</span><strong>'+esc(p?fmt(p.value):'—')+'</strong><small>'+esc([p?.year,unit].filter(Boolean).join(' · '))+'</small></div>';}).join('');
  return;
 }
 box.innerHTML=cols.map(k=>{
  const point=latestMetricPoint(ds,k);
  return'<div class="macro-kpi"><span>'+esc(metricLabel(ds,k))+'</span><strong>'+
   esc(point?fmt(point.value):'—')+'</strong><small>'+
   esc([point?.year,metricUnit(ds,k)].filter(Boolean).join(' · '))+'</small></div>';
 }).join('');
}
function chartPoints(ds,metric){
 const label=firstColumn(ds),points=(ds.rows||[])
  .map((r,i)=>({x:i,label:r[label]??String(i+1),y:r[metric]}))
  .filter(p=>typeof p.y==='number'&&Number.isFinite(p.y) &&
   // GDP sector outliers are documented by the feed. Keep only plausible
   // rows from each chosen metric; do not hide the whole GDP dataset.
   (ds?.id!=='gdp_growth'||p.y>=-20&&p.y<=20));
 return ds.allYears?points:points.slice(-48);
}
function renderChart(){
 const ds=state.data?.datasets?.[state.active],box=$('macro-chart'),card=box?.closest('.macro-chart-card');
 if(!ds||!state.metric){
   if(card)card.hidden=false;
   const company=ds?.companySymbol&&state.esg?.companies?.[ds.companySymbol];
   const documented=company?.coverage?.documents||company?.documents?.length||0;
   box.innerHTML=ds?.companySymbol?
    '<div class="macro-source-notice">Đang đối chiếu KPI ESG của '+esc(ds.companySymbol)+'. Đã ghi nhận '+
     documented+' báo cáo nguồn; chỉ số định lượng chưa xác minh không được tự điền. Chọn tài liệu nguồn phía trên để đối chiếu.</div>':
    '<div class="macro-source-notice">Nguồn vĩ mô đang được kiểm tra. Chọn một chỉ tiêu có số kỳ công bố hợp lệ.</div>';
   return;
 }
 const pts=chartPoints(ds,state.metric),unit=metricUnit(ds,state.metric),label=metricLabel(ds,state.metric);
 if(ds.companySymbol&&pts.length===1){
  if(card)card.hidden=false;
  $('macro-chart-title').textContent='KPI ESG · '+label;
  $('macro-chart-subtitle').textContent='1 năm có dữ liệu kiểm chứng · không nội suy';
  box.innerHTML='<div class="macro-single-observation"><strong>'+esc(fmt(pts[0].y))+
    '</strong><span>'+esc(unit)+' · Năm '+esc(pts[0].label)+
    '</span><small>Chưa có năm thứ hai để tính biến động. Giá trị lấy từ công bố nguồn.</small></div>';
  return;
 }
 if(card)card.hidden=false;
 $('macro-chart-title').textContent=ds.companySymbol?'Xu hướng · '+label:displayTitle(ds.title||'Dữ liệu vĩ mô & ESG');
 $('macro-chart-subtitle').textContent=(unit?unit+' · ':'')+(ds.companySymbol?pts.length+' năm có dữ liệu':label+(ds.allYears?'':''))+(ds.status==='retained'?'':'');
 if(pts.length<2){box.innerHTML='<div class="analysis-empty">Chưa đủ hai kỳ công bố có số liệu hợp lệ cho chỉ tiêu này.</div>';return;}
 const w=900,h=320,pad=42,min=Math.min(...pts.map(x=>x.y)),max=Math.max(...pts.map(x=>x.y)),span=max-min||1,xx=i=>pad+(w-2*pad)*(i/Math.max(1,pts.length-1)),yy=v=>h-pad-(h-2*pad)*((v-min)/span),path=pts.map((p,i)=>(i?'L':'M')+xx(i).toFixed(1)+' '+yy(p.y).toFixed(1)).join(' '),last=pts.at(-1);const ticks=[0,.25,.5,.75,1].map(t=>{const val=min+span*t,y=yy(val);return'<line x1="'+pad+'" y1="'+y+'" x2="'+(w-pad)+'" y2="'+y+'" stroke="#edf1f6"/><text x="4" y="'+(y+4)+'" font-size="10" fill="#7c889a">'+esc(fmt(val))+'</text>';}).join('');const labels=[0,Math.floor((pts.length-1)/2),pts.length-1].map(i=>'<text x="'+xx(i)+'" y="'+(h-10)+'" text-anchor="'+(i===0?'start':i===pts.length-1?'end':'middle')+'" font-size="10" fill="#7c889a">'+esc(String(pts[i].label).slice(0,18))+'</text>').join('');box.innerHTML='<svg viewBox="0 0 '+w+' '+h+'" role="img" aria-label="'+esc(ds.title+' '+state.metric)+'">'+ticks+'<path d="'+path+'" fill="none" stroke="#4d67c8" stroke-width="2"/><circle cx="'+xx(pts.length-1)+'" cy="'+yy(last.y)+'" r="4" fill="#4d67c8"/>'+labels+'</svg>';
}
function renderTable(){
 const ds=state.data?.datasets?.[state.active];if(!ds)return;const head=$('macro-table-head'),body=$('macro-table-body'),wrap=body?.closest('.macro-table-wrap');
 if(ds.companySymbol&&!state.metric){if(wrap)wrap.hidden=true;head.innerHTML='';body.innerHTML='';return;}
 if(wrap)wrap.hidden=false;
 const first=firstColumn(ds),cols=ds.metricTable?[first,state.metric].filter(Boolean):(ds.columns||[]),base=ds.rows||[];
 const filtered=ds.metricTable&&state.metric?base.filter(r=>Number.isFinite(Number(r?.[state.metric]))):base;
 const rows=(ds.allYears?filtered:filtered.slice(-20)).slice().reverse();
 head.innerHTML='<tr>'+cols.map(x=>'<th>'+esc(x===first?(ds.metricTable?'Năm':x):metricLabel(ds,x))+'</th>').join('')+'</tr>';
 body.innerHTML=rows.map(r=>'<tr>'+cols.map(x=>'<td>'+esc(x===first&&ds.metricTable?String(r[x]??'—'):fmt(r[x]))+'</td>').join('')+'</tr>').join('');
}
function conciseSourceTitle(row){
 const year=row?.year||'',type=row?.sourceType||row?.type||'',title=String(row?.sourceTitle||row?.title||'').replace(/\s+/g,' ').trim();
 if(type==='sustainability_report')return'Báo cáo PTBV'+(year?' '+year:'');
 if(type==='annual_report')return'Báo cáo thường niên'+(year?' '+year:'');
 if(type==='climate_disclosure')return'Báo cáo khí hậu'+(year?' '+year:'');
 if(type==='esg_web_content')return'Công bố ESG/PTBV'+(year?' '+year:'');
 return title.length>84?title.slice(0,81)+'…':(title||'Nguồn công bố');
}
function renderAssessments(){
 const box=$('macro-esg-assessments'),ds=state.data?.datasets?.[state.active],company=ds?.companySymbol&&state.esg?.companies?.[ds.companySymbol];if(!box)return;
 if(!company){box.hidden=true;box.innerHTML='';return;}
 // Raw PDF matches are NOT validated ESG values. Only canonical rows may
 // appear in KPI charts, summaries, or external-source comparison.
 const metrics=(window.FinMacroDashboard?.corporateRows?.(state.esg,ds.companySymbol)||
  (Array.isArray(company.canonicalMetrics)?company.canonicalMetrics:[]))
  .filter(x=>typeof x.value==='number'&&Number.isFinite(x.value)&&x.sourceUrl);
 const metricSources=metrics.filter(x=>x.metricId===state.metric).sort((a,b)=>(b.year||0)-(a.year||0));
 const ratings=(company.externalAssessments||[]).slice().sort((a,b)=>(b.year||0)-(a.year||0)).slice(0,8);
 const years=[...new Set(metrics.map(x=>Number(x.year)).filter(Number.isFinite))].sort((a,b)=>a-b);
 const metricIds=[...new Set(metrics.map(x=>x.metricId).filter(Boolean))];
 const sourceCount=new Set(metrics.map(x=>x.sourceUrl).filter(Boolean)).size;
 const pillarMetricIds=metrics.reduce((acc,x)=>{const p=x.pillar||'—';acc[p]??=new Set();if(x.metricId)acc[p].add(x.metricId);return acc;},{});
 const pillarCounts=Object.fromEntries(Object.entries(pillarMetricIds).map(([k,v])=>[k,v.size]));
 const docsRaw=(company.documents||[]).filter(d=>d.processedAt&&d.url&&d.year).sort((a,b)=>(b.year||0)-(a.year||0));
 const seenDocs=new Set(),docs=[];for(const d of docsRaw){const key=(d.type||'')+'|'+(d.year||'');if(seenDocs.has(key))continue;seenDocs.add(key);docs.push(d);if(docs.length>=4)break;}
 const coverage='<div class="macro-esg-summary"><span><b>'+metricIds.length+'</b> chỉ tiêu</span><span><b>'+metrics.length+'</b> điểm dữ liệu</span><span><b>'+years.length+'</b> năm</span><span><b>'+sourceCount+'</b> nguồn</span><span><b>'+(ratings.length||0)+'</b> đánh giá ngoài</span></div>';
 const pillars='<div class="macro-esg-pillars"><span class="e">E · '+(pillarCounts.E||0)+'</span><span class="s">S · '+(pillarCounts.S||0)+'</span><span class="g">G · '+(pillarCounts.G||0)+'</span></div>';
 const selected=metricSources.length?'<div class="macro-esg-metric-sources"><strong>KPI đang xem · '+esc(metricLabel(ds,state.metric))+'</strong>'+metricSources.map(x=>'<a href="'+esc(x.sourceUrl||'#')+'" target="_blank" rel="noopener"><span>'+esc(String(x.year||'—'))+'</span><b>'+esc(fmt(x.value))+(x.unit?' '+esc(x.unit):'')+'</b><small>'+esc(conciseSourceTitle(x))+'</small></a>').join('')+'</div>':'';
 const ratingBlock=ratings.length?'<div class="macro-esg-section-title">Đánh giá bên ngoài</div><div class="macro-esg-rating-grid">'+ratings.map(x=>'<article><span>'+esc(x.provider||'Nguồn ngoài')+' · '+esc(String(x.year||'—'))+'</span><strong>'+esc(x.value||x.assessmentType||'Đã công bố')+'</strong><small>'+esc(x.assessmentType||'')+'</small>'+(x.sourceUrl?'<a href="'+esc(x.sourceUrl)+'" target="_blank" rel="noopener">Mở nguồn ↗</a>':'')+'</article>').join('')+'</div>':'';
 const noData=!metrics.length?'<p class="macro-source-notice">Chưa chuẩn hóa được KPI ESG định lượng từ công bố hiện có. Các tài liệu tìm được vẫn được giữ ở mục nguồn; không tạo điểm ESG ước tính.</p>':'';
 const docsBlock=docs.length?'<div class="macro-esg-docs"><strong>Nguồn chính</strong>'+docs.map(d=>'<a href="'+esc(d.url)+'" target="_blank" rel="noopener">'+esc(conciseSourceTitle(d))+'</a>').join('')+'</div>':'';
 box.hidden=false;box.innerHTML='<div class="macro-esg-head"><div><strong>ESG doanh nghiệp · '+esc(ds.companySymbol)+'</strong></div>'+pillars+'</div>'+coverage+noData+selected+ratingBlock+docsBlock;
}
function renderDashboard(){window.FinMacroDashboard?.render(state.data,state.esg,state.symbol);}
function renderEsgPanels(){window.FinMacroDashboard?.renderEsg(state.data,state.esg,state.symbol);}
function updateSourceStatus(){
 const el=$('macro-source-status');if(!el)return;
 const vn=date=>{const d=new Date(date||'');return Number.isNaN(+d)?'chưa xác định':
  d.toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',
    hour:'2-digit',minute:'2-digit',hour12:false});};
 const macro=state.rawMacro?'Vĩ mô '+vn(state.rawMacro.checkedAt)+
  ((state.rawMacro.sources||[]).some(src=>src.qualityStatus==='warning')?' · có chuỗi cần đối chiếu':''):
  'Vĩ mô chưa kết nối';
 const esg=state.esg?'ESG '+vn(state.esg.checkedAt)+
  ' · '+Object.keys(state.esg.companies||{}).filter(symbol=>
    window.FinMacroDashboard?.corporateRows?.(state.esg,symbol)?.length).length+'/100 mã có KPI kiểm chứng':
  'ESG chưa kết nối';
 const retained=[state.sourceStatus.macro,state.sourceStatus.esg].includes('retained');
 el.textContent=macro+' · '+esg+(retained?' · đang giữ bản trước':'');
 el.title='Ngày thu thập khác kỳ công bố kinh tế/ESG. Chỉ dùng chỉ tiêu có giá trị và nguồn gốc.';
}
function render(){
 if(!state.data)return;
 const sets=state.data.datasets||{};
 if(!sets[state.active]){
  const companyTab=state.symbol&&'company_esg_'+state.symbol;
  state.active=String(state.active||'').startsWith('company_esg_')&&sets[companyTab]?
    companyTab:sets.pmi?'pmi':Object.keys(sets)[0]||'';
 }
 renderCompanyPicker();renderDashboard();renderExplore();updateSourceStatus();
}
async function load(){
 if(state.loading)return;
 state.loading=true;
 if(!state.data){const status=$('macro-source-status');if(status)status.textContent='Đang kết nối nguồn vĩ mô và ESG…';}
 // The two sources must not form a single point of failure. Render the
 // successful half as soon as it lands; retain last verified data on failure.
 const update=()=>{
  state.symbol=currentSymbol()||state.symbol;
  state.data=normalizePayload(state.rawMacro||{datasets:{},sources:[],checkedAt:''},
   state.esg,state.symbol);
  render();
 };
 const jobs=[
  fetchMacro().then(value=>{
   const last=Date.parse(state.rawMacro?.checkedAt||'');
   if(!Number.isFinite(last)||Date.parse(value.checkedAt)>=last)
    state.rawMacro=value;
   state.sourceStatus.macro=Date.parse(value.checkedAt)<last?'retained':'ok';update();
  }).catch(error=>{
   state.sourceStatus.macro=state.rawMacro?'retained':'error';
   console.warn('FinQuery macro source:',String(error?.message||error));update();
  }),
  fetchCompanyEsg().then(value=>{
   const last=Date.parse(state.esg?.checkedAt||'');
   if(!Number.isFinite(last)||Date.parse(value.checkedAt)>=last)
    state.esg=value;
   state.sourceStatus.esg=Date.parse(value.checkedAt)<last?'retained':'ok';update();
  }).catch(error=>{
   state.sourceStatus.esg=state.esg?'retained':'error';
   console.warn('FinQuery company ESG source:',String(error?.message||error));update();
  })
 ];
 try{await Promise.allSettled(jobs)}
 finally{state.loading=false;updateSourceStatus()}
}
function renderExplore(){
 const details=$('macro-explore');if(!details?.open)return;
 renderTabs();metricOptions();renderKpis();renderAssessments();renderChart();renderTable();
}
$('macro-tabs')?.addEventListener('click',e=>{const b=e.target.closest('[data-macro-tab]');if(!b)return;state.active=b.dataset.macroTab;state.metric='';renderExplore();});
$('macro-metric')?.addEventListener('change',e=>{state.metric=e.target.value;renderKpis();renderAssessments();renderChart();renderTable();});
$('macro-company-ticker')?.addEventListener('change',e=>{
 const symbol=String(e.target.value||'').toUpperCase();
 if(!state.esg?.companies?.[symbol])return;
 manuallySelectedCompany=symbol;
 state.symbol=symbol;state.companyMetric='';
 state.data=normalizePayload(state.rawMacro||{datasets:{},sources:[],checkedAt:''},state.esg,symbol);
 // Follow the selected issuer without switching the actual stock chart.
 render();
 window.dispatchEvent(new CustomEvent('finquery:macro-company-change',{detail:{symbol}}));
});
$('macro-explore')?.addEventListener('toggle',renderExplore);
$('macro-refresh')?.addEventListener('click',load);
// Macro/Esg are publication-frequency datasets, not intraday prices: revalidate
// the two feed clocks when the page is visible, without refetching on each tab.
let lastSourceCheck=Date.now();
const refreshBounded=()=>{if(document.hidden||state.loading)return;
 if(Date.now()-lastSourceCheck<30*60000)return;
 lastSourceCheck=Date.now();void load();
};
window.setInterval(refreshBounded,15*60000);
document.addEventListener('visibilitychange',refreshBounded);
window.addEventListener('focus',refreshBounded);
$('macro-country-metric')?.addEventListener('change',e=>{state.countryMetric=e.target.value;renderEsgPanels();});
$('macro-company-metric')?.addEventListener('change',e=>{state.companyMetric=e.target.value;renderEsgPanels();});
window.addEventListener('finquery:symbol-change',e=>{
 const symbol=String(e.detail?.symbol||'').toUpperCase();
 if(!symbol||symbol===state.symbol)return;
 manuallySelectedCompany='';state.symbol=symbol;state.companyMetric='';
 if(state.rawMacro||state.esg){state.data=normalizePayload(state.rawMacro||{datasets:{},sources:[],checkedAt:''},state.esg,symbol);render();}
 else load();
});
load();

window.FinMacro={context(){if(!state.data)return null;const compact={};for(const [id,ds]of Object.entries(state.data.datasets||{}))compact[id]={title:ds.title,source:ds.source||null,companySymbol:ds.companySymbol||null,columns:ds.columns,numericColumns:ds.numericColumns,metricLabels:ds.metricLabels||null,metricUnits:ds.metricUnits||null,rows:(ds.rows||[]).slice(-12),status:ds.status};const company=state.esg?.companies?.[state.symbol];return{checkedAt:state.data.checkedAt,active:state.active,datasets:compact,corporateEsg:company?{symbol:state.symbol,externalAssessments:(company.externalAssessments||[]).slice(-12),coverage:company.coverage||null}:null};},refresh:load};
})();