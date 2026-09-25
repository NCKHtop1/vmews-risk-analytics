(function(){'use strict';
const $=id=>document.getElementById(id);
const DATA_BASE=new URL(document.currentScript.dataset.base||'../data/',document.currentScript.src||location.href).href;
const BOOT=JSON.parse(document.getElementById('financial-bootstrap')?.textContent||'{}');
const LIVE_BASE=document.documentElement.dataset.hosting==='pages'?DATA_BASE:'https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-report-data/data/';
const state={bundle:null,data:null,companies:[],years:[],reports:[],active:'balance_sheet',chartMetric:'profit',overviewPeriod:null,overviewCompare:null,loading:false,controller:null,mode:new URLSearchParams(location.search).get('mode')==='year'?'year':'quarter',fallback:false};
const names={balance_sheet:'Cân đối kế toán',income_statement:'Kết quả kinh doanh',cash_flow:'Lưu chuyển tiền tệ',ratios:'Chỉ số từ nguồn',derived_ratios:'Chỉ số tính từ BCTC',notes:'Thuyết minh',off_balance:'Ngoại bảng'};
const esc=s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const nf=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2});
const fmt=v=>v==null?'':v===0?'–':v<0?`(${nf.format(-v)})`:nf.format(v);
const label=p=>String(p).includes('-Q')?'Q'+String(p).at(-1)+'/'+String(p).slice(0,4):String(p);
const sorted=a=>[...new Set(a)].sort((a,b)=>String(a).localeCompare(String(b)));
const liveUrl=file=>LIVE_BASE+file+'?v='+Math.floor(Date.now()/300000);
async function json(url,signal,timeout=12000){const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),timeout);const abort=()=>ctl.abort();signal?.addEventListener('abort',abort,{once:true});try{const r=await fetch(url,{signal:ctl.signal,cache:'no-cache'});if(!r.ok)throw Error('Dữ liệu tạm thời chưa tải được. Vui lòng thử lại.');return await r.json();}finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}}
function error(message){$('error').hidden=!message;$('error').textContent=message||'';}
function reportPeriods(s,mode){return sorted(s.rows.flatMap(r=>Object.keys(r.values).filter(p=>Number.isFinite(r.values[p])).map(p=>mode==='quarter'?p:Number(p))));}
function eligible(){if(!state.data||!state.reports.length)return[];const ss=state.data.sections.filter(s=>state.reports.includes(s.id));return ss.length?ss.map(s=>s.periods).reduce((a,b)=>a.filter(p=>b.includes(p))):[];}
function checkData(d,symbol,mode='year'){
 if(d.symbol!==symbol||!Array.isArray(d.sections)||!d.sections.length)throw Error('Không tìm thấy báo cáo phù hợp.');
 const pattern=mode==='quarter'?/^\d{4}-Q[1-4]$/:/^\d{4}$/;const sectionIds=new Set();
 for(const s of d.sections){if(sectionIds.has(s.id)||!Array.isArray(s.rows)||!s.rows.length)throw Error('Báo cáo chưa có chỉ tiêu hợp lệ.');sectionIds.add(s.id);const rowIds=new Set();
  for(const r of s.rows){if(s.id!=='ratios'&&r.unit==='triệu đồng'&&['outstanding_shares_volume','treasury_stocks_volume','foreign_currencies'].includes(r.id)){r.unit=r.id==='foreign_currencies'?'nguyên tệ':'cổ phiếu';r.values=Object.fromEntries(Object.entries(r.values).map(([y,v])=>[y,v==null?null:Math.round(v*1000000)]));}
   if(!r.label||rowIds.has(r.id)||!r.values||Object.entries(r.values).some(([p,v])=>!pattern.test(p)||(v!==null&&!Number.isFinite(v))))throw Error('Dữ liệu chưa qua kiểm tra định dạng.');rowIds.add(r.id);
  }s.periods=reportPeriods(s,mode);s.years=s.periods;
 }d.periodType=mode;d.periods=d.sections.filter(s=>['balance_sheet','income_statement','cash_flow'].includes(s.id)).map(s=>s.periods).reduce((a,b)=>a.filter(p=>b.includes(p)),d.sections[0].periods);
 if(mode==='year'&&d.quarterly)checkData(d.quarterly,symbol,'quarter');return FinancialMetrics.decorate(d);
}
function setMode(mode,preserve=false){
 if(!['year','quarter'].includes(mode))throw Error('Kỳ báo cáo không hợp lệ.');state.mode=mode;state.overviewPeriod=null;state.overviewCompare=null;
 if(!state.bundle)return;
 state.data=mode==='quarter'?state.bundle.quarterly:state.bundle;
 document.querySelectorAll('input[name="period-type"]').forEach(b=>{b.checked=b.value===mode;});
 $('recent-years').textContent=mode==='quarter'?'4 quý gần nhất':'3 năm gần nhất';
 if(!state.data){state.years=[];state.reports=[];$('report-options').replaceChildren();$('availability').textContent=`${state.bundle.symbol}: chưa có dữ liệu ${mode==='quarter'?'quý':'năm'}.`;$('year-options').replaceChildren();renderPreview();return;}
 state.reports=preserve?state.reports.filter(id=>state.data.sections.some(s=>s.id===id)):state.data.sections.filter(s=>!['ratios','derived_ratios','notes'].includes(s.id)).map(s=>s.id);
 state.years=preserve?state.years.filter(p=>eligible().includes(p)):eligible().slice(mode==='quarter'?-4:-6);
 const updated=state.data.updatedAt;const date=updated?new Date(updated).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'short'}):'chưa xác định';
 $('updated-at').textContent='Dữ liệu cập nhật '+date;
 $('data-state').textContent=state.fallback?'Bản đã lưu':state.data.refreshStatus==='retained'?'Bản gần nhất':'Có dữ liệu';
 $('data-state').className='status-badge ready';
 const url=new URL(location.href);url.searchParams.set('symbol',state.bundle.symbol);url.searchParams.set('mode',mode);history.replaceState(null,'',url);
 renderReports();update();
}
function renderYears(){
 const available=eligible(),all=sorted(state.data?.sections.flatMap(s=>s.periods)||[]);state.years=state.years.filter(p=>available.includes(p));
 const checkbox=p=>`<label class="year-option"><input type="checkbox" value="${p}" ${state.years.includes(p)?'checked':''} ${!available.includes(p)?'disabled':''} aria-label="${state.mode==='quarter'?'Quý '+String(p).at(-1)+' năm '+String(p).slice(0,4):'Năm '+p}"><span>${state.mode==='quarter'?'Q'+String(p).at(-1):p}</span></label>`;
 $('year-options').classList.toggle('quarter-grid',state.mode==='quarter');
 $('year-options').innerHTML=state.mode==='quarter'?[...new Set(all.map(p=>p.slice(0,4)))].reverse().map(y=>`<div class="period-year">${y}</div><div class="quarter-row">${[1,2,3,4].map(q=>y+'-Q'+q).map(checkbox).join('')}</div>`).join(''):all.map(checkbox).join('');
 $('availability').textContent=available.length?`${state.data.symbol}: ${available.length} ${state.mode==='quarter'?'quý':'năm'} có dữ liệu, từ ${label(available[0])} đến ${label(available.at(-1))}.`:'Chưa có kỳ phù hợp với nội dung đã chọn.';
}
function renderReports(){if(!state.data)return;$('report-options').innerHTML=state.data.sections.map(s=>`<div class="report-option"><input type="checkbox" id="report-${esc(s.id)}" value="${esc(s.id)}" ${!s.periods.length?'disabled':''} ${state.reports.includes(s.id)?'checked':''}><label for="report-${esc(s.id)}">${esc(names[s.id]||s.name)}${s.qualityStatus==='periods_unverified'?' · Chưa khớp kỳ':''}</label><small>${s.rows.filter(r=>Object.values(r.values).some(v=>v!==null)).length}</small></div>`).join('');}
function renderPreview(){
 const overview=FinancialDashboard.render(state.data,state.years,state.chartMetric,state.overviewPeriod,state.overviewCompare);state.chartMetric=overview.metric;state.overviewPeriod=overview.focus;state.overviewCompare=overview.compare;
 const reports=state.data?.sections.filter(s=>state.reports.includes(s.id))||[];if(!reports.some(s=>s.id===state.active))state.active=reports[0]?.id||'';
 $('report-tabs').innerHTML=reports.map(s=>`<button type="button" role="tab" id="tab-${esc(s.id)}" aria-selected="${state.active===s.id}" data-report="${esc(s.id)}">${esc(names[s.id]||s.name)}</button>`).join('');const section=reports.find(s=>s.id===state.active);
 $('unit-caption').textContent=['ratios','derived_ratios'].includes(section?.id)?'Đơn vị theo chỉ tiêu':section?.basis==='year_to_date'?'Triệu đồng · Lũy kế':'Triệu đồng';
 if(!section||!state.years.length){$('table-container').innerHTML='<div class="empty-state"><h3>Chọn kỳ và nội dung báo cáo</h3><p></p></div>';}
 else{$('table-container').innerHTML=`<table aria-label="${esc(section.name)}"><thead><tr><th scope="col">CHỈ TIÊU</th>${state.years.map(p=>`<th scope="col">${label(p)}</th>`).join('')}</tr></thead><tbody>${section.rows.map(r=>`<tr class="${r.bold?'bold':''}"><td>${esc(r.label)}${r.unit&&(r.unit!=='triệu đồng'||['ratios','derived_ratios'].includes(section.id))&&!r.label.toLowerCase().includes(r.unit.toLowerCase())?` <span class="muted">(${esc(r.unit)})</span>`:''}</td>${state.years.map(p=>`<td>${fmt(r.values[String(p)])}</td>`).join('')}</tr>`).join('')}</tbody></table>`;}
 const count=section?.rows.filter(r=>state.years.some(p=>r.values[String(p)]!==null&&r.values[String(p)]!==undefined)).length||0;const unit=state.mode==='quarter'?'quý':'năm';
 $('row-count').textContent=`${count} chỉ tiêu · ${state.years.length} ${unit}`;$('summary').textContent=`${reports.length} báo cáo · ${state.years.length} ${unit}`;$('download').disabled=state.loading||!reports.length||!state.years.length;
}
function update(){renderYears();renderPreview();$('download-status').textContent='';}
async function loadCompany(raw){
 const match=state.companies.find(c=>c.symbol===raw.trim().toUpperCase()||c.name.toLowerCase()===raw.trim().toLowerCase());const symbol=match?.symbol||raw.trim().split(/[\s—–]/)[0].toUpperCase();
 if(!state.companies.some(c=>c.symbol===symbol)){state.controller?.abort();state.bundle=null;state.data=null;state.years=[];state.reports=[];state.loading=false;$('report-options').replaceChildren();$('year-options').replaceChildren();$('availability').textContent='Hãy chọn một doanh nghiệp VN100.';$('data-state').textContent='Mã ngoài VN100';$('preview-title').textContent=symbol;$('company-name').textContent='';$('updated-at').textContent='—';$('refresh-data').disabled=false;renderPreview();error('Trang này hỗ trợ các doanh nghiệp thuộc VN100. Hãy chọn một mã trong danh sách.');return;}
 window.FinancialMarket?.select(symbol,state.companies);
 state.controller?.abort();const ctl=new AbortController();state.controller=ctl;state.loading=true;state.bundle=null;state.data=null;state.years=[];state.reports=[];state.overviewPeriod=null;state.overviewCompare=null;$('ticker').value=symbol;error('');$('download').disabled=true;$('refresh-data').disabled=true;$('data-state').className='status-badge';$('data-state').textContent='Đang tải';$('availability').textContent='Đang kiểm tra kỳ có dữ liệu…';$('report-options').replaceChildren();$('year-options').replaceChildren();$('report-tabs').replaceChildren();$('preview-title').innerHTML=`${esc(symbol)} <span>/ Báo cáo tài chính</span>`;$('company-name').textContent=match?.name||symbol;$('table-container').innerHTML='<div class="empty-state"><span class="loading-ring"></span><h3>Đang tải báo cáo</h3><p></p></div>';
 FinancialDashboard.render(null,[]);
 try{
  let d;state.fallback=false;
  try{d=checkData(await json(liveUrl(symbol+'.json'),ctl.signal),symbol);}
  catch(e){if(ctl.signal.aborted)throw e;state.fallback=true;d=BOOT.datasets?.[symbol]?structuredClone(BOOT.datasets[symbol]):await json(DATA_BASE+symbol+'.json',ctl.signal);d=checkData(d,symbol);}
  if(ctl.signal.aborted)return;state.bundle=d;state.active='balance_sheet';$('company-name').textContent=d.name||match?.name||symbol;$('company-description').textContent='VN100 · '+(d.exchange||match?.exchange||'HOSE');document.querySelectorAll('[data-symbol]').forEach(b=>b.classList.toggle('active',b.dataset.symbol===symbol));
  setMode(state.mode);
 }catch(e){if(ctl.signal.aborted)return;error(`${symbol} chưa tải được báo cáo trong lần này. Hãy bấm Làm mới để thử lại.`);$('data-state').textContent='Chưa tải được';$('availability').textContent='Chưa mở lựa chọn kỳ cho mã này.';$('table-container').innerHTML='<div class="empty-state"><h3>Chưa có báo cáo để tải</h3><p>Thử tải lại hoặc chọn doanh nghiệp khác.</p></div>';$('row-count').textContent='0 chỉ tiêu';$('updated-at').textContent='—';$('summary').textContent='Chưa có báo cáo';}
 finally{if(!ctl.signal.aborted){state.loading=false;$('refresh-data').disabled=false;if(state.data)update();}}
}
function download(){if(!state.data||!state.years.length||!state.reports.length)return;try{const bytes=FinancialXlsx.workbook(state.data,state.years,state.reports);const blob=new Blob([bytes],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});const link=document.createElement('a'),url=URL.createObjectURL(blob);link.href=url;link.download=`${state.data.symbol}_BCTC_${state.years.join('_')}.xlsx`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);$('download-status').textContent='Đã tạo file Excel.';}catch(e){error(e.message);}}
$('company-form').addEventListener('submit',e=>{e.preventDefault();loadCompany($('ticker').value);});$('ticker').addEventListener('change',()=>loadCompany($('ticker').value));document.querySelectorAll('[data-symbol]').forEach(b=>b.addEventListener('click',()=>loadCompany(b.dataset.symbol)));
$('year-options').addEventListener('change',e=>{const p=state.mode==='quarter'?e.target.value:Number(e.target.value);state.years=e.target.checked?sorted([...state.years,p]):state.years.filter(v=>v!==p);renderPreview();});
$('report-options').addEventListener('change',e=>{const r=e.target.value;state.reports=e.target.checked?[...state.reports,r]:state.reports.filter(v=>v!==r);update();});
$('all-years').addEventListener('click',()=>{state.years=eligible();update();});$('recent-years').addEventListener('click',()=>{state.years=eligible().slice(state.mode==='quarter'?-4:-3);update();});$('latest-period').addEventListener('click',()=>{state.years=eligible().slice(-1);update();});$('clear-years').addEventListener('click',()=>{state.years=[];update();});
$('refresh-data').addEventListener('click',()=>loadCompany($('ticker').value));document.querySelectorAll('input[name="period-type"]').forEach(r=>r.addEventListener('change',()=>setMode(r.value)));
$('report-tabs').addEventListener('click',e=>{const b=e.target.closest('button[data-report]');if(b){state.active=b.dataset.report;renderPreview();}});
$('chart-metric').addEventListener('change',e=>{state.chartMetric=e.target.value;const overview=FinancialDashboard.render(state.data,state.years,state.chartMetric,state.overviewPeriod,state.overviewCompare);state.chartMetric=overview.metric;state.overviewPeriod=overview.focus;state.overviewCompare=overview.compare;});
$('overview-focus-period').addEventListener('change',e=>{state.overviewPeriod=e.target.value;const overview=FinancialDashboard.render(state.data,state.years,state.chartMetric,state.overviewPeriod,state.overviewCompare);state.chartMetric=overview.metric;state.overviewPeriod=overview.focus;state.overviewCompare=overview.compare;});
$('overview-compare-period').addEventListener('change',e=>{state.overviewCompare=e.target.value;const overview=FinancialDashboard.render(state.data,state.years,state.chartMetric,state.overviewPeriod,state.overviewCompare);state.chartMetric=overview.metric;state.overviewPeriod=overview.focus;state.overviewCompare=overview.compare;});
for(const event of ['pointerover','focusin'])$('trend-chart').addEventListener(event,e=>{const point=e.target.closest('[data-tooltip]');if(point)$('trend-chart').querySelector('.chart-readout').textContent=point.dataset.tooltip;});
$('copyright-year').textContent=new Date().getFullYear();
$('report-tabs').addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key))return;const ids=state.data?.sections.filter(s=>state.reports.includes(s.id)).map(s=>s.id)||[];if(!ids.length)return;e.preventDefault();state.active=ids[(ids.indexOf(state.active)+(e.key==='ArrowRight'?1:ids.length-1))%ids.length];renderPreview();$('tab-'+state.active)?.focus();});$('download').addEventListener('click',download);
function companyOptions(){ $('company-options').innerHTML=state.companies.map(c=>`<option value="${esc(c.symbol)}">${esc(c.name)}</option>`).join(''); }
async function init(){
 try{state.companies=BOOT.companies||await json(DATA_BASE+'companies.json',null);companyOptions();$('company-description').textContent='100 doanh nghiệp thuộc VN100.';}catch{error('Chưa tải được danh sách VN100. Vui lòng tải lại trang.');return;}
 // Membership updates do not block a company request, and a failed manifest
 // never disables live financial data fetching.
 json(liveUrl('companies.json'),null,6000).then(list=>{if(Array.isArray(list)&&new Set(list.map(c=>c.symbol)).size===100){state.companies=list;companyOptions();}}).catch(()=>{});
 await loadCompany(new URLSearchParams(location.search).get('symbol')||'MBB');registerTools();
}
function registerTools(){const context=document.modelContext;if(!context?.registerTool)return;const life=new AbortController();context.registerTool({name:'select_financial_report',title:'Chọn báo cáo tài chính',description:'Chọn doanh nghiệp VN100, năm hoặc quý có dữ liệu và cập nhật bảng xem trước.',inputSchema:{type:'object',properties:{symbol:{type:'string'},mode:{type:'string',enum:['year','quarter']},periods:{type:'array',items:{type:['string','integer']},minItems:1}},required:['symbol'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:true},async execute(input){if(!input||typeof input.symbol!=='string')throw Error('Mã không hợp lệ');await loadCompany(input.symbol);if(!state.bundle)throw Error('Chưa có báo cáo');if(input.mode)setMode(input.mode);if(input.periods){if(!Array.isArray(input.periods)||!input.periods.length||input.periods.some(p=>!eligible().includes(p)))throw Error('Kỳ không có dữ liệu');state.years=sorted(input.periods);update();}return{symbol:state.bundle.symbol,mode:state.mode,periods:state.years,reports:state.reports};}},{signal:life.signal});window.addEventListener('pagehide',()=>life.abort(),{once:true});}
init();
})();


