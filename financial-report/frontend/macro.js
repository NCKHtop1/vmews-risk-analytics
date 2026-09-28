(function(){'use strict';
const $=id=>document.getElementById(id);
const BASE=document.documentElement.dataset.hosting==='pages'?new URL('market/',location.href).href:'https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/';
const ACCESS_HASH='0a0667865bc17f9d624bcf11088057bbab46336e7dae65f3d5366f4f7a18333e';
const state={data:null,esg:null,symbol:'',active:'',metric:'',unlocked:false};
const fmt=v=>typeof v==='number'&&Number.isFinite(v)?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2}).format(v):String(v??'—');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function digest(text){const buf=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));return[...new Uint8Array(buf)].map(b=>b.toString(16).padStart(2,'0')).join('');}
async function fetchMacro(){const r=await fetch(BASE+'macro.json?v='+Math.floor(Date.now()/60000),{cache:'no-cache',signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('HTTP '+r.status);const data=await r.json();if(!data?.datasets||typeof data.datasets!=='object')throw Error('Dữ liệu Macro & ESG không hợp lệ');return data;}
async function fetchCompanyEsg(){const r=await fetch(BASE+'company-esg.json?v='+Math.floor(Date.now()/60000),{cache:'no-cache',signal:AbortSignal.timeout(20000)});if(!r.ok)return null;const data=await r.json();return data?.companies?data:null;}
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
function currentSymbol(){return String(new URL(location.href).searchParams.get('symbol')||$('ticker')?.value||'').trim().toUpperCase();}
function corporateDataset(esg,symbol){
 const company=esg?.companies?.[symbol];if(!company)return null;
 const years={},labels={},units={};for(const row of company.metrics||[]){const year=Number(row.year);if(!Number.isFinite(year)||!Number.isFinite(Number(row.value)))continue;years[year]??={Year:year};years[year][row.metricId]=Number(row.value);labels[row.metricId]=row.label||row.metricId;if(row.unit)units[row.metricId]=row.unit;}
 for(const row of company.externalAssessments||[]){const year=Number(row.year);if(Number.isFinite(year))years[year]??={Year:year};}
 const rows=Object.values(years).sort((a,b)=>a.Year-b.Year),metrics=[...new Set(rows.flatMap(r=>Object.keys(r).filter(k=>k!=='Year'&&Number.isFinite(r[k]))))];
 return{id:'company_esg_'+symbol,title:'ESG doanh nghiệp · '+symbol,source:'Bank disclosures + external assessments',status:'ok',companySymbol:symbol,columns:['Year',...metrics],numericColumns:metrics,metricLabels:labels,metricUnits:units,rows,allYears:true,metricTable:true};
}
function normalizePayload(data,esg,symbol){const datasets={};for(const[id,ds]of Object.entries(data.datasets||{}))datasets[id]=normalizeDataset(ds);const corporate=corporateDataset(esg,symbol);if(corporate)datasets[corporate.id]=normalizeDataset(corporate);return{...data,datasets};}
function firstColumn(ds){return(ds.columns||[])[0]||'Date';}
function latestRow(ds){const rows=ds.rows||[];for(let i=rows.length-1;i>=0;i--){if(Object.values(rows[i]||{}).some(v=>v!==null&&v!==''))return rows[i];}return null;}
function renderTabs(){const box=$('macro-tabs'),sets=state.data?.datasets||{};box.innerHTML=Object.entries(sets).map(([id,ds])=>'<button type="button" data-macro-tab="'+esc(id)+'" class="'+(id===state.active?'active':'')+'">'+esc(ds.title||id)+'</button>').join('');}
function metricLabel(ds,key){return ds?.metricLabels?.[key]||key;}
function metricUnit(ds,key){return ds?.metricUnits?.[key]||ds?.units?.[key]||'';}
function metricOptions(){const ds=state.data?.datasets?.[state.active];if(!ds)return;$('macro-metric').innerHTML=(ds.numericColumns||[]).map(x=>'<option value="'+esc(x)+'">'+esc(metricLabel(ds,x))+(x!==metricLabel(ds,x)?' · '+esc(x):'')+'</option>').join('');if(!(ds.numericColumns||[]).includes(state.metric))state.metric=(ds.numericColumns||[])[0]||'';$('macro-metric').value=state.metric;}
function renderKpis(){const ds=state.data?.datasets?.[state.active],row=ds&&latestRow(ds),box=$('macro-kpis');if(!ds||!row){box.innerHTML='';return;}const cols=(ds.numericColumns||[]).slice(0,4);box.innerHTML=cols.map(k=>'<div class="macro-kpi"><span>'+esc(metricLabel(ds,k))+'</span><strong>'+esc(fmt(row[k]))+'</strong>'+(metricUnit(ds,k)?'<small>'+esc(metricUnit(ds,k))+'</small>':'')+'</div>').join('');}
function chartPoints(ds,metric){const label=firstColumn(ds),points=(ds.rows||[]).map((r,i)=>({x:i,label:r[label]??String(i+1),y:typeof r[metric]==='number'?r[metric]:Number(r[metric])})).filter(x=>Number.isFinite(x.y));return ds.allYears?points:points.slice(-48);}
function renderChart(){const ds=state.data?.datasets?.[state.active],box=$('macro-chart');if(!ds||!state.metric){box.innerHTML='<div class="analysis-empty">Chưa có chuỗi số phù hợp để vẽ.</div>';return;}const pts=chartPoints(ds,state.metric),unit=metricUnit(ds,state.metric),label=metricLabel(ds,state.metric);$('macro-chart-title').textContent=ds.title||'Dữ liệu vĩ mô & ESG';$('macro-chart-subtitle').textContent=label+(unit?' · '+unit:'')+(ds.allYears?' · toàn bộ năm có dữ liệu':'')+(ds.status==='retained'?' · bản dữ liệu đã lưu':'');if(pts.length<2){box.innerHTML='<div class="analysis-empty">Chưa đủ điểm dữ liệu để vẽ chuỗi.</div>';return;}const w=900,h=320,pad=42,min=Math.min(...pts.map(x=>x.y)),max=Math.max(...pts.map(x=>x.y)),span=max-min||1,xx=i=>pad+(w-2*pad)*(i/Math.max(1,pts.length-1)),yy=v=>h-pad-(h-2*pad)*((v-min)/span),path=pts.map((p,i)=>(i?'L':'M')+xx(i).toFixed(1)+' '+yy(p.y).toFixed(1)).join(' '),last=pts.at(-1);const ticks=[0,.25,.5,.75,1].map(t=>{const val=min+span*t,y=yy(val);return'<line x1="'+pad+'" y1="'+y+'" x2="'+(w-pad)+'" y2="'+y+'" stroke="#edf1f6"/><text x="4" y="'+(y+4)+'" font-size="10" fill="#7c889a">'+esc(fmt(val))+'</text>';}).join('');const labels=[0,Math.floor((pts.length-1)/2),pts.length-1].map(i=>'<text x="'+xx(i)+'" y="'+(h-10)+'" text-anchor="'+(i===0?'start':i===pts.length-1?'end':'middle')+'" font-size="10" fill="#7c889a">'+esc(String(pts[i].label).slice(0,18))+'</text>').join('');box.innerHTML='<svg viewBox="0 0 '+w+' '+h+'" role="img" aria-label="'+esc(ds.title+' '+state.metric)+'">'+ticks+'<path d="'+path+'" fill="none" stroke="#4d67c8" stroke-width="2"/><circle cx="'+xx(pts.length-1)+'" cy="'+yy(last.y)+'" r="4" fill="#4d67c8"/>'+labels+'</svg>';}
function renderTable(){const ds=state.data?.datasets?.[state.active];if(!ds)return;const first=firstColumn(ds),cols=ds.metricTable?[first,state.metric].filter(Boolean):(ds.columns||[]),base=ds.rows||[],rows=(ds.allYears?base:base.slice(-20)).slice().reverse();$('macro-table-head').innerHTML='<tr>'+cols.map(x=>'<th>'+esc(x===first?x:metricLabel(ds,x))+'</th>').join('')+'</tr>';$('macro-table-body').innerHTML=rows.map(r=>'<tr>'+cols.map(x=>'<td>'+esc(fmt(r[x]))+'</td>').join('')+'</tr>').join('');}
function renderAssessments(){const box=$('macro-esg-assessments'),ds=state.data?.datasets?.[state.active],company=ds?.companySymbol&&state.esg?.companies?.[ds.companySymbol];if(!box)return;if(!company){box.hidden=true;box.innerHTML='';return;}const ratings=(company.externalAssessments||[]).slice().sort((a,b)=>(b.year||0)-(a.year||0)).slice(0,12),docs=(company.documents||[]).filter(d=>d.processedAt).slice(0,8),metricSources=(company.metrics||[]).filter(x=>x.metricId===state.metric).sort((a,b)=>(b.year||0)-(a.year||0)).slice(0,8);box.hidden=false;box.innerHTML='<div class="macro-esg-head"><div><strong>ESG doanh nghiệp · '+esc(ds.companySymbol)+'</strong><span>KPI ngân hàng tự công bố và đánh giá bên ngoài được giữ nguyên nguồn, năm và thang đo.</span></div></div>'+(metricSources.length?'<div class="macro-esg-metric-sources"><strong>Nguồn KPI đang chọn</strong>'+metricSources.map(x=>'<a href="'+esc(x.sourceUrl||'#')+'" target="_blank" rel="noopener"><span>'+esc(x.year||'—')+' · '+esc(x.label||x.metricId)+'</span><b>'+esc(fmt(x.value))+(x.unit?' '+esc(x.unit):'')+'</b><small>'+esc(x.sourceTitle||'Báo cáo ngân hàng')+'</small></a>').join('')+'</div>':'')+(ratings.length?'<div class="macro-esg-rating-grid">'+ratings.map(x=>'<article><span>'+esc(x.provider||'Nguồn ngoài')+' · '+esc(x.year||'—')+'</span><strong>'+esc(x.value||x.assessmentType||'Đã công bố')+'</strong><small>'+esc(x.assessmentType||'')+'</small>'+(x.sourceUrl?'<a href="'+esc(x.sourceUrl)+'" target="_blank" rel="noopener">Nguồn</a>':'')+'</article>').join('')+'</div>':'<p class="analysis-empty">Chưa trích được external rating công khai cho mã này.</p>')+(docs.length?'<div class="macro-esg-docs"><strong>Tài liệu nguồn gần nhất</strong>'+docs.map(d=>'<a href="'+esc(d.url)+'" target="_blank" rel="noopener">'+esc((d.year||'')+' · '+(d.title||d.type||'Tài liệu ESG'))+'</a>').join('')+'</div>':'');}
function render(){if(!state.data)return;const sets=state.data.datasets||{};if(!sets[state.active])state.active=Object.keys(sets)[0]||'';renderTabs();metricOptions();renderKpis();renderAssessments();renderChart();renderTable();$('macro-source-status').textContent=(state.data.source||'Macro & ESG')+(state.esg?' + Corporate ESG':'')+' · cập nhật '+new Date(state.data.checkedAt).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'});}
async function load(){try{$('macro-source-status').textContent='Đang tải vĩ mô + ESG doanh nghiệp…';state.symbol=currentSymbol();const[macro,esg]=await Promise.all([fetchMacro(),fetchCompanyEsg().catch(()=>null)]);state.esg=esg;state.data=normalizePayload(macro,esg,state.symbol);render();}catch(e){$('macro-source-status').textContent='Chưa tải được dữ liệu Macro & ESG';$('macro-chart').innerHTML='<div class="analysis-empty">Nguồn vĩ mô/ESG tạm thời chưa phản hồi.</div>';}}
function showWorkspace(){
 const gate=$('macro-gate'),workspace=$('macro-workspace'),input=$('macro-access-code');
 if(gate){gate.hidden=true;gate.style.display='none';}
 if(workspace){workspace.hidden=false;workspace.style.display='block';}
 if(input)input.value='';
 requestAnimationFrame(()=>workspace?.scrollIntoView({behavior:'smooth',block:'start'}));
}
async function unlock(code){
 const button=$('macro-unlock-form')?.querySelector('button[type=submit]');
 if(await digest(String(code||'').trim())!==ACCESS_HASH){$('macro-gate-error').textContent='Mã truy cập không đúng.';return false;}
 state.unlocked=true;sessionStorage.setItem('finquery-macro-access','1');$('macro-gate-error').textContent='';if(button){button.disabled=true;button.textContent='Đang mở…';}
 showWorkspace();
 await load();
 if(button){button.disabled=false;button.textContent='Mở dữ liệu';}
 return true;
}
$('macro-unlock-form')?.addEventListener('submit',e=>{e.preventDefault();unlock($('macro-access-code').value);});
$('macro-tabs')?.addEventListener('click',e=>{const b=e.target.closest('[data-macro-tab]');if(!b)return;state.active=b.dataset.macroTab;state.metric='';render();});
$('macro-metric')?.addEventListener('change',e=>{state.metric=e.target.value;renderKpis();renderAssessments();renderChart();renderTable();});
$('macro-refresh')?.addEventListener('click',load);window.addEventListener('finquery:symbol-change',e=>{state.symbol=String(e.detail?.symbol||'').toUpperCase();if(state.unlocked)load();});
if(sessionStorage.getItem('finquery-macro-access')==='1'){state.unlocked=true;showWorkspace();load();}
window.FinMacro={context(){if(!state.unlocked||!state.data)return null;const compact={};for(const [id,ds]of Object.entries(state.data.datasets||{}))compact[id]={title:ds.title,source:ds.source||null,companySymbol:ds.companySymbol||null,columns:ds.columns,numericColumns:ds.numericColumns,metricLabels:ds.metricLabels||null,metricUnits:ds.metricUnits||null,rows:(ds.rows||[]).slice(-12),status:ds.status};const company=state.esg?.companies?.[state.symbol];return{checkedAt:state.data.checkedAt,active:state.active,datasets:compact,corporateEsg:company?{symbol:state.symbol,externalAssessments:(company.externalAssessments||[]).slice(-12),coverage:company.coverage||null}:null};},refresh:load};
})();