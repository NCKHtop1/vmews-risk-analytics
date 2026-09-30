(function(){'use strict';
const $=id=>document.getElementById(id);
const PAGES=document.documentElement.dataset.hosting==='pages';
const MARKET_BASE=PAGES?new URL('market/',location.href).href:'https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/';
const DATA_BASE=PAGES?new URL('../data/',location.href).href:'https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/main/data/';
const state={loading:false,lastMarket:null,last:null};
const fmt=(v,d=1)=>Number.isFinite(Number(v))?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:d}).format(Number(v)):'—';
function ageMinutes(v){const t=Date.parse(v||'');if(!Number.isFinite(t))return Infinity;const a=(Date.now()-t)/60000;return a>=-5?a:Infinity;}
function vnClock(ts=Date.now()){const p=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(ts)).filter(x=>x.type!=='literal').map(x=>[x.type,x.value]));return{day:p.year+'-'+p.month+'-'+p.day,weekday:p.weekday,minutes:Number(p.hour)*60+Number(p.minute)};}
function activeSession(){const x=vnClock(),weekday=!['Sat','Sun'].includes(x.weekday);return weekday&&((x.minutes>=9*60&&x.minutes<=11*60+40)||(x.minutes>=12*60+55&&x.minutes<=15*60+15));}
function sameVnDay(v){const t=Date.parse(v||'');return Number.isFinite(t)&&vnClock(t).day===vnClock().day;}
function quantile(values,q){if(!values.length)return null;const a=[...values].sort((x,y)=>x-y),i=(a.length-1)*q,lo=Math.floor(i),hi=Math.ceil(i);return lo===hi?a[lo]:a[lo]+(a[hi]-a[lo])*(i-lo);}
async function get(url){const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),10000);try{const r=await fetch(url+(url.includes('?')?'&':'?')+'health='+Math.floor(Date.now()/60000),{cache:'no-store',signal:ctl.signal});if(!r.ok)throw Error('HTTP '+r.status);return await r.json();}finally{clearTimeout(timer);}}
function toneRank(t){return t==='bad'?3:t==='warn'?2:t==='good'?1:0;}
function card(label,value,detail,tone='neutral'){return '<div class="data-health-card '+tone+'"><span>'+label+'</span><strong>'+value+'</strong><small>'+detail+'</small></div>';}
function setStatus(tone,text){const badge=$('data-health-status');if(!badge)return;badge.className='data-health-status '+tone;badge.textContent=text;}
function render(x){
 state.last=x;const grid=$('data-health-grid'),meta=$('data-health-meta');if(!grid)return;
 const cards=[];
 cards.push(card('Giá HOSE',x.quoteCoverage+'/'+x.quoteExpected,x.sessionActive?('P50 '+fmt(x.quoteMedianAge)+'p · P95 '+fmt(x.quoteP95Age)+'p'):'Ngoài phiên · giữ snapshot cuối',x.quoteTone));
 cards.push(card('Mã đang xem',x.selectedAge===null?'—':fmt(x.selectedAge)+' phút',x.selectedFallback?'Đã dùng nguồn trực tiếp':x.selectedFresh?'Đúng nhịp nguồn':'Bản gần nhất',x.selectedTone));
 cards.push(card('Technical Scanner',x.scannerCoverage?x.scannerCoverage+'/'+x.scannerUniverse:'—',x.scannerAligned?'Đồng bộ sourceTime với giá':'Chưa đồng bộ snapshot',x.scannerTone));
 cards.push(card('Tin tức',Number.isFinite(x.newsAge)?fmt(x.newsAge)+' phút':'—',x.newsSources+' nguồn phản hồi',x.newsTone));
 cards.push(card('Evidence scanner',x.evidenceSignals?x.evidenceSignals+' rule':'—',x.evidenceReady?'Backtest lịch sử đã sẵn sàng':'Đang chờ evidence',x.evidenceTone));
 cards.push(card('Live OOS model',fmt(x.liveMatured,0)+' matured',fmt(x.livePending,0)+' pending · '+x.liveStatus,x.liveTone));
 grid.innerHTML=cards.join('');
 const worst=[x.quoteTone,x.selectedTone,x.scannerTone,x.newsTone,x.evidenceTone,x.liveTone].sort((a,b)=>toneRank(b)-toneRank(a))[0]||'neutral';
 setStatus(worst,worst==='bad'?'Cần chú ý':worst==='warn'?'Có độ trễ':'Hệ thống ổn');
 if(meta)meta.textContent='SLO intraday: xanh ≤18p · vàng 18–25p · đỏ >25p. SourceTime được ưu tiên hơn thời điểm trình duyệt tải.';
}
async function refresh(){
 if(state.loading)return;state.loading=true;setStatus('neutral','Đang kiểm tra…');
 try{
  const urls=[MARKET_BASE+'quotes.json',MARKET_BASE+'news.json',MARKET_BASE+'technical-signals.json',MARKET_BASE+'technical-evidence.json',DATA_BASE+'live-track/track-record.json'];
  const rs=await Promise.allSettled(urls.map(get));
  const quotes=rs[0].status==='fulfilled'?rs[0].value:{},news=rs[1].status==='fulfilled'?rs[1].value:{},scanner=rs[2].status==='fulfilled'?rs[2].value:{},evidence=rs[3].status==='fulfilled'?rs[3].value:{},track=rs[4].status==='fulfilled'?rs[4].value:{};
  const active=activeSession(),rows=Object.values(quotes.quotes||{}).filter(q=>q&&q.status!=='retained'&&sameVnDay(q.sourceTime||q.collectedAt));
  const ages=rows.map(q=>ageMinutes(q.sourceTime||q.collectedAt)).filter(Number.isFinite);
  const med=quantile(ages,.5),p95=quantile(ages,.95),coverage=Number(quotes.coverage||rows.length||0),expected=Number(quotes.expected||0);
  const quoteTone=coverage<expected*.9?'bad':active?(p95<=18?'good':p95<=25?'warn':'bad'):'good';
  const lm=state.lastMarket||{},selectedAge=Number.isFinite(lm.selectedAge)?lm.selectedAge:null,selectedFresh=lm.selectedFresh!==false&&selectedAge!==null;
  const selectedTone=!active?'good':selectedAge===null?'warn':selectedAge<=18?'good':selectedAge<=25?'warn':'bad';
  const scannerAligned=Boolean(scanner.sourceTime&&quotes.latestSourceTime&&String(scanner.sourceTime)===String(quotes.latestSourceTime));
  const scannerCoverage=Number(scanner.coverage||0),scannerUniverse=Number(scanner.universe||0),scannerTone=scannerUniverse&&scannerCoverage<scannerUniverse*.9?'bad':scannerAligned?'good':'warn';
  const newsAge=ageMinutes(news.checkedAt),newsOk=(news.sources||[]).filter(s=>s.status==='ok').length,newsTotal=(news.sources||[]).length;
  const newsTone=newsAge<=20?'good':newsAge<=35?'warn':'bad';
  const evidenceSignals=Object.keys(evidence.signals||{}).length,evidenceReady=evidence.status==='ok'&&evidenceSignals>0,evidenceTone=evidenceReady?'good':'warn';
  const live=track.tDayLiveTrack||{},cal=track.calibrationLiveMonitor||{},liveMatured=Number(live.maturedSignals||0),livePending=Number(live.pendingSignals||0);
  const liveStatus=liveMatured>=100?(cal.stable?'đủ mẫu · calibration ổn':'đủ mẫu · cần review'):'đang tích lũy live OOS';
  const liveTone=liveMatured>=100?(cal.stable?'good':'warn'):'warn';
  render({sessionActive:active,quoteCoverage:coverage,quoteExpected:expected,quoteMedianAge:med,quoteP95Age:p95,quoteTone,selectedAge,selectedFresh,selectedFallback:Boolean(lm.usedQuoteFallback),selectedTone,scannerCoverage,scannerUniverse,scannerAligned,scannerTone,newsAge,newsSources:newsOk+'/'+newsTotal,newsTone,evidenceSignals,evidenceReady,evidenceTone,liveMatured,livePending,liveStatus,liveTone});
 }catch(e){setStatus('bad','Không kiểm tra được');}
 finally{state.loading=false;}
}
document.addEventListener('finquery:market-refresh',e=>{state.lastMarket=e.detail||null;refresh();});
$('data-health-refresh')?.addEventListener('click',refresh);
refresh();setInterval(()=>{if(!document.hidden)refresh();},60000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
window.FinDataHealth={refresh,context:()=>state.last};
})();