(function(){'use strict';
const $=id=>document.getElementById(id), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const BASE=document.documentElement.dataset.hosting==='pages'?new URL('market/',location.href).href:'https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/';
const fmt=n=>Number.isFinite(n)?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2}).format(n):'—';
const date=s=>s&&Number.isFinite(Date.parse(s))?new Date(s).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'short'}):'chưa xác định';
const safeURL=u=>{try{const p=new URL(u);return p.protocol==='https:'&&!p.username&&!p.password&&['vnexpress.net','baodautu.vn','vietnamnet.vn','cafef.vn','vneconomy.vn'].some(h=>p.hostname===h||p.hostname.endsWith('.'+h))?p.href:'';}catch{return '';}};
let watch=[];try{const v=JSON.parse(localStorage.getItem('finquery-watchlist')||'[]');if(Array.isArray(v))watch=v.filter(s=>/^[A-Z]{3}$/.test(s));}catch{}

const state={symbol:'',companies:[],quotes:{},drivers:{symbols:{}},news:null,bars:[],sourceBars:[],interval:'day',chartType:'candles',history:null,count:120,end:0,request:0,watchOnly:false,sort:'symbol',newsMode:'company',driverOpen:'',refreshing:false,initialized:false,marketView:'price'};
const compareCache=new Map();
const companyLogoUrl=symbol=>'https://storage.googleapis.com/cdn-entrade/company/'+encodeURIComponent(symbol);
const companyLogoFallback=symbol=>'https://cdn.simplize.vn/simplizevn/logo/'+encodeURIComponent(symbol)+'.jpeg';
const companyLogoFallback2=symbol=>'https://companiesmarketcap.com/img/company-logos/64/'+encodeURIComponent(symbol)+'.VN.png';
function placeholderLogo(symbol){const label=String(symbol||'VN').slice(0,3).toUpperCase(),svg=`<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#eef6ff"/><stop offset="1" stop-color="#e8e8ff"/></linearGradient></defs><rect width="64" height="64" rx="17" fill="url(#g)"/><circle cx="49" cy="15" r="10" fill="#ffffff88"/><text x="32" y="39" text-anchor="middle" font-family="Arial,sans-serif" font-size="18" font-weight="700" fill="#315dcc">${label}</text></svg>`;return'data:image/svg+xml;charset=UTF-8,'+encodeURIComponent(svg);}
function logoHTML(symbol,name,size='sm'){return `<span class="ticker-logo ticker-logo-${size}"><img src="${companyLogoUrl(symbol)}" data-logo-stage="0" data-logo-alt="${companyLogoFallback(symbol)}" data-logo-alt2="${companyLogoFallback2(symbol)}" data-logo-placeholder="${placeholderLogo(symbol)}" alt="${esc(name||symbol)} logo" loading="lazy" decoding="async"><b>${esc(symbol)}</b></span>`;}
async function get(file){const ctl=new AbortController(),t=setTimeout(()=>ctl.abort(),15000);try{const r=await fetch(BASE+file+'?v='+Math.floor(Date.now()/60000),{signal:ctl.signal,cache:'no-cache'});if(!r.ok)throw Error('HTTP '+r.status);return await r.json();}finally{clearTimeout(t);}}
function old(s){return !s||!Number.isFinite(Date.parse(s))||Date.now()-Date.parse(s)>30*60*1000;}
function quoteTime(q){return q?.sourceTime?date(q.sourceTime)+(old(q.sourceTime)||q.status==='retained'?' · Bản gần nhất':''):q?'Nguồn chưa có giờ · Lấy '+date(q.collectedAt):'Chưa có';}
function showQuote(){const link=$('forecast-link');const url=new URL(link.href);url.searchParams.set('symbol',state.symbol);link.href=url.href;link.textContent='Xem dự báo '+state.symbol+' ↗';$('forecast-symbol').textContent=state.symbol;const nativeTitle=$('native-chart-title');if(nativeTitle)nativeTitle.textContent='Biểu đồ FinQuery · '+state.symbol;$('market-symbol').textContent=state.symbol;const q=state.quotes[state.symbol];$('watch-toggle').textContent=(watch.includes(state.symbol)?'★ Đang theo dõi':'☆ Theo dõi');$('watch-toggle').setAttribute('aria-pressed',String(watch.includes(state.symbol)));$('quote-price').textContent=q?fmt(q.price)+' đ':'Chưa có giá';$('quote-change').textContent=q?`${q.changePct>0?'+':''}${fmt(q.changePct)}%`:'—';$('quote-change').className=q?.changePct>0?'price-up':q?.changePct<0?'price-down':'price-flat';$('quote-time').textContent=q?`${q.source||'Vietcap'} · snapshot 15 phút · Lấy lúc ${date(q.collectedAt)}${q.sourceTime?' · Thời điểm nguồn '+date(q.sourceTime):' · Nguồn chưa xác định thời điểm khớp lệnh'}${old(q.sourceTime||q.collectedAt)||q.status==='retained'?' · Bản đã lưu':''}`:'Chưa tải được bảng giá. Bấm cập nhật để thử lại.';}
function factorTone(v){return v>8?'driver-positive':v<-8?'driver-negative':'driver-neutral';}
function driverSummary(d){if(!d)return'<span class="driver-missing">Đang tính…</span>';const top=d.factors?.[0];return `<button type="button" class="driver-button ${factorTone(d.score)}" data-driver="${esc(d.symbol)}" aria-expanded="${state.driverOpen===d.symbol}"><strong>${d.score>0?'+':''}${fmt(d.score)}</strong><span>${esc(top?.label||'Tín hiệu hỗn hợp')}</span></button>`;}
function driverDetail(d){if(!d)return'';const factors=(d.factors||[]).map(f=>`<div class="driver-factor"><span>${esc(f.label)} <small>trọng số ${Math.round((f.weight||0)*100)}%</small></span><b class="${factorTone(f.contribution)}">${f.contribution>0?'+':''}${fmt(f.contribution)}</b></div>`).join('');const metrics=[['Thị trường',Number.isFinite(d.marketMedianChangePct)?(d.marketMedianChangePct>0?'+':'')+fmt(d.marketMedianChangePct)+'%':'—'],['Sức mạnh tương đối',Number.isFinite(d.relativeStrengthPct)?(d.relativeStrengthPct>0?'+':'')+fmt(d.relativeStrengthPct)+'%':'—'],['KL / TB20',Number.isFinite(d.volumeRatio20)?fmt(d.volumeRatio20)+'x':'—'],['Động lượng 5P',Number.isFinite(d.momentum5dPct)?(d.momentum5dPct>0?'+':'')+fmt(d.momentum5dPct)+'%':'—'],['Biến động 20P',Number.isFinite(d.volatility20dPct)?fmt(d.volatility20dPct)+'%':'—']].map(x=>`<div><span>${x[0]}</span><b>${x[1]}</b></div>`).join('');const headlines=(d.headlines||[]).slice(0,3).map(h=>{const u=safeURL(h.url);return u?`<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(h.title)} <small>${esc(h.source||'Nguồn')}</small></a>`:'';}).join('');return `<tr class="driver-row"><td colspan="8"><div class="driver-panel"><div class="driver-panel-head"><div><strong>Phân rã biến động · ${esc(d.symbol)}</strong><p>${esc(d.summary||'')}</p></div><span>Mức xác nhận dữ liệu: ${esc(d.confidence||'—')} · ${fmt(d.confidenceScore)}/100</span></div><div class="driver-metrics">${metrics}</div><div class="driver-factors">${factors}</div>${headlines?`<div class="driver-headlines"><span>Tin liên quan gần nhất</span>${headlines}</div>`:''}</div></td></tr>`;}
function board(){let list=state.companies.filter(c=>(!state.watchOnly||watch.includes(c.symbol))&&(`${c.symbol} ${c.name}`).toLocaleLowerCase('vi').includes($('market-filter').value.toLocaleLowerCase('vi')));list.sort((a,b)=>state.sort==='change'?(state.quotes[b.symbol]?.changePct??-Infinity)-(state.quotes[a.symbol]?.changePct??-Infinity):a.symbol.localeCompare(b.symbol));$('market-count').textContent=`${list.length} / ${state.companies.length} mã`;$('market-rows').innerHTML=list.map(c=>{const q=state.quotes[c.symbol],d=state.drivers?.symbols?.[c.symbol],delta=Number.isFinite(q?.price)&&Number.isFinite(q?.reference)?q.price-q.reference:null,deltaText=Number.isFinite(delta)?`${delta>0?'+':''}${fmt(delta)} đ · ${q.changePct>0?'+':''}${fmt(q.changePct)}%`:'—';const main=`<tr${c.symbol===state.symbol?' class="selected"':''}><td><button class="star-button" data-watch="${c.symbol}" aria-label="${watch.includes(c.symbol)?'Bỏ theo dõi':'Theo dõi'} ${c.symbol}" aria-pressed="${watch.includes(c.symbol)}">${watch.includes(c.symbol)?'★':'☆'}</button></td><th><button class="ticker-link ticker-with-logo" data-market-symbol="${c.symbol}" title="${esc(c.name)}">${logoHTML(c.symbol,c.name)}<span>${c.symbol}</span></button></th><td><strong>${fmt(q?.price)}</strong></td><td>${fmt(q?.reference)}</td><td class="${q?.changePct>0?'price-up':q?.changePct<0?'price-down':'price-flat'}">${deltaText}</td><td>${fmt(q?.volume)}</td><td>${driverSummary(d)}</td><td>${quoteTime(q)}</td></tr>`;return main+(state.driverOpen===c.symbol?driverDetail(d):'');}).join('')||'<tr><td colspan="8">Chưa có mã phù hợp. Bấm ☆ để lưu doanh nghiệp quan tâm.</td></tr>';}
function toggleWatch(symbol){watch=watch.includes(symbol)?watch.filter(s=>s!==symbol):[...watch,symbol];try{localStorage.setItem('finquery-watchlist',JSON.stringify(watch));}catch{}showQuote();board();chartController.select(state.symbol,watch);}

const SECTOR_GROUPS=[
 {id:'banking',label:'Ngân hàng',symbols:['ACB','BID','CTG','EIB','HDB','LPB','MBB','MSB','OCB','SHB','SSB','STB','TCB','TPB','VCB','VIB','VPB']},
 {id:'steel',label:'Thép',symbols:['HPG','HSG','NKG','POM','GDA','SMC','TLH','TVN','VGS']},
 {id:'securities',label:'Chứng khoán',symbols:['SSI','VND','VCI','HCM','BSI','FTS','CTS','ORS','SHS','VIX']},
 {id:'real-estate',label:'Bất động sản',symbols:['VIC','VHM','VRE','NVL','PDR','DXG','KDH','NLG','BCM','KBC','SZC','DIG']},
 {id:'technology',label:'Công nghệ',symbols:['FPT','CMG','ELC','CTR']},
 {id:'retail',label:'Bán lẻ',symbols:['MWG','FRT','PNJ','DGW']},
 {id:'oil-gas',label:'Dầu khí',symbols:['GAS','PLX','PVD','PVS','BSR','OIL']},
 {id:'utilities',label:'Điện & tiện ích',symbols:['POW','REE','NT2','GEG','PC1']},
 {id:'construction',label:'Xây dựng & hạ tầng',symbols:['CTD','HBC','HHV','CII','VCG']},
 {id:'seafood',label:'Thủy sản',symbols:['VHC','ANV','FMC']},
 {id:'chemicals',label:'Hóa chất & phân bón',symbols:['DGC','CSV','DCM','DPM']},
 {id:'transport',label:'Vận tải & logistics',symbols:['GMD','HAH','VSC','VJC','HVN']},
 {id:'insurance',label:'Bảo hiểm',symbols:['BVH','MIG','BIC','PVI']},
 {id:'consumer',label:'Tiêu dùng',symbols:['VNM','SAB','MSN','QNS']}
];
const COMPARE_COLORS=['#4263eb','#0b9f8a','#f59f00','#d9485f','#7950f2','#1971c2'];
function sectorInfo(symbol){
 const configured=SECTOR_GROUPS.find(g=>g.symbols.includes(symbol));
 if(configured)return configured;
 const name=String(state.companies.find(x=>x.symbol===symbol)?.name||'');
 if(/Ngân hàng/i.test(name))return SECTOR_GROUPS.find(g=>g.id==='banking');
 if(/Chứng khoán/i.test(name))return SECTOR_GROUPS.find(g=>g.id==='securities');
 return null;
}
async function compareHistory(symbol){
 if(compareCache.has(symbol))return compareCache.get(symbol);
 const promise=get('history/'+encodeURIComponent(symbol)+'.json').then(raw=>{
  if(raw?.symbol!==symbol||!Array.isArray(raw.bars))throw Error('Invalid history '+symbol);
  return raw.bars.filter(b=>Number.isFinite(Number(b.close))&&Number(b.close)>0&&b.time).slice(-160);
 });
 compareCache.set(symbol,promise);
 try{return await promise;}catch(error){compareCache.delete(symbol);throw error;}
}
function normalizedPerformance(bars,limit=120){
 const rows=(bars||[]).slice(-limit),base=Number(rows[0]?.close);
 if(!Number.isFinite(base)||base<=0)return[];
 return rows.map(b=>({time:String(b.time),value:(Number(b.close)/base-1)*100})).filter(x=>Number.isFinite(x.value));
}
function sectorMembers(info){
 if(!info)return[];
 const available=new Set(state.companies.map(x=>x.symbol));
 const list=info.symbols.filter(s=>available.has(s));
 return list.includes(state.symbol)?list:[state.symbol,...list];
}
function svgPath(points,dateIndex,x,y){
 let d='';for(const p of points){const idx=dateIndex.get(p.time);if(idx==null)continue;const px=x(idx),py=y(p.value);d+=(d?' L ':'M ')+px.toFixed(1)+' '+py.toFixed(1);}return d;
}
function renderCompareSvg(series){
 const host=$('market-compare-chart');if(!host)return;
 const usable=series.filter(s=>s.points?.length>1);
 if(!usable.length){host.innerHTML='<div class="market-compare-empty">Chưa có đủ lịch sử giá để so sánh.</div>';return;}
 const dates=[...new Set(usable.flatMap(s=>s.points.map(p=>p.time)))].sort(),dateIndex=new Map(dates.map((d,i)=>[d,i]));
 let vals=usable.flatMap(s=>s.points.map(p=>p.value)),min=Math.min(...vals),max=Math.max(...vals);
 if(!Number.isFinite(min)||!Number.isFinite(max)){host.innerHTML='<div class="market-compare-empty">Dữ liệu so sánh chưa hợp lệ.</div>';return;}
 const pad=Math.max(2,(max-min)*.12);min-=pad;max+=pad;if(max-min<4){min-=2;max+=2;}
 const W=920,H=360,L=52,R=20,T=20,B=38,x=i=>L+(W-L-R)*(dates.length<=1?0:i/(dates.length-1)),y=v=>T+(H-T-B)*(max-v)/(max-min);
 const grid=[];for(let i=0;i<5;i++){const v=max-(max-min)*i/4,yy=y(v);grid.push('<line x1="'+L+'" y1="'+yy+'" x2="'+(W-R)+'" y2="'+yy+'" stroke="#e6ebf3" stroke-width="1"/><text x="'+(L-8)+'" y="'+(yy+4)+'" text-anchor="end" font-size="10" fill="#7c8798">'+v.toFixed(1)+'%</text>');}
 const zero=(min<=0&&max>=0)?'<line x1="'+L+'" y1="'+y(0)+'" x2="'+(W-R)+'" y2="'+y(0)+'" stroke="#aeb8c8" stroke-width="1.2" stroke-dasharray="4 4"/>':'';
 const paths=usable.map((s,i)=>'<path d="'+svgPath(s.points,dateIndex,x,y)+'" fill="none" stroke="'+(s.color||COMPARE_COLORS[i%COMPARE_COLORS.length])+'" stroke-width="'+(s.strong?3:2)+'" stroke-linejoin="round" stroke-linecap="round"/>').join('');
 const first=dates[0]||'',last=dates.at(-1)||'';
 host.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none" aria-hidden="true">'+grid.join('')+zero+paths+'<text x="'+L+'" y="'+(H-10)+'" font-size="10" fill="#7c8798">'+esc(first)+'</text><text x="'+(W-R)+'" y="'+(H-10)+'" text-anchor="end" font-size="10" fill="#7c8798">'+esc(last)+'</text></svg>';
}
function renderCompareLegend(series){
 const host=$('market-compare-legend');if(!host)return;host.innerHTML=series.map(s=>'<span><i style="background:'+esc(s.color)+'"></i><b>'+esc(s.label)+'</b><em>'+(s.points?.length?((s.points.at(-1).value>=0?'+':'')+fmt(s.points.at(-1).value)+'%'):'—')+'</em></span>').join('');
}
async function renderMarketCompare(){
 if(state.marketView==='price')return;
 const panel=$('market-compare-panel'),chart=$('market-compare-chart'),title=$('market-compare-title'),sub=$('market-compare-subtitle'),kicker=$('market-compare-kicker'),period=$('market-compare-period');
 if(!panel||!chart)return;chart.innerHTML='<div class="market-compare-loading"><span class="loading-ring"></span>Đang tải lịch sử giá để so sánh…</div>';$('market-compare-legend').innerHTML='';
 const info=sectorInfo(state.symbol);
 if(!info){title.textContent='Chưa có nhóm ngành cho '+state.symbol;sub.textContent='FinQuery chưa cấu hình nhóm so sánh cho mã này.';kicker.textContent='SO SÁNH NGÀNH';period.textContent='—';chart.innerHTML='<div class="market-compare-empty">Mã này chưa có nhóm ngành được cấu hình. Biểu đồ giá gốc vẫn sử dụng bình thường.</div>';return;}
 const members=sectorMembers(info),selected=state.symbol;
 try{
  if(state.marketView==='peers'){
   const others=members.filter(s=>s!==selected).sort((a,b)=>(state.quotes[b]?.volume||0)-(state.quotes[a]?.volume||0)).slice(0,5);
   const symbols=[selected,...others],histories=await Promise.allSettled(symbols.map(compareHistory)),series=[];
   histories.forEach((r,i)=>{if(r.status==='fulfilled'){const pts=normalizedPerformance(r.value);if(pts.length)series.push({label:symbols[i],points:pts,color:COMPARE_COLORS[i%COMPARE_COLORS.length],strong:i===0});}});
   kicker.textContent='CỔ PHIẾU CÙNG NGÀNH';title.textContent=selected+' so với các mã '+info.label;sub.textContent='So sánh hiệu suất giá chuẩn hóa với các mã cùng ngành có thanh khoản nổi bật.';period.textContent='120 phiên';renderCompareLegend(series);renderCompareSvg(series);return;
  }
  const symbols=members.slice(0,12),histories=await Promise.allSettled(symbols.map(compareHistory)),normalized=[];
  histories.forEach((r,i)=>{if(r.status==='fulfilled'){const pts=normalizedPerformance(r.value);if(pts.length)normalized.push({symbol:symbols[i],points:pts});}});
  const selectedSeries=normalized.find(x=>x.symbol===selected);
  if(!selectedSeries)throw Error('Missing selected history');
  const byDate=new Map();
  for(const row of normalized)for(const p of row.points){const arr=byDate.get(p.time)||[];arr.push(p.value);byDate.set(p.time,arr);}
  const sectorPoints=[...byDate.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([time,vals])=>({time,value:vals.reduce((a,b)=>a+b,0)/vals.length}));
  const series=[{label:selected,points:selectedSeries.points,color:COMPARE_COLORS[0],strong:true},{label:'Ngành '+info.label,points:sectorPoints,color:COMPARE_COLORS[1],strong:true}];
  kicker.textContent='CỔ PHIẾU VS NGÀNH';title.textContent=selected+' so với ngành '+info.label;sub.textContent='Chỉ số ngành = bình quân equal-weight của '+normalized.length+' mã có lịch sử giá hợp lệ.';period.textContent='120 phiên';renderCompareLegend(series);renderCompareSvg(series);
 }catch(error){title.textContent='Chưa tải được dữ liệu so sánh';sub.textContent='Biểu đồ giá chính vẫn hoạt động bình thường.';period.textContent='—';chart.innerHTML='<div class="market-compare-empty">Không tải đủ lịch sử ngành. Hãy thử lại sau.</div>';}
}
function setMarketView(view){
 state.marketView=['price','peers','sector'].includes(view)?view:'price';
 document.querySelectorAll('[data-market-view]').forEach(btn=>{const on=btn.dataset.marketView===state.marketView;btn.classList.toggle('active',on);btn.setAttribute('aria-selected',String(on));});
 const terminal=$('chart-terminal'),panel=$('market-compare-panel');if(terminal)terminal.hidden=state.marketView!=='price';if(panel)panel.hidden=state.marketView==='price';
 if(state.marketView!=='price')void renderMarketCompare();
}
const NEWS_LABELS={all:'Tin kinh tế mới nhất',finance:'Tài chính',market:'Thị trường',rates:'Lãi suất',stocks:'Chứng khoán',banking:'Ngân hàng',investment:'Đầu tư',macro:'Kinh tế vĩ mô'};
const COMPANY_NEWS_ALIASES={
 MBB:['MBB','MBBANK','MB BANK','NGÂN HÀNG QUÂN ĐỘI','NGÂN HÀNG TMCP QUÂN ĐỘI','MILITARY COMMERCIAL JOINT STOCK BANK','MB'],
 VCB:['VCB','VIETCOMBANK','NGÂN HÀNG NGOẠI THƯƠNG'],TCB:['TCB','TECHCOMBANK','NGÂN HÀNG KỸ THƯƠNG'],VPB:['VPB','VPBANK','VIỆT NAM THỊNH VƯỢNG'],CTG:['CTG','VIETINBANK','NGÂN HÀNG CÔNG THƯƠNG'],BID:['BID','BIDV','NGÂN HÀNG ĐẦU TƯ VÀ PHÁT TRIỂN'],HDB:['HDB','HDBANK'],STB:['STB','SACOMBANK'],ACB:['ACB','Á CHÂU'],FPT:['FPT','FPT CORPORATION','CÔNG TY CỔ PHẦN FPT'],VIC:['VIC','VINGROUP','TẬP ĐOÀN VINGROUP']
};
function normNewsText(value){return String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').replace(/Đ/g,'D').toLowerCase();}
function exactToken(hay,token){const escaped=String(token).replace(/[.*+?^$\{\}()|[\]\\]/g,'\\$&');return new RegExp('(^|[^a-z0-9])'+escaped+'([^a-z0-9]|$)','i').test(hay);}
function companyAliases(symbol){const company=state.companies.find(x=>x.symbol===symbol),aliases=[symbol,...(COMPANY_NEWS_ALIASES[symbol]||[])];if(company?.name)aliases.push(company.name);return [...new Set(aliases.map(normNewsText).filter(x=>x.length>=2))];}
function companyNewsScore(item,symbol=state.symbol){const title=normNewsText(item?.title),summary=normNewsText(item?.summary),aliases=companyAliases(symbol);let score=(item?.symbols||[]).includes(symbol)?1:0;for(const alias of aliases){const short=alias.length<=3,bankShort=symbol==='MBB'&&alias==='mb';const titleHit=short?exactToken(title,alias):title.includes(alias),summaryHit=short?exactToken(summary,alias):summary.includes(alias);if(titleHit){if(bankShort&&!/ngan hang|lai suat|tin dung|tien gui|bank/.test(title))continue;score=Math.max(score,bankShort?7:9);}if(summaryHit)score=Math.max(score,short?5:6);}return score;}
function strictCompanyNews(items,symbol=state.symbol,limit=50){return(items||[]).map(item=>({item,score:companyNewsScore(item,symbol)})).filter(x=>x.score>=7).sort((a,b)=>b.score-a.score||Date.parse(b.item.publishedAt)-Date.parse(a.item.publishedAt)).slice(0,limit).map(x=>x.item);}
function sectorNews(items,symbol=state.symbol,limit=40){const direct=new Set(strictCompanyNews(items,symbol,100).map(x=>x.url||x.title));return(items||[]).filter(item=>!direct.has(item.url||item.title)&&(item.topics||inferredTopics(item)).some(t=>['market','stocks','rates','banking','macro','finance'].includes(t))).sort((a,b)=>Date.parse(b.publishedAt)-Date.parse(a.publishedAt)).slice(0,limit);}
function inferredTopics(r){const s=(r.title||'').toLocaleLowerCase('vi-VN'),t=[];if(/tài chính|trái phiếu|tỷ giá|bảo hiểm|ngân sách/.test(s))t.push('finance');if(/thị trường|giá vàng|giá dầu|hàng hóa|bất động sản/.test(s))t.push('market');if(/lãi suất|tiền gửi|cho vay|tín dụng/.test(s))t.push('rates');if(/chứng khoán|cổ phiếu|vn-?index|hose|hnx|upcom|phái sinh/.test(s))t.push('stocks');if(/ngân hàng|tín dụng|tiền gửi/.test(s))t.push('banking');if(/đầu tư|fdi|giải ngân|dự án|quỹ đầu tư/.test(s))t.push('investment');if(/gdp|cpi|lạm phát|kinh tế|xuất khẩu|nhập khẩu|tăng trưởng/.test(s))t.push('macro');return t;}
function news(){
 const data=state.news,items=data?.items||[];let rows;
 if(state.newsMode==='all')rows=items.slice();
 else if(state.newsMode==='company')rows=strictCompanyNews(items,state.symbol,50);
 else rows=items.filter(r=>{const topics=Array.isArray(r.topics)&&r.topics.length?r.topics:inferredTopics(r);return topics.includes(state.newsMode);});
 rows.sort((a,b)=>Date.parse(b.publishedAt)-Date.parse(a.publishedAt));
 $('news-title').textContent=state.newsMode==='company'?'Tin doanh nghiệp · '+state.symbol:(NEWS_LABELS[state.newsMode]||'Tin kinh tế mới nhất');
 $('news-status').textContent=data?'Kiểm tra '+date(data.checkedAt)+' · '+(data.sources||[]).filter(s=>s.status==='ok').length+'/'+(data.sources||[]).length+' nguồn phản hồi · '+rows.length+' bài phù hợp'+(data.status==='retained'?' · Đang dùng tin đã lưu':''):'Chưa tải được tin tức.';
 const limit=state.newsMode==='company'?50:80;
 $('news-list').innerHTML=rows.slice(0,limit).map(r=>{const url=safeURL(r.url);return url?'<article class="news-item"><p>'+(state.newsMode==='company'?'TIN DOANH NGHIỆP · ':'')+esc(r.source)+' <span>· '+esc(date(r.publishedAt))+'</span></p><a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc(r.title)+' <span aria-hidden="true">↗</span></a></article>':'';}).join('')||(state.newsMode==='company'?'<p class="market-empty">Chưa có tin doanh nghiệp '+esc(state.symbol)+' đủ mức liên quan trong nguồn hiện tại. Có thể chọn “Ngân hàng”, “Thị trường” hoặc “Tin kinh tế” để xem bối cảnh ngành.</p>':'<p class="market-empty">Chưa tìm thấy tin phù hợp trong 30 ngày gần đây.</p>');
}
async function refresh(){if(state.refreshing)return;state.refreshing=true;$('market-refresh').disabled=true;$('market-refresh-status').textContent='Đang tải giá, hệ số và tin…';const previousNewsMax=Math.max(0,...(state.news?.items||[]).map(x=>Date.parse(x.publishedAt)||0)),results=await Promise.allSettled([get('quotes.json'),get('news.json'),get('drivers.json')]);if(results[0].status==='fulfilled'&&results[0].value.quotes){for(const [symbol,q]of Object.entries(results[0].value.quotes)){const old=state.quotes[symbol];if(!old?.sourceTime||!q.sourceTime||Date.parse(q.sourceTime)>=Date.parse(old.sourceTime))state.quotes[symbol]=q;}}if(results[1].status==='fulfilled'&&Array.isArray(results[1].value.items))state.news=results[1].value;if(results[2].status==='fulfilled'&&results[2].value.symbols)state.drivers=results[2].value;showQuote();board();news();const currentQuote=state.quotes[state.symbol];if(currentQuote)chartController.snapshot(currentQuote);if(state.initialized&&previousNewsMax){const fresh=(state.news?.items||[]).filter(x=>(Date.parse(x.publishedAt)||0)>previousNewsMax).sort((a,b)=>Date.parse(b.publishedAt)-Date.parse(a.publishedAt));const relevant=strictCompanyNews(fresh,state.symbol,1)[0];if(relevant)chartController.noteNews(relevant);}state.initialized=true;window.FinQueryAI?.sync(state.symbol);$('market-refresh-status').textContent=results.some(r=>r.status==='rejected')?'Một phần dữ liệu chưa tải được; giữ bản gần nhất nếu có.':'Đã đồng bộ snapshot, tín hiệu và tin mới nhất.';state.refreshing=false;$('market-refresh').disabled=false;}
window.FinancialMarket={select(symbol,companies){state.companies=companies;state.symbol=symbol;showQuote();board();news();chartController.select(symbol,watch);window.FinInsights?.select?.(symbol);if(state.marketView!=='price')void renderMarketCompare();window.FinQueryAI?.sync(symbol);},context(){const all=(state.news?.items||[]).slice().sort((a,b)=>Date.parse(b.publishedAt)-Date.parse(a.publishedAt)),items=strictCompanyNews(all,state.symbol,15),marketNews=sectorNews(all,state.symbol,40);return{symbol:state.symbol,quote:state.quotes[state.symbol]||null,driver:state.drivers?.symbols?.[state.symbol]||null,market:{generatedAt:state.drivers?.generatedAt||null,medianChangePct:state.drivers?.marketMedianChangePct??null},technical:chartController?.technicalContext?.()||null,news:items,sectorNews:marketNews,marketNews};},registerInsights(api){api?.attachChart?.(chartController);api?.select?.(state.symbol);},newsScore:(item,symbol)=>companyNewsScore(item,symbol||state.symbol)};
document.querySelectorAll('[data-market-view]').forEach(btn=>btn.addEventListener('click',()=>setMarketView(btn.dataset.marketView)));
$('watch-toggle').addEventListener('click',()=>toggleWatch(state.symbol));$('market-rows').addEventListener('error',e=>{const img=e.target;if(img.tagName!=='IMG'||!img.closest('.ticker-logo'))return;const stage=Number(img.dataset.logoStage||0);if(stage===0&&img.dataset.logoAlt){img.dataset.logoStage='1';img.src=img.dataset.logoAlt;return;}if(stage===1&&img.dataset.logoAlt2){img.dataset.logoStage='2';img.src=img.dataset.logoAlt2;return;}if(stage<=2&&img.dataset.logoPlaceholder){img.dataset.logoStage='3';img.src=img.dataset.logoPlaceholder;return;}img.hidden=true;},true);$('market-rows').addEventListener('click',e=>{const star=e.target.closest('[data-watch]'),ticker=e.target.closest('[data-market-symbol]'),driver=e.target.closest('[data-driver]');if(star)toggleWatch(star.dataset.watch);if(driver){state.driverOpen=state.driverOpen===driver.dataset.driver?'':driver.dataset.driver;board();return;}if(ticker){$('ticker').value=ticker.dataset.marketSymbol;$('company-form').requestSubmit();}});$('market-filter').addEventListener('input',board);$('watch-only').addEventListener('change',e=>{state.watchOnly=e.target.checked;board();});$('market-sort').addEventListener('change',e=>{state.sort=e.target.value;board();});$('market-refresh').addEventListener('click',()=>{refresh();window.FinInsights?.reload?.();if(state.symbol)chartController.load(true);});$('news-mode').addEventListener('change',e=>{state.newsMode=e.target.value;news();});
const chartController=window.FinChart.create(BASE,q=>{const previous=state.quotes[q.symbol];if(previous?.sourceTime&&Date.parse(previous.sourceTime)>Date.parse(q.sourceTime))return;state.quotes[q.symbol]={...previous,...q,changePct:Number.isFinite(q.changePct)?q.changePct:(q.reference||previous?.reference)>0?(q.price/(q.reference||previous.reference)-1)*100:null,unit:'VND',source:'WebSocket',status:'ok',collectedAt:new Date().toISOString()};showQuote();board();});
setMarketView('price');refresh();setInterval(()=>{if(!document.hidden)refresh();},60000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
})();
