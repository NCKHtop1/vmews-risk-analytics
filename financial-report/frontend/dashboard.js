/* Read-only visual summaries of the same normalized statement rows used by Excel. */
(function(root){'use strict';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const nf=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1});
const precise=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2});
const label=p=>String(p).includes('-Q')?'Q'+String(p).at(-1)+'/'+String(p).slice(0,4):String(p);
const previous=p=>String(p).includes('-Q')?(Number(String(p).at(-1))===1?`${Number(String(p).slice(0,4))-1}-Q4`:`${String(p).slice(0,4)}-Q${Number(String(p).at(-1))-1}`):String(Number(p)-1);
const definitions=[
 {key:'assets',label:'Tổng tài sản',section:'balance_sheet',ids:['total_assets'],icon:'M3 21h18M5 21V7l7-4 7 4v14M9 10h1m4 0h1m-6 4h1m4 0h1m-6 4h6'},
 {key:'revenue',label:'Doanh thu thuần',section:'income_statement',ids:['net_sales','net_interest_income','net_sales_from_insurance_business','net_insurance_operating_revenue','net_revenue_of_insurance_premium','total_operating_income'],icon:'M4 18V6m0 12h16M7 14l4-4 4 2 5-7m-5 0h5v5'},
 {key:'profit',label:'Lợi nhuận sau thuế',section:'income_statement',ids:['net_profit_loss_after_tax','profit_after_tax'],icon:'M5 20V10h4v10m2 0V4h4v16m2 0v-7h4v7'},
 {key:'cash',label:'Dòng tiền HĐKD',section:'cash_flow',ids:['net_cash_inflows_outflows_from_operating_activities','net_cash_from_operating_activities'],icon:'M4 7h15l-3-3M20 17H5l3 3M4 7v6m16 4v-6'}
];
function selectRow(data,section,ids){const rows=data?.sections.find(s=>s.id===section)?.rows||[];const standard=ids.map(id=>rows.find(r=>r.id===id)).find(Boolean);if(standard)return standard;
 // The independently reviewed MBB annual workbook retains its original row IDs.
 if(data?.symbol==='MBB'&&data.periodType!=='quarter'){
  const aliases={total_assets:'mbb_47',total_liabilities:'mbb_62',owners_equity:'mbb_73',net_interest_income:'mbb_79',net_profit_loss_after_tax:'mbb_98',net_cash_from_operating_activities:'mbb_130'};
  for(const id of ids){const row=rows.find(r=>r.id===aliases[id]);if(row)return{...row,id};}
 }return undefined;
}
function amount(row,p){const v=row?.values[String(p)];if(!Number.isFinite(v))return null;return row.unit==='triệu đồng'?v/1000:row.unit==='tỷ đồng'?v:row.unit==='đồng'?v/1e9:null;}
function model(data,selected){
 const periods=[...new Set(selected)].map(String).sort();const latest=periods.at(-1);const prior=latest?previous(latest):null;
 const metrics=definitions.map(d=>{const row=selectRow(data,d.section,d.ids);let title=d.label;
  if(d.key==='revenue'&&row?.id!=='net_sales')title=({net_interest_income:'Thu nhập lãi thuần',net_sales_from_insurance_business:'Doanh thu bảo hiểm thuần',net_insurance_operating_revenue:'Doanh thu bảo hiểm thuần',net_revenue_of_insurance_premium:'Doanh thu phí bảo hiểm thuần',total_operating_income:'Tổng thu nhập hoạt động'})[row?.id]||d.label;
  const basis=data?.sections.find(s=>s.id===d.section)?.basis;const ytd=data?.periodType==='quarter'&&basis==='year_to_date';if(ytd)title+=' · Lũy kế';
  const value=amount(row,latest),before=ytd?null:amount(row,prior);return{...d,label:title,value,delta:before!==null&&before>0&&value!==null?(value-before)/before*100:null,prior,series:periods.map(p=>({period:p,value:amount(row,p)}))};
 });
 const assets=amount(selectRow(data,'balance_sheet',['total_assets']),latest),debt=amount(selectRow(data,'balance_sheet',['liabilities','total_liabilities']),latest),equity=amount(selectRow(data,'balance_sheet',['owners_equity']),latest);
 const capital=assets>0&&debt!==null&&equity!==null&&debt>=0&&equity>=0&&Math.abs(debt+equity-assets)<=Math.max(.001,assets*.000001)?{assets,debt,equity,equityPercent:equity/assets*100}:null;
 return{periods,latest,metrics,capital};
}
function periodIndex(p){return p.includes('-Q')?Number(p.slice(0,4))*4+Number(p.at(-1)):Number(p)*4;}
function geometry(series,width=560,height=190,padding={left:65,right:24,top:18,bottom:35}){
 const values=series.map(p=>p.value).filter(Number.isFinite),min=Math.min(0,...values),max=Math.max(0,...values);const span=max-min||1;
 const lo=min<0?min-span*.12:0,hi=max>0?max+span*.12:span*.08;const start=series.length?periodIndex(series[0].period):0,end=series.length?periodIndex(series.at(-1).period):1;
 const x=p=>start===end?(padding.left+width-padding.right)/2:padding.left+(periodIndex(p)-start)/(end-start)*(width-padding.left-padding.right);
 const y=v=>padding.top+(hi-v)/(hi-lo)*(height-padding.top-padding.bottom);
 const points=series.map(s=>({...s,x:x(s.period),y:s.value===null?null:y(s.value)}));let pen=false;const path=points.map(p=>{if(p.y===null){pen=false;return'';}const out=`${pen?'L':'M'}${p.x.toFixed(2)},${p.y.toFixed(2)}`;pen=true;return out;}).join(' ');
 return{points,path,zero:y(0),lo,hi,y,padding,width,height};
}
function sparkline(series){const g=geometry(series,96,32,{left:4,right:4,top:4,bottom:4});return`<svg class="sparkline" viewBox="0 0 96 32" aria-hidden="true"><path d="${g.path}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;}
function cards(m){return m.metrics.map((k,i)=>`<article class="kpi-card kpi-${i}"><div class="kpi-label"><span>${esc(k.label)}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${k.icon}"/></svg></div><div class="kpi-value">${k.value===null?'—':nf.format(k.value)}<span>tỷ đồng</span></div><div class="kpi-bottom"><div>${k.delta===null?`<span class="kpi-context">${k.value===null?'Chưa có dữ liệu':esc(label(m.latest))}</span>`:`<span class="kpi-change ${k.delta<0?'down':'up'}">${k.delta>0?'+':''}${nf.format(k.delta)}%</span><span class="kpi-context">so với ${esc(label(k.prior))}</span>`}</div>${sparkline(k.series)}</div></article>`).join('');}
function axisNumber(v){return Math.abs(v)>=1e6?nf.format(v/1e6)+'tr':Math.abs(v)>=1000?nf.format(v/1000)+'k':nf.format(v);}
function trend(metric){
 if(!metric||!metric.series.some(s=>s.value!==null))return'<div class="chart-empty">Chưa có dữ liệu cho chỉ tiêu này.</div>';
 const g=geometry(metric.series),ticks=Array.from({length:4},(_,i)=>g.lo+(g.hi-g.lo)*i/3),valid=g.points.filter(p=>p.value!==null);
 const axis=ticks.map(v=>`<g><line x1="65" x2="536" y1="${g.y(v)}" y2="${g.y(v)}" class="chart-gridline"/><text x="55" y="${g.y(v)+4}" text-anchor="end">${esc(axisNumber(v))}</text></g>`).join('');
 const points=g.points.map((p,i)=>`${i===0||i===g.points.length-1||g.points.length<=7?`<text x="${p.x}" y="178" text-anchor="${i===0?'start':i===g.points.length-1?'end':'middle'}">${esc(label(p.period))}</text>`:''}${p.value===null?'':`<g class="chart-point" tabindex="0" role="img" aria-label="${esc(label(p.period)+': '+precise.format(p.value)+' tỷ đồng')}" data-tooltip="${esc(label(p.period)+' · '+metric.label+': '+precise.format(p.value)+' tỷ đồng')}"><title>${esc(label(p.period)+': '+precise.format(p.value)+' tỷ đồng')}</title><circle cx="${p.x}" cy="${p.y}" r="12" class="point-hit"/><circle cx="${p.x}" cy="${p.y}" r="4" class="point-dot"/></g>`}`).join('');
 return`<svg class="trend-svg" viewBox="0 0 560 190" role="group" aria-label="${esc(metric.label)} theo kỳ, đơn vị tỷ đồng">${axis}<line x1="65" x2="536" y1="${g.zero}" y2="${g.zero}" class="zero-line"/><path d="${g.path}" class="trend-line"/>${points}</svg><div class="chart-readout" aria-live="polite">${esc(label(valid.at(-1).period))}<strong>${precise.format(valid.at(-1).value)} <span>tỷ đồng</span></strong></div>`;
}
function capital(m){
 if(!m.capital)return'<div class="chart-empty">Chưa đủ dữ liệu cơ cấu nguồn vốn.</div>';
 const c=m.capital,length=2*Math.PI*47,e=length*c.equityPercent/100;
 return`<div class="capital-content"><svg class="capital-ring" viewBox="0 0 130 130" role="img" aria-label="Vốn chủ sở hữu ${nf.format(c.equityPercent)} phần trăm tổng nguồn vốn"><circle cx="65" cy="65" r="47" fill="none" stroke="#dce3f5" stroke-width="15"/><circle cx="65" cy="65" r="47" fill="none" stroke="#5264dc" stroke-width="15" stroke-dasharray="${e} ${length-e}" transform="rotate(-90 65 65)"/><text x="65" y="63" text-anchor="middle" class="ring-number">${nf.format(c.equityPercent)}%</text><text x="65" y="82" text-anchor="middle" class="ring-caption">Vốn chủ sở hữu</text></svg><div class="capital-legend"><div><span><i class="equity-swatch"></i>Vốn chủ sở hữu</span><strong>${nf.format(c.equity)} <small>tỷ</small></strong></div><div><span><i class="debt-swatch"></i>Nợ phải trả</span><strong>${nf.format(c.debt)} <small>tỷ</small></strong></div></div></div>`;
}
function render(data,periods,selected='profit'){
 const el=id=>document.getElementById(id),m=model(data,periods);el('overview').hidden=!data||!m.latest;if(!data||!m.latest)return selected;
 el('overview-period').textContent=label(m.latest)+' · Kỳ cuối được chọn';el('kpi-grid').innerHTML=cards(m);
 const available=m.metrics.filter(k=>k.series.some(p=>p.value!==null));if(!available.some(k=>k.key===selected))selected=available[0]?.key||'';
 el('chart-metric').innerHTML=available.map(k=>`<option value="${k.key}" ${k.key===selected?'selected':''}>${esc(k.label)}</option>`).join('');el('chart-metric').disabled=!available.length;
 el('trend-chart').innerHTML=trend(m.metrics.find(k=>k.key===selected));el('capital-period').textContent=label(m.latest);el('capital-chart').innerHTML=capital(m);return selected;
}
root.FinancialDashboard={model,geometry,render};if(typeof module!=='undefined')module.exports=root.FinancialDashboard;
})(typeof window==='undefined'?globalThis:window);
