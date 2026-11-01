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