/* FinQuery Portfolio Intelligence v1.3 — native workspace, shared market source, five-minute review. */
(()=>{'use strict';
const $=id=>document.getElementById(id),root=$('portfolio');
if(!root)return;
const FIVE_MIN=300000,SECTOR_RECHECK=3600000,Policy=window.FinPortfolioPolicy;
const vnInt=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:0});
const formatMoney=n=>Number.isFinite(n)?vnInt.format(Math.round(n))+' đ':'—';
const formatPct=n=>Number.isFinite(n)?(n>0?'+':'')+n.toFixed(2)+'%':'—';
const formatDate=s=>{const d=Date.parse(s||'');return Number.isFinite(d)?new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(d)):'—'};
const safe=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=v=>{const n=Number(v);return Number.isFinite(n)?n:0};
const method={DEPOSIT:'Nạp tiền',WITHDRAW:'Rút tiền',BUY:'Mua',SELL:'Bán',DIVIDEND:'Cổ tức'};
const state={loaded:false,loading:false,events:[],quotes:{},risk:null,rotation:null,tab:'overview',chartMode:'chart',sourceTime:null,
 lastLoadedAt:0,lastSectorAt:0,selectedSector:null,hoverSector:null,trailVisible:false,saveKey:null,saveFingerprint:null,
 policy:Policy.normalize({preset:'balanced'}),policyLoaded:false,policySaved:false,policyRev:0,policyBusy:false,policyDirty:false};
function status(message,warning=false){const el=$('portfolio-status');if(!el)return;el.hidden=!message;el.textContent=message||'';el.classList.toggle('portfolio-status-warning',warning);}
function isOpen(){return !root.hidden&&!document.hidden&&!document.body.classList.contains('site-locked');}
async function json(url,options={}){
 const r=await fetch(url,{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(16000),...options});
 const v=await r.json();
 if(!r.ok)throw Object.assign(Error(v?.error||'Không kết nối được danh mục.'),{code:v?.code,status:r.status});
 return v;
}
function calculate(){
 let cash=0,external=0,realized=0,dividends=0,invalid=false;
 const positions=new Map();
 for(const e of state.events){
  const k=e.kind,s=e.symbol,q=number(e.quantity),p=number(e.unit_price_vnd),fee=number(e.fee_vnd),amount=number(e.amount_vnd);
  if(k==='DEPOSIT'||k==='WITHDRAW'){
   const delta=k==='DEPOSIT'?amount:-amount;
   cash+=delta;external+=delta;continue;
  }
  if(k==='DIVIDEND'){cash+=amount;dividends+=amount;continue;}
  if(!s)continue;
  if(!positions.has(s))positions.set(s,{symbol:s,quantity:0,cost:0,realized:0});
  const h=positions.get(s);
  if(k==='BUY'){cash-=q*p+fee;h.quantity+=q;h.cost+=q*p+fee;}
  else if(k==='SELL'){
   if(q>h.quantity)invalid=true;
   const avg=h.quantity>0?h.cost/h.quantity:0;
   const gain=q*(p-avg)-fee;
   h.quantity-=q;h.cost-=q*avg;h.realized+=gain;realized+=gain;cash+=q*p-fee;
  }
 }
 let equity=0,unrealized=0;const missing=[],rows=[];
 for(const h of positions.values()){
  if(h.quantity<1)continue;
  const q=state.quotes?.[h.symbol],price=number(q?.price),valid=price>0 && Number.isFinite(price);
  if(!valid)missing.push(h.symbol);
  const value=valid?h.quantity*price:null;
  if(valid){equity+=value;unrealized+=value-h.cost;}
  rows.push({...h,price:valid?price:null,value,pnl:valid?value-h.cost:null,weight:null});
 }
 const nav=missing.length?null:cash+equity;
 for(const h of rows)h.weight=nav>0&&Number.isFinite(h.value)?100*h.value/nav:null;
 const concentration=Math.max(0,...rows.map(r=>r.weight||0)),top=rows.find(r=>(r.weight||0)===concentration)||null;
 const pnl=nav===null?null:nav-external;
 if(!Number.isSafeInteger(Math.round(cash))||nav!==null&&!Number.isSafeInteger(Math.round(nav)))invalid=true;
 const sectorAllocations=sectorWeights(rows);
 const sectorMax=sectorAllocations[0]||null;
 return{cash,equity,external,realized,dividends,unrealized,pnl,nav,rows,missing,invalid,concentration,top,sectorAllocations,sectorMax};
}
function sectorWeights(rows){
 const sectorMap=new Map(),sectorNames=new Map();
 for(const sec of Array.isArray(state.risk?.sectors)?state.risk.sectors:[]){
  for(const r of sec.memberRows||[])sectorMap.set(r.symbol,sec.id);
  sectorNames.set(sec.id,sec.label);
 }
 const list=new Map();
 for(const h of rows){
  const id=sectorMap.get(h.symbol)||state.rotation?.stocks?.[h.symbol]?.sectorId||'other';
  const old=list.get(id)||{id,name:sectorNames.get(id)||state.rotation?.sectors?.find(s=>s.id===id)?.label||'Khác',value:0,symbols:[]};
  if(Number.isFinite(h.value))old.value+=h.value;
  old.symbols.push(h.symbol);
  list.set(id,old);
 }
 const sum=[...list.values()].reduce((a,v)=>a+v.value,0);
 return [...list.values()].map(s=>({...s,weight:sum>0?100*s.value/sum:0})).sort((a,b)=>b.value-a.value);
}
function sectorOf(symbol){
 const id=state.rotation?.stocks?.[symbol]?.sectorId;
 if(id)return state.rotation?.sectors?.find(s=>s.id===id);
 for(const s of state.risk?.sectors||[]){if((s.memberRows||[]).some(row=>row.symbol===symbol))return s;}
 return null;
}
function printHoldings(z){
 $('portfolio-count').textContent=z.rows.length+' mã';
 $('portfolio-holdings-body').innerHTML=z.rows.length?z.rows.map(h=>{
  const rs=state.rotation?.stocks?.[h.symbol]?.rs20;
  return '<tr><td><button type="button" class="portfolio-symbol" data-portfolio-symbol="'+safe(h.symbol)+'">'+safe(h.symbol)+'</button></td>'+
    '<td>'+vnInt.format(h.quantity)+'</td><td>'+formatMoney(h.quantity?h.cost/h.quantity:null)+'</td>'+
    '<td>'+formatMoney(h.price)+'</td><td>'+formatMoney(h.value)+'</td>'+
    '<td class="'+(h.pnl<0?'portfolio-down':h.pnl>0?'portfolio-up':'')+'">'+formatMoney(h.pnl)+'</td>'+
    '<td>'+formatPct(h.weight)+'</td><td class="'+(rs<0?'portfolio-down':rs>0?'portfolio-up':'')+'">'+formatPct(rs)+'</td>'+
    '<td><button type="button" class="portfolio-open" data-portfolio-symbol="'+safe(h.symbol)+'">Biểu đồ ↗</button></td></tr>';
 }).join(''):'<tr><td colspan="9" class="portfolio-empty">Chưa có mã. Chọn + Giao dịch để bắt đầu theo dõi.</td></tr>';
}
function renderKPIs(z){
 const noTransactions=state.events.length===0;
 $('portfolio-nav').textContent=noTransactions?'—':formatMoney(z.nav);
 $('portfolio-cash').textContent=noTransactions?'—':formatMoney(z.cash);
 $('portfolio-pnl').textContent=noTransactions?'—':formatMoney(z.pnl);
 $('portfolio-pnl').className=z.pnl<0?'portfolio-down':z.pnl>0?'portfolio-up':'';
 $('portfolio-nav-note').textContent=noTransactions?'Chưa thiết lập':z.missing.length?'Thiếu giá: '+z.missing.join(', '):'Cổ phiếu + tiền mặt';
 $('portfolio-pnl-detail').textContent=noTransactions?'Bắt đầu bằng mẫu phân bổ':z.missing.length?'Đang chờ giá đủ mã':'Đã chốt · Chưa chốt · Cổ tức';
 $('portfolio-concentration').textContent=z.rows.length&&z.nav!==null?formatPct(z.concentration):'—';
 $('portfolio-concentration-detail').textContent=z.top?z.top.symbol+' trong giá trị danh mục':'Chưa có mã';
 $('portfolio-cash-detail').textContent=z.rows.length+' mã đang nắm giữ';
}
function renderAllocation(z){
 const host=$('portfolio-allocation');
 if(!z.sectorAllocations.length){host.innerHTML='<p class="portfolio-muted">Chưa có cơ cấu để phân tích.</p>';return;}
 host.innerHTML=z.sectorAllocations.map((g,i)=>
  '<div class="portfolio-alloc-row"><span title="'+safe(g.name)+'">'+safe(g.name)+'</span><div class="portfolio-track"><i style="width:'+Math.min(100,Math.max(0,g.weight)).toFixed(2)+'%;background:'+
  ['#5671d8','#53a88b','#e6ae61','#9180d4','#8ba5ba'][i%5]+'"></i></div><strong>'+formatPct(g.weight)+'</strong></div>'
 ).join('');
}
function renderInsights(z){
 const alerts=[];
 if(z.missing.length)alerts.push({title:'Đang chờ giá',detail:z.missing.join(', ')+' chưa có báo giá khớp.'});
 if(z.concentration>=50)alerts.push({title:'Tập trung một mã',detail:(z.top?.symbol||'Mã lớn nhất')+' chiếm '+formatPct(z.concentration)+'. Ngưỡng giám sát: 50%.'});
 if(z.sectorMax&&z.sectorMax.weight>=65&&z.rows.length>1)alerts.push({title:'Tập trung một ngành',detail:z.sectorMax.name+' chiếm '+formatPct(z.sectorMax.weight)+' giá trị cổ phiếu. Ngưỡng giám sát: 65%.'});
 if(z.invalid)alerts.push({title:'Cần đối soát',detail:'Giá trị hoặc khối lượng ghi nhận cần được kiểm tra.'});
 const risk=state.risk?.sectors;
 const sectorRisk=Array.isArray(risk)?z.sectorAllocations
  .map(a=>({weight:a.weight,name:a.name,s:risk.find(r=>r.id===a.id)}))
  .filter(a=>a.s&&Number.isFinite(Number(a.s.score))):[];
 const weighted=sectorRisk.reduce((a,r)=>a+r.weight*Number(r.s.score),0)/(sectorRisk.reduce((a,r)=>a+r.weight,0)||1);
 const hasStress=sectorRisk.length&&weighted>=75;
 if(hasStress)alerts.push({title:'Áp lực ngành',detail:'Điểm áp lực theo ngành đang ở mức '+Math.round(weighted)+'/100. Xem Giám sát rủi ro để đối chiếu.'});
 $('portfolio-alerts').innerHTML=alerts.length?alerts.slice(0,4).map(a=>'<div class="portfolio-alert"><b>'+safe(a.title)+'</b> · '+safe(a.detail)+'</div>').join('')
  :'<div class="portfolio-alert portfolio-alert-ok">Chưa phát hiện vượt ngưỡng tập trung theo các quy tắc hiện tại.</div>';
 const cards=[];
 if(z.top)cards.push({title:'Cổ phiếu lớn nhất',detail:z.top.symbol+' · '+formatPct(z.top.weight)+' danh mục. Theo dõi biến động mã này trước khi đánh giá cả danh mục.'});
 const leaders=z.rows.filter(h=>Number.isFinite(state.rotation?.stocks?.[h.symbol]?.rs20)).sort((a,b)=>
   number(state.rotation.stocks[b.symbol].rs20)-number(state.rotation.stocks[a.symbol].rs20));
 if(leaders.length){
  const strongest=leaders[0],weakest=leaders[leaders.length-1];
  cards.push({title:'Sức mạnh tương đối',detail:strongest.symbol+' RS20 '+formatPct(state.rotation.stocks[strongest.symbol].rs20)+
    (weakest.symbol!==strongest.symbol?' · '+weakest.symbol+' RS20 '+formatPct(state.rotation.stocks[weakest.symbol].rs20):'')});
 }
 if(z.sectorMax)cards.push({title:'Ngành nổi bật trong danh mục',detail:z.sectorMax.name+' · '+formatPct(z.sectorMax.weight)+' giá trị cổ phiếu.'});
 if(!cards.length)cards.push({title:'Bắt đầu phân tích',detail:'Thêm giao dịch để xem phân bổ, tín hiệu ngành và mức tập trung.'});
 $('portfolio-insights').innerHTML=cards.slice(0,3).map(c=>'<div class="portfolio-insight"><strong>'+safe(c.title)+'</strong><p>'+safe(c.detail)+'</p></div>').join('');
}
function renderHistory(){
 const events=[...state.events].reverse();
 $('portfolio-history-body').innerHTML=events.length?events.map(e=>
  '<tr><td>'+safe(String(e.trade_date||'').slice(0,10))+'</td><td>'+safe(method[e.kind]||e.kind)+'</td>'+
  '<td>'+safe(e.symbol||'—')+'</td><td>'+((e.quantity===null||e.quantity===undefined)?'—':vnInt.format(number(e.quantity)))+'</td>'+
  '<td>'+formatMoney(['BUY','SELL'].includes(e.kind)?number(e.unit_price_vnd):number(e.amount_vnd))+'</td>'+
  '<td>'+formatMoney(e.fee_vnd)+'</td></tr>').join('')
  :'<tr><td colspan="6" class="portfolio-empty">Chưa có giao dịch.</td></tr>';
}
function switchTab(tab,focus=false){
 if(!['overview','plan','rotation','history'].includes(tab))return;
 state.tab=tab;
 for(const b of $('portfolio-tabs').querySelectorAll('[data-portfolio-tab]')){
  const on=b.dataset.portfolioTab===tab;b.classList.toggle('active',on);b.setAttribute('aria-selected',String(on));b.tabIndex=on?0:-1;if(on&&focus)b.focus({preventScroll:true});
 }
 for(const sec of root.querySelectorAll('[data-portfolio-panel]'))sec.hidden=sec.dataset.portfolioPanel!==tab;
 if(tab==='rotation'&&Date.now()-state.lastSectorAt>SECTOR_RECHECK)refreshSector().catch(()=>{});
 if(tab==='rotation')requestAnimationFrame(()=>renderRotation());
 if(tab==='plan')document.dispatchEvent(new Event('finquery:portfolio-plan-open'));
}
function rotateStatus(s){return s.rs20>=0?(s.rs5>=0?'Khỏe':'Đang suy yếu'):(s.rs5>=0?'Hồi phục':'Yếu');}
function renderRotation(){
 const data=state.rotation,all=Array.isArray(data?.sectors)?data.sectors:[],
   items=all.filter(x=>Number.isFinite(x.rs5)&&Number.isFinite(x.rs20));
 const held=new Set(calculate().sectorAllocations.map(x=>x.id));
 const stamp=data?.sourceDate?'Phiên '+data.sourceDate+' · '+(data.benchmark?.eligibleSymbols||0)+' mã đủ chuỗi · '+items.length+' ngành có RS':'Chưa có dữ liệu ngành';
 $('portfolio-sector-stamp').textContent=stamp;
 const railTitle=root.querySelector('.portfolio-sector-rail-head strong');if(railTitle)railTitle.textContent=items.length+' nhóm ngành';
 $('portfolio-rotation-rows').innerHTML=all.length?all.map(x=>'<tr><td>'+safe(x.label||x.id)+'</td><td>'+formatPct(x.rs5)+'</td><td>'+
  formatPct(x.rs20)+'</td><td>'+safe((x.used??0)+'/'+(x.members??0))+'</td><td>'+safe(Number.isFinite(x.rs5)?rotateStatus(x):'Chưa đủ chuỗi')+'</td></tr>').join(''):
 '<tr><td colspan="5" class="portfolio-empty">Chưa có dữ liệu ngành.</td></tr>';
 $('portfolio-rotation-chart').hidden=state.chartMode!=='chart';
 $('portfolio-rotation-table').hidden=state.chartMode!=='table';
 root.querySelector('.portfolio-sector-rail').hidden=state.chartMode!=='chart';
 for(const button of root.querySelectorAll('[data-portfolio-view]')){
  const on=button.dataset.portfolioView===state.chartMode;
  button.classList.toggle('active',on);button.setAttribute('aria-pressed',String(on));
 }
 $('portfolio-sector-list').innerHTML=items.map(x=>{
  const selected=state.selectedSector===x.id;
  const color=x.rs20>=0?(x.rs5>=0?'#3caa72':'#dda84e'):(x.rs5>=0?'#54aebc':'#d96a76');
  return '<button type="button" class="portfolio-sector-option'+(selected?' is-selected':'')+'" data-portfolio-sector="'+safe(x.id)+'" aria-pressed="'+selected+'"><span class="portfolio-sector-option-label-wrap"><i class="portfolio-sector-dot" style="background:'+color+'"></i><span class="portfolio-sector-option-label">'+safe(x.label)+'</span></span>'+
   '<span class="portfolio-sector-option-score">'+formatPct(x.rs20)+'</span></button>';
 }).join('');
 if(!items.length){
  $('portfolio-rotation-chart').innerHTML='<p class="portfolio-muted">Chưa có chuỗi giá đủ điều kiện.</p>';
  $('portfolio-rotation-detail').textContent='Chưa có dữ liệu ngành.';
  return;
 }
 if(state.hoverSector&&!items.some(x=>x.id===state.hoverSector))state.hoverSector=null;
 if(!items.some(x=>x.id===state.selectedSector)){
  state.selectedSector=items.find(x=>held.has(x.id))?.id||items[0].id;
 }
 const chosen=items.find(x=>x.id===(state.hoverSector||state.selectedSector));
 const rail=$('portfolio-sector-list');
 for(const btn of rail.querySelectorAll('[data-portfolio-sector]')){
  const on=btn.dataset.portfolioSector===chosen.id;
  btn.classList.toggle('is-selected',on);btn.setAttribute('aria-pressed',String(on));
 }
 const mx=Math.max(4,Math.ceil(Math.max(...items.flatMap(x=>[Math.abs(x.rs5),Math.abs(x.rs20)]))*1.12)),
  left=59,right=855,top=40,bottom=390,w=right-left,h=bottom-top;
 const xx=x=>left+(x+mx)/(2*mx)*w,yy=y=>bottom-(y+mx)/(2*mx)*h;
 const zx=xx(0),zy=yy(0);
 const rect=(x,y,ww,hh,col)=>'<rect x="'+x+'" y="'+y+'" width="'+ww+'" height="'+hh+'" rx="5" fill="'+col+'"/>';
 const bg=rect(left,top,zx-left,zy-top,'#e9f6f3')+rect(zx,top,right-zx,zy-top,'#e9f6ee')+
  rect(left,zy,zx-left,bottom-zy,'#fdf1f2')+rect(zx,zy,right-zx,bottom-zy,'#fff4e7');
 const labels='<text x="'+(left+10)+'" y="'+(top+19)+'" fill="#368e96" font-size="12">Hồi phục</text>'+
  '<text x="'+(right-10)+'" y="'+(top+19)+'" fill="#2c8e68" font-size="12" text-anchor="end">Khỏe</text>'+
  '<text x="'+(left+10)+'" y="'+(bottom-11)+'" fill="#b86168" font-size="12">Yếu</text>'+
  '<text x="'+(right-10)+'" y="'+(bottom-11)+'" fill="#b0864a" font-size="12" text-anchor="end">Suy yếu</text>'+
  '<text x="'+((left+right)/2)+'" y="435" fill="#75869c" text-anchor="middle" font-size="12">RS 20 phiên →</text>'+
  '<text x="17" y="'+((top+bottom)/2)+'" text-anchor="middle" transform="rotate(-90 17 '+((top+bottom)/2)+')" fill="#75869c" font-size="12">RS 5 phiên →</text>'+
  '<text x="'+left+'" y="409" text-anchor="middle" fill="#8290a6" font-size="10">−'+mx+'%</text>'+
  '<text x="'+right+'" y="409" text-anchor="middle" fill="#8290a6" font-size="10">+'+mx+'%</text>';
 const circle=x=>{
  const col=x.rs20>=0?(x.rs5>=0?'#3caa72':'#dda84e'):(x.rs5>=0?'#54aebc':'#d96a76');
  const isSelected=x.id===state.selectedSector; const focused=x.id===chosen.id;
  const r=isSelected?8.5:focused?8:5.8;
  const hold=held.has(x.id);
  const title=safe(x.label)+' · RS5 '+formatPct(x.rs5)+' · RS20 '+formatPct(x.rs20);
  return '<circle class="portfolio-rot-dot" data-portfolio-sector="'+safe(x.id)+'" cx="'+xx(x.rs20)+'" cy="'+yy(x.rs5)+
   '" r="'+r+'" role="button" tabindex="0" fill="'+col+'" opacity="'+(focused?'1':hold?'.85':'.62')+
   '" stroke="'+(isSelected?'#5065a2':hold?'#7a8cbd':'#fff')+'" stroke-width="'+(isSelected?2:hold?1.7:1.2)+
   '" aria-label="'+title+'"><title>'+title+'</title></circle>';
 };
 const trail=Array.isArray(chosen.trail)?chosen.trail.filter(p=>Number.isFinite(p.rs5)&&Number.isFinite(p.rs20)):[];
 const points=trail.map(p=>xx(p.rs20).toFixed(1)+','+yy(p.rs5).toFixed(1)).join(' ');
 const line=(state.hoverSector||state.trailVisible)&&points?'<polyline points="'+points+'" fill="none" stroke="#6a84bd" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" opacity=".67"/>':'';
 const axis='<line x1="'+zx+'" y1="'+top+'" x2="'+zx+'" y2="'+bottom+'" stroke="#9aaac0" stroke-dasharray="4 5"/>'+
  '<line x1="'+left+'" y1="'+zy+'" x2="'+right+'" y2="'+zy+'" stroke="#9aaac0" stroke-dasharray="4 5"/>';
 const dotSvg=items.filter(x=>x.id!==chosen.id).map(circle).join('')+circle(chosen);
 // Only the selected sector has a trail and a label. Others are accessed by the list or tooltip.
 $('portfolio-rotation-chart').innerHTML='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 920 457" role="img" aria-label="Biểu đồ sức mạnh ngành, đường di chuyển của '+safe(chosen.label)+'">'+bg+axis+labels+line+dotSvg+
  '</svg>';
 const owned=calculate().rows.filter(h=>sectorOf(h.symbol)?.id===chosen.id).map(h=>h.symbol);
 const dates=trail.map(p=>p.date+' ('+formatPct(p.rs20)+' / '+formatPct(p.rs5)+')');
 $('portfolio-rotation-detail').innerHTML='<strong>'+safe(chosen.label)+'</strong> · '+safe(rotateStatus(chosen))+
  ' · RS20 '+formatPct(chosen.rs20)+' · RS5 '+formatPct(chosen.rs5)+' · '+safe(chosen.used+'/'+chosen.members)+' mã'+
  (owned.length?' · Đang nắm giữ: '+safe(owned.join(', ')):'')+
  '<div class="portfolio-method-note">Đường đi của ngành đã chọn: '+safe(dates.join(' → '))+'</div>';
}
function selectSector(id){
 if(!state.rotation?.sectors?.some(x=>x.id===id))return;
 state.selectedSector=id;state.hoverSector=null;state.trailVisible=true;renderRotation();
}
function render(){
 if(!state.loaded)return;
 const z=calculate();renderKPIs(z);printHoldings(z);renderAllocation(z);renderInsights(z);renderHistory();renderRotation();
 document.dispatchEvent(new Event('finquery:portfolio-render'));
 $('portfolio-source').textContent=state.sourceTime?'Giá: '+formatDate(state.sourceTime):'Đang đồng bộ giá';
}
async function refreshSector(){
 if(Date.now()-state.lastSectorAt<SECTOR_RECHECK&&state.rotation)return;
 try{
  const rotation=await window.FinMarketData.get('sector-rotation.json',{timeout:10000});
  if(rotation?.version==='FINQUERY-SECTOR-RS-1.0'&&Array.isArray(rotation?.sectors)){
   const current=Date.parse(state.rotation?.generatedAt||''),incoming=Date.parse(rotation.generatedAt||'');
   if(!state.rotation||!Number.isFinite(current)||Number.isFinite(incoming)&&incoming>=current)state.rotation=rotation;
   state.lastSectorAt=Date.now();if(isOpen())render();
  }
 }catch(e){if(!state.rotation)state.lastSectorAt=0;}
}
async function refresh({force=false,marketOnly=false}={}){
 if(!isOpen()||state.loading)return;
 if(!force&&Date.now()-state.lastLoadedAt<FIVE_MIN-3000)return;
 state.loading=true;
 const button=$('portfolio-refresh');if(button)button.disabled=true;
 try{
  const bundle=window.FinMarketData?.currentBundle?.();
  const ledger=marketOnly&&state.loaded?Promise.resolve(null):json('/api/user/portfolio');
  const quoteReq=bundle?.quotes?.quotes&&Date.parse(bundle.sourceTime)>Date.parse(state.sourceTime||0)?
   Promise.resolve(bundle.quotes):window.FinMarketData.get('quotes.json',{timeout:12000});
  const riskReq=bundle?.risk?Promise.resolve(bundle.risk):window.FinMarketData.get('risk-monitor.json',{timeout:10000});
  const result=await Promise.allSettled([ledger,quoteReq,riskReq]);
  if(result[0].status==='fulfilled'&&result[0].value?.events){
   state.events=result[0].value.events;
   state.loaded=true;
  }else if(!state.loaded){
   const err=result[0].reason;
   throw err||Error('Chưa tải được sổ giao dịch.');
  }
  if(result[1].status==='fulfilled'){
   const q=result[1].value,newTime=q.latestSourceTime||q.sourceTime||q.checkedAt;
   if(q.quotes&&(!state.sourceTime||Date.parse(newTime)>=Date.parse(state.sourceTime))){
    state.quotes=q.quotes;state.sourceTime=newTime;
   }
  }
  if(result[2].status==='fulfilled'){
   const r=result[2].value;
   if(r?.sectors&&(String(r.sourceTime||'')===String(state.sourceTime||'')||!state.sourceTime)){
    state.risk=r;
   }
  }
  state.lastLoadedAt=Date.now();
  status(result[1].status!=='fulfilled'?'Giá chưa đồng bộ; đang hiển thị bản gần nhất.':'');
  render();
  if(!state.rotation||Date.now()-state.lastSectorAt>SECTOR_RECHECK)void refreshSector();
 }catch(err){
  status(err?.status===401?'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.':String(err.message||'Chưa tải được danh mục.'),true);
 }finally{state.loading=false;if(button)button.disabled=false;}
}
function open(){document.dispatchEvent(new Event('finquery:portfolio-plan-open'));if(!state.loaded||Date.now()-state.lastLoadedAt>=FIVE_MIN)void refresh({force:true});else render();}
function openMarket(symbol,view='price'){
 window.FinPlatformViews?.openAnalysis?.();
 if(symbol){
  const s=String(symbol).toUpperCase();if(/^[A-Z0-9]{2,12}$/.test(s)){
   const ok=window.FinancialMarket?.openChart?.(s);
   if(!ok){const ticker=$('ticker');if(ticker)ticker.value=s;document.getElementById('company-form')?.requestSubmit();}
  }
 }
 document.querySelector('[data-market-view="'+(view==='scanner'?'scanner':'price')+'"]')?.click();
 setTimeout(()=>document.getElementById('market')?.scrollIntoView({behavior:'smooth',block:'start'}),70);
}
function go(where){
 if(where==='scanner'){openMarket(null,'scanner');return;}
 if(where==='risk'){window.FinPlatformViews?.openRisk?.();return;}
 if(where==='strategy'){window.FinPlatformViews?.openStrategy?.();return;}
 openMarket(null);
}
function dialog(opened){
 $('portfolio-entry-layer').hidden=!opened;
 if(opened){$('portfolio-entry-error').hidden=true;switchTab('history');$('portfolio-type').focus({preventScroll:true});}
 else $('portfolio-add').focus({preventScroll:true});
}
function toggleFields(){
 const kind=$('portfolio-type').value,trade=['BUY','SELL'].includes(kind),hasSymbol=trade||kind==='DIVIDEND';
 for(const field of root.querySelectorAll('[data-portfolio-field]')){
  field.hidden=field.dataset.portfolioField==='symbol'?!hasSymbol:
   field.dataset.portfolioField==='amount'?trade:!trade;
 }
 const required=[['portfolio-symbol',hasSymbol],['portfolio-quantity',trade],['portfolio-price',trade],['portfolio-amount',!trade]];
 for(const [id,on] of required)$(id).required=on;
}
function today(){const parts=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());const p=Object.fromEntries(parts.map(x=>[x.type,x.value]));return p.year+'-'+p.month+'-'+p.day;}
async function save(event){
 event.preventDefault();
 if(!state.loaded){status('Đang đồng bộ dữ liệu, thử lại sau.',true);return;}
 const v=id=>$(id).value.trim(),kind=v('portfolio-type'),trade=['BUY','SELL'].includes(kind);
 const fingerprint=JSON.stringify([kind,v('portfolio-date'),v('portfolio-symbol'),v('portfolio-quantity'),v('portfolio-price'),v('portfolio-fee'),v('portfolio-amount')]);
 if(state.saveFingerprint!==fingerprint){state.saveKey='portfolio_'+crypto.randomUUID().replace(/-/g,'');state.saveFingerprint=fingerprint;}
 const payload={kind,requestKey:state.saveKey,tradeDate:v('portfolio-date'),
   symbol:trade||kind==='DIVIDEND'?v('portfolio-symbol').toUpperCase():null,
   quantity:trade?Number(v('portfolio-quantity')):null,unitPriceVnd:trade?Number(v('portfolio-price')):null,
   feeVnd:trade?Number(v('portfolio-fee')):0,amountVnd:trade?null:Number(v('portfolio-amount'))};
 const btn=$('portfolio-save');btn.disabled=true;$('portfolio-entry-error').hidden=true;
 try{
  await json('/api/user/portfolio',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  state.saveKey=null;state.saveFingerprint=null;
  dialog(false);$('portfolio-entry-form').reset();$('portfolio-date').value=today();toggleFields();
  state.lastLoadedAt=0;await refresh({force:true});
 }catch(err){
  const e=$('portfolio-entry-error');e.hidden=false;e.textContent=err?.message||'Chưa lưu được giao dịch.';
 }finally{btn.disabled=false;}
}
function exportEvents(){
 if(!state.loaded)return;
 const blob=new Blob([JSON.stringify({exportedAt:new Date().toISOString(),events:state.events},null,2)],{type:'application/json'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='finquery-danh-muc.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),500);
}
$('portfolio-tabs').addEventListener('click',e=>{const b=e.target.closest('[data-portfolio-tab]');if(b)switchTab(b.dataset.portfolioTab);});
$('portfolio-tabs').addEventListener('keydown',e=>{
 if(!['ArrowRight','ArrowLeft','Home','End'].includes(e.key))return;
 const keys=['overview','plan','rotation','history'],i=keys.indexOf(state.tab),n=e.key==='Home'?0:e.key==='End'?3:(i+(e.key==='ArrowRight'?1:3))%4;
 e.preventDefault();switchTab(keys[n],true);
});
root.addEventListener('click',e=>{
 const stock=e.target.closest('[data-portfolio-symbol]');if(stock){openMarket(stock.dataset.portfolioSymbol);return;}
 const to=e.target.closest('[data-portfolio-go]');if(to){go(to.dataset.portfolioGo);return;}
 const sub=e.target.closest('[data-portfolio-subtab]');if(sub){switchTab(sub.dataset.portfolioSubtab);return;}
 const sector=e.target.closest('[data-portfolio-sector]');if(sector)selectSector(sector.dataset.portfolioSector);
});
$('portfolio-rotation-chart').addEventListener('pointerover',e=>{const dot=e.target.closest?.('[data-portfolio-sector]');if(dot&&dot.dataset.portfolioSector!==state.hoverSector){state.hoverSector=dot.dataset.portfolioSector;renderRotation();}});
$('portfolio-rotation-chart').addEventListener('pointerleave',()=>{if(state.hoverSector){state.hoverSector=null;renderRotation();}});
$('portfolio-rotation-chart').addEventListener('focusin',e=>{const dot=e.target.closest?.('[data-portfolio-sector]');if(dot){state.hoverSector=dot.dataset.portfolioSector;renderRotation();}});
$('portfolio-rotation-chart').addEventListener('keydown',e=>{
 if(!['Enter',' '].includes(e.key))return;const b=e.target.closest('[data-portfolio-sector]');if(!b)return;e.preventDefault();selectSector(b.dataset.portfolioSector);
});
root.querySelectorAll('[data-portfolio-view]').forEach(b=>b.addEventListener('click',()=>{state.chartMode=b.dataset.portfolioView;renderRotation();}));
$('portfolio-refresh').addEventListener('click',()=>{state.lastLoadedAt=0;void refresh({force:true});});
$('portfolio-add').addEventListener('click',()=>dialog(true));
$('portfolio-entry-close').addEventListener('click',()=>dialog(false));
$('portfolio-entry-backdrop').addEventListener('click',()=>dialog(false));
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('portfolio-entry-layer').hidden)dialog(false);});
$('portfolio-entry-form').addEventListener('submit',save);
$('portfolio-type').addEventListener('change',toggleFields);
$('portfolio-export').addEventListener('click',exportEvents);
$('portfolio-date').value=today();
toggleFields();
document.addEventListener('finquery:market-bundle',()=>{if(isOpen()&&!state.loading){state.lastLoadedAt=0;void refresh({force:true,marketOnly:true});}});
document.addEventListener('visibilitychange',()=>{if(isOpen()&&Date.now()-state.lastLoadedAt>FIVE_MIN)void refresh({force:true});});
window.addEventListener('online',()=>{if(isOpen()){state.lastLoadedAt=0;void refresh({force:true});}});
setInterval(()=>{if(isOpen()&&Date.now()-state.lastLoadedAt>=FIVE_MIN)void refresh({force:true});},FIVE_MIN);
window.FinPortfolio={open,refresh:()=>refresh({force:true}),setTab:switchTab,context:()=>({events:state.events,quoteTime:state.sourceTime,rotationTime:state.rotation?.sourceDate||null,ready:state.loaded,snapshot:calculate(),sectors:state.risk?.sectors||[],rotation:state.rotation,quoteCount:Object.keys(state.quotes||{}).length})};
})();