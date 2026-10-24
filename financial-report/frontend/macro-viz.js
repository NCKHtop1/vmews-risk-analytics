(function(){'use strict';
/* FinQuery Embedded Macro & ESG: presentation-only. No forecast or strategy inputs. */
const $=id=>document.getElementById(id);
const nf=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2});
const escaped=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const numeric=value=>typeof value==='number'&&Number.isFinite(value)?value:null;
const formatted=(value,maximum=2)=>value===null||!Number.isFinite(value)?'—':new Intl.NumberFormat('vi-VN',{maximumFractionDigits:maximum}).format(value);
const data={macro:null,esg:null,symbol:'MBB',range:36,countryMetric:'AG.LND.FRST.ZS',companyMetric:'',status:'not_loaded'};
const DATASETS={
 pmi:{title:'PMI sản xuất',key:'PMI',sub:'Điểm · trên 50 là mở rộng',unit:'điểm',decimals:1,scale:1,legend:'Mốc 50',color:'#4c71dc',reference:50},
 money_supply:{title:'Cung tiền M2',key:'M2 (tỷ VND)',sub:'Nghìn tỷ VND',unit:'nghìn tỷ VND',decimals:1,scale:1000,color:'#327eaf'},
 credit_sector:{title:'Dư nợ tín dụng',key:'Tổng dư nợ',sub:'Nghìn tỷ VND',unit:'nghìn tỷ VND',decimals:1,scale:1000,color:'#168b78'},
 fdi:{title:'FDI giải ngân',key:'FDI giải ngân (lũy kế năm) (tỷ USD)',sub:'Lũy kế từ đầu năm · tỷ USD',unit:'tỷ USD',decimals:2,scale:1,color:'#a277c6',yearCompare:true}
};
const COUNTRY=[
 {id:'AG.LND.FRST.ZS',label:'Tỷ lệ diện tích rừng',unit:'% diện tích đất'},
 {id:'EG.ELC.RNEW.ZS',label:'Tỷ trọng điện tái tạo',unit:'% sản lượng điện'},
 {id:'EG.FEC.RNEW.ZS',label:'Năng lượng tái tạo tiêu thụ',unit:'% tiêu thụ năng lượng'},
 {id:'EG.ELC.ACCS.ZS',label:'Tiếp cận điện',unit:'% dân số'},
 {id:'SP.DYN.LE00.IN',label:'Tuổi thọ trung bình',unit:'năm'},
 {id:'ER.PTD.TOTL.ZS',label:'Diện tích bảo tồn',unit:'% tổng lãnh thổ'}
];
function rank(label){
 const s=String(label??'').trim();
 let m=s.match(/^T(1[0-2]|[1-9])\s+(20\d{2})$/i);
 if(m)return Number(m[2])*12+Number(m[1])-1;
 m=s.match(/^Q([1-4])\s+(20\d{2})$/i);
 if(m)return Number(m[2])*12+(Number(m[1])-1)*3+2;
 m=s.match(/^(20\d{2})[-/](\d{1,2})$/);
 if(m&&Number(m[2])>=1&&Number(m[2])<=12)return Number(m[1])*12+Number(m[2])-1;
 m=s.match(/^(20\d{2})$/);
 return m?Number(m[1])*12+11:null;
}
function extractSeries(ds,key,scale=1){
 if(!ds||!Array.isArray(ds.rows)||!Array.isArray(ds.columns))return[];
 const first=ds.columns[0];if(!first)return[];
 const horizontal=ds.columns.some(col=>rank(col)!==null);
 const points=[];
 if(horizontal){
   // VBMA's PMI/GDP tables: rows are metrics; columns are observation months.
   const record=ds.rows.find(row=>String(row[first]||'').trim()===key);
   if(!record)return[];
   for(const col of ds.columns){const r=rank(col),v=numeric(record[col]);if(r!==null&&v!==null)points.push({date:col,rank:r,value:v/scale});}
 }else{
   // VBMA's M2/credit/FDI tables: rows are months in reverse order.
   for(const row of ds.rows){
     const label=row[first],r=rank(label),v=numeric(row[key]);
     if(r!==null&&v!==null)points.push({date:String(label),rank:r,value:v/scale});
   }
 }
 points.sort((a,b)=>a.rank-b.rank);
 const seen=new Set();
 return points.filter(p=>{if(seen.has(p.rank))return false;seen.add(p.rank);return true;});
}
function displayPeriod(period){return String(period||'').replace(/^T(\d+)\s+(\d{4})$/,'Tháng $1/$2').replace(/^Q(\d)\s+(\d{4})$/,'Quý $1/$2');}
function sourceFor(id){
 const s=(data.macro?.sources||[]).find(x=>x.id===id);
 return s&&/^https:\/\//.test(s.url||'')?s.url:'';
}
function usable(ds,id){
 const src=(data.macro?.sources||[]).find(x=>x.id===id);
 return ds && ds.status!=='error' && ds.qualityStatus!=='warning' &&
    (!src || ((src.status==='ok'||src.status==='cached')&&src.qualityStatus!=='warning'));
}
function svgChart(series,{reference=null,unit='',decimals=2,color='#4c71dc',range=null}={}){
 const valid=series.map((s,i)=>({name:s.name||'',color:s.color||color,pts:(s.points||[]).filter(p=>numeric(p.value)!==null)})).filter(s=>s.pts.length);
 if(!valid.length)return'<div class="macro-viz-empty">Chưa có đủ số liệu có thể biểu diễn.</div>';
 const combined=valid.flatMap(s=>s.pts.map(p=>p.value));if(reference!==null)combined.push(reference);
 const rawMin=Math.min(...combined),rawMax=Math.max(...combined);
 const margin=Math.max((rawMax-rawMin)*0.13,Math.abs(rawMax)*0.02,0.05);
 let minimum=rawMin-margin, maximum=rawMax+margin;
 if(reference===50){minimum=Math.min(minimum,48);maximum=Math.max(maximum,52);}
 const w=680,h=250,left=59,right=18,top=14,bottom=36;
 let allRanks=valid.flatMap(s=>s.pts.map(p=>p.rank));
 let minR=Math.min(...allRanks),maxR=Math.max(...allRanks);
 // FDI comparisons use month-of-year 1..12 (the same X dimension each year).
 if(minR===maxR){minR-=1;maxR+=1;}
 const xx=n=>left+(w-left-right)*(n-minR)/(maxR-minR);
 const yy=n=>top+(h-top-bottom)*(maximum-n)/(maximum-minimum);
 const grids=Array.from({length:5},(_,i)=>{
   const tick=minimum+(maximum-minimum)*i/4,cy=yy(tick).toFixed(1);
   return'<line x1="'+left+'" x2="'+(w-right)+'" y1="'+cy+'" y2="'+cy+'" stroke="#e9eef7" stroke-width="1"/>'+
     '<text x="'+(left-8)+'" y="'+(Number(cy)+4)+'" text-anchor="end" fill="#71829a" font-size="12">'+escaped(formatted(tick,decimals))+'</text>';
 }).join('');
 const ref=reference===null?'':'<line x1="'+left+'" x2="'+(w-right)+'" y1="'+yy(reference).toFixed(1)+'" y2="'+yy(reference).toFixed(1)+'" stroke="#d19a56" stroke-width="1.6" stroke-dasharray="6 5"/>';
 const lines=valid.map(s=>{
   const pts=s.pts;
   const d=pts.map((p,i)=>(i?'L':'M')+xx(p.rank).toFixed(1)+' '+yy(p.value).toFixed(1)).join(' ');
   const circles=pts.map((p,i)=>{
     const n=(i===pts.length-1)?4.4:3.0;
     return'<circle class="macro-chart-point" cx="'+xx(p.rank).toFixed(1)+'" cy="'+yy(p.value).toFixed(1)+'" r="'+n+'" fill="'+escaped(s.color)+'" data-label="'+escaped(s.name+' · '+displayPeriod(p.date)+': '+formatted(p.value,decimals)+' '+unit)+'" tabindex="0" role="button" aria-label="'+escaped(displayPeriod(p.date)+': '+formatted(p.value,decimals)+' '+unit)+'"><title>'+escaped(s.name+' · '+displayPeriod(p.date)+': '+formatted(p.value,decimals)+' '+unit)+'</title></circle>';
   }).join('');
   return'<path d="'+d+'" fill="none" stroke="'+escaped(s.color)+'" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>'+circles;
 }).join('');
 const labels=[];
 for(const s of valid)if(s.pts.length){
   labels.push(s.pts[0],s.pts[Math.floor((s.pts.length-1)/2)],s.pts[s.pts.length-1]);
 }
 const ranks=[...new Set(labels.map(x=>x.rank))].sort((a,b)=>a-b);
 const chosen=ranks.length>3?[ranks[0],ranks[Math.floor(ranks.length/2)],ranks[ranks.length-1]]:ranks;
 const firstSeries=valid[0].pts;
 const xlabels=chosen.map((r,i)=>{
   const pt=valid.flatMap(s=>s.pts).find(p=>p.rank===r)||firstSeries[0];
   const label=pt.date;
   return'<text x="'+xx(r).toFixed(1)+'" y="'+(h-9)+'" text-anchor="'+(i===0?'start':i===chosen.length-1?'end':'middle')+'" fill="#71829a" font-size="12">'+escaped(label)+'</text>';
 }).join('');
 const legend=valid.length>1?'<div class="macro-viz-legend">'+valid.map(s=>'<span><i style="background:'+escaped(s.color)+'"></i>'+escaped(s.name)+'</span>').join('')+'</div>':'';
 return'<div class="macro-viz-chart">'+legend+'<svg viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Biểu đồ chuỗi thời gian '+escaped(unit)+'">'+grids+ref+lines+xlabels+'</svg><div class="macro-viz-readout" aria-live="polite">Chạm vào điểm trên biểu đồ để xem kỳ và giá trị.</div></div>';
}
function macroPoints(id,range){
 const ds=data.macro?.datasets?.[id],spec=DATASETS[id];
 if(!usable(ds,id))return[];
 const points=extractSeries(ds,spec.key,spec.scale);
 return range===0?points:points.slice(-range);
}
function sourceFoot(id,pointCount){
 const src=(data.macro?.sources||[]).find(x=>x.id===id);
 const url=sourceFor(id),title=src?.provider||'VBMA';
 const source=url?'<a href="'+escaped(url)+'" target="_blank" rel="noopener noreferrer">Nguồn '+escaped(title)+' ↗</a>':'<span>Nguồn chưa xác thực</span>';
 return'<span>'+source+'</span><span>'+pointCount+' kỳ · Không realtime</span>';
}
function fdiSeries(ds){
 const points=extractSeries(ds,DATASETS.fdi.key,1);
 const years=[...new Set(points.map(p=>Math.floor(p.rank/12)))].sort((a,b)=>b-a).slice(0,2).sort((a,b)=>a-b);
 return years.map((year,i)=>({
   name:String(year),color:i===0?'#b7a2d9':'#8460b9',
   points:points.filter(p=>Math.floor(p.rank/12)===year).map(p=>({date:p.date,rank:p.rank%12+1,value:p.value}))
 })).filter(s=>s.points.length);
}
function macroCard(id){
 const ds=data.macro?.datasets?.[id],spec=DATASETS[id],supported=usable(ds,id);
 const points=supported?extractSeries(ds,spec.key,spec.scale):[];
 const latest=points[points.length-1];
 const lastDate=latest?displayPeriod(latest.date):'Chưa đủ dữ liệu';
 const value=latest?formatted(latest.value,spec.decimals):'—';
 const warning=(ds?.qualityStatus==='warning'||(data.macro?.sources||[]).find(x=>x.id===id)?.qualityStatus==='warning');
 const detail=warning?'Nguồn có cảnh báo chất lượng, tạm ngừng biểu đồ.':(!supported?'Nguồn chưa có dữ liệu đạt chuẩn.':(!latest?'Chưa có dữ liệu số.':'Kỳ gần nhất: '+lastDate));
 const series=spec.yearCompare?fdiSeries(ds):[{name:spec.title,color:spec.color,points:macroPoints(id,data.range)}];
 const chart=supported&&points.length>=2?svgChart(series,{reference:spec.reference??null,unit:spec.unit,decimals:spec.decimals,color:spec.color}):
 '<div class="macro-viz-empty">'+escaped(detail)+'</div>';
 return'<article class="macro-viz-card" data-macro-id="'+id+'">'+
 '<div class="macro-viz-head"><div><span class="macro-viz-kicker">'+escaped(spec.sub)+'</span><h4>'+escaped(spec.title)+'</h4></div><div class="macro-viz-main-value"><strong>'+value+'</strong><small>'+escaped(spec.unit)+'</small></div></div>'+
 '<p class="macro-viz-period">'+escaped(detail)+'</p>'+chart+
 '<div class="macro-viz-source">'+sourceFoot(id,points.length)+'</div></article>';
}
function renderMacro(){
 if(!data.macro)return;
 const place=$('macro-overview');if(!place)return;
 const ok=Object.keys(DATASETS).every(x=>data.macro.datasets?.[x]);
 const sourceCount=(data.macro.sources||[]).filter(s=>s.qualityStatus==='warning').length;
 const stamp=new Date(data.macro.checkedAt);
 const date=Number.isFinite(stamp.getTime())?stamp.toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',day:'2-digit',month:'2-digit',year:'numeric'}):'không xác định';
 if($('macro-data-freshness'))$('macro-data-freshness').textContent='Kiểm tra nguồn: '+date+(sourceCount?' · '+sourceCount+' cảnh báo':'');
 if($('macro-source-status'))$('macro-source-status').textContent=ok?'VBMA & World Bank · '+date:'Dữ liệu chưa đầy đủ';
 const ranges=[{n:12,label:'12 tháng'},{n:36,label:'3 năm'},{n:0,label:'Toàn bộ'}];
 const selectors='<div class="macro-viz-range" role="group" aria-label="Khoảng thời gian cho biểu đồ vĩ mô">'+ranges.map(x=>'<button type="button" data-macro-range="'+x.n+'" aria-pressed="'+(x.n===data.range)+'" class="'+(x.n===data.range?'active':'')+'">'+x.label+'</button>').join('')+'</div>';
 place.innerHTML='<div class="macro-viz-range-line"><span>Chọn khoảng thời gian</span>'+selectors+'</div>'+
 Object.keys(DATASETS).map(macroCard).join('');
}
function countryOptions(ds){
 return COUNTRY.filter(x=>extractSeries(ds,x.id).length);
}
function latestPointText(pts,unit,decimals){
 const latest=pts[pts.length-1];
 return latest?formatted(latest.value,decimals)+' '+unit+' · '+displayPeriod(latest.date):'Không có quan sát';
}
function renderCountry(){
 const el=$('macro-country-chart'),sel=$('macro-country-metric'),source=$('macro-country-source');
 if(!el||!sel)return;
 const ds=data.macro?.datasets?.esg_world_bank;
 if(!ds){el.innerHTML='<div class="macro-viz-empty">Dữ liệu World Bank chưa sẵn sàng.</div>';return;}
 const opts=countryOptions(ds);
 if(!opts.some(x=>x.id===data.countryMetric))data.countryMetric=opts[0]?.id||'';
 sel.innerHTML=opts.map(x=>'<option value="'+escaped(x.id)+'">'+escaped(x.label)+'</option>').join('');
 sel.value=data.countryMetric;
 const spec=opts.find(x=>x.id===data.countryMetric);
 if(!spec){el.innerHTML='<div class="macro-viz-empty">Không có chỉ tiêu ESG đủ dữ liệu.</div>';return;}
 const pts=extractSeries(ds,spec.id).slice(-30);
 const latest=pts.at(-1);
 el.innerHTML='<div class="macro-esg-latest"><strong>'+escaped(latest?formatted(latest.value,2):'—')+'</strong><span>'+escaped(spec.unit)+' · '+escaped(latest?String(latest.date):'—')+'</span></div>'+
 (pts.length>=2?svgChart([{name:spec.label,color:'#249783',points:pts}],{unit:spec.unit,decimals:1,color:'#249783'}):'<div class="macro-viz-empty">Chưa đủ dữ liệu nhiều năm để vẽ xu hướng.</div>');
 const url=(data.macro.sources||[]).find(x=>x.id==='esg_world_bank')?.url;
 source.innerHTML='<span>World Bank · Năm gần nhất '+escaped(latest?.date||'—')+' (không phải năm hiện hành)</span>'+
 (url&&/^https:\/\//.test(url)?'<a href="'+escaped(url)+'" target="_blank" rel="noopener noreferrer">Xem nguồn ↗</a>':'');
}
function validCompanyMetrics(company){
 const rows=(company?.canonicalMetrics?.length?company.canonicalMetrics:company?.metrics)||[];
 return rows.filter(x=>x.metricId&&Number.isFinite(Number(x.year))&&Number(x.year)>=2000&&Number(x.year)<=new Date().getUTCFullYear()&&numeric(x.value)!==null&&x.sourceUrl&&/^https:\/\//.test(x.sourceUrl));
}
function companyChoices(metrics){
 const groups=new Map();
 for(const row of metrics){
   const key=row.metricId;
   if(!groups.has(key))groups.set(key,{id:key,label:row.label||key,unit:row.unit||'',pillar:row.pillar||'',rows:[]});
   const grp=groups.get(key);
   if(grp.unit!== (row.unit||''))continue; // prevent unit-mixed trend lines
   grp.rows.push(row);
 }
 return [...groups.values()].sort((a,b)=>b.rows.length-a.rows.length||a.label.localeCompare(b.label,'vi'));
}
function renderCompany(){
 const el=$('macro-company-chart'),sel=$('macro-company-metric'),source=$('macro-company-source');
 if(!el||!sel||!source)return;
 const company=data.esg?.companies?.[data.symbol];
 if($('macro-company-symbol'))$('macro-company-symbol').textContent='DOANH NGHIỆP · '+escaped(data.symbol);
 if(!data.esg){el.innerHTML='<div class="macro-viz-empty">Đang lấy nguồn công bố ESG doanh nghiệp...</div>';sel.replaceChildren();source.textContent='Chưa có kết quả kiểm tra';return;}
 const options=companyChoices(validCompanyMetrics(company));
 if(!options.some(x=>x.id===data.companyMetric))data.companyMetric=options[0]?.id||'';
 sel.innerHTML=options.map(x=>'<option value="'+escaped(x.id)+'">'+escaped(x.label)+'</option>').join('');
 sel.disabled=!options.length;
 sel.value=data.companyMetric;
 const picked=options.find(x=>x.id===data.companyMetric);
 if(!picked){
   el.innerHTML='<div class="macro-viz-empty">Chưa có KPI ESG định lượng đủ điều kiện cho '+escaped(data.symbol)+'. Không tạo điểm ESG hoặc dữ liệu thay thế.</div>';
   source.textContent='Kỳ/nguồn: chưa có quan sát được chứng nhận';
   return;
 }
 const distinct=new Map();
 for(const r of picked.rows.sort((a,b)=>Number(a.year)-Number(b.year)))if(!distinct.has(Number(r.year)))distinct.set(Number(r.year),r);
 const rows=[...distinct.values()];
 const latest=rows.at(-1);
 const points=rows.map(x=>({date:String(x.year),rank:Number(x.year),value:x.value}));
 el.innerHTML='<div class="macro-esg-latest"><strong>'+escaped(formatted(latest.value,2))+'</strong><span>'+escaped(picked.unit)+' · Năm '+escaped(String(latest.year))+' · Trụ cột '+escaped(picked.pillar||'chưa phân loại')+'</span></div>'+
 (points.length>=2?svgChart([{name:picked.label,color:'#5b6cc5',points}],{unit:picked.unit,decimals:2,color:'#5b6cc5'}):
 '<div class="macro-viz-empty macro-esg-single">Chỉ có một kỳ công bố ('+escaped(String(latest.year))+'). Không đủ dữ liệu để kết luận xu hướng.</div>');
 const links=[...new Set(rows.map(x=>x.sourceUrl))].filter(u=>/^https:\/\//.test(u)).slice(-2);
 source.innerHTML='<span>'+rows.length+' năm có số liệu · Công bố doanh nghiệp</span>'+
 links.map((u,i)=>'<a href="'+escaped(u)+'" target="_blank" rel="noopener noreferrer">Nguồn '+(i+1)+' ↗</a>').join('');
}
function renderAll(){renderMacro();renderCountry();renderCompany();}
$('macro-overview')?.addEventListener('click',event=>{
 const btn=event.target.closest('[data-macro-range]');
 if(btn){const n=Number(btn.dataset.macroRange);if([0,12,36].includes(n)){data.range=n;renderMacro();}}
});
$('macro-country-metric')?.addEventListener('change',e=>{data.countryMetric=e.target.value;renderCountry();});
$('macro-company-metric')?.addEventListener('change',e=>{data.companyMetric=e.target.value;renderCompany();});
document.getElementById('macro')?.addEventListener('pointerover',event=>{
 const point=event.target.closest?.('.macro-chart-point');
 if(!point)return;
 const chart=point.closest('.macro-viz-chart'),readout=chart?.querySelector('.macro-viz-readout');
 if(readout)readout.textContent=point.dataset.label||'';
});
document.getElementById('macro')?.addEventListener('focusin',event=>{
 const point=event.target.closest?.('.macro-chart-point');
 if(point){const readout=point.closest('.macro-viz-chart')?.querySelector('.macro-viz-readout');if(readout)readout.textContent=point.dataset.label||'';}
});
document.getElementById('macro')?.addEventListener('click',event=>{
 const point=event.target.closest?.('.macro-chart-point');
 if(point){const readout=point.closest('.macro-viz-chart')?.querySelector('.macro-viz-readout');if(readout)readout.textContent=point.dataset.label||'';}
});
window.FinMacroViz={
 renderMacro(macro){data.macro=macro;renderMacro();renderCountry();},
 renderCompany(esg,symbol){data.esg=esg;data.symbol=String(symbol||data.symbol).toUpperCase();data.companyMetric='';renderCompany();},
 setSymbol(symbol){if(!symbol)return;data.symbol=String(symbol).toUpperCase();data.companyMetric='';renderCompany();},
 refresh(){renderAll();},
 _test:{rank,extractSeries,usable,fdiSeries,companyChoices,validCompanyMetrics,svgChart}
};
})();