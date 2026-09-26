(function(){'use strict';
const configURL=new URL(document.currentScript?.dataset.config||'chart-config.json',document.currentScript?.src||location.href).href;
const M=window.FinChartMath,L=window.LightweightCharts,$=id=>document.getElementById(id);
const fmt=n=>Number.isFinite(n)?n.toLocaleString('vi-VN',{maximumFractionDigits:2}):'—';
const stamp=t=>new Date(t).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'});
const timeLabel=t=>typeof t==='number'?new Date(t*1000).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):typeof t==='string'?t:`${t.year}-${String(t.month).padStart(2,'0')}-${String(t.day).padStart(2,'0')}`;
const defaults={sma:20,ema:20,wma:20,vwma:20,rsi:14,fast:12,slow:26,signal:9,bb:20,deviation:2,vma:20,atr:14,adx:14,stoch:14,stochSignal:3,cci:20,roc:10,willr:14,mfi:14,cmf:20,supertrend:10,supertrendFactor:3};
class ChartController{
 constructor(base,onQuote){this.base=base;this.onQuote=onQuote;this.cache=new Map();this.params={...defaults};this.symbol='';this.tf=$('chart-interval')?.value||'1d';this.type='candles';this.bars=[];this.baseBars=[];this.values=[];this.series={};this.watch=[];this.generation=0;this.retries=0;this.stopped=false;this.buffer=[];this.signalEvents=[];this.signalCooldown=new Map();this.lastQuote=null;this.lastSnapshotSource='';
 this.chart=L.createChart($('price-chart'),{autoSize:true,height:540,layout:{background:{type:'solid',color:'#ffffff'},textColor:'#65728b',fontFamily:'Arial',attributionLogo:true},grid:{vertLines:{color:'#f2f4f8'},horzLines:{color:'#edf0f6'}},rightPriceScale:{borderColor:'#e5eaf3'},timeScale:{borderColor:'#e5eaf3',timeVisible:false,rightOffset:5,lockVisibleTimeRangeOnResize:true},crosshair:{mode:L.CrosshairMode.Normal},localization:{locale:'vi-VN',timeFormatter:timeLabel}});
 this.chart.subscribeCrosshairMove(e=>{const b=e.seriesData.get(this.series.price);if(b)this.readout({...b,volume:e.seriesData.get(this.series.volume)?.value});else this.readout(this.bars.at(-1));});
 this.controls();this.configPromise=this.config();window.addEventListener('pagehide',()=>this.close());window.addEventListener('pageshow',e=>{if(e.persisted){this.stopped=false;this.connect();}});
 window.addEventListener('online',()=>this.connect());
 }
 async config(){try{const r=await fetch(configURL,{cache:'no-cache',signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error();this.options=await r.json();}catch{this.options={};}this.connect();}
 status(text){const node=$('chart-stream-status');node.textContent=text;node.hidden=!text;}
 controls(){
 $('chart-interval').addEventListener('change',e=>{this.tf=e.target.value;const period=$('chart-period');if(M.intraday(this.tf)&&Number(period.value)!==0&&Number(period.value)>=12)period.value='3';if(M.intraday(this.tf)&&period.value==='0')period.value='3';this.load();});
 $('chart-type').addEventListener('change',e=>{this.type=e.target.value;this.rebuild(true);});
 $('chart-period').addEventListener('change',e=>{const months=Number(e.target.value);if(M.intraday(this.tf)&&(!months||months>=12)){this.tf='1d';$('chart-interval').value='1d';this.load();return;}this.range();});
 $('chart-zoom-in').addEventListener('click',()=>this.zoom(.75));$('chart-zoom-out').addEventListener('click',()=>this.zoom(1.3));
 $('chart-fit').addEventListener('click',()=>this.chart.timeScale().fitContent());
 $('chart-fullscreen').addEventListener('click',async()=>{const terminal=$('chart-terminal');if(terminal.classList.contains('chart-expanded')){terminal.classList.remove('chart-expanded');$('chart-fullscreen').textContent='Toàn màn hình';return;}try{if(document.fullscreenElement)await document.exitFullscreen();else await terminal.requestFullscreen();}catch{terminal.classList.add('chart-expanded');$('chart-fullscreen').textContent='Thoát toàn màn hình';}});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('chart-terminal').classList.contains('chart-expanded')){$('chart-terminal').classList.remove('chart-expanded');$('chart-fullscreen').textContent='Toàn màn hình';}});
 document.addEventListener('fullscreenchange',()=>{$('chart-fullscreen').textContent=document.fullscreenElement?'Thoát toàn màn hình':'Toàn màn hình';});
 const dialog=$('chart-indicators');$('indicator-open')?.addEventListener('click',()=>{this.syncIndicatorSettings();dialog.showModal();$('indicator-search')?.focus();});$('indicator-close')?.addEventListener('click',()=>dialog.close());dialog?.addEventListener('click',e=>{if(e.target===dialog)dialog.close();});$('indicator-search')?.addEventListener('input',e=>{const q=String(e.target.value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();(document.querySelectorAll?.('.indicator-list-item')||[]).forEach(row=>row.hidden=q&&!String(row.dataset.indicatorName||'').includes(q));});
 dialog.addEventListener('change',e=>{if(e.target.type==='number'){const key=e.target.dataset.param,n=Number(e.target.value),min=Number(e.target.min||0),max=Number(e.target.max||1e9),step=Number(e.target.step||1);const integer=step>=1;if(!Number.isFinite(n)||n<min||n>max||(integer&&!Number.isInteger(n))){e.target.value=this.params[key];return;}const next={...this.params,[key]:n};if(next.fast>=next.slow){e.target.value=this.params[key];$('chart-indicator-error').textContent='MACD: chu kỳ nhanh phải nhỏ hơn chu kỳ chậm.';return;}this.params=next;}$('chart-indicator-error').textContent='';this.syncIndicatorSettings();this.values=M.indicators(this.bars,this.params);this.rebuild(true);});
 this.syncIndicatorSettings();
 }
 select(symbol,watch=[]){this.watch=[...new Set([symbol,...watch])].filter(s=>/^[A-Z]{3}$/.test(s));if(this.symbol!==symbol){this.symbol=symbol;this.signalEvents=[];this.signalCooldown.clear();this.lastQuote=null;this.lastSnapshotSource='';this.renderSignals();this.load();}else this.subscribe();}
 async load(force=false){const generation=++this.generation;this.abort?.abort();this.abort=new AbortController();const controller=this.abort;this.loading=true;this.buffer=[];const symbol=this.symbol,baseTF=M.intraday(this.tf)?'1m':'1d',key=symbol+':'+baseTF;
 $('chart-status').textContent='Đang tải lịch sử '+symbol+'…';this.bars=[];this.baseBars=[];this.values=[];this.rebuild(false);this.subscribe();await this.configPromise;if(generation!==this.generation)return;
 try{let data=this.cache.get(key);if(force||!data||Date.now()-data.cachedAt>300000){const url=this.options?.historyBase?new URL(`history?symbol=${symbol}&interval=${baseTF}`,this.options.historyBase).href:this.base+(baseTF==='1m'?'intraday/':'history/')+symbol+'.json';const r=await fetch(url,{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(15000)]),cache:'no-cache'});if(!r.ok)throw Error('HTTP '+r.status);const raw=await r.json();if(raw.symbol!==symbol||raw.unit!=='VND'||!Array.isArray(raw.bars))throw Error('Invalid history');data={...raw,bars:M.cleanBars(raw.bars,baseTF==='1m'),cachedAt:Date.now()};if(!data.bars.length)throw Error('Empty');this.cache.set(key,data);if(this.cache.size>24)this.cache.delete(this.cache.keys().next().value);}
 if(generation!==this.generation)return;this.baseBars=data.bars.map(b=>({...b}));this.bars=M.aggregate(this.baseBars,this.tf);this.values=M.indicators(this.bars,this.params);this.loading=false;this.rebuild(false);this.range();this.evaluateSignals(false);$('chart-status').textContent=`${data.source||'Vietcap'} · ${baseTF==='1m'?'Lịch sử nến phút':'Lịch sử nến ngày'} · Lấy lúc ${stamp(data.collectedAt)}${data.status==='retained'?' · Bản đã lưu':''}. Nến cuối có thể chưa hoàn tất.`;
 for(const message of this.buffer)this.candle(message);this.buffer=[];
 }catch(e){if(generation!==this.generation||e.name==='AbortError')return;this.loading=false;if(baseTF==='1m'){this.tf='1d';$('chart-interval').value='1d';$('chart-status').textContent='Chưa có nến phút cho '+symbol+'; đang chuyển sang dữ liệu ngày.';return this.load(force);}$('chart-status').textContent='Không tải được lịch sử. Bấm Cập nhật để thử lại.';}
 }
 enabled(name){return !!$('ind-'+name)?.checked;}
 rebuild(keep){const range=keep?this.chart.timeScale().getVisibleLogicalRange():null;for(const s of Object.values(this.series))this.chart.removeSeries(s);this.series={};
 const kind=this.type==='line'?L.LineSeries:this.type==='area'?L.AreaSeries:L.CandlestickSeries;
 this.series.price=this.chart.addSeries(kind,{upColor:'#089981',downColor:'#f23645',wickUpColor:'#089981',wickDownColor:'#f23645',borderVisible:false,color:'#4564cc',lineColor:'#4564cc',topColor:'#4564cc50',bottomColor:'#4564cc05',priceFormat:{type:'price',precision:0,minMove:1}},0);
 let pane=0;const line=(key,color,index=0)=>this.series[key]=this.chart.addSeries(L.LineSeries,{color,lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false},index);const guides=(series,levels)=>levels.forEach(price=>series.createPriceLine({price,color:'#abb3c3',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:''}));
 if(this.enabled('volume')||this.enabled('vma')){pane++;this.series.volume=this.chart.addSeries(L.HistogramSeries,{priceFormat:{type:'volume'},priceLineVisible:false,lastValueVisible:false,visible:this.enabled('volume')},pane);if(this.enabled('vma'))line('vma','#d59637',pane);}
 if(this.enabled('sma'))line('sma','#da962b');if(this.enabled('ema'))line('ema','#725cce');if(this.enabled('wma'))line('wma','#227c9d');if(this.enabled('vwma'))line('vwma','#00897b');if(this.enabled('supertrend'))line('supertrend','#d04b64');
 if(this.enabled('bb')){line('upper','#7597ba');line('middle','#adb5c5');line('lower','#7597ba');}
 if(this.enabled('rsi')){pane++;line('rsi','#9764c7',pane);guides(this.series.rsi,[30,70]);}
 if(this.enabled('macd')){pane++;line('macd','#3777bc',pane);line('signal','#e69239',pane);this.series.hist=this.chart.addSeries(L.HistogramSeries,{priceLineVisible:false,lastValueVisible:false},pane);guides(this.series.macd,[0]);}
 if(this.enabled('atr')){pane++;line('atr','#8b6f47',pane);}
 if(this.enabled('adx')){pane++;line('adx','#6d5aa7',pane);guides(this.series.adx,[20,25]);}
 if(this.enabled('stoch')){pane++;line('stoch','#3478b8',pane);line('stochSignal','#e08a35',pane);guides(this.series.stoch,[20,80]);}
 if(this.enabled('cci')){pane++;line('cci','#7a5f9e',pane);guides(this.series.cci,[-100,100]);}
 if(this.enabled('roc')){pane++;line('roc','#2b8a7e',pane);guides(this.series.roc,[0]);}
 if(this.enabled('willr')){pane++;line('willr','#a56b35',pane);guides(this.series.willr,[-80,-20]);}
 if(this.enabled('obv')){pane++;line('obv','#4e6bb3',pane);}
 if(this.enabled('mfi')){pane++;line('mfi','#7b5cab',pane);guides(this.series.mfi,[20,80]);}
 if(this.enabled('cmf')){pane++;line('cmf','#318b6c',pane);guides(this.series.cmf,[0]);}
 this.series.price.setData(this.bars.map(b=>this.priceData(b)));if(this.series.volume)this.series.volume.setData(this.bars.map(b=>this.volumeData(b)));
 for(const [key,s]of Object.entries(this.series)){if(['price','volume'].includes(key))continue;s.setData(this.values.filter(v=>Number.isFinite(v[key])).map(v=>({time:v.time,value:v[key],...(key==='hist'?{color:v.hist>=0?'#08998188':'#f2364588'}:{})})));}
 this.chart.panes().forEach((p,i)=>p.setHeight(i?95:350));this.chart.applyOptions({timeScale:{timeVisible:M.intraday(this.tf),tickMarkFormatter:t=>M.intraday(this.tf)?new Date(t*1000).toLocaleTimeString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit'}):null}});
 if(range)this.chart.timeScale().setVisibleLogicalRange(range);this.readout(this.bars.at(-1));
 }
 priceData(b){return this.type==='candles'?{time:b.time,open:b.open,high:b.high,low:b.low,close:b.close}:{time:b.time,value:b.close};}
 volumeData(b){return {time:b.time,value:b.volume,color:b.close>=b.open?'#08998177':'#f2364577'};}
 readout(b){if(!b){$('price-readout').textContent='Chưa có dữ liệu ở khung thời gian này.';return;}const original=this.bars.findLast(x=>x.time===b.time)||b;$('price-readout').textContent=`${this.symbol} · ${timeLabel(b.time)} · O ${fmt(original.open)}  H ${fmt(original.high)}  L ${fmt(original.low)}  C ${fmt(original.close)}  Vol ${fmt(original.volume)}`;}
 syncIndicatorSettings(){const selected=[];(document.querySelectorAll?.('#indicator-list input[type=checkbox]')||[]).forEach(x=>{if(x.checked)selected.push(x.id.replace('ind-',''));});(document.querySelectorAll?.('[data-settings-for]')||[]).forEach(card=>card.classList.toggle('active',selected.includes(card.dataset.settingsFor)));const empty=$('indicator-selected-empty');if(empty)empty.hidden=selected.length>0;}
 technicalSnapshot(){
  if(!this.bars.length||!this.values.length)return null;
  const b=this.bars.at(-1),p=this.values.at(-2)||{},v=this.values.at(-1)||{},prior=this.bars.slice(-21,-1);
  const avgVolume=prior.length?prior.reduce((s,z)=>s+(Number(z.volume)||0),0)/prior.length:null;
  const volumeRatio=avgVolume&&Number.isFinite(b.volume)?b.volume/avgVolume:null;
  const priceSmaPct=Number.isFinite(v.sma)&&v.sma?((b.close/v.sma)-1)*100:null;
  const priceEmaPct=Number.isFinite(v.ema)&&v.ema?((b.close/v.ema)-1)*100:null;
  const macdDiff=Number.isFinite(v.macd)&&Number.isFinite(v.signal)?v.macd-v.signal:null;
  const macdCross=Number.isFinite(p.macd)&&Number.isFinite(p.signal)&&Number.isFinite(v.macd)&&Number.isFinite(v.signal)?(p.macd<=p.signal&&v.macd>v.signal?'up':p.macd>=p.signal&&v.macd<v.signal?'down':'none'):'none';
  const rsi=Number(v.rsi),rsiDelta=Number.isFinite(rsi)&&Number.isFinite(p.rsi)?rsi-p.rsi:null;
  let rsiState='không có RSI',rsiVote=0;
  if(Number.isFinite(rsi)){
   if(rsi>=70){rsiState=Number.isFinite(rsiDelta)&&rsiDelta<0?'quay về mean từ vùng quá mua':'duy trì vùng quá mua';rsiVote=.5;}
   else if(rsi<=30){rsiState=Number.isFinite(rsiDelta)&&rsiDelta>0?'quay về mean từ vùng quá bán':'duy trì vùng quá bán';rsiVote=-.5;}
   else if(rsi>=55){rsiState='động lượng tăng trên vùng trung tính';rsiVote=1;}
   else if(rsi<=45){rsiState='động lượng giảm dưới vùng trung tính';rsiVote=-1;}
   else{rsiState='dao động quanh mean 50';rsiVote=0;}
  }
  const votes=[];
  if(Number.isFinite(macdDiff))votes.push({id:'macd',vote:macdDiff>0?1:macdDiff<0?-1:0});
  if(Number.isFinite(rsi))votes.push({id:'rsi',vote:rsiVote});
  if(Number.isFinite(priceSmaPct))votes.push({id:'sma',vote:priceSmaPct>0?1:-1});
  if(Number.isFinite(v.supertrendDir))votes.push({id:'supertrend',vote:v.supertrendDir>0?1:-1});
  if(Number.isFinite(priceEmaPct))votes.push({id:'ema',vote:priceEmaPct>0?1:-1});
  const sum=votes.reduce((s,x)=>s+x.vote,0),available=votes.length,bull=votes.filter(x=>x.vote>0).length,bear=votes.filter(x=>x.vote<0).length;
  let direction=sum>=1.5?'bullish':sum<=-1.5?'bearish':'neutral';
  const adx=Number(v.adx),trendStrength=Number.isFinite(adx)?(adx>=30?'mạnh':adx>=25?'đủ mạnh':adx>=20?'trung bình':'yếu'):'chưa có ADX';
  const volumeState=Number.isFinite(volumeRatio)?(volumeRatio>=1.5?'bùng nổ':volumeRatio>=1.15?'xác nhận tốt':volumeRatio>=.8?'bình thường':'thấp'):'chưa có';
  let confidence=available?48+Math.min(28,Math.abs(sum)/Math.max(1,available)*42):35;
  if(Number.isFinite(adx))confidence+=adx>=25?10:adx<18?-6:0;
  if(Number.isFinite(volumeRatio))confidence+=volumeRatio>=1.15?10:volumeRatio<.7?-7:0;
  confidence=Math.max(20,Math.min(95,Math.round(confidence)));
  const label=direction==='bullish'?'TĂNG':direction==='bearish'?'GIẢM':'TRUNG TÍNH',tone=direction==='bullish'?'positive':direction==='bearish'?'negative':'neutral';
  const parts=[];
  if(Number.isFinite(macdDiff))parts.push('MACD '+(macdDiff>0?'trên':'dưới')+' Signal'+(macdCross==='up'?' và vừa cắt lên':macdCross==='down'?' và vừa cắt xuống':''));
  if(Number.isFinite(rsi))parts.push('RSI '+fmt(rsi)+' · '+rsiState);
  if(Number.isFinite(priceSmaPct))parts.push('giá '+(priceSmaPct>=0?'trên':'dưới')+' SMA'+this.params.sma+' '+fmt(Math.abs(priceSmaPct))+'%');
  if(Number.isFinite(v.supertrendDir))parts.push('Supertrend '+(v.supertrendDir>0?'tăng':'giảm'));
  if(Number.isFinite(adx))parts.push('ADX '+fmt(adx)+' · xu hướng '+trendStrength);
  if(Number.isFinite(volumeRatio))parts.push('KL '+fmt(volumeRatio)+'x TB20 · '+volumeState);
  return{symbol:this.symbol,timeframe:this.tf,label,tone,direction,confidence,bull,bear,available,score:sum,macd:{value:v.macd,signal:v.signal,hist:v.hist,diff:macdDiff,cross:macdCross},rsi:{value:rsi,delta:rsiDelta,state:rsiState},price:{close:b.close,sma:v.sma,ema:v.ema,vsSmaPct:priceSmaPct,vsEmaPct:priceEmaPct},supertrend:{value:v.supertrend,direction:v.supertrendDir},adx:{value:adx,state:trendStrength},volume:{value:b.volume,ratio20:volumeRatio,state:volumeState},summary:parts.join(' · ')};
 }
 signalDetail(prefix=''){const s=this.technicalSnapshot();return s?(prefix?prefix+' ':'')+`Tổng hợp ${s.label} · độ tin cậy ${s.confidence}/100 · xác nhận tăng ${s.bull}, giảm ${s.bear}. ${s.summary}.`:prefix;}
 pushSignal(id,title,detail,tone='neutral',toast=true){const key=this.symbol+':'+this.tf+':'+id,now=Date.now(),last=this.signalCooldown.get(key)||0;if(toast&&now-last<12*60*1000)return;this.signalCooldown.set(key,now);const event={id,title,detail,tone,time:now};this.signalEvents=[event,...this.signalEvents.filter(x=>x.id!==id)].slice(0,6);this.renderSignals();if(toast){const stack=$('signal-toast-stack');if(stack){const node=document.createElement('div');node.className='signal-toast '+tone;node.innerHTML='<strong>'+title.replace(/[<>]/g,'')+'</strong><p>'+detail.replace(/[<>]/g,'')+'</p>';stack.prepend(node);setTimeout(()=>node.remove(),9000);}}}
 renderSignals(){const title=$('signal-title'),status=$('signal-status'),feed=$('signal-feed'),s=this.technicalSnapshot();if(title)title.textContent=s?`${this.symbol} · ${this.tf} · Tín hiệu ${s.label} ${s.confidence}/100`:(this.symbol||'Mã đang xem')+' · '+this.tf;if(status)status.textContent=s?`Xác nhận tăng ${s.bull} · giảm ${s.bear} · ${s.rsi.state} · KL ${Number.isFinite(s.volume.ratio20)?fmt(s.volume.ratio20)+'x TB20':'—'}`:'Đang tính tín hiệu tổng hợp';if(!feed)return;const composite=s?'<div class="signal-chip composite '+s.tone+'"><strong>'+('Tín hiệu tổng hợp: '+s.label+' · '+s.confidence+'/100').replace(/[<>]/g,'')+'</strong><span>'+s.summary.replace(/[<>]/g,'')+'</span></div>':'';const events=this.signalEvents.map(x=>'<div class="signal-chip '+x.tone+'"><strong>'+x.title.replace(/[<>]/g,'')+'</strong><span>'+x.detail.replace(/[<>]/g,'')+'</span></div>').join('');feed.innerHTML=composite+events||( '<p>Đang tính tín hiệu từ dữ liệu hiện có.</p>');}
 evaluateSignals(toast=true){if(this.values.length<3||this.bars.length<3){this.renderSignals();return;}const p=this.values.at(-2),v=this.values.at(-1),pb=this.bars.at(-2),b=this.bars.at(-1);if(!p||!v)return;
  const cross=(a0,b0,a1,b1)=>Number.isFinite(a0)&&Number.isFinite(b0)&&Number.isFinite(a1)&&Number.isFinite(b1)&&((a0<=b0&&a1>b1)?1:(a0>=b0&&a1<b1)?-1:0);
  let x=cross(p.macd,p.signal,v.macd,v.signal);if(x>0)this.pushSignal('macd-up','MACD cắt lên Signal',this.signalDetail('MACD đã chuyển sang trạng thái tăng.'),'positive',toast);if(x<0)this.pushSignal('macd-down','MACD cắt xuống Signal',this.signalDetail('MACD đã chuyển sang trạng thái giảm.'),'negative',toast);
  if(Number.isFinite(p.rsi)&&Number.isFinite(v.rsi)){if(p.rsi<30&&v.rsi>=30)this.pushSignal('rsi-exit-low','RSI quay lại từ quá bán',this.signalDetail('RSI đã rời vùng quá bán và bắt đầu mean reversion hướng về 50.'),'positive',toast);if(p.rsi<=70&&v.rsi>70)this.pushSignal('rsi-high','RSI vào vùng quá mua',this.signalDetail('RSI vượt 70; động lượng tăng mạnh nhưng khoảng cách tới mean 50 đã mở rộng.'),'positive',toast);if(p.rsi>=70&&v.rsi<70)this.pushSignal('rsi-mean-high','RSI mean reversion từ quá mua',this.signalDetail('RSI rời vùng quá mua và quay về mean; động lượng tăng đang hạ nhiệt.'),'negative',toast);if(p.rsi>=30&&v.rsi<30)this.pushSignal('rsi-low','RSI vào vùng quá bán',this.signalDetail('RSI xuống dưới 30; lực giảm đang ở trạng thái cực đoan so với mean 50.'),'negative',toast);}
  x=cross(pb.close,p.sma,b.close,v.sma);if(x>0)this.pushSignal('price-sma-up','Giá cắt lên SMA'+this.params.sma,this.signalDetail('Giá đóng cửa đã lấy lại SMA'+this.params.sma+'.'),'positive',toast);if(x<0)this.pushSignal('price-sma-down','Giá cắt xuống SMA'+this.params.sma,this.signalDetail('Giá đóng cửa đã mất SMA'+this.params.sma+'.'),'negative',toast);
  if(Number.isFinite(p.supertrendDir)&&Number.isFinite(v.supertrendDir)&&p.supertrendDir!==v.supertrendDir)this.pushSignal('supertrend-flip','Supertrend đổi hướng',this.signalDetail(v.supertrendDir>0?'Supertrend chuyển sang tăng.':'Supertrend chuyển sang giảm.'),v.supertrendDir>0?'positive':'negative',toast);
  if(Number.isFinite(p.adx)&&Number.isFinite(v.adx)&&p.adx<25&&v.adx>=25)this.pushSignal('adx-25','ADX vượt 25',this.signalDetail('ADX vượt 25; xu hướng hiện tại đã có độ mạnh đáng kể.'),this.technicalSnapshot()?.tone||'neutral',toast);
  if(this.bars.length>=21){const prior=this.bars.slice(-21,-1),avg=prior.reduce((s,z)=>s+z.volume,0)/prior.length,ratio=avg?b.volume/avg:null;if(Number.isFinite(ratio)&&ratio>=1.5)this.pushSignal('volume-spike','Khối lượng tăng mạnh',this.signalDetail('Khối lượng đạt '+fmt(ratio)+'x trung bình 20 nến và đang xác nhận biến động hiện tại.'),this.technicalSnapshot()?.tone||'neutral',toast);}
  this.renderSignals();
 }
 snapshot(q){if(!q||q.symbol!==this.symbol||!M.intraday(this.tf)||!Number.isFinite(q.price)||!Number.isFinite(Date.parse(q.sourceTime||''))||q.sourceTime===this.lastSnapshotSource||!this.bars.length)return;const ts=Date.parse(q.sourceTime)/1000,bucket=M.bucket(ts,this.tf),last=this.bars.at(-1);if(typeof last.time!=='number'||bucket<last.time)return;const prevQ=this.lastQuote,deltaVol=prevQ&&Number.isFinite(q.volume)&&Number.isFinite(prevQ.volume)&&q.volume>=prevQ.volume?Math.max(0,q.volume-prevQ.volume):0;let bar;if(bucket===last.time){bar={...last,high:Math.max(last.high,q.price),low:Math.min(last.low,q.price),close:q.price,volume:last.volume+deltaVol};this.bars[this.bars.length-1]=bar;}else{const open=prevQ?.price||last.close||q.price;bar={time:bucket,open,high:Math.max(open,q.price),low:Math.min(open,q.price),close:q.price,volume:deltaVol};this.bars.push(bar);}this.lastQuote={price:q.price,volume:q.volume,sourceTime:q.sourceTime};this.lastSnapshotSource=q.sourceTime;this.values=M.indicators(this.bars,this.params);this.rebuild(true);this.evaluateSignals(true);this.status('Snapshot '+this.tf+' · '+timeLabel(bucket)+' · tự cập nhật chỉ báo');}
 noteNews(item){if(!item?.title)return;const topics=item.topics||[],s=this.technicalSnapshot();let role='Bối cảnh thị trường';if((item.symbols||[]).includes(this.symbol))role='Catalyst trực tiếp cho '+this.symbol;else if(topics.includes('rates')||topics.includes('banking'))role='Catalyst ngành tài chính/ngân hàng';else if(topics.includes('stocks')||topics.includes('market'))role='Catalyst thị trường chung';const tech=s?` Tín hiệu kỹ thuật hiện ${s.label} ${s.confidence}/100: ${s.summary}.`:'';this.pushSignal('news:'+String(item.url||item.title).slice(-48),'Tin mới · '+(item.source||'Thị trường'),item.title+' — '+role+'.'+tech,'news',true);}
 context(){const s=this.technicalSnapshot(),first=this.baseBars[0],last=this.baseBars.at(-1);return{symbol:this.symbol,timeframe:this.tf,technical:s,history:{barCount:this.baseBars.length,firstBar:first?.time||null,lastBar:last?.time||null}};}

 range(){if(!this.bars.length)return;const months=Number($('chart-period').value),first=this.bars[0],last=this.bars.at(-1),labelTime=t=>typeof t==='number'?new Date(t*1000).toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):String(t);if(!months){this.chart.timeScale().fitContent();$('chart-range-label').textContent=`${this.bars.length} nến · ${labelTime(first.time)} → ${labelTime(last.time)} · toàn bộ lịch sử có sẵn`;return;}const end=typeof last.time==='number'?new Date(last.time*1000):new Date(last.time+'T12:00:00Z'),start=new Date(end);start.setUTCMonth(start.getUTCMonth()-months);let index=this.bars.findIndex(b=>(typeof b.time==='number'?b.time*1000:Date.parse(b.time+'T12:00:00Z'))>=+start);if(index<0)index=0;this.chart.timeScale().setVisibleLogicalRange({from:Math.max(0,index),to:this.bars.length+3});$('chart-range-label').textContent=`${this.bars.length-index} nến trong khoảng xem · ${labelTime(this.bars[index]?.time)} → ${labelTime(last.time)}`;}
 zoom(f){const r=this.chart.timeScale().getVisibleLogicalRange();if(r){const mid=(r.from+r.to)/2,half=(r.to-r.from)*f/2;this.chart.timeScale().setVisibleLogicalRange({from:mid-half,to:mid+half});}}
 subscribe(){if(this.socket?.readyState===WebSocket.OPEN){this.socket.send(JSON.stringify({type:'subscribe',symbols:this.watch,intervals:['1m','1d']}));}}
 connect(){clearTimeout(this.retry);if(this.stopped||!this.options)return;if(!this.options.websocketUrl){this.status('');return;}if(!/^wss:\/\//.test(this.options.websocketUrl)){this.status('Cấu hình WebSocket cần địa chỉ wss:// hợp lệ.');return;}if(this.socket&&this.socket.readyState<2)return;
 this.status('Đang kết nối luồng giá…');const socket=this.socket=new WebSocket(this.options.websocketUrl);
 socket.onopen=()=>{this.retries=0;this.status('Đã kết nối · Đang chờ dữ liệu thị trường');this.subscribe();if(this.hasConnected)this.load(true);this.hasConnected=true;};
 socket.onmessage=e=>{if(socket!==this.socket)return;clearTimeout(this.staleTimer);this.staleTimer=setTimeout(()=>this.status('Chưa nhận thông điệp mới trong 90 giây · Kiểm tra trạng thái nguồn/phiên'),90000);try{const m=JSON.parse(e.data);if(m.type==='ping'){socket.send(JSON.stringify({type:'pong'}));return;}if(m.type==='status'){this.status(String(m.message||'Đang chờ dữ liệu').slice(0,160));return;}if(m.type==='quote'&&this.watch.includes(m.symbol)&&Number.isFinite(m.price)&&m.price>0&&Number.isFinite(Date.parse(m.sourceTime))){this.onQuote(m);return;}if(m.type==='candle'){if(this.loading){if(this.buffer.length<2000)this.buffer.push(m);}else this.candle(m);}}catch{this.status('Bỏ qua thông điệp thị trường không hợp lệ.');}};
 socket.onclose=()=>{if(this.stopped)return;this.status('Mất kết nối · Giữ dữ liệu cuối, đang kết nối lại');this.retry=setTimeout(()=>this.connect(),Math.min(30000,1000*2**Math.min(this.retries++,5))+Math.random()*500);};socket.onerror=()=>socket.close();
 }
 candle(m){const baseTF=M.intraday(this.tf)?'1m':'1d';if(m.symbol!==this.symbol||m.interval!==baseTF||m.unit!=='VND')return;const next=M.cleanBars([m.bar],baseTF==='1m')[0];if(!next||(typeof next.time==='number'&&next.time>Date.now()/1000+60))return;const last=this.baseBars.at(-1);if(last&&next.time<last.time)return;if(last&&next.time===last.time)this.baseBars[this.baseBars.length-1]=next;else this.baseBars.push(next);
 // Reaggregate only the current bucket, preserving every earlier rendered candle.
 const t=M.bucket(next.time,this.tf),tail=[];for(let i=this.baseBars.length-1;i>=0&&M.bucket(this.baseBars[i].time,this.tf)===t;i--)tail.unshift(this.baseBars[i]);const b=M.aggregate(tail,this.tf)[0];if(this.bars.at(-1)?.time===b.time)this.bars[this.bars.length-1]=b;else this.bars.push(b);
 const i=this.bars.length-1,v=M.point(this.bars,i,this.params,this.values[i-1]);this.values[i]=v;this.series.price.update(this.priceData(b));this.series.volume?.update(this.volumeData(b));for(const [key,s]of Object.entries(this.series))if(!['price','volume'].includes(key)&&Number.isFinite(v[key]))s.update({time:b.time,value:v[key],...(key==='hist'?{color:v.hist>=0?'#08998188':'#f2364588'}:{})});
 this.readout(b);this.evaluateSignals(true);this.cache.delete(this.symbol+':'+baseTF);this.status(`WebSocket · Nến ${timeLabel(next.time)} · Nhận lúc ${new Date().toLocaleTimeString('vi-VN')}`);
 }
 close(){this.stopped=true;clearTimeout(this.retry);clearTimeout(this.staleTimer);this.abort?.abort();this.socket?.close();}
}
window.FinChart={create:(base,onQuote)=>{if(!L||!M){$('chart-status').textContent='Không tải được thư viện biểu đồ. Vui lòng mở lại trang.';return {select(){},load(){},snapshot(){},noteNews(){},context(){return null;}};}return new ChartController(base,onQuote);}};
})();
