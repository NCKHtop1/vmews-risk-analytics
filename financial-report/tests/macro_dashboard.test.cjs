const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8');
const dashboardSource=fs.readFileSync(path.join(root,'frontend/macro-dashboard.js'),'utf8');
const macroSource=fs.readFileSync(path.join(root,'frontend/macro.js'),'utf8');
const collapseSource=fs.readFileSync(path.join(root,'frontend/section-collapse.js'),'utf8');
const makeRow=(date,key,value)=>({Date:date,[key]:value});
function harness(){
 const elements=new Map();
 const $=id=>{
  if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',value:'',disabled:false,hidden:false});
  return elements.get(id);
 };
 const context={window:{},document:{getElementById:$},Intl,URL,Date,Number};
 vm.createContext(context);
 vm.runInContext(dashboardSource,context,{filename:'macro-dashboard.js',timeout:2000});
 return {api:context.window.FinMacroDashboard,$};
}
const source=(id,url='https://vbma.org.vn/example.csv')=>({id,status:'ok',qualityStatus:'ok',url});
function fixture(){
 return{
  checkedAt:'2026-10-23T01:58:17+00:00',
  sources:[source('pmi'),source('money_supply'),source('credit_sector'),source('fdi'),
    {id:'esg_world_bank',status:'cached',url:'https://esgdata.worldbank.org/data/countries?iso3=VNM'}],
  datasets:{
   pmi:{status:'ok',qualityStatus:'ok',columns:['Date','PMI'],rows:[makeRow('T7 2026','PMI',52.9),makeRow('T8 2026','PMI',53.3),makeRow('T9 2026','PMI',51.9)]},
   money_supply:{status:'ok',qualityStatus:'ok',columns:['Date','M2 (tỷ VND)'],rows:[makeRow('T5 2026','M2 (tỷ VND)',19974985),makeRow('T6 2026','M2 (tỷ VND)',20414616),makeRow('T7 2026','M2 (tỷ VND)',20455644)]},
   credit_sector:{status:'ok',qualityStatus:'ok',columns:['Date','Tổng dư nợ'],rows:[makeRow('T5 2026','Tổng dư nợ',19703851),makeRow('T6 2026','Tổng dư nợ',20150411),makeRow('T7 2026','Tổng dư nợ',20262110)]},
   fdi:{status:'ok',qualityStatus:'ok',columns:['Date','FDI giải ngân (lũy kế năm) (tỷ USD)'],rows:[makeRow('T7 2026','FDI giải ngân (lũy kế năm) (tỷ USD)',15.2),makeRow('T8 2026','FDI giải ngân (lũy kế năm) (tỷ USD)',17.25),makeRow('T9 2026','FDI giải ngân (lũy kế năm) (tỷ USD)',21.07)]},
   esg_world_bank:{status:'cached',columns:['Year','AG.LND.FRST.ZS','EG.FEC.RNEW.ZS'],rows:[{Year:2021,'AG.LND.FRST.ZS':46.96,'EG.FEC.RNEW.ZS':24.2},{Year:2022,'AG.LND.FRST.ZS':47.2},{Year:2023,'AG.LND.FRST.ZS':47.44}]}
  }
 };
}
function mbb(){
 return{companies:{MBB:{canonicalMetrics:[
  {metricId:'green_credit',label:'Dư nợ tín dụng xanh',pillar:'E',year:2025,value:68501,unit:'billion VND',sourceUrl:'https://example.com/mbb.pdf'},
  {metricId:'women_workforce_pct',label:'Tỷ lệ lao động nữ',pillar:'S',year:2025,value:61,unit:'%',sourceUrl:'https://example.com/mbb.pdf'}
 ]}}};
}
test('main page embeds real charts in Macro & ESG; no second PIN gate',()=>{
 assert.match(html,/id="macro-overview"/);
 assert.match(html,/id="macro-country-chart"/);
 assert.match(html,/id="macro-company-chart"/);
 assert.match(html,/id="macro-explore"/);
 assert.doesNotMatch(html,/id="macro-unlock-form"/);
 assert.doesNotMatch(macroSource,/ACCESS_HASH|macro-unlock-form|finquery-macro-access/);
 assert.match(collapseSource,/setOpen\(c,false\)/);
 assert.doesNotMatch(collapseSource,/toggle\?\.addEventListener\('click'/);
 assert.match(collapseSource,/chevron\?\.addEventListener\('click'/);
 assert.match(html,/id="macro-body" class="collapsible-section-body" hidden/);
 assert.ok(html.indexOf('src="macro-dashboard.js"')<html.indexOf('src="macro.js"'));
});
test('full macro dashboard shows four real trends with period, units and source links',()=>{
 const {api,$}=harness();
 api.render(fixture(),mbb(),'MBB');
 const grid=$('macro-overview').innerHTML;
 assert.equal((grid.match(/class="macro-viz-card"/g)||[]).length,4);
 assert.equal((grid.match(/class="macro-trend-svg"/g)||[]).length,4);
 for(const label of ['PMI sản xuất','Cung tiền M2','Dư nợ tín dụng','FDI giải ngân','T9 2026','nghìn tỷ đồng','tỷ USD'])assert.ok(grid.includes(label),label);
 assert.match(grid,/51,9/);
 assert.match(grid,/50 phân biệt/);
 assert.match(grid,/https:\/\/vbma\.org\.vn\/example\.csv/);
 assert.match($('macro-data-freshness').textContent,/23\/10\/2026/);
});
test('source quality warnings suppress only the affected plot, not all charts',()=>{
 const {api,$}=harness(),data=fixture();
 data.sources[0].qualityStatus='warning';
 data.datasets.pmi.qualityStatus='warning';
 api.render(data,mbb(),'MBB');
 const grid=$('macro-overview').innerHTML;
 assert.match(grid,/Chưa có chuỗi được xác minh/);
 assert.equal((grid.match(/class="macro-trend-svg"/g)||[]).length,3);
});
test('sparse or invalid data never turn missing observation into zero',()=>{
 const {api}=harness();
 const pts=api.series({columns:['Date','PMI'],rows:[
  {Date:'T9 2026',PMI:51.9},
  {Date:'T7 2026',PMI:null},
  {Date:'T8 2026',PMI:'—'},
  {Date:'T6 2026',PMI:0},
  {Date:'bad',PMI:50},
  {Date:'T5 2026',PMI:49.2}
 ]},'PMI');
 assert.equal(pts.length,3);
 assert.equal(pts.map(p=>p.label).join(','),'T5 2026,T6 2026,T9 2026');
 assert.equal(pts[1].y,0);
 assert.match(api.plot(pts,{title:'PMI',unit:'điểm',threshold:50}),/<svg/);
});
test('World Bank chart states actual last observation year instead of crawl year',()=>{
 const {api,$}=harness();
 api.render(fixture(),mbb(),'MBB');
 assert.match($('macro-country-chart').innerHTML,/2023/);
 assert.match($('macro-country-chart').innerHTML,/class="macro-trend-svg"/);
 assert.match($('macro-country-source').innerHTML,/World Bank ESG/);
 assert.doesNotMatch($('macro-country-chart').innerHTML,/2026/);
});
test('MBB with one green-credit year shows value but cannot fake a trend',()=>{
 const {api,$}=harness();
 api.render(fixture(),mbb(),'MBB');
 const data=$('macro-company-chart').innerHTML;
 assert.match(data,/68\.501/);
 assert.match(data,/Dư nợ tín dụng xanh/);
 assert.match(data,/Chưa đủ hai năm cùng chỉ tiêu/);
 assert.doesNotMatch(data,/<svg/);
 assert.match($('macro-company-source').innerHTML,/https:\/\/example.com\/mbb.pdf/);
});
test('two genuine comparable annual disclosures draw one ESG company chart',()=>{
 const {api,$}=harness(),data=mbb();
 data.companies.MBB.canonicalMetrics.push({metricId:'green_credit',label:'Dư nợ tín dụng xanh',year:2024,value:49000,unit:'billion VND',sourceUrl:'https://example.com/mbb-2024.pdf'});
 api.render(fixture(),data,'MBB');
 assert.match($('macro-company-chart').innerHTML,/class="macro-trend-svg"/);
 assert.match($('macro-company-chart').innerHTML,/So với 2024/);
});
test('unverified ESG company has no fabricated score or bar',()=>{
 const {api,$}=harness();
 api.render(fixture(),{companies:{FPT:{canonicalMetrics:[],documents:[]}}},'FPT');
 assert.match($('macro-company-chart').innerHTML,/chưa có KPI ESG định lượng/);
 assert.doesNotMatch($('macro-company-chart').innerHTML,/<svg/);
 assert.equal($('macro-company-metric').disabled,true);
});
test('unsafe company sources or text do not become executable links or markup',()=>{
 const {api,$}=harness();
 const esg={companies:{MBB:{canonicalMetrics:[
  {metricId:'bad',label:'<img src=x onerror=alert(1)>',year:2025,value:22,unit:'%',sourceUrl:'javascript:alert(1)'},
  {metricId:'safe',label:'<b>chỉ tiêu</b>',year:2025,value:10,unit:'%',sourceUrl:'https://example.com/doc'}
 ]}}};
 api.render(fixture(),esg,'MBB');
 const html=$('macro-company-chart').innerHTML;
 assert.match(html,/&lt;b&gt;chỉ tiêu&lt;\/b&gt;/);
 assert.doesNotMatch(html,/javascript:|<img/);
});

test('FDI cumulative curve stays within a year instead of showing January collapse',()=>{
 const data=fixture(),{api,$}=harness();
 data.datasets.fdi.rows.unshift(makeRow('T12 2025','FDI giải ngân (lũy kế năm) (tỷ USD)',27.6));
 api.render(data,mbb(),'MBB');
 const plotted=$('macro-overview').innerHTML;
 assert.match(plotted,/FDI giải ngân/);
 assert.doesNotMatch(plotted,/T12 2025/);
 assert.match(plotted,/Lũy kế trong năm/);
});
