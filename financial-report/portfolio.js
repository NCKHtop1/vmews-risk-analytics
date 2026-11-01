/* FinQuery Portfolio Intelligence v1.1: private, server-backed cash/share ledger. */
(()=>{'use strict';
const $=id=>document.getElementById(id),money=n=>Number.isFinite(n)?Math.round(n).toLocaleString('vi-VN')+' ₫':'—',
 pct=n=>Number.isFinite(n)?(n>0?'+':'')+n.toFixed(2)+'%':'—',
 safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
 state={events:[],quotes:{},sourceTime:null,risk:null,rotation:null,rotationMode:'chart',lastPrices:null,loaded:false,baseline:false};
function setStatus(msg,err){$('status').textContent=msg;$('status').className=err?'bad':'muted';}
async function getJSON(url,options={}){const r=await fetch(url,{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(18000),...options});const x=await r.json();if(!r.ok)throw Object.assign(Error(x.error||'Không tải được dữ liệu.'),{code:x.code,status:r.status});return x;}
const num=v=>Number(v||0),kindName={DEPOSIT:'Nạp tiền',WITHDRAW:'Rút tiền',BUY:'Mua',SELL:'Bán',DIVIDEND:'Cổ tức'};
function calculate(events,quotes){
 let cash=0,realized=0,dividends=0,external=0;const positions={};const errors=[];
 for(const e of events){
  const k=e.kind,s=e.symbol,q=num(e.quantity),p=num(e.unit_price_vnd),fee=num(e.fee_vnd),v=num(e.amount_vnd);
  if(['DEPOSIT','WITHDRAW'].includes(k)){const amt=k==='DEPOSIT'?v:-v;cash+=amt;external+=amt;continue;}
  if(k==='DIVIDEND'){cash+=v;dividends+=v;continue;}
  if(!positions[s])positions[s]={symbol:s,quantity:0,cost:0,realized:0};
  const h=positions[s];if(k==='BUY'){cash-=q*p+fee;h.quantity+=q;h.cost+=q*p+fee;}
  if(k==='SELL'){
   if(q>h.quantity)errors.push('Không khớp số lượng '+s);
   const avg=h.quantity>0?h.cost/h.quantity:0;
   const pnl=q*(p-avg)-fee;cash+=q*p-fee;h.quantity-=q;h.cost-=q*avg;h.realized+=pnl;realized+=pnl;
  }
 }
 let invested=0,unrealized=0,priced=0,missing=[];const rows=[];
 for(const h of Object.values(positions)){
  if(h.quantity<=0)continue;
  const quote=quotes[h.symbol],price=num(quote?.price),ok=price>0;
  const value=ok?h.quantity*price:null;
  if(ok){invested+=value;unrealized+=value-h.cost;priced++;}else missing.push(h.symbol);
  rows.push({...h,price:ok?price:null,value,unrealized:ok?value-h.cost:null});
 }
 const nav=missing.length?null:cash+invested;
 for(const h of rows)h.weight=nav>0&&h.value!==null?h.value/nav:null;
 const maxWeight=Math.max(0,...rows.map(h=>h.weight||0));
 const hhi=rows.reduce((a,h)=>a+(h.weight||0)**2,0);
 return{cash,invested,nav,realized,unrealized,dividends,external,rows,priced,missing,errors,maxWeight,hhi,effective:hhi>0?1/hhi:0,totalPnL:nav===null?null:nav-external};
}
function render(){
 const z=calculate(state.events,state.quotes);$('nav').textContent=money(z.nav);$('cash').textContent=money(z.cash);$('pnl').textContent=money(z.totalPnL);
 $('pnl').className=z.totalPnL<0?'bad':z.totalPnL>0?'good':'';
 $('concentration').textContent=z.nav===null?'Chưa đủ giá':pct(z.maxWeight*100);
 $('priced').textContent=z.rows.length?z.priced+'/'+z.rows.length+' mã':'Chưa có mã';
 $('lastPrice').textContent=state.sourceTime?new Date(state.sourceTime).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'—';
 $('sourceStatus').textContent=z.missing.length?'Chưa đủ giá cho '+z.missing.join(', '):'Đã kiểm tra giá theo snapshot';
 $('metrics').innerHTML='<span>Vốn nạp ròng: <b>'+money(z.external)+'</b></span><span>Lãi đã chốt: <b>'+money(z.realized)+'</b></span><span>Cổ tức: <b>'+money(z.dividends)+'</b></span><span>Số mã hiệu dụng: <b>'+z.effective.toFixed(2)+'</b></span>';
 let alerts=[];
 if(z.maxWeight>.35)alerts.push('Tập trung một mã '+pct(z.maxWeight*100)+' vượt ngưỡng theo dõi 35%.');
 if(z.missing.length)alerts.push('Thiếu giá '+z.missing.join(', ')+'; không công bố NAV đầy đủ.');
 if(z.errors.length)alerts.push('Sổ giao dịch phát hiện sai lệch: '+z.errors.join(', '));
 if(z.nav!==null&&z.cash<-.01)alerts.push('Số dư tiền âm, cần đối chiếu.');
 $('alert').innerHTML=alerts.length?alerts.map(x=>'<p>⚠ '+safe(x)+'</p>').join(''):'<p class="good">Không có cảnh báo tập trung hoặc dữ liệu thiếu theo các ngưỡng hiện tại.</p>';
 $('positions').innerHTML=z.rows.length?z.rows.map(h=>'<tr><td><b>'+safe(h.symbol)+'</b></td><td>'+h.quantity.toLocaleString('vi-VN')+'</td><td>'+money(h.quantity?h.cost/h.quantity:null)+'</td><td>'+money(h.price)+'</td><td>'+money(h.value)+'</td><td class="'+(h.unrealized<0?'bad':'good')+'">'+money(h.unrealized)+'</td><td>'+pct(h.weight===null?null:h.weight*100)+'</td><td>'+(state.rotation?.stocks?.[h.symbol]?pct(state.rotation.stocks[h.symbol].rs20):'—')+'</td><td>'+(state.rotation?.stocks?.[h.symbol]?safe(state.rotation.stocks[h.symbol].rankWithinSector+'/'+state.rotation.stocks[h.symbol].sectorCount):'—')+'</td></tr>').join(''):'<tr><td colspan="9" class="muted">Chưa có cổ phiếu. Nạp tiền và ghi nhận giao dịch mua để bắt đầu.</td></tr>';
 $('trades').innerHTML=state.events.length?state.events.slice().reverse().map(e=>'<tr><td>'+safe(e.trade_date||'')+'</td><td>'+safe(kindName[e.kind]||e.kind)+'</td><td>'+safe(e.symbol||'—')+'</td><td>'+safe(e.quantity??'—')+'</td><td>'+money(num(e.unit_price_vnd)||num(e.amount_vnd))+'</td></tr>').join(''):'<tr><td colspan="5" class="muted">Chưa có giao dịch.</td></tr>';
 renderSector(z);renderRotation();
}
function renderSector(z){
 const r=state.risk;
 const list=Array.isArray(r?.sectors)?r.sectors:(typeof r?.sectors==='object'?Object.values(r.sectors):[]);
 $('sectorStatus').textContent=r?.sourceTime?'Rủi ro ngành theo phiên '+String(r.sourceTime).slice(0,10):'Đang chờ dữ liệu ngành';
 if(!list.length){$('sectors').innerHTML='<p class="muted">Không có dữ liệu ngành được xác thực.</p>';return;}
 // This is a sector stress map, NOT an unvalidated 5/20 day sector rotation.
 $('sectors').innerHTML=list.slice(0,18).map(s=>{
 const score=Number(s.score),high=Number.isFinite(score)&&score>=75;
 return '<div class="sector"><span>'+safe(s.label||s.id||'')+'</span><div class="bar"><i style="width:'+Math.max(0,Math.min(100,score||0))+'%;background:'+(high?'#db885c':'#60a5fa')+'"></i></div><b>'+ (Number.isFinite(score)?score.toFixed(0)+'/100':'—')+'</b></div>';
 }).join('')+'<p class="muted small">Điểm căng thẳng từ Risk Monitor FinQuery; điểm cao biểu thị rủi ro tăng, không phải sức mạnh tương đối. Biểu đồ luân chuyển 5/20 phiên được tính riêng từ lịch sử giá.</p>';
}

function renderRotation(){
 const data=state.rotation,records=Array.isArray(data?.sectors)?data.sectors:[];
 const valid=records.filter(s=>Number.isFinite(s.rs5)&&Number.isFinite(s.rs20));
 $('rotationStatus').textContent=data?.sourceDate?
  'Phiên '+data.sourceDate+' · '+(data.benchmark?.eligibleSymbols||0)+' mã so sánh · '+valid.length+'/'+records.length+' ngành đủ dữ liệu'
  :'Chưa có snapshot sức mạnh ngành đồng bộ; không hiển thị điểm mô phỏng.';
 if(!valid.length){
  $('rotationChart').innerHTML='<p class="muted">Chưa đủ chuỗi lịch sử để tính sức mạnh ngành 5/20 phiên.</p>';
  $('rotationRows').innerHTML='<tr><td colspan="5">Chưa đủ dữ liệu ngành.</td></tr>';
  return;
 }
 $('rotationRows').innerHTML=records.map(s=>
  '<tr><td>'+safe(s.label)+'</td><td>'+pct(s.rs5)+'</td><td>'+pct(s.rs20)+'</td><td>'+
  safe(s.used+'/'+s.members)+'</td><td>'+safe(s.status==='sufficient'?'Đủ mẫu':'Mẫu mỏng')+'</td></tr>'
 ).join('');
 const left=62,right=766,top=34,bottom=335,width=right-left,height=bottom-top;
 const max=Math.max(5,Math.ceil(Math.max(...valid.flatMap(s=>[Math.abs(s.rs5),Math.abs(s.rs20)]))*1.17));
 const xpos=v=>left+((v+max)/(2*max))*width;
 const ypos=v=>bottom-((v+max)/(2*max))*height;
 const x0=xpos(0),y0=ypos(0);
 const color=s=>s.rs20>=0?(s.rs5>=0?'#3ad399':'#f4bf56'):(s.rs5>=0?'#65c8dd':'#f47b8b');
 const rect=(x,y,w,h,fill)=>'<rect x="'+x+'" y="'+y+'" width="'+w+'" height="'+h+'" fill="'+fill+'" rx="6"/>';
 const area=rect(left,top,x0-left,y0-top,'#15363d')+rect(x0,top,right-x0,y0-top,'#153b31')+
            rect(left,y0,x0-left,bottom-y0,'#3a2737')+rect(x0,y0,right-x0,bottom-y0,'#3c3324');
 const axes='<line x1="'+x0+'" y1="'+top+'" x2="'+x0+'" y2="'+bottom+'" stroke="#8197b4" stroke-dasharray="4 6" opacity=".7"/>'+
 '<line x1="'+left+'" y1="'+y0+'" x2="'+right+'" y2="'+y0+'" stroke="#8197b4" stroke-dasharray="4 6" opacity=".7"/>';
 const labels='<text x="'+(left+10)+'" y="'+(top+20)+'" fill="#80c8d7" font-size="12">Đang phục hồi</text>'+
 '<text x="'+(right-10)+'" y="'+(top+20)+'" fill="#83e9b8" text-anchor="end" font-size="12">Khỏe</text>'+
 '<text x="'+(left+10)+'" y="'+(bottom-12)+'" fill="#f4afb4" font-size="12">Yếu</text>'+
 '<text x="'+(right-10)+'" y="'+(bottom-12)+'" fill="#f6cf83" text-anchor="end" font-size="12">Đang suy yếu</text>'+
 '<text x="'+((left+right)/2)+'" y="381" fill="#a8bdd6" font-size="12" text-anchor="middle">RS 20 phiên so với rổ cổ phiếu →</text>'+
 '<text x="16" y="'+((top+bottom)/2)+'" fill="#a8bdd6" font-size="12" text-anchor="middle" transform="rotate(-90 16 '+((top+bottom)/2)+')">RS 5 phiên →</text>'+
 '<text x="'+left+'" y="353" fill="#8199bc" font-size="11" text-anchor="middle">-'+max+'%</text>'+
 '<text x="'+right+'" y="353" fill="#8199bc" font-size="11" text-anchor="middle">+'+max+'%</text>';
 const dots=valid.map(s=>{
  const c=color(s),r=Math.min(11,Math.max(5,4+Math.sqrt(s.used||0)*1.6));
  const x=xpos(s.rs20),y=ypos(s.rs5);
  const trail=Array.isArray(s.trail)?s.trail.filter(p=>Number.isFinite(p.rs5)&&Number.isFinite(p.rs20)):[];
  const points=trail.map(p=>xpos(p.rs20).toFixed(2)+','+ypos(p.rs5).toFixed(2)).join(' ');
  const detail=s.label+': RS5 '+pct(s.rs5)+', RS20 '+pct(s.rs20)+'. '+s.used+'/'+s.members+' mã.';
  const rightEdge=x>right-108;
  const pos=rightEdge?x-r-6:x+r+6,anchor=rightEdge?'end':'start';
  return (points?'<polyline points="'+points+'" fill="none" stroke="'+c+'" stroke-width="1.5" opacity=".48"/>':'')+
    '<circle tabindex="0" class="rot-dot" role="button" aria-label="'+safe(detail)+'" data-rotation-id="'+safe(s.id)+'" cx="'+x+'" cy="'+y+'" r="'+r+'" fill="'+c+'" stroke="#132238" stroke-width="'+(s.status==='thin'?3:1.5)+'" opacity="'+(s.status==='thin'?.62:1)+'"><title>'+safe(detail)+'</title></circle>'+
    '<text x="'+pos+'" y="'+(y-9)+'" fill="#ecf4ff" text-anchor="'+anchor+'" font-size="11">'+safe(s.label)+'</text>';
 }).join('');
 $('rotationChart').innerHTML='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 810 393" role="img" aria-label="Biểu đồ sức mạnh tương đối ngành 20 và 5 phiên">'+area+axes+labels+dots+'</svg>';
 $('rotationChart').hidden=state.rotationMode!=='chart';$('rotationTable').hidden=state.rotationMode!=='table';
 $('rotationChartMode').setAttribute('aria-pressed',state.rotationMode==='chart'?'true':'false');
 $('rotationTableMode').setAttribute('aria-pressed',state.rotationMode==='table'?'true':'false');
}
function chooseSector(id){
 const sector=state.rotation?.sectors?.find(x=>x.id===id);
 if(!sector)return;
 const trajectory=(sector.trail||[]).map(p=>p.date+' ('+pct(p.rs20)+', '+pct(p.rs5)+')').join(' → ');
 $('rotationSelected').innerHTML='<b>'+safe(sector.label)+'</b> · RS 5 phiên '+pct(sector.rs5)+' · RS 20 phiên '+pct(sector.rs20)+
 ' · '+safe(sector.used+'/'+sector.members)+' mã có dữ liệu · '+(sector.status==='sufficient'?'Đủ mẫu':'Mẫu mỏng')+
 '<p class="small muted">'+safe(trajectory)+'</p>';
}
$('rotationChart').addEventListener('click',e=>{
 const target=e.target.closest('[data-rotation-id]');
 if(target)chooseSector(target.getAttribute('data-rotation-id'));
});
$('rotationChart').addEventListener('keydown',e=>{
 if(e.key!=='Enter'&&e.key!==' ')return;
 const target=e.target.closest('[data-rotation-id]');
 if(target){e.preventDefault();chooseSector(target.getAttribute('data-rotation-id'));}
});
$('rotationChartMode').addEventListener('click',()=>{state.rotationMode='chart';renderRotation();});
$('rotationTableMode').addEventListener('click',()=>{state.rotationMode='table';renderRotation();});

async function load(){
 setStatus('Đang xác thực và tải danh mục…'); 
 try{
  const [portfolio,quotes,risk,rotation]=await Promise.allSettled([
   getJSON('/api/user/portfolio'),
   getJSON('market/quotes.json'),
   getJSON('market/risk-monitor.json'),
   getJSON('market/sector-rotation.json')
  ]);
  if(portfolio.status!=='fulfilled')throw portfolio.reason;
  state.events=portfolio.value.events||[];
  if(quotes.status==='fulfilled'){state.quotes=quotes.value.quotes||{};state.sourceTime=quotes.value.latestSourceTime||quotes.value.checkedAt;}
  else {state.quotes={};state.sourceTime=null;}
  if(risk.status==='fulfilled')state.risk=risk.value;
  state.rotation=rotation.status==='fulfilled' && (!state.risk?.sourceDate || rotation.value?.sourceDate===state.risk.sourceDate)?rotation.value:null;
  state.loaded=true;render();
  setStatus('Đã đồng bộ sổ giao dịch'+(quotes.status!=='fulfilled'?'; dữ liệu giá chưa khả dụng':'')+'.',quotes.status!=='fulfilled');
 }catch(err){setStatus((err.status===401?'Vui lòng đăng nhập FinQuery để quản lý danh mục.':err.message||'Không thể kết nối.'),true);}
}
function toggleFields(){
 const type=$('type').value,trade=['BUY','SELL'].includes(type),div=type==='DIVIDEND';
 $('symbolBox').hidden=!(trade||div);$('qtyBox').hidden=!trade;$('priceBox').hidden=!trade;
 $('amountBox').hidden=trade;$('feeBox').hidden=!trade;
 $('formNote').textContent=trade?'Giá theo VND/cổ phiếu, phí nhập riêng. Chỉ ghi sổ, không đặt lệnh.':'Vốn và cổ tức theo VND; nhập theo thứ tự ngày.';
}
$('type').addEventListener('change',toggleFields);toggleFields();
$('form').addEventListener('submit',async e=>{
 e.preventDefault(); if(!state.loaded)return;
 const k=$('type').value,trade=['BUY','SELL'].includes(k),value=id=>$(id).value.trim();
 const payload={kind:k,requestKey:'portfolio_'+crypto.randomUUID().replaceAll('-',''),tradeDate:value('date'),
 symbol:trade||k==='DIVIDEND'?value('symbol').toUpperCase():null,
 quantity:trade?Number(value('quantity')):null,unitPriceVnd:trade?Number(value('price')):null,
 feeVnd:trade?Number(value('fee')):0,amountVnd:trade?null:Number(value('amount'))};
 const btn=$('submit');btn.disabled=true;
 try{await getJSON('/api/user/portfolio',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});$('form').reset();$('date').value=new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Ho_Chi_Minh'});toggleFields();await load();setStatus('Đã ghi nhận giao dịch vào tài khoản.');}
 catch(err){setStatus(err.message,true);}
 finally{btn.disabled=false;}
});
$('refresh').addEventListener('click',load);
$('date').value=new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Ho_Chi_Minh'});
$('export').addEventListener('click',()=>{
 if(!state.loaded)return;const blob=new Blob([JSON.stringify({events:state.events,exportedAt:new Date().toISOString()},null,2)],{type:'application/json'});
 const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download='finquery-portfolio-transactions.json';a.click();URL.revokeObjectURL(u);
});
load();
})();