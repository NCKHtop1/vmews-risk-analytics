(function(){'use strict';
const $=id=>document.getElementById(id);
const DATA_BASE=new URL(document.currentScript.dataset.base||'../data/',document.currentScript.src||location.href).href;
const BOOT=JSON.parse(document.getElementById('financial-bootstrap')?.textContent||'{}');
const LIVE_BASE=document.documentElement.dataset.hosting==='pages'?DATA_BASE:'https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-report-data/data/';
const MARKET_BASE=document.documentElement.dataset.hosting==='pages'?new URL('market/',location.href).href:'https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/';
const SITE_ACCESS_HASH='0a0667865bc17f9d624bcf11088057bbab46336e7dae65f3d5366f4f7a18333e';
const TERM_INFO={
 'risk-score':{title:'Thang điểm rủi ro',html:'<ul><li><b>0–69,9:</b> Bình thường.</li><li><b>70–84,9:</b> Cần theo dõi.</li><li><b>85–94,9:</b> Cao.</li><li><b>95–100:</b> Rất cao.</li></ul><p><b>Trọng số:</b> độ rộng thị trường 30% · biến động bất thường 20% · thanh khoản & áp lực bán 20% · đồng biến giữa các ngành 20% · tập trung khi thị trường suy yếu 10%.</p><p>Điểm được chuẩn hóa theo lịch sử; dữ liệu trong phiên được điều chỉnh theo thời gian giao dịch trước khi so sánh.</p>'},
 'technical-signals':{title:'Cách đọc nhanh',html:'<ul><li><b>Xu hướng:</b> giá đang đi lên hay đi xuống.</li><li><b>Động lượng:</b> lực tăng/giảm đang mạnh hay yếu.</li><li><b>Thanh khoản:</b> giao dịch nhiều hay ít hơn bình quân.</li><li><b>Dòng tiền:</b> bên mua hay bên bán đang chiếm ưu thế.</li></ul><p class="term-info-note">Volume cao chỉ cho thấy giao dịch sôi động hơn. Muốn nói tiền vào hay ra cần xem thêm CMF, MFI và OBV.</p>'},
 'volume-ratio':{title:'KL/TB20',html:'<ul><li><b>≥ 1,5x:</b> xác nhận mạnh.</li><li><b>1,2–1,5x:</b> xác nhận khá.</li><li><b>1,05–1,2x:</b> cải thiện nhẹ.</li><li><b>0,9–1,05x:</b> gần mức bình quân.</li><li><b>&lt; 0,9x:</b> thanh khoản yếu dần.</li></ul><p class="term-info-note">KL/TB20 chỉ nói mức giao dịch so với 20 phiên gần nhất, không tự nói tiền đang vào hay ra.</p>'},
 'scanner-bias':{title:'Bias & Rule priority',html:'<p><b>Bias:</b> tín hiệu hiện đang nghiêng tăng, giảm hay trung tính.</p><p><b>Rule priority:</b> điểm để xếp mã nào nên xem trước. Điểm cao không có nghĩa là xác suất thắng cao.</p>'},
 'strategy-builder':{title:'Cách dùng Strategy Lab',html:'<ol><li>Kéo hoặc bấm một chỉ báo trong <b>TA Library</b> để đưa vào vùng chiến lược.</li><li>Chọn điều kiện cho từng chỉ báo: lớn hơn, nhỏ hơn, cắt lên, cắt xuống…</li><li>Chọn <b>AND</b> nếu cần tất cả điều kiện cùng đúng; chọn <b>OR</b> nếu chỉ cần một điều kiện đúng.</li><li>Chọn phạm vi quét rồi bấm <b>Quét mã</b>.</li><li>Nếu muốn theo dõi tiếp, bấm <b>Lưu strategy + alert</b>.</li></ol><p class="term-info-note">Muốn làm nhanh có thể chọn một mẫu có sẵn như MACD + RSI, EMA Trend + ADX hoặc Breakout + Volume.</p>'},
 'scanner-guide':{title:'Cách dùng Technical Scanner',html:'<ol><li>Chọn <b>Phạm vi</b> muốn quét.</li><li>Dùng các nút MACD, RSI hoặc Volume để lọc tín hiệu.</li><li>Nhìn <b>Bias</b>, RSI và KL/TB20 để biết tín hiệu có được xác nhận thêm hay không.</li><li>Bấm mã cổ phiếu để mở và xem chart chi tiết.</li></ol>'},
 'universe-tiers':{title:'Core · Liquid · Discovery',html:'<p><b>Core:</b> nhóm mã chính được theo dõi đầy đủ.</p><p><b>Liquid:</b> nhóm ngoài Core nhưng thanh khoản đủ để cập nhật trong phiên.</p><p><b>Discovery:</b> nhóm mở rộng, chủ yếu dùng dữ liệu cuối ngày khi chưa đạt điều kiện cập nhật trong phiên.</p>'},
 'market-driver':{title:'Động lực / hệ số',html:'<p>Điểm này gom các yếu tố đang tác động lên biến động giá, như sức mạnh so với thị trường, thanh khoản, động lượng và tin gần nhất.</p><p class="term-info-note">Điểm cao hoặc thấp chỉ giúp xếp mức đáng chú ý, không phải xác suất tăng/giảm.</p>'},
 'broker-consensus':{title:'Giá mục tiêu đồng thuận',html:'<p>Lấy giá mục tiêu gần nhất của từng CTCK rồi dùng <b>trung vị</b> làm mức đồng thuận.</p><p>Vùng mục tiêu là khoảng thấp nhất–cao nhất trong các báo cáo đang có.</p><p class="term-info-note">Đây là quan điểm của các CTCK, không phải giá mục tiêu do FinQuery tự đưa ra.</p>'}
};
async function siteDigest(text){const buf=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));return[...new Uint8Array(buf)].map(b=>b.toString(16).padStart(2,'0')).join('');}
function setSiteAccess(unlocked){
 document.body.classList.toggle('site-locked',!unlocked);
 const form=$('site-unlock-form'),error=$('site-access-error');
 if(form)form.hidden=unlocked;
 if(error&&unlocked)error.textContent='';
 if(!unlocked)setTimeout(()=>$('site-access-code')?.focus(),0);
 if(unlocked){
  if(location.hash==='#risk-monitor')window.FinPlatformViews?.openRisk?.();
  else if(location.hash==='#strategy-builder')window.FinPlatformViews?.openStrategy?.();
 }
}
async function unlockSite(code){
 if(await siteDigest(String(code||'').trim())!==SITE_ACCESS_HASH){const error=$('site-access-error');if(error)error.textContent='Mã truy cập không đúng.';return false;}
 sessionStorage.setItem('finquery-site-access','1');setSiteAccess(true);return true;
}
function closeTermInfo(){
 const pop=$('term-info-popover');if(pop)pop.hidden=true;
 document.querySelectorAll('[data-info-key][aria-expanded=true]').forEach(b=>b.setAttribute('aria-expanded','false'));
}
function openTermInfo(button){
 const item=TERM_INFO[button?.dataset?.infoKey];const pop=$('term-info-popover');if(!item||!pop)return;
 $('term-info-title').textContent=item.title;$('term-info-body').innerHTML=item.html;
 document.querySelectorAll('[data-info-key]').forEach(b=>b.setAttribute('aria-expanded',String(b===button)));
 pop.hidden=false;pop.style.left='12px';pop.style.top='12px';
 const rect=button.getBoundingClientRect(),width=Math.min(370,window.innerWidth-24),left=Math.max(12,Math.min(window.innerWidth-width-12,rect.right-width)),height=pop.offsetHeight,below=rect.bottom+8,top=below+height<=window.innerHeight-12?below:Math.max(12,rect.top-height-8);
 pop.style.left=left+'px';pop.style.top=top+'px';
}
setSiteAccess(sessionStorage.getItem('finquery-site-access')==='1');
$('site-unlock-form')?.addEventListener('submit',e=>{e.preventDefault();unlockSite($('site-access-code')?.value);});
$('term-info-close')?.addEventListener('click',closeTermInfo);
document.addEventListener('click',e=>{const button=e.target.closest?.('[data-info-key]');if(button){e.preventDefault();e.stopPropagation();const pop=$('term-info-popover');if(!pop.hidden&&button.getAttribute('aria-expanded')==='true')closeTermInfo();else openTermInfo(button);return;}const pop=$('term-info-popover');if(pop&&!pop.hidden&&!pop.contains(e.target))closeTermInfo();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeTermInfo();});
const state={bundle:null,data:null,companies:[],years:[],reports:[],active:'balance_sheet',chartMetric:'profit',overviewPeriod:null,overviewCompare:null,loading:false,controller:null,mode:new URLSearchParams(location.search).get('mode')==='year'?'year':'quarter',fallback:false};
const names={balance_sheet:'Cân đối kế toán',income_statement:'Kết quả kinh doanh',cash_flow:'Lưu chuyển tiền tệ',ratios:'Chỉ số từ nguồn',derived_ratios:'Chỉ số tính từ BCTC',notes:'Thuyết minh',off_balance:'Ngoại bảng'};
const esc=s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const nf=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2});
const fmt=v=>v==null?'':v===0?'–':v<0?`(${nf.format(-v)})`:nf.format(v);
const label=p=>String(p).includes('-Q')?'Q'+String(p).at(-1)+'/'+String(p).slice(0,4):String(p);
const sorted=a=>[...new Set(a)].sort((a,b)=>String(a).localeCompare(String(b)));
const liveUrl=file=>LIVE_BASE+file+'?v='+Math.floor(Date.now()/300000);
const companyLogoUrl=symbol=>'https://storage.googleapis.com/cdn-entrade/company/'+encodeURIComponent(symbol);
const companyLogoFallback=symbol=>'https://cdn.simplize.vn/simplizevn/logo/'+encodeURIComponent(symbol)+'.jpeg';
const companyLogoFallback2=symbol=>'https://companiesmarketcap.com/img/company-logos/64/'+encodeURIComponent(symbol)+'.VN.png';
function placeholderLogo(symbol){const label=String(symbol||'VN').slice(0,3).toUpperCase(),svg=`<svg xmlns="http://www.w3.org/2000/svg" width="72" height="72"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#eff7ff"/><stop offset="1" stop-color="#ebe9ff"/></linearGradient></defs><rect width="72" height="72" rx="20" fill="url(#g)"/><circle cx="55" cy="16" r="11" fill="#ffffffaa"/><text x="36" y="44" text-anchor="middle" font-family="Arial,sans-serif" font-size="20" font-weight="700" fill="#315dcc">${label}</text></svg>`;return'data:image/svg+xml;charset=UTF-8,'+encodeURIComponent(svg);}
function syncCompanyIdentity(symbol,name='',exchange='HOSE'){
 const img=$('company-logo'),fallback=$('company-logo-fallback'),meta=$('company-meta');
 if(fallback){fallback.textContent=symbol;fallback.hidden=true;}
 if(img){img.alt=(name||symbol)+' logo';img.hidden=false;img.dataset.symbol=symbol;img.dataset.logoStage='0';img.dataset.logoAlt=companyLogoFallback(symbol);img.dataset.logoAlt2=companyLogoFallback2(symbol);img.dataset.logoPlaceholder=placeholderLogo(symbol);img.src=companyLogoUrl(symbol);}
 if(meta)meta.textContent=(exchange||'HOSE')+' · VN100 · Dữ liệu tài chính & thị trường';
}
async function json(url,signal,timeout=12000){const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),timeout);const abort=()=>ctl.abort();signal?.addEventListener('abort',abort,{once:true});try{const r=await fetch(url,{signal:ctl.signal,cache:'no-cache'});if(!r.ok)throw Error('Dữ liệu tạm thời chưa tải được. Vui lòng thử lại.');return await r.json();}finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}}
async function marketJson(file,timeout=8000){return window.FinMarketData.get(file,{timeout});}
function watchChange(value){const n=Number(value);return Number.isFinite(n)?(n>0?'+':'')+n.toFixed(2)+'%':'—';}
function watchMove(row){if(row?.isNew)return'<em class="watch-new">MỚI</em>';const n=Number(row?.rankChange);if(n>0)return'<em class="watch-up">↑'+Math.abs(n)+'</em>';if(n<0)return'<em class="watch-down">↓'+Math.abs(n)+'</em>';return'<em class="watch-flat">•</em>';}
function vnMarketPhase(ts=Date.now()){const d=new Date(ts),p=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(d).filter(x=>x.type!=='literal').map(x=>[x.type,x.value])),minutes=Number(p.hour)*60+Number(p.minute);if(['Sat','Sun'].includes(p.weekday))return'CLOSED';if(minutes<9*60)return'PREOPEN';if(minutes<=11*60+30)return'MORNING';if(minutes<13*60)return'LUNCH';if(minutes<=14*60+45)return'AFTERNOON';return'CLOSED';}
function vnMarketLive(){const phase=vnMarketPhase();return phase==='MORNING'||phase==='AFTERNOON';}
function renderTodayWatch(data){
 const box=$('quick-tickers'),track=$('quick-tickers-track'),status=$('today-watch-status'),label=$('today-watch-label');if(!box||!track)return;
 const now=Date.now(),sourceTime=Date.parse(data?.sourceTime||''),checkedAt=Date.parse(data?.checkedAt||''),futureSource=Number.isFinite(sourceTime)&&sourceTime>now+5*60*1000,futureCheck=Number.isFinite(checkedAt)&&checkedAt>now+5*60*1000;
 const vnDay=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 const futureDate=Boolean(data?.sourceDate&&data.sourceDate>vnDay),invalidFuture=futureSource||futureCheck||futureDate;
 const items=!invalidFuture&&Array.isArray(data?.items)?data.items.filter(x=>state.companies.some(c=>c.symbol===x.symbol)).slice(0,8):[];
 const priorSession=Boolean(data?.sourceDate&&data.sourceDate<vnDay);if(label){label.hidden=!invalidFuture&&priorSession;label.textContent=invalidFuture?'DỮ LIỆU CHƯA HỢP LỆ':'ĐÁNG XEM HÔM NAY';}
 const live=vnMarketLive(),stale=live&&(!Number.isFinite(checkedAt)||now-checkedAt>30*60000),phase=vnMarketPhase();
 if(status){const mode=invalidFuture?'CHƯA LIVE':live?(stale?'ĐANG ĐỒNG BỘ':'TRONG PHIÊN'):(phase==='LUNCH'?'CHỐT PHIÊN SÁNG':'CHỐT PHIÊN');status.textContent=mode+(Number.isFinite(checkedAt)?' · '+new Date(checkedAt).toLocaleTimeString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit'}):'');}
 if(invalidFuture){track.classList.remove('is-running');track.innerHTML='<span class="quick-tickers-loading">Snapshot nguồn có thời gian chưa hợp lệ; chờ dữ liệu phiên thực.</span>';return;}
 if(!items.length){track.classList.remove('is-running');track.innerHTML='<span class="quick-tickers-loading">Chưa có tín hiệu đủ mạnh.</span>';return;}
 const rowHTML=row=>{const reasons=(row.reasons||[]).join(' · '),score=Number(row.score),title=[reasons,Number.isFinite(score)?'Điểm theo dõi '+score+'/100':''].filter(Boolean).join(' · '),chg=Number(row.changePct),cls=Number.isFinite(chg)?(chg>0?'positive':chg<0?'negative':'neutral'):'neutral';return'<button type="button" class="quick-watch-button '+cls+'" data-symbol="'+esc(row.symbol)+'" title="'+esc(title)+'"><strong>'+esc(row.symbol)+'</strong><span>'+esc(watchChange(chg))+'</span>'+watchMove(row)+'</button>';};
 const pieces=items.map(rowHTML);track.innerHTML=(pieces.length>3?pieces.concat(pieces):pieces).join('');track.classList.toggle('is-running',pieces.length>3);
}
async function loadTodayWatch(){try{renderTodayWatch(await marketJson('watch-today.json'));}catch{const track=$('quick-tickers-track'),status=$('today-watch-status');if(status)status.textContent='TRONG PHIÊN';if(track){track.classList.remove('is-running');track.innerHTML='<span class="quick-tickers-loading">Đang chờ snapshot tín hiệu.</span>';}}}
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
 if(!state.companies.some(c=>c.symbol===symbol)){syncCompanyIdentity(symbol,'','');state.controller?.abort();state.bundle=null;state.data=null;state.years=[];state.reports=[];state.loading=false;$('report-options').replaceChildren();$('year-options').replaceChildren();$('availability').textContent='Hãy chọn một doanh nghiệp VN100.';$('data-state').textContent='Mã ngoài VN100';$('preview-title').textContent=symbol;$('company-name').textContent='';$('updated-at').textContent='—';$('refresh-data').disabled=false;renderPreview();error('Trang này hỗ trợ các doanh nghiệp thuộc VN100. Hãy chọn một mã trong danh sách.');return;}
 window.FinancialMarket?.select(symbol,state.companies);
 window.dispatchEvent(new CustomEvent('finquery:symbol-change',{detail:{symbol}}));
 state.controller?.abort();const ctl=new AbortController();state.controller=ctl;state.loading=true;state.bundle=null;state.data=null;state.years=[];state.reports=[];state.overviewPeriod=null;state.overviewCompare=null;$('ticker').value=symbol;error('');$('download').disabled=true;$('refresh-data').disabled=true;$('data-state').className='status-badge';$('data-state').textContent='Đang tải';$('availability').textContent='Đang kiểm tra kỳ có dữ liệu…';$('report-options').replaceChildren();$('year-options').replaceChildren();$('report-tabs').replaceChildren();$('preview-title').innerHTML=`${esc(symbol)} <span>/ Báo cáo tài chính</span>`;$('company-name').textContent=match?.name||symbol;syncCompanyIdentity(symbol,match?.name||symbol,match?.exchange||'HOSE');$('table-container').innerHTML='<div class="empty-state"><span class="loading-ring"></span><h3>Đang tải báo cáo</h3><p></p></div>';
 FinancialDashboard.render(null,[]);
 try{
  let d;state.fallback=false;
  try{d=checkData(await json(liveUrl(symbol+'.json'),ctl.signal),symbol);}
  catch(e){if(ctl.signal.aborted)throw e;state.fallback=true;d=BOOT.datasets?.[symbol]?structuredClone(BOOT.datasets[symbol]):await json(DATA_BASE+symbol+'.json',ctl.signal);d=checkData(d,symbol);}
  if(ctl.signal.aborted)return;state.bundle=d;state.active='balance_sheet';$('company-name').textContent=d.name||match?.name||symbol;syncCompanyIdentity(symbol,d.name||match?.name||symbol,d.exchange||match?.exchange||'HOSE');$('company-description').textContent='VN100 · '+(d.exchange||match?.exchange||'HOSE');document.querySelectorAll('[data-symbol]').forEach(b=>b.classList.toggle('active',b.dataset.symbol===symbol));
  setMode(state.mode);
 }catch(e){if(ctl.signal.aborted)return;error(`${symbol} chưa tải được báo cáo trong lần này. Hãy bấm Làm mới để thử lại.`);$('data-state').textContent='Chưa tải được';$('availability').textContent='Chưa mở lựa chọn kỳ cho mã này.';$('table-container').innerHTML='<div class="empty-state"><h3>Chưa có báo cáo để tải</h3><p>Thử tải lại hoặc chọn doanh nghiệp khác.</p></div>';$('row-count').textContent='0 chỉ tiêu';$('updated-at').textContent='—';$('summary').textContent='Chưa có báo cáo';}
 finally{if(!ctl.signal.aborted){state.loading=false;$('refresh-data').disabled=false;if(state.data)update();}}
}
function download(){if(!state.data||!state.years.length||!state.reports.length)return;try{const bytes=FinancialXlsx.workbook(state.data,state.years,state.reports);const blob=new Blob([bytes],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});const link=document.createElement('a'),url=URL.createObjectURL(blob);link.href=url;link.download=`${state.data.symbol}_BCTC_${state.years.join('_')}.xlsx`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);$('download-status').textContent='Đã tạo file Excel.';}catch(e){error(e.message);}}
$('company-logo')?.addEventListener('load',()=>{const f=$('company-logo-fallback');if(f)f.hidden=true;});
$('company-logo')?.addEventListener('error',e=>{const img=e.currentTarget,stage=Number(img.dataset.logoStage||0);if(stage===0&&img.dataset.logoAlt){img.dataset.logoStage='1';img.src=img.dataset.logoAlt;return;}if(stage===1&&img.dataset.logoAlt2){img.dataset.logoStage='2';img.src=img.dataset.logoAlt2;return;}if(stage<=2&&img.dataset.logoPlaceholder){img.dataset.logoStage='3';img.src=img.dataset.logoPlaceholder;return;}img.hidden=true;const f=$('company-logo-fallback');if(f)f.hidden=false;});
$('company-form').addEventListener('submit',e=>{e.preventDefault();loadCompany($('ticker').value);});$('ticker').addEventListener('change',()=>loadCompany($('ticker').value));$('quick-tickers')?.addEventListener('click',e=>{const b=e.target.closest('button[data-symbol]');if(b)loadCompany(b.dataset.symbol);});
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
function normCompanyLookup(value){return String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').replace(/Đ/g,'D').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();}
function resolveCompanySymbol(value){
 const raw=String(value||'').trim();if(!raw)return'';
 const upper=raw.toUpperCase(),exact=state.companies.find(c=>c.symbol===upper||String(c.name||'').toLowerCase()===raw.toLowerCase());if(exact)return exact.symbol;
 const tokens=upper.match(/(^|[^A-Z0-9])([A-Z]{3})(?=[^A-Z0-9]|$)/g)||[];
 for(const token of tokens){const symbol=token.replace(/[^A-Z]/g,'');const hit=state.companies.find(c=>c.symbol===symbol);if(hit)return hit.symbol;}
 const normalized=normCompanyLookup(raw);
 const byName=state.companies.find(c=>{const name=normCompanyLookup(c.name||'');return name.length>=6&&normalized.includes(name);});
 return byName?.symbol||'';
}
function reportContextRaw(){if(!state.bundle&&!state.data)return null;return{symbol:state.bundle?.symbol||state.data?.symbol,name:state.bundle?.name||state.data?.name||'',mode:state.mode,updatedAt:state.data?.updatedAt||state.bundle?.updatedAt||null,selectedPeriods:[...state.years],data:state.data,annual:state.bundle||null,quarterly:state.bundle?.quarterly||null};}
window.FinancialReportContext={
 raw:reportContextRaw,
 companies(){return state.companies.map(c=>({symbol:c.symbol,name:c.name,exchange:c.exchange||'HOSE'}));},
 resolveSymbol:resolveCompanySymbol,
 async select(value){
  const symbol=resolveCompanySymbol(value)||String(value||'').trim().toUpperCase();if(!symbol)return null;
  const current=reportContextRaw();if(current?.symbol===symbol)return current;
  await loadCompany(symbol);return reportContextRaw();
 }
};
async function init(){
 try{state.companies=BOOT.companies||await json(DATA_BASE+'companies.json',null);companyOptions();$('company-description').textContent='100 doanh nghiệp thuộc VN100.';}catch{error('Chưa tải được danh sách VN100. Vui lòng tải lại trang.');return;}
 loadTodayWatch();setInterval(()=>{if(!document.hidden)loadTodayWatch();},60000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)loadTodayWatch();});window.addEventListener('online',loadTodayWatch);
 // Membership updates do not block a company request, and a failed manifest
 // never disables live financial data fetching.
 json(liveUrl('companies.json'),null,6000).then(list=>{if(Array.isArray(list)&&new Set(list.map(c=>c.symbol)).size===100){state.companies=list;companyOptions();}}).catch(()=>{});
 await loadCompany(new URLSearchParams(location.search).get('symbol')||'MBB');registerTools();
}
function registerTools(){const context=document.modelContext;if(!context?.registerTool)return;const life=new AbortController();context.registerTool({name:'select_financial_report',title:'Chọn báo cáo tài chính',description:'Chọn doanh nghiệp VN100, năm hoặc quý có dữ liệu và cập nhật bảng xem trước.',inputSchema:{type:'object',properties:{symbol:{type:'string'},mode:{type:'string',enum:['year','quarter']},periods:{type:'array',items:{type:['string','integer']},minItems:1}},required:['symbol'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:true},async execute(input){if(!input||typeof input.symbol!=='string')throw Error('Mã không hợp lệ');await loadCompany(input.symbol);if(!state.bundle)throw Error('Chưa có báo cáo');if(input.mode)setMode(input.mode);if(input.periods){if(!Array.isArray(input.periods)||!input.periods.length||input.periods.some(p=>!eligible().includes(p)))throw Error('Kỳ không có dữ liệu');state.years=sorted(input.periods);update();}return{symbol:state.bundle.symbol,mode:state.mode,periods:state.years,reports:state.reports};}},{signal:life.signal});window.addEventListener('pagehide',()=>life.abort(),{once:true});}
init();
})();


