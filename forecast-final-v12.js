(()=>{"use strict";
const $=s=>document.querySelector(s);
const finite=x=>x!==null&&x!==undefined&&x!==""&&Number.isFinite(Number(x));
const pct=(x,d=1)=>finite(x)?`${(+x*100).toFixed(d)}%`:"—";
const price=x=>finite(x)?(+x).toLocaleString("vi-VN",{maximumFractionDigits:0}):"—";
const num=(x,d=2)=>finite(x)?(+x).toFixed(d):"—";
const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
const CDN_PATH=location.pathname.split("/").filter(Boolean),ROOT=location.hostname==="cdn.githubraw.com"&&CDN_PATH.length>=3?`https://raw.githubusercontent.com/${encodeURIComponent(CDN_PATH[0])}/${encodeURIComponent(CDN_PATH[1])}/main/data`:"./data",CDN_REVISION=Math.floor(Date.now()/300000);
let BASE=null,BASE_PROMISE=null,last=null,btH=5,hoverPoints=[],chartRange=65,chartFrame=0,chartBounds=null;

async function json(name){const r=await fetch(`${ROOT}/${name}?refresh=${CDN_REVISION}`,{cache:"no-store"});if(!r.ok)throw Error(`${name}: HTTP ${r.status}`);return r.json()}
async function loadBase(){if(BASE)return BASE;if(BASE_PROMISE)return BASE_PROMISE;BASE_PROMISE=(async()=>{const[dash,legacyModel,audit,gates,market]=await Promise.all([json("forecast-dashboard-v12.json"),json("forecast-model-v12.json"),json("data-audit-v12.json"),json("phase-gates-v12.json"),json("forecast-market-v13.json").catch(()=>null)]);const model=market?.model||legacyModel,back=market?.backtest||await json("forecast-backtest-v12.json");BASE={dash,model,back,audit,gates,market,legacyModel};return BASE})();return BASE_PROMISE}
window.__VMEWS_LOAD_BASE__=loadBase;
window.__VMEWS_DATA_ROOT__=ROOT;
function assertProduction(B){if(B.gates?.status!=="PASS")throw Error("Bộ kiểm soát dữ liệu chưa đạt; dự báo đang tạm khóa.");if(B.model?.promotion?.status!=="PASS")throw Error("Mô hình chưa vượt điều kiện phát hành; dự báo đang tạm khóa.")}
function h(z,n){return z?.horizons?.[String(n)]||{}}
function validatedPrice(q){return q?.priceValidated===true&&finite(q.expectedPrice)&&finite(q.q20Price)&&finite(q.q80Price)}
function validatedDirection(q){return q?.directionValidated===true&&finite(q.probUp)}
function pupText(q,d=0){return validatedDirection(q)?`P(tăng) ${pct(q.probUp,d)}`:q?.pointDirectionValidated===true&&finite(q.historicalDirectionAccuracy)?`Đúng chiều lịch sử ${pct(q.historicalDirectionAccuracy,0)}`:"Chưa đủ kiểm định"}
function expertLabel(k){return({NUMERICAL:"Giá / kỹ thuật",REGIME:"Trạng thái thị trường",VOLATILITY:"Biến động thực tế",SECTOR:"Luân chuyển ngành",EVENT:"Tin tức / sự kiện",FLOW:"Dòng tiền tổ chức",FUND:"Danh mục quỹ",FUNDAMENTAL:"Tài chính doanh nghiệp",FUNDAMENTAL_EVENT:"Sự kiện doanh nghiệp",RUMOR:"Thông tin lan truyền"})[k]||k}
function driverTone(v){return v>0?"good":v<0?"bad":""}
function setText(id,text){const e=$(id);if(e)e.textContent=text}
function issuerHeadlineMatches(symbol,title){const name=String(symbol||"").toUpperCase(),text=String(title||""),primary=/^\s*(?:(?:HOSE|HSX|HNX|UPCOM)\s*[:/\-]\s*)?\$?([A-Z][A-Z0-9]{2,4})\s*[:\-–|]/i.exec(text);if(primary&&primary[1].toUpperCase()!==name&&(last?.B?.dash?.symbols?.[primary[1].toUpperCase()]||["FRT","FTS","FOC"].includes(primary[1].toUpperCase())))return false;if(name==="FPT"&&/\bfpt\s+(retail|long\s+châu|online)\b|chứng\s+khoán\s+fpt|bán\s+lẻ\s+kỹ\s+thuật\s+số\s+fpt/i.test(text))return false;return true}
window.__VMEWS_ISSUER_HEADLINE_MATCHES__=issuerHeadlineMatches;

function decision(z){const q=h(z,5);if(!validatedPrice(q))return{label:"CHƯA ĐỦ DỮ LIỆU",tone:"warning",text:"Chưa thể xác định vùng giá T+5."};const er=+q.expectedReturn||0,p=validatedDirection(q)?+q.probUp:null,r=z.riskStatus||"GREEN",ps=validatedDirection(q)?` · P(tăng) ${pct(p,0)}`:"",move=finite(q.expectedAbsReturn)?` · biên độ hai chiều ±${pct(q.expectedAbsReturn,2)}`:"",vol=Math.max(.004,Math.min(.012,(+z.dailyVolatility||.02)*.30)),line=`Trọng tâm ${price(q.expectedPrice)} (${er>=0?"+":""}${pct(er)})${ps}${move} · vùng giá ${price(q.q20Price)} – ${price(q.q80Price)}.`;if(r==="RED")return{label:"RỦI RO CAO",tone:"negative",text:line};if(r==="YELLOW")return{label:er>=0?"TÍCH CỰC CÓ ĐIỀU KIỆN":"THẬN TRỌNG",tone:"warning",text:line};if(q.conditionalValueValidated===false)return{label:er>=vol?"NGHIÊNG TĂNG · CHỈ THEO DÕI":er<=-vol?"NGHIÊNG GIẢM · CHỈ THEO DÕI":"THEO DÕI · CHƯA CÓ LỢI THẾ SAU PHÍ",tone:"warning",text:`${line} Chưa chứng minh được lợi thế giao dịch sau chi phí.`};if(er>=vol&&(!validatedDirection(q)||p>.46))return{label:"NGHIÊNG TĂNG",tone:"positive",text:line};if(er<=-vol&&(!validatedDirection(q)||p<.54))return{label:"NGHIÊNG GIẢM",tone:"negative",text:line};return{label:"TRUNG TÍNH",tone:"neutral",text:line}}

function renderDrivers(z,horizon=5){const q=h(z,horizon),box=$("#drivers");box.replaceChildren();setText("#driverTitle",`Các yếu tố chính · T+${horizon}`);setText("#expertMeta","");if(!validatedPrice(q)){box.innerHTML='<div class="empty">Chưa đủ dữ liệu để phân tích.</div>';return}const c=q.expertContributions||{},entries=Object.entries(c).filter(([,value])=>Math.abs(+value||0)>1e-7).sort((a,b)=>Math.abs(+b[1])-Math.abs(+a[1])),max=Math.max(...entries.map(x=>Math.abs(+x[1]||0)),1e-6);for(const[name,val]of entries){const e=document.createElement("article");e.className="driver";e.innerHTML=`<span>${esc(expertLabel(name))}</span><b class="${driverTone(+val)}">${+val>=0?"+":""}${pct(val)}</b><div class="driverBar ${driverTone(+val)}"><i style="width:${Math.min(100,Math.abs(+val)/max*100)}%"></i></div>`;box.append(e)}if(!entries.length)box.innerHTML='<div class="empty">Chưa có yếu tố đủ nổi bật.</div>'}

function renderForecastCards(z){const box=$("#forecastCards");box.replaceChildren();for(let n=1;n<=5;n++){const q=h(z,n),e=document.createElement("article");e.className="forecastCard"+(n===5?" active":"");e.setAttribute("role","button");e.tabIndex=0;e.setAttribute("aria-label",`Xem phân tích kỳ T+${n}`);if(!validatedPrice(q)){e.innerHTML=`<span>T+${n}</span><strong>Chưa đủ dữ liệu</strong>`}else{const d=(+q.expectedPrice/+z.close)-1,date=q.targetDate?new Date(`${q.targetDate}T00:00:00`).toLocaleDateString("vi-VN",{day:"2-digit",month:"2-digit"}):"",scenario=finite(q.expectedAbsReturn)&&finite(q.bearScenarioPrice)&&finite(q.bullScenarioPrice)?`<small>Biến động học được ±${pct(q.expectedAbsReturn,2)}</small><small>Kịch bản hai chiều ${price(q.bearScenarioPrice)} / ${price(q.bullScenarioPrice)}</small>`:"";e.innerHTML=`<span>T+${n}${date?` · ${date}`:""}</span><strong>${price(q.expectedPrice)}</strong><small>Trọng tâm ${d>=0?"▲ +":"▼ "}${pct(d,2)}</small>${scenario}<small>Vùng giá ${price(q.q20Price)} – ${price(q.q80Price)}</small><small>${pupText(q,0)}</small>`}const activate=()=>{document.querySelectorAll(".forecastCard").forEach(x=>x.classList.remove("active"));e.classList.add("active");renderDrivers(z,n);if(last){renderEventImpact(last.B,z,n);draw(last.sym,last.z,last.B.dash.charts?.[last.sym]||[],false)}};e.onclick=activate;e.onkeydown=event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();activate()}};box.append(e)}}

function traceCurve(context,points){if(!points.length)return;context.moveTo(points[0].x,points[0].y);if(points.length===1)return;for(let index=1;index<points.length-1;index++){const point=points[index],next=points[index+1];context.quadraticCurveTo(point.x,point.y,(point.x+next.x)/2,(point.y+next.y)/2)}const final=points.at(-1);context.lineTo(final.x,final.y)}

function draw(sym,z,history,animate=true){
  const canvas=$("#chart"),overlay=$("#chartOverlay"),rectangle=canvas.parentElement.getBoundingClientRect();
  const density=Math.min(devicePixelRatio||1,2),width=Math.max(280,rectangle.width),height=Math.max(300,rectangle.height);
  for(const surface of [canvas,overlay].filter(Boolean)){surface.width=Math.round(width*density);surface.height=Math.round(height*density);surface.style.width=`${rectangle.width}px`;surface.style.height=`${rectangle.height}px`}
  const context=canvas.getContext("2d");context.setTransform(density,0,0,density,0,0);
  if(overlay){const layer=overlay.getContext("2d");layer.setTransform(density,0,0,density,0,0);layer.clearRect(0,0,width,height)}
  const compact=width<650,padding={left:compact?55:73,right:compact?15:35,top:39,bottom:52};
  const hist=(history||[]).slice(-chartRange);if(hist.length<2)return;
  const current=+z.close,forecasts=[];
  for(let n=1;n<=5;n++){const item=h(z,n);if(validatedPrice(item))forecasts.push({n,price:+item.expectedPrice,lo:+item.q20Price,hi:+item.q80Price,p:+item.probUp,dir:validatedDirection(item),ret:+item.expectedReturn,active:item.activeExperts||[],contrib:item.expertContributions||{},calN:item.calibrationN})}
  const values=hist.map(item=>+item.close).concat(forecasts.flatMap(item=>[item.lo,item.price,item.hi]),[current]);
  let minimum=Math.min(...values),maximum=Math.max(...values);const gutter=(maximum-minimum)*.11||1;minimum-=gutter;maximum+=gutter;
  const innerWidth=width-padding.left-padding.right,historyWidth=innerWidth*(compact?.62:.69),forecastWidth=innerWidth-historyWidth;
  const xHistory=index=>padding.left+index*historyWidth/(hist.length-1),xForecast=index=>padding.left+historyWidth+forecastWidth*index/5;
  const y=value=>padding.top+(maximum-value)/(maximum-minimum)*(height-padding.top-padding.bottom);
  const split=padding.left+historyWidth,currentY=y(current),floorY=height-padding.bottom;
  const historic=hist.map((item,index)=>({x:xHistory(index),y:y(+item.close)}));
  const future=[{x:split,y:currentY},...forecasts.map(item=>({x:xForecast(item.n),y:y(item.price)}))];
  const activeCard=Array.from(document.querySelectorAll(".forecastCard")).findIndex(card=>card.classList.contains("active"))+1||5;
  hoverPoints=hist.map((item,index)=>({kind:"history",x:xHistory(index),y:y(+item.close),data:item}));
  hoverPoints.push(...forecasts.map(item=>({kind:"forecast",x:xForecast(item.n),y:y(item.price),data:item})));
  chartBounds={left:padding.left,right:width-padding.right,top:padding.top,bottom:floorY,width,height,density};
  canvas.dataset.range=String(chartRange);

  function paint(progress){
    context.clearRect(0,0,width,height);
    const forecastBackground=context.createLinearGradient(split,0,width,0);forecastBackground.addColorStop(0,"rgba(168,235,101,.018)");forecastBackground.addColorStop(1,"rgba(168,235,101,.068)");
    context.fillStyle=forecastBackground;context.fillRect(split,padding.top,width-padding.right-split,floorY-padding.top);

    context.font=`${compact?9:10}px SFMono-Regular,Consolas,monospace`;
    for(let index=0;index<5;index++){
      const row=padding.top+index*(floorY-padding.top)/4;
      context.strokeStyle="rgba(182,193,170,.105)";context.lineWidth=1;context.setLineDash([3,7]);context.beginPath();context.moveTo(padding.left,row);context.lineTo(width-padding.right,row);context.stroke();context.setLineDash([]);
      context.fillStyle="#8a9284";context.fillText(price(maximum-index*(maximum-minimum)/4),7,row+4);
    }

    context.save();context.beginPath();context.rect(padding.left,padding.top,innerWidth*progress+5,floorY-padding.top+2);context.clip();
    const historicGradient=context.createLinearGradient(0,padding.top,0,floorY);historicGradient.addColorStop(0,"rgba(201,216,187,.18)");historicGradient.addColorStop(1,"rgba(201,216,187,.008)");
    context.beginPath();traceCurve(context,historic);context.lineTo(split,floorY);context.lineTo(padding.left,floorY);context.closePath();context.fillStyle=historicGradient;context.fill();
    context.beginPath();traceCurve(context,historic);context.strokeStyle="#d9dfd0";context.lineWidth=2.05;context.lineCap="round";context.lineJoin="round";context.stroke();

    if(forecasts.length){
      const ceiling=[{x:split,y:currentY},...forecasts.map(item=>({x:xForecast(item.n),y:y(item.hi)}))],floor=[{x:split,y:currentY},...forecasts.map(item=>({x:xForecast(item.n),y:y(item.lo)}))];
      context.beginPath();traceCurve(context,ceiling);for(let index=floor.length-1;index>=0;index--)context.lineTo(floor[index].x,floor[index].y);context.closePath();
      const intervalGradient=context.createLinearGradient(0,padding.top,0,floorY);intervalGradient.addColorStop(0,"rgba(168,235,101,.20)");intervalGradient.addColorStop(.5,"rgba(168,235,101,.09)");intervalGradient.addColorStop(1,"rgba(168,235,101,.025)");context.fillStyle=intervalGradient;context.fill();
      for(const edge of [ceiling,floor]){context.beginPath();traceCurve(context,edge);context.setLineDash([4,5]);context.strokeStyle="rgba(168,235,101,.31)";context.lineWidth=.95;context.stroke();context.setLineDash([])}
      context.save();context.shadowColor="rgba(168,235,101,.53)";context.shadowBlur=12;context.beginPath();traceCurve(context,future);context.strokeStyle="#a8eb65";context.lineWidth=2.55;context.stroke();context.restore();
    }
    context.restore();

    context.setLineDash([4,6]);context.strokeStyle="rgba(187,168,239,.54)";context.lineWidth=1;context.beginPath();context.moveTo(padding.left,currentY);context.lineTo(width-padding.right,currentY);context.stroke();context.setLineDash([]);
    context.fillStyle="#bba8ef";context.textAlign="right";context.fillText(`${compact?"T0":"GIÁ T0"} ${price(current)}`,width-padding.right-4,Math.max(padding.top+13,currentY-8));context.textAlign="left";

    context.setLineDash([3,6]);context.strokeStyle="rgba(199,214,188,.29)";context.beginPath();context.moveTo(split,padding.top);context.lineTo(split,floorY);context.stroke();context.setLineDash([]);
    context.fillStyle="#858c7e";context.font=`${compact?8:9}px SFMono-Regular,Consolas,monospace`;
    if(!compact)context.fillText("LỊCH SỬ",Math.max(padding.left,split-67),padding.top-14);
    context.fillStyle="#b7df94";context.fillText(compact?"DỰ BÁO":"KỊCH BẢN T+1 → T+5",split+7,padding.top-14);

    for(const item of forecasts){
      const pointX=xForecast(item.n),pointY=y(item.price),selected=item.n===activeCard;
      if(progress*innerWidth<pointX-padding.left-8)continue;
      context.strokeStyle=selected?"rgba(168,235,101,.43)":"rgba(168,235,101,.19)";context.lineWidth=selected?1.4:1;context.beginPath();context.moveTo(pointX,y(item.hi));context.lineTo(pointX,y(item.lo));context.stroke();
      if(selected){context.fillStyle="rgba(168,235,101,.17)";context.beginPath();context.arc(pointX,pointY,11,0,Math.PI*2);context.fill()}
      context.fillStyle=selected?"#d6ffa9":"#a8eb65";context.beginPath();context.arc(pointX,pointY,selected?5.1:3.8,0,Math.PI*2);context.fill();
      context.fillStyle=selected?"#dbf6c4":"#a5ab9f";context.font=`${selected?"600 ":""}${compact?9:10}px SFMono-Regular,Consolas,monospace`;context.textAlign="center";context.fillText(`T+${item.n}`,pointX,height-20);context.textAlign="left";
    }

    context.fillStyle="#777f72";context.font=`${compact?8:9}px SFMono-Regular,Consolas,monospace`;context.fillText(hist[0].date,padding.left,height-20);
    if(!compact)context.fillText(hist.at(-1).date,Math.max(padding.left+88,split-79),height-20);
  }

  if(chartFrame){cancelAnimationFrame(chartFrame);chartFrame=0}
  if(!animate||window.matchMedia("(prefers-reduced-motion: reduce)").matches){paint(1);return}
  let started=0;const duration=780;
  const step=timestamp=>{if(!started)started=timestamp;const linear=Math.min(1,(timestamp-started)/duration),smooth=1-Math.pow(1-linear,3);paint(smooth);if(linear<1)chartFrame=requestAnimationFrame(step);else chartFrame=0};
  chartFrame=requestAnimationFrame(step);
}
function tooltipHTML(p){if(p.kind==="history"){const d=p.data;return`<strong>${esc(d.date)}</strong><hr><div class="tooltipRow"><span>Giá đóng cửa</span><b>${price(d.rawClose??d.close)}</b></div><div class="tooltipRow"><span>Khối lượng</span><b>${finite(d.volume)?(+d.volume).toLocaleString("vi-VN"):"—"}</b></div>`}const q=p.data,cs=Object.entries(q.contrib||{}).sort((a,b)=>Math.abs(+b[1])-Math.abs(+a[1])).slice(0,4);return`<strong>Dự báo T+${q.n}</strong><hr><div class="tooltipRow"><span>Trọng tâm</span><b>${price(q.price)}</b></div><div class="tooltipRow"><span>Biến động</span><b>${q.ret>=0?"+":""}${pct(q.ret)}</b></div><div class="tooltipRow"><span>P(tăng)</span><b>${q.dir?pct(q.p,0):"—"}</b></div><div class="tooltipRow"><span>Vùng giá</span><b>${price(q.lo)} – ${price(q.hi)}</b></div><hr>${cs.map(([k,v])=>`<div class="tooltipRow"><span>${esc(expertLabel(k))}</span><b class="${driverTone(+v)}">${+v>=0?"+":""}${pct(v)}</b></div>`).join("")}`}
function bindChartHover(){
  const canvas=$("#chart"),overlay=$("#chartOverlay"),tooltip=$("#tooltip");
  let pending=0;

  function clear(){tooltip.style.display="none";if(!overlay||!chartBounds)return;const context=overlay.getContext("2d");context.clearRect(0,0,chartBounds.width,chartBounds.height)}

  canvas.onmousemove=event=>{
    if(!hoverPoints.length||!chartBounds)return;
    const rectangle=canvas.getBoundingClientRect(),mouseX=event.clientX-rectangle.left,mouseY=event.clientY-rectangle.top;
    if(pending)cancelAnimationFrame(pending);
    pending=requestAnimationFrame(()=>{
      pending=0;
      let selected=null,score=Infinity;
      for(const point of hoverPoints){const distance=Math.abs(point.x-mouseX)+(point.kind==="forecast"?Math.abs(point.y-mouseY)*.12:0);if(distance<score){score=distance;selected=point}}
      if(!selected||score>Math.max(30,rectangle.width*.042)){clear();return}

      if(overlay){
        const context=overlay.getContext("2d");context.clearRect(0,0,chartBounds.width,chartBounds.height);
        context.setLineDash([3,5]);context.strokeStyle="rgba(205,244,169,.46)";context.beginPath();context.moveTo(selected.x,chartBounds.top);context.lineTo(selected.x,chartBounds.bottom);context.stroke();context.setLineDash([]);
        context.fillStyle="rgba(168,235,101,.18)";context.beginPath();context.arc(selected.x,selected.y,10,0,Math.PI*2);context.fill();
        context.fillStyle="#caff9c";context.beginPath();context.arc(selected.x,selected.y,4,0,Math.PI*2);context.fill();
      }

      tooltip.innerHTML=tooltipHTML(selected);tooltip.style.display="block";
      const tooltipWidth=Math.min(340,Math.max(235,tooltip.offsetWidth||250)),tooltipHeight=Math.max(110,tooltip.offsetHeight||170);
      const side=selected.x>rectangle.width*.66?selected.x-tooltipWidth-15:selected.x+16;
      tooltip.style.left=`${Math.max(8,Math.min(rectangle.width-tooltipWidth-8,side))}px`;
      tooltip.style.top=`${Math.max(8,Math.min(rectangle.height-tooltipHeight-8,mouseY-34))}px`;
    });
  };
  canvas.onmouseleave=()=>{if(pending)cancelAnimationFrame(pending);pending=0;clear()};

  for(const button of document.querySelectorAll(".chartRanges button")){
    button.addEventListener("click",()=>{chartRange=Math.max(20,Math.min(125,+button.dataset.range||65));document.querySelectorAll(".chartRanges button").forEach(item=>item.classList.toggle("active",item===button));if(last)draw(last.sym,last.z,last.B.dash.charts?.[last.sym]||[],true)})
  }
}

function renderNews(z){const box=$("#news");box.replaceChildren();const a=(z?.evidence?.decisionRecent||z?.evidence?.recent||[]).filter(item=>issuerHeadlineMatches(z?.symbol,item?.title));for(const x of a.slice(0,12)){const e=document.createElement(x.link?"a":"div");e.className="newsItem";if(x.link){e.href=x.link;e.target="_blank";e.rel="noopener"}const label=({POS:"TÍCH CỰC",NEG:"TIÊU CỰC",NEU:"TRUNG TÍNH"})[x.label]||x.label||"TRUNG TÍNH",event=({GENERAL:"THỊ TRƯỜNG",CORPORATE_ACTION:"DOANH NGHIỆP",EARNINGS:"KINH DOANH",OWNERSHIP:"SỞ HỮU",OPERATIONS_MA:"HOẠT ĐỘNG",ANALYST:"PHÂN TÍCH",REGULATORY:"PHÁP LÝ",FINANCING:"TÀI CHÍNH",MARKET_FLOW:"DÒNG TIỀN"})[x.event]||"SỰ KIỆN";e.innerHTML=`<b>${esc(x.title)}</b><small>${esc(x.publisher)} · ${esc(x.publishedAt||x.availableDate||"")}</small><div class="chips"><span class="chip">${esc(event)}</span><span class="chip">${esc(label)}</span>${x.decisionTimeEligible?'<span class="chip">MỚI CÔNG BỐ</span>':''}</div>`;box.append(e)}if(!a.length)box.innerHTML='<div class="empty">Chưa có tin mới đáng chú ý.</div>'}
function renderRumors(z){
  const box=$("#rumors");
  box.replaceChildren();
  const claims=z?.evidence?.rumorClaims||[],watchlist=z?.evidence?.communityWatchlist||[],audit=z?.evidence?.rumorAudit||{},source=audit.source||{};
  if(!claims.length&&!watchlist.length){
    box.innerHTML=`<div class="rumorQuiet"><span class="rumorQuietOrbit" aria-hidden="true"><i></i></span><strong>Chưa có tín hiệu mới.</strong><small>${source.articles>0?"FireAnt · 24HMoney · nguồn công bố":"Đang cập nhật nguồn công khai."}</small></div>`;
    return;
  }
  const stateLabel={CONFIRMED:"ĐÃ XÁC NHẬN",DENIED:"ĐÃ BÁC BỎ",CORROBORATED:"ĐÃ ĐỐI CHIẾU",UNVERIFIED:"ĐANG XÁC MINH",PENDING:"ĐANG ĐỐI CHIẾU"};
  for(const claim of claims.slice(0,8)){
    const item=document.createElement("article");
    const state=claim.truthState==="CONFIRMED"||claim.truthState==="DENIED"?claim.truthState:claim.verificationState||"UNVERIFIED";
    const quality=Math.max(0,Math.min(100,Number(claim.qualityScore)||0));
    const sources=(claim.sourceDetails||[]).map(row=>String(row.name||"").trim()).filter(Boolean);
    const uniqueSources=[...new Set(sources)].slice(0,3);
    const sentiment=finite(claim.sentimentScore)&&Math.abs(+claim.sentimentScore)>.05?(+claim.sentimentScore>0?"NGHIÊNG TÍCH CỰC":"NGHIÊNG TIÊU CỰC"):"CHƯA RÕ CHIỀU";
    item.className=`newsItem rumorItem rumorState${state}`;
    item.innerHTML=`<div class="rumorTopline"><span class="rumorBadge">${esc(stateLabel[state]||stateLabel.UNVERIFIED)}</span><span class="rumorQuality">${quality}<i>/100</i></span></div><b>${esc(claim.title||claim.claimId)}</b><small>${esc(claim.firstDate||"")}${claim.lastDate&&claim.lastDate!==claim.firstDate?` → ${esc(claim.lastDate)}`:""}</small><div class="rumorQualityTrack"><i style="width:${quality}%"></i></div><div class="chips"><span class="chip">${claim.sources||1} nguồn độc lập</span><span class="chip">${claim.items||1} lượt ghi nhận</span><span class="chip">${esc(sentiment)}</span>${claim.fireantMentions?'<span class="chip rumorFireant">FireAnt</span>':""}${claim.money24hMentions?'<span class="chip rumor24h">24HMoney</span>':""}</div>${uniqueSources.length?`<small class="rumorSources">${esc(uniqueSources.join(" · "))}</small>`:""}${claim.resolutionTitle?`<small class="rumorResolution">Công bố đối chiếu: ${esc(claim.resolutionTitle)}</small>`:""}`;
    box.append(item);
  }
  const shown=new Set(claims.map(claim=>String(claim.title||"").trim().toLocaleLowerCase("vi")));
  for(const signal of watchlist.slice(0,Math.max(2,8-claims.length))){
    const title=String(signal.title||"").trim();
    if(!title||shown.has(title.toLocaleLowerCase("vi")))continue;
    shown.add(title.toLocaleLowerCase("vi"));
    const item=document.createElement("article"),quality=Math.max(0,Math.min(100,Number(signal.qualityScore)||0));
    item.className="newsItem rumorItem rumorStatePENDING";
    item.innerHTML=`<div class="rumorTopline"><span class="rumorBadge">${stateLabel.PENDING}</span><span class="rumorQuality">${quality}<i>/100</i></span></div><b>${esc(title)}</b><small>${esc(signal.publisher||"")} · ${esc(String(signal.publishedAt||"").replace("T"," ").slice(0,16))}</small><div class="chips"><span class="chip">1 nguồn</span>${signal.fireant?'<span class="chip rumorFireant">FireAnt</span>':""}${signal.money24h?'<span class="chip rumor24h">24HMoney</span>':""}</div>`;
    box.append(item);
  }
}

function renderSource(B,sym){const box=$("#sourceAudit");box.replaceChildren();const z=B.dash.symbols?.[sym]||{},u=B.model.universe||{},signal=B.market?.sources?.signalAudit||{},fundAudit=B.market?.sources?.fundAudit||{},rumorAudit=B.market?.sources?.rumorAudit||{},flow=z.flow||{},fund=z.fundContext||{},foreign=flow.foreign||{},prop=flow.proprietary||{},age=item=>item.latestDate?item.stale===true||(+item.ageSessions||0)>0?`Cập nhật chậm ${Math.max(1,+item.ageSessions||0)} phiên`:"Đã cập nhật cùng phiên":"Chưa có dữ liệu từ nguồn",tracked=(z.rumorContext?.claimCount||0)+(z.evidence?.communityWatchlist?.length||0),communitySource=rumorAudit.source?.publishers?.join(" · ")||"FireAnt · 24HMoney",priceDetail=z.priceSourceAgreement?.status==="PASS"?"Đã đối chiếu hai nguồn":z.dataFreshness==="CURRENT"?"Đã cập nhật từ nguồn chính":"Cần cập nhật trước khi sử dụng",fundDetail=fund.available?(fund.scenarioEligible===true||fund.inferenceEligible===true?"Bối cảnh tham khảo · chưa điều chỉnh giá trung tâm":"Chưa đủ lịch sử kiểm định"):`${fundAudit.snapshotCount||0} kỳ công bố`,rows=[["Giá thị trường",z.date||"—",priceDetail],["Độ phủ HOSE",`${u.currentSymbols??"—"} mã`,finite(u.hoseCoverage)?pct(u.hoseCoverage,1):"—"],["Tin đã đối chiếu",`${(+signal.acceptedEvents||0).toLocaleString("vi-VN")} bài`,`${signal.newsSymbols??"—"} mã cổ phiếu`],["Dòng tiền khối ngoại",foreign.latestDate||"CHƯA CÓ",age(foreign)],["Dòng tiền tự doanh",prop.latestDate||"CHƯA CÓ",age(prop)],["Danh mục quỹ",fund.available?`${fund.fundCount||0} quỹ`:"CHƯA CÓ",fundDetail],["Tài chính doanh nghiệp",z.fundamentalContext?.available?"ĐÃ GHI NHẬN":"CHƯA CÓ",z.fundamentalContext?.available?"Bối cảnh tham khảo · chưa điều chỉnh giá trung tâm":"Đang mở rộng nguồn"],["Tín hiệu cộng đồng",`${tracked} tín hiệu`,rumorAudit.source?.articles?`${communitySource} · ${rumorAudit.source.articles} bài`:communitySource],["Rổ VN30",B.dash.lists?.vn30?.symbols?.includes(sym)?"THÀNH VIÊN":"NGOÀI RỔ",B.dash.lists?.vn30?.effectiveDate||"03/08/2026"]];for(const[label,value,detail]of rows){const e=document.createElement("article");e.className="sourceCard";e.innerHTML=`<span>${esc(label)}</span><b>${esc(value)}</b><small>${esc(detail)}</small>`;box.append(e)}}

function renderEventImpact(B,z,horizon=5){const box=$("#eventImpact");if(!box)return;const hAudit=B.model.horizons?.[String(horizon)]||{},study=hAudit.eventImpactAudit||{},news=study.positiveNews||{},negative=study.negativeNews||{},feature=z.newsFeatures||{},signed=v=>finite(v)?`${+v>=0?"+":""}${pct(v,2)}`:"—";setText("#eventImpactMeta",`T+${horizon} · ${(study.observations||0).toLocaleString("vi-VN")} quan sát`);box.innerHTML=`<article class="proofCard"><span>Sau tin tích cực</span><b class="${(+news.meanAbnormalReturn)>=0?"good":"bad"}">${signed(news.meanAbnormalReturn)}</b><small>${news.n||0} quan sát</small></article><article class="proofCard"><span>Sau tin tiêu cực</span><b class="${(+negative.meanAbnormalReturn)>=0?"good":"bad"}">${signed(negative.meanAbnormalReturn)}</b><small>${negative.n||0} quan sát</small></article><article class="proofCard"><span>Tin của ${esc(z.symbol||"")} · 5 phiên</span><b>${feature.count5||0} bài</b><small>${feature.positive5||0} tích cực · ${feature.negative5||0} tiêu cực</small></article><article class="proofCard"><span>Nguồn chính thức</span><b>${feature.official5||0} bài</b><small>trong 5 phiên gần nhất</small></article>`}

function metricCard(label,value,detail=""){return`<div class="metric"><span>${esc(label)}</span><b>${esc(value)}</b>${detail?`<small>${esc(detail)}</small>`:""}</div>`}
function renderBacktest(B,sym,horizon=5){btH=horizon;const z=B.back.horizons?.[String(horizon)]||{},m=z.metrics||{},cost=m.costAwareLongAudit||{},tabs=$("#tabs");tabs.replaceChildren();for(let n=1;n<=5;n++){const b=document.createElement("button");b.textContent=`T+${n}`;b.className=n===horizon?"active":"";b.onclick=()=>renderBacktest(B,sym,n);tabs.append(b)}setText("#btMeta",`T+${horizon} · ${(m.n??0).toLocaleString("vi-VN")} quan sát`);$("#metrics").innerHTML=[metricCard("Xếp hạng tín hiệu",pct(m.rankIC)),metricCard("Phiên xếp hạng đúng",pct(m.positiveICDayShare)),metricCard("Khoảng cách mạnh/yếu",pct(m.spread,2),"chênh lệch nhóm; không phải lãi chắc chắn"),metricCard("Cải thiện sai số",pct(m.executableMAESkill),"so với giá không đổi"),metricCard("Dự báo biên độ",pct(m.magnitudeMAESkill),"so với biên độ nền"),metricCard("Độ phủ vùng giá",pct(m.coverage20_80)),metricCard("Đúng chiều lịch sử",pct(m.directionalAccuracy),"không phải xác suất mã"),metricCard("Xác suất hướng",z.directionStatus==="PASS"?pct(m.brierSkill):"CHƯA ĐẠT","kiểm định Brier"),metricCard("Dịch chuyển trung tâm",pct(m.executableMedianAbs,2)),metricCard("Biên độ mô hình học",pct(m.medianExpectedAbsMove,2)),metricCard("Biến động thực tế",pct(m.realizedMedianAbs,2)),metricCard("Mức bám biên độ",pct(m.magnitudeCalibrationRatio,0),"biên độ học / thực tế"),metricCard("Sàng lọc sau phí",pct(cost.meanNetRealizedReturn,2),cost.observations?`${(+cost.observations).toLocaleString("vi-VN")} quan sát · phí ${(cost.roundTripCostBps/100).toFixed(2)}%`:"chưa đủ kiểm định")].join("");const all=(B.back.cases?.[String(horizon)]||[]),same=all.filter(x=>x.symbol===sym),cases=(same.length?same:all).slice(-120).reverse(),tbody=$("#btRows");tbody.replaceChildren();for(const x of cases){const tr=document.createElement("tr");const dir=x.correctDirection===true?"✓":x.correctDirection===false?"✕":"—",hit=x.intervalHit===true?"✓":x.intervalHit===false?"✕":"—";tr.innerHTML=`<td>${esc(x.symbol)}</td><td>${esc(x.originDate)}</td><td>${pct(x.prior20)}</td><td>${x.predictedReturn>=0?"+":""}${pct(x.predictedReturn)}</td><td>${price(x.expectedPrice)}</td><td>${validatedDirection({directionValidated:z.directionStatus==="PASS",probUp:x.probUp})?pct(x.probUp,0):"—"}</td><td>${price(x.actualRawPrice)}</td><td>${price(x.realizedComparablePrice)}</td><td>${x.actualReturn>=0?"+":""}${pct(x.actualReturn)}</td><td class="${x.correctDirection?"good":"bad"}">${dir}</td><td class="${x.intervalHit?"good":"bad"}">${hit}</td>`;tr.onclick=()=>renderBacktestDetail(x,horizon);tbody.append(tr)}if(!cases.length)tbody.innerHTML='<tr><td colspan="11">Chưa có trường hợp phù hợp.</td></tr>';$("#ablation").replaceChildren();if(cases[0])renderBacktestDetail(cases[0],horizon);renderEventImpact(B,B.dash.symbols?.[sym]||{},horizon)}
function renderBacktestDetail(x,horizon){const box=$("#btDetail");if(!box)return;const c=x.contextAtOrigin||{},expert=x.expertPredictions||{};box.innerHTML=`<div class="eyebrow">Kiểm chứng tại thời điểm dự báo</div><h3>${esc(x.symbol)} · ${esc(x.originDate)} · T+${horizon}</h3><div class="sourceGrid">${metricCard("Giá tại thời điểm dự báo",price(x.originPrice))}${metricCard("Giá dự báo",price(x.expectedPrice),pct(x.predictedReturn))}${metricCard("Giá thực tế",price(x.actualRawPrice),pct(x.actualReturn))}${metricCard("Giá điều chỉnh so sánh",price(x.realizedComparablePrice))}${metricCard("Biến động 20 phiên",pct(c.prior20??x.prior20))}${metricCard("Độ rộng thị trường",pct(c.breadth20))}${metricCard("Tin tức / lan truyền",`${num(c.newsN20,0)} / ${num(c.rumorN20,0)}`)}${metricCard("Dòng tiền tổ chức",`Ngoại ${num(c.foreignAvailable,0)} · Tự doanh ${num(c.propAvailable,0)}`)}</div><div class="chips">${Object.entries(expert).map(([k,v])=>`<span class="chip">${esc(expertLabel(k))}: ${+v>=0?"+":""}${pct(v)}</span>`).join("")}</div>`}

function renderSummary(B,sym,z){const d=decision(z),de=$("#decision");de.textContent=d.label;de.className=`decision ${d.tone}`;setText("#summary",d.text);setText("#close",price(z.close));for(const n of [1,3,5]){const q=h(z,n);setText(`#t${n}`,validatedPrice(q)?price(q.expectedPrice):"—")}const q5=h(z,5),audit=B.model.horizons?.["5"]?.sealedAudit||{},ratio=finite(q5.magnitudeCalibrationRatio)?+q5.magnitudeCalibrationRatio:finite(audit.medianExpectedAbsMove)&&finite(audit.realizedMedianAbs)?+audit.medianExpectedAbsMove/Math.max(+audit.realizedMedianAbs,1e-12):null,signValidated=q5.pointDirectionValidated===true||(+audit.directionalAccuracy||0)>=.52&&(audit.chronologicalFolds||[]).filter(item=>(+item.directionalAccuracy||0)>.5).length>=3,signRate=finite(q5.historicalDirectionAccuracy)?+q5.historicalDirectionAccuracy:+audit.directionalAccuracy,rank=q5.crossSectionalRankValidated===true&&finite(q5.crossSectionalRankPercentile)?` ${sym} thuộc nhóm ${Math.max(1,Math.ceil((1-+q5.crossSectionalRankPercentile)*100))}% có xếp hạng mạnh nhất toàn HOSE.`:"",liveScenario=q5.liveScenarioOverlay?.scenarioPrice?" Thông tin mới chỉ được lưu thành kịch bản tham khảo và không làm thay đổi giá trung tâm.":"";setText("#range5",validatedPrice(q5)?`${price(q5.q20Price)} – ${price(q5.q80Price)}`:"—");setText("#pup",validatedDirection(q5)?`P(tăng) ${pct(q5.probUp,0)}`:signValidated?`Đúng chiều lịch sử ${pct(signRate,0)}`:"CHƯA ĐỦ KIỂM ĐỊNH");setText("#move5",finite(q5.expectedAbsReturn)?`±${pct(q5.expectedAbsReturn,2)}`:"—");setText("#bear5",finite(q5.bearScenarioPrice)?price(q5.bearScenarioPrice):"—");setText("#scenarioCenter5",validatedPrice(q5)?price(q5.expectedPrice):"—");setText("#bull5",finite(q5.bullScenarioPrice)?price(q5.bullScenarioPrice):"—");setText("#scenarioCaveat",`${finite(ratio)?`Biên độ mô hình bám ${pct(ratio,0)} mức biến động ngoài mẫu. `:""}${validatedDirection(q5)?"Xác suất chiều giá đã qua kiểm định; kịch bản vẫn không phải cam kết giá.":signValidated?`Dấu dự báo đúng ${pct(signRate,1)} ngoài mẫu; đây không phải xác suất tăng của mã. Hai kịch bản vẫn có thể xảy ra.`:"Chiều tăng/giảm T+5 chưa qua kiểm định xác suất; hai kịch bản chỉ biểu diễn độ lớn có thể xảy ra."}${liveScenario}${rank}`);setText("#risk",({GREEN:"THẤP",YELLOW:"THEO DÕI",WATCH:"THEO DÕI",RED:"CAO"})[z.riskStatus]||"—");setText("#chartTitle",`${sym} · ${price(z.close)} → T+1…T+5`);setText("#modelBadge",`HOSE · ${B.dash.asOf||z.date||"—"}`)}
function quickButtons(B){const box=$("#quick");box.replaceChildren();for(const s of ["FPT","VCB","HPG","MBB","FRT","PNJ","VNM","SSI"]){if(!B.dash.symbols?.[s])continue;const b=document.createElement("button");b.textContent=s;b.onclick=()=>{$("#symbol").value=s;renderSymbol(s)};box.append(b)}}
function rerender(B,sym,z){last={B,sym,z};renderSummary(B,sym,z);renderForecastCards(z);renderDrivers(z,5);draw(sym,z,B.dash.charts?.[sym]||[]);renderNews(z);renderRumors(z);renderSource(B,sym);renderBacktest(B,sym,btH);window.dispatchEvent(new CustomEvent("vmews:symbol-changed",{detail:{symbol:sym,snapshot:z}}))}
function applyCommunity(B,payload){
  if(!payload||payload.asOf!==B.dash.asOf||!payload.generatedAt)return false;
  const timestamp=Date.parse(payload.generatedAt),previous=Date.parse(window.__VMEWS_COMMUNITY_LIVE__?.generatedAt||"");
  if(!Number.isFinite(timestamp)||(Number.isFinite(previous)&&timestamp<=previous)||timestamp>Date.now()+300000)return false;
  window.__VMEWS_COMMUNITY_LIVE__=payload;
  const source=B.market?.sources?.rumorAudit?.source;
  if(source){source.publishers=payload.publishers||source.publishers;source.publisherCounts=payload.publisherCounts||source.publisherCounts;source.articles=Object.values(payload.publisherCounts||{}).reduce((sum,value)=>sum+(+value||0),0)||source.articles;source.collectedAt=payload.generatedAt}
  let scenarios=0;
  for(const[symbol,update]of Object.entries(payload.symbols||{})){
    const snapshot=B.dash.symbols?.[symbol];
    if(!snapshot)continue;
    snapshot.evidence=snapshot.evidence||{};
    snapshot.evidence.communityWatchlist=Array.isArray(update.watchlist)?update.watchlist:[];
    if(Array.isArray(update.claims)&&update.claims.length)snapshot.evidence.rumorClaims=update.claims;
    if(update.rumorContext&&Object.keys(update.rumorContext).length)snapshot.rumorContext=update.rumorContext;
    if(snapshot.evidence.rumorAudit){snapshot.evidence.rumorAudit.source=source||snapshot.evidence.rumorAudit.source;snapshot.evidence.rumorAudit.qualifiedClaims=snapshot.evidence.rumorClaims?.length||0}
    for(const[key,adjustment]of Object.entries(update.horizons||{})){
      const horizon=snapshot.horizons?.[key];
      const scenarioPrice=Number.isFinite(+adjustment.scenarioPrice)?+adjustment.scenarioPrice:+adjustment.expectedPrice;
      const tickSize=+adjustment.tickSize||+horizon?.tickSize||1;
      if(!horizon||horizon.priceValidated!==true||!Number.isFinite(scenarioPrice)||scenarioPrice%tickSize!==0)continue;
      horizon.liveScenarioOverlay={
        scenarioPrice,
        scenarioReturn:Number.isFinite(+adjustment.scenarioReturn)?+adjustment.scenarioReturn:Number.isFinite(+adjustment.expectedReturn)?+adjustment.expectedReturn:null,
        scenarioQ20Price:Number.isFinite(+adjustment.scenarioQ20Price)?+adjustment.scenarioQ20Price:Number.isFinite(+adjustment.q20Price)?+adjustment.q20Price:null,
        scenarioQ80Price:Number.isFinite(+adjustment.scenarioQ80Price)?+adjustment.scenarioQ80Price:Number.isFinite(+adjustment.q80Price)?+adjustment.q80Price:null,
        liveEvidence:adjustment.liveEvidence||null,
        observedAt:adjustment.liveAdjustment?.observedAt||payload.generatedAt,
        appliedToCentralForecast:false,
      };
      scenarios++;
    }
  }
  if(last?.B===B)rerender(B,last.sym,B.dash.symbols[last.sym]);
  window.dispatchEvent(new CustomEvent("vmews:community-updated",{detail:{generatedAt:payload.generatedAt,forecastUpdates:0,scenarioUpdates:scenarios}}));
  return true;
}
async function refreshCommunity(B){
  try{
    const revision=Math.floor(Date.now()/90000),response=await fetch(`${ROOT}/community-intelligence-live-v19.json?refresh=${revision}`,{cache:"no-store"});
    if(!response.ok)return false;
    return applyCommunity(B,await response.json());
  }catch{return false}
}
window.__VMEWS_APPLY_COMMUNITY_LIVE__=applyCommunity;
async function renderSymbol(raw){const B=await loadBase();assertProduction(B);const sym=String(raw||"").trim().toUpperCase(),z=B.dash.symbols?.[sym];if(!z)throw Error(`${sym}: chưa có đủ dữ liệu để phân tích.`);$("#symbol").value=sym;setText("#sparkSymbol",sym);rerender(B,sym,z);setText("#status",`${sym} · dữ liệu ${z.date||B.dash.asOf||"—"}${z.dataFreshness==="STALE_EOD"?" · cần cập nhật":""}`);history.replaceState(null,"",`?symbol=${encodeURIComponent(sym)}`)}
window.__VMEWS_RENDER_SYMBOL__=renderSymbol;
async function init(){try{const B=await loadBase();assertProduction(B);quickButtons(B);const q=new URLSearchParams(location.search).get("symbol")||"FPT";await renderSymbol(q);bindChartHover();void refreshCommunity(B);window.setInterval(()=>{if(!document.hidden)void refreshCommunity(B)},120000);$("#go").onclick=()=>renderSymbol($("#symbol").value).catch(showError);$("#symbol").addEventListener("keydown",e=>{if(e.key==="Enter")renderSymbol(e.currentTarget.value).catch(showError)});window.addEventListener("resize",()=>{if(last)draw(last.sym,last.z,last.B.dash.charts?.[last.sym]||[])})}catch(e){showError(e)}}
function showError(e){console.error(e);setText("#status",String(e?.message||e));const d=$("#decision");if(d){d.textContent="DỰ BÁO TẠM KHÓA";d.className="decision warning"}setText("#summary",String(e?.message||e))}
document.addEventListener("DOMContentLoaded",init);
})();
