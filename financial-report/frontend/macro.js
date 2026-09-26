(function(){'use strict';
const $=id=>document.getElementById(id);
const BASE=document.documentElement.dataset.hosting==='pages'?new URL('market/',location.href).href:'https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/';
const ACCESS_HASH='0a0667865bc17f9d624bcf11088057bbab46336e7dae65f3d5366f4f7a18333e';
const state={data:null,active:'',metric:'',unlocked:false};
const fmt=v=>typeof v==='number'&&Number.isFinite(v)?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2}).format(v):String(v??'—');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function digest(text){const buf=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));return[...new Uint8Array(buf)].map(b=>b.toString(16).padStart(2,'0')).join('');}
async function fetchMacro(){const r=await fetch(BASE+'macro.json?v='+Math.floor(Date.now()/60000),{cache:'no-cache',signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('HTTP '+r.status);const data=await r.json();if(!data?.datasets||typeof data.datasets!=='object')throw Error('Dữ liệu VBMA không hợp lệ');return data;}
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
function normalizePayload(data){const datasets={};for(const[id,ds]of Object.entries(data.datasets||{}))datasets[id]=normalizeDataset(ds);return{...data,datasets};}
function firstColumn(ds){return(ds.columns||[])[0]||'Date';}
function latestRow(ds){const rows=ds.rows||[];for(let i=rows.length-1;i>=0;i--){if(Object.values(rows[i]||{}).some(v=>v!==null&&v!==''))return rows[i];}return null;}
function renderTabs(){const box=$('macro-tabs'),sets=state.data?.datasets||{};box.innerHTML=Object.entries(sets).map(([id,ds])=>'<button type="button" data-macro-tab="'+esc(id)+'" class="'+(id===state.active?'active':'')+'">'+esc(ds.title||id)+'</button>').join('');}
function metricOptions(){const ds=state.data?.datasets?.[state.active];if(!ds)return;$('macro-metric').innerHTML=(ds.numericColumns||[]).map(x=>'<option value="'+esc(x)+'">'+esc(x)+'</option>').join('');if(!(ds.numericColumns||[]).includes(state.metric))state.metric=(ds.numericColumns||[])[0]||'';$('macro-metric').value=state.metric;}
function renderKpis(){const ds=state.data?.datasets?.[state.active],row=ds&&latestRow(ds),box=$('macro-kpis');if(!ds||!row){box.innerHTML='';return;}const cols=(ds.numericColumns||[]).slice(0,4);box.innerHTML=cols.map(k=>'<div class="macro-kpi"><span>'+esc(k)+'</span><strong>'+esc(fmt(row[k]))+'</strong></div>').join('');}
function chartPoints(ds,metric){const label=firstColumn(ds);return(ds.rows||[]).map((r,i)=>({x:i,label:r[label]??String(i+1),y:typeof r[metric]==='number'?r[metric]:Number(r[metric])})).filter(x=>Number.isFinite(x.y)).slice(-48);}
function renderChart(){const ds=state.data?.datasets?.[state.active],box=$('macro-chart');if(!ds||!state.metric){box.innerHTML='<div class="analysis-empty">Chưa có chuỗi số phù hợp để vẽ.</div>';return;}const pts=chartPoints(ds,state.metric);$('macro-chart-title').textContent=ds.title||'Dữ liệu vĩ mô';$('macro-chart-subtitle').textContent=state.metric+(ds.status==='retained'?' · bản dữ liệu đã lưu':'');if(pts.length<2){box.innerHTML='<div class="analysis-empty">Chưa đủ điểm dữ liệu để vẽ chuỗi.</div>';return;}const w=900,h=320,pad=42,min=Math.min(...pts.map(x=>x.y)),max=Math.max(...pts.map(x=>x.y)),span=max-min||1,xx=i=>pad+(w-2*pad)*(i/Math.max(1,pts.length-1)),yy=v=>h-pad-(h-2*pad)*((v-min)/span),path=pts.map((p,i)=>(i?'L':'M')+xx(i).toFixed(1)+' '+yy(p.y).toFixed(1)).join(' '),last=pts.at(-1);const ticks=[0,.25,.5,.75,1].map(t=>{const val=min+span*t,y=yy(val);return'<line x1="'+pad+'" y1="'+y+'" x2="'+(w-pad)+'" y2="'+y+'" stroke="#edf1f6"/><text x="4" y="'+(y+4)+'" font-size="10" fill="#7c889a">'+esc(fmt(val))+'</text>';}).join('');const labels=[0,Math.floor((pts.length-1)/2),pts.length-1].map(i=>'<text x="'+xx(i)+'" y="'+(h-10)+'" text-anchor="'+(i===0?'start':i===pts.length-1?'end':'middle')+'" font-size="10" fill="#7c889a">'+esc(String(pts[i].label).slice(0,18))+'</text>').join('');box.innerHTML='<svg viewBox="0 0 '+w+' '+h+'" role="img" aria-label="'+esc(ds.title+' '+state.metric)+'">'+ticks+'<path d="'+path+'" fill="none" stroke="#4d67c8" stroke-width="2"/><circle cx="'+xx(pts.length-1)+'" cy="'+yy(last.y)+'" r="4" fill="#4d67c8"/>'+labels+'</svg>';}
function renderTable(){const ds=state.data?.datasets?.[state.active];if(!ds)return;const cols=ds.columns||[],rows=(ds.rows||[]).slice(-20).reverse();$('macro-table-head').innerHTML='<tr>'+cols.map(x=>'<th>'+esc(x)+'</th>').join('')+'</tr>';$('macro-table-body').innerHTML=rows.map(r=>'<tr>'+cols.map(x=>'<td>'+esc(fmt(r[x]))+'</td>').join('')+'</tr>').join('');}
function render(){if(!state.data)return;const sets=state.data.datasets||{};if(!sets[state.active])state.active=Object.keys(sets)[0]||'';renderTabs();metricOptions();renderKpis();renderChart();renderTable();$('macro-source-status').textContent='VBMA · cập nhật '+new Date(state.data.checkedAt).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'});}
async function load(){try{$('macro-source-status').textContent='Đang tải VBMA…';state.data=normalizePayload(await fetchMacro());render();}catch(e){$('macro-source-status').textContent='Chưa tải được dữ liệu VBMA';$('macro-chart').innerHTML='<div class="analysis-empty">Nguồn vĩ mô tạm thời chưa phản hồi.</div>';}}
async function unlock(code){if(await digest(String(code||''))!==ACCESS_HASH){$('macro-gate-error').textContent='Mã truy cập không đúng.';return false;}state.unlocked=true;sessionStorage.setItem('finquery-macro-access','1');$('macro-gate').hidden=true;$('macro-workspace').hidden=false;$('macro-gate-error').textContent='';await load();return true;}
$('macro-unlock-form')?.addEventListener('submit',e=>{e.preventDefault();unlock($('macro-access-code').value);});
$('macro-tabs')?.addEventListener('click',e=>{const b=e.target.closest('[data-macro-tab]');if(!b)return;state.active=b.dataset.macroTab;state.metric='';render();});
$('macro-metric')?.addEventListener('change',e=>{state.metric=e.target.value;renderKpis();renderChart();});
$('macro-refresh')?.addEventListener('click',load);
if(sessionStorage.getItem('finquery-macro-access')==='1'){state.unlocked=true;$('macro-gate').hidden=true;$('macro-workspace').hidden=false;load();}
window.FinMacro={context(){if(!state.unlocked||!state.data)return null;const compact={};for(const [id,ds]of Object.entries(state.data.datasets||{}))compact[id]={title:ds.title,columns:ds.columns,numericColumns:ds.numericColumns,rows:(ds.rows||[]).slice(-12),status:ds.status};return{checkedAt:state.data.checkedAt,active:state.active,datasets:compact};},refresh:load};
})();