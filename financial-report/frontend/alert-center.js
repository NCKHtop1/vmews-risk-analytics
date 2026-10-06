(function(){'use strict';
const $=id=>document.getElementById(id),E=window.FinStrategyEngine;
if(!E)return;
const KEY='finquery-strategies-v2',HIT_KEY='finquery-strategy-hits-v2';
const state={snapshot:null,conditions:[],strategies:[],hits:[],matches:[],filter:'',loading:false,dragId:null,marketSourceTime:null,retryTimer:null};
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function clone(x){return JSON.parse(JSON.stringify(x));}
function loadLocal(){try{const v=JSON.parse(localStorage.getItem(KEY)||'[]');if(Array.isArray(v))state.strategies=v;}catch{}try{const v=JSON.parse(localStorage.getItem(HIT_KEY)||'[]');if(Array.isArray(v))state.hits=v.slice(0,100);}catch{}}
function saveLocal(){try{localStorage.setItem(KEY,JSON.stringify(state.strategies));localStorage.setItem(HIT_KEY,JSON.stringify(state.hits.slice(0,100)));}catch{}}
function fmt(v,d=2){return Number.isFinite(Number(v))?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:d}).format(Number(v)):'—';}
function time(v){const t=Date.parse(v||'');return Number.isFinite(t)?new Date(t).toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'}):'—';}
function currentStrategy(){return{name:String($('strategy-name')?.value||'').trim()||'Chiến lược mới',join:$('strategy-join')?.value||'AND',scope:$('strategy-scope')?.value||'LIVE',conditions:state.conditions.map(E.normalizeCondition)};}
function defaultRight(c){
 const noRight=['rising','falling'].includes(c.op);
 if(noRight)return'';
 if(c.rightType==='indicator')return'<select data-cond-right-indicator="'+esc(c.id)+'">'+E.CATALOG.map(x=>'<option value="'+esc(x.id)+'" '+(x.id===c.rightIndicator?'selected':'')+'>'+esc(x.label)+'</option>').join('')+'</select>';
 return '<input data-cond-right-value="'+esc(c.id)+'" type="number" step="0.01" value="'+esc(c.rightValue??0)+'">';
}
function renderLibrary(){
 const q=String($('strategy-library-search')?.value||'').trim().toLocaleLowerCase('vi');
 const host=$('strategy-library');if(!host)return;
 const groups=[...new Set(E.CATALOG.map(x=>x.group))];
 host.innerHTML=groups.map(group=>{
  const rows=E.CATALOG.filter(x=>x.group===group&&(!q||x.label.toLocaleLowerCase('vi').includes(q)||x.id.includes(q)));
  if(!rows.length)return'';
  return '<section class="strategy-lib-group"><h4>'+esc(group)+'</h4><div>'+rows.map(x=>'<button type="button" draggable="true" class="strategy-indicator-chip" data-strategy-indicator="'+esc(x.id)+'"><span>⋮⋮</span><strong>'+esc(x.label)+'</strong><small>'+esc(x.id)+'</small></button>').join('')+'</div></section>';
 }).join('');
}
function renderCanvas(){
 const host=$('strategy-canvas');if(!host)return;
 if(!state.conditions.length){host.innerHTML='<div class="strategy-drop-empty"><strong>Thả indicator vào đây</strong><span>Ví dụ: MACD cắt lên Signal + RSI ≥ 50</span></div>';return;}
 host.innerHTML=state.conditions.map((c,idx)=>'<article class="strategy-condition" data-cond="'+esc(c.id)+'"><span class="strategy-condition-index">'+(idx+1)+'</span><div class="strategy-condition-main"><div class="strategy-condition-title"><strong>'+esc(E.label(c.left))+'</strong><button type="button" data-cond-delete="'+esc(c.id)+'" aria-label="Xóa điều kiện">×</button></div><div class="strategy-condition-controls"><select data-cond-op="'+esc(c.id)+'">'+E.OPS.map(o=>'<option value="'+esc(o.id)+'" '+(o.id===c.op?'selected':'')+'>'+esc(o.label)+'</option>').join('')+'</select><select data-cond-right-type="'+esc(c.id)+'" '+(['rising','falling'].includes(c.op)?'disabled':'')+'><option value="value" '+(c.rightType!=='indicator'?'selected':'')+'>Giá trị</option><option value="indicator" '+(c.rightType==='indicator'?'selected':'')+'>Indicator</option></select>'+defaultRight(c)+'</div></div></article>').join('');
}
function addCondition(id){if(!E.MAP[id])return;state.conditions.push(E.condition(id));renderCanvas();renderPreview();}
function renderPreview(){const host=$('strategy-preview');if(!host)return;const s=currentStrategy();host.innerHTML=s.conditions.length?'<strong>'+esc(s.join)+'</strong> '+s.conditions.map(c=>'<span>'+esc(E.describe(c))+'</span>').join('<b> '+esc(s.join)+' </b> '):'<span>Chưa có điều kiện.</span>';}
function applyPreset(id){const p=E.PRESETS[id];if(!p)return;state.conditions=p.conditions.map(E.normalizeCondition);if($('strategy-name'))$('strategy-name').value=p.name;if($('strategy-join'))$('strategy-join').value=p.join;if($('strategy-scope'))$('strategy-scope').value=p.scope;renderCanvas();renderPreview();scanNow();}
function renderResults(){
 const host=$('strategy-results'),meta=$('strategy-result-meta');if(!host)return;
 const s=currentStrategy();
 if(meta)meta.textContent=state.snapshot?(state.matches.length+' mã khớp · '+(state.snapshot.coverage||0)+' mã đủ dữ liệu · nguồn '+time(state.snapshot.sourceTime||state.snapshot.checkedAt)):'Chưa tải dữ liệu chiến lược';
 host.innerHTML=state.matches.length?'<div class="strategy-results-table-wrap"><table class="strategy-results-table"><thead><tr><th>Mã</th><th>Nhóm</th><th>Giá</th><th>% phiên</th><th>RSI</th><th>MACD hist</th><th>Vol/TB20</th><th>Thời điểm</th></tr></thead><tbody>'+state.matches.slice(0,120).map(r=>'<tr><td><button type="button" data-strategy-open="'+esc(r.symbol)+'">'+esc(r.symbol)+'</button></td><td>'+esc(r.tier||'')+'</td><td>'+fmt(r.current?.price,0)+'</td><td class="'+(Number(r.current?.changePct)>0?'price-up':Number(r.current?.changePct)<0?'price-down':'')+'">'+(Number(r.current?.changePct)>0?'+':'')+fmt(r.current?.changePct,2)+'%</td><td>'+fmt(r.current?.rsi14,1)+'</td><td>'+fmt(r.current?.macdHistogram,2)+'</td><td>'+fmt(r.current?.volumeRatio20,2)+'x</td><td>'+(r.cadence==='EOD'?esc((r.barDate||'—')+' · EOD'):time(r.sourceTime||state.snapshot?.sourceTime))+'</td></tr>').join('')+'</tbody></table></div>':'<div class="strategy-no-result">'+(s.conditions.length?'Không có mã nào khớp toàn bộ điều kiện hiện tại.':'Kéo indicator vào canvas rồi bấm “Quét mã”.')+'</div>';
}
function scanNow(){if(!state.snapshot){renderResults();return;}state.matches=E.scan(state.snapshot,currentStrategy());renderResults();}
function strategySummary(s){return(s.conditions||[]).map(E.describe).join(' '+(s.join||'AND')+' ');}
function renderSaved(){
 const host=$('strategy-saved');if(!host)return;
 host.innerHTML=state.strategies.length?state.strategies.map(s=>{
  const count=state.snapshot?E.scan(state.snapshot,s).length:0;
  return '<article class="strategy-saved-card"><div><strong>'+esc(s.name)+'</strong><small>'+esc(strategySummary(s))+'</small><span>'+esc(s.scope||'ALL')+' · '+count+' mã đang khớp</span></div><div class="strategy-saved-actions"><label><input type="checkbox" data-strategy-alert="'+esc(s.id)+'" '+(s.alert?'checked':'')+'> Alert</label><button type="button" data-strategy-load="'+esc(s.id)+'">Mở</button><button type="button" data-strategy-delete="'+esc(s.id)+'" aria-label="Xóa">×</button></div></article>';
 }).join(''):'<div class="strategy-no-result">Chưa lưu chiến lược nào.</div>';
}
function renderHits(){
 const host=$('strategy-hits');if(!host)return;
 host.innerHTML=state.hits.length?state.hits.slice(0,30).map(h=>'<button type="button" class="strategy-hit" data-strategy-open="'+esc(h.symbol)+'"><span><strong>'+esc(h.symbol)+'</strong> · '+esc(h.strategyName)+'</span><small>'+new Date(h.at).toLocaleString('vi-VN',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})+'</small></button>').join(''):'<div class="strategy-no-result">Chưa có tín hiệu mới.</div>';
}
function saveStrategy(){
 const s=currentStrategy();if(!s.conditions.length)return;
 const id='s'+Date.now().toString(36)+Math.random().toString(36).slice(2,7),matches=state.snapshot?E.scan(state.snapshot,s).map(x=>x.symbol):[];
 state.strategies.unshift({...s,id,alert:true,lastMatches:matches,lastCheckedSourceTime:state.snapshot?.sourceTime||state.snapshot?.checkedAt||null,createdAt:new Date().toISOString()});
 saveLocal();renderSaved();
}
function loadStrategy(id){const s=state.strategies.find(x=>x.id===id);if(!s)return;state.conditions=(s.conditions||[]).map(E.normalizeCondition);$('strategy-name').value=s.name||'';$('strategy-join').value=s.join||'AND';$('strategy-scope').value=s.scope||'ALL';renderCanvas();renderPreview();scanNow();document.getElementById('strategy-builder')?.scrollIntoView({behavior:'smooth',block:'start'});}
function openSymbol(symbol){window.FinPlatformViews?.openAnalysis?.();const ticker=$('ticker');if(ticker)ticker.value=symbol;$('company-form')?.requestSubmit();setTimeout(()=>document.getElementById('market')?.scrollIntoView({behavior:'smooth',block:'start'}),50);}
function notify(strategy,rows){
 if(!rows.length)return;
 const names=rows.slice(0,5).map(x=>x.symbol).join(', '),body=names+(rows.length>5?' +' +(rows.length-5):'');
 if('Notification'in window&&Notification.permission==='granted')try{new Notification('FinQuery · '+strategy.name,{body});}catch{}
}
function evaluateAlerts(){
 if(!state.snapshot)return;
 let changed=false,newHits=[];
 for(const s of state.strategies){
  const rows=E.scan(state.snapshot,s),current=rows.map(x=>x.symbol),previous=new Set(s.lastMatches||[]);
  if(s.alert&&s.lastCheckedSourceTime){const fresh=rows.filter(x=>!previous.has(x.symbol));for(const r of fresh)newHits.push({key:s.id+'|'+r.symbol+'|'+(state.snapshot.sourceTime||state.snapshot.checkedAt),symbol:r.symbol,strategyId:s.id,strategyName:s.name,at:Date.now()});notify(s,fresh);}
  s.lastMatches=current;s.lastCheckedSourceTime=state.snapshot.sourceTime||state.snapshot.checkedAt||new Date().toISOString();changed=true;
 }
 if(newHits.length){const known=new Set(state.hits.map(x=>x.key));state.hits=[...newHits.filter(x=>!known.has(x.key)),...state.hits].slice(0,100);}
 if(changed){saveLocal();renderSaved();renderHits();}
}
async function refreshSnapshot(){
 if(state.loading)return;state.loading=true;const b=$('strategy-refresh');if(b)b.disabled=true;const status=$('strategy-status');if(status)status.textContent='Đang tải indicator snapshot…';
 try{
  const data=await window.FinMarketData.get('strategy-indicators.json');if(!data?.symbols)throw Error('Invalid strategy snapshot');
  const expected=state.marketSourceTime,actual=data.sourceTime||null;
  if(expected&&String(actual)!==String(expected)){
   if(state.snapshot){scanNow();renderSaved();}
   if(status)status.textContent=(state.snapshot?'Đang giữ snapshot Strategy Lab gần nhất · ':'')+'Đang đồng bộ với snapshot giá mới nhất…';
   clearTimeout(state.retryTimer);state.retryTimer=setTimeout(()=>{if(Date.parse(actual||0)>Date.parse(expected||0))window.FinancialMarket?.refresh?.();refreshSnapshot();},1200);
   return;
  }
  const changed=(data.sourceTime||data.checkedAt)!==(state.snapshot?.sourceTime||state.snapshot?.checkedAt);state.snapshot=data;if(status)status.textContent=(data.coverage||0)+' mã · Live '+(data.liveCoverage||0)+' · Discovery '+(data.discoveryCoverage||0)+' · '+time(data.sourceTime||data.checkedAt);scanNow();if(changed)evaluateAlerts();else renderSaved();
 }
 catch(e){if(status)status.textContent='Chưa tải được dữ liệu quét chiến lược.';}
 finally{state.loading=false;if(b)b.disabled=false;}
}
function bind(){
 $('strategy-library-search')?.addEventListener('input',renderLibrary);
 $('strategy-library')?.addEventListener('dragstart',e=>{const b=e.target.closest('[data-strategy-indicator]');if(!b)return;state.dragId=b.dataset.strategyIndicator;e.dataTransfer?.setData('text/plain',state.dragId);});
 $('strategy-library')?.addEventListener('click',e=>{const b=e.target.closest('[data-strategy-indicator]');if(b)addCondition(b.dataset.strategyIndicator);});
 const canvas=$('strategy-canvas');canvas?.addEventListener('dragover',e=>{e.preventDefault();canvas.classList.add('drag-over');});canvas?.addEventListener('dragleave',()=>canvas.classList.remove('drag-over'));canvas?.addEventListener('drop',e=>{e.preventDefault();canvas.classList.remove('drag-over');addCondition(e.dataTransfer?.getData('text/plain')||state.dragId);});
 canvas?.addEventListener('change',e=>{const op=e.target.dataset.condOp,type=e.target.dataset.condRightType,ri=e.target.dataset.condRightIndicator,rv=e.target.dataset.condRightValue,id=op||type||ri||rv,c=state.conditions.find(x=>x.id===id);if(!c)return;if(op)c.op=e.target.value;if(type){c.rightType=e.target.value;if(c.rightType==='indicator'&&!E.MAP[c.rightIndicator])c.rightIndicator='sma20';}if(ri)c.rightIndicator=e.target.value;if(rv)c.rightValue=Number(e.target.value);renderCanvas();renderPreview();});
 canvas?.addEventListener('input',e=>{const id=e.target.dataset.condRightValue,c=state.conditions.find(x=>x.id===id);if(c){c.rightValue=Number(e.target.value);renderPreview();}});
 canvas?.addEventListener('click',e=>{const b=e.target.closest('[data-cond-delete]');if(!b)return;state.conditions=state.conditions.filter(x=>x.id!==b.dataset.condDelete);renderCanvas();renderPreview();});
 document.querySelectorAll('[data-strategy-preset]').forEach(b=>b.addEventListener('click',()=>applyPreset(b.dataset.strategyPreset)));
 $('strategy-join')?.addEventListener('change',()=>{renderPreview();scanNow();});$('strategy-scope')?.addEventListener('change',scanNow);$('strategy-name')?.addEventListener('input',renderPreview);
 $('strategy-scan')?.addEventListener('click',scanNow);$('strategy-save')?.addEventListener('click',saveStrategy);$('strategy-refresh')?.addEventListener('click',refreshSnapshot);
 $('strategy-clear')?.addEventListener('click',()=>{state.conditions=[];state.matches=[];renderCanvas();renderPreview();renderResults();});
 $('strategy-results')?.addEventListener('click',e=>{const b=e.target.closest('[data-strategy-open]');if(b)openSymbol(b.dataset.strategyOpen);});
 $('strategy-saved')?.addEventListener('click',e=>{const load=e.target.closest('[data-strategy-load]'),del=e.target.closest('[data-strategy-delete]');if(load)loadStrategy(load.dataset.strategyLoad);if(del){state.strategies=state.strategies.filter(x=>x.id!==del.dataset.strategyDelete);saveLocal();renderSaved();}});
 $('strategy-saved')?.addEventListener('change',e=>{const id=e.target.dataset.strategyAlert,s=state.strategies.find(x=>x.id===id);if(s){s.alert=e.target.checked;s.lastMatches=state.snapshot?E.scan(state.snapshot,s).map(x=>x.symbol):[];s.lastCheckedSourceTime=state.snapshot?.sourceTime||state.snapshot?.checkedAt||null;saveLocal();renderSaved();}});
 $('strategy-hits')?.addEventListener('click',e=>{const b=e.target.closest('[data-strategy-open]');if(b)openSymbol(b.dataset.strategyOpen);});
 $('strategy-notifications')?.addEventListener('click',async()=>{if(!('Notification'in window))return;const p=await Notification.requestPermission();$('strategy-notifications').textContent=p==='granted'?'Thông báo đã bật':'Thông báo bị chặn';});
}
loadLocal();renderLibrary();renderCanvas();renderPreview();renderResults();renderSaved();renderHits();bind();refreshSnapshot();setInterval(()=>{if(!document.hidden)refreshSnapshot();},60000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshSnapshot();});
window.FinStrategyBuilder={refresh:refreshSnapshot,scan:scanNow,setMarketSourceTime(value){const next=value||null,changed=String(next||'')!==String(state.marketSourceTime||'');state.marketSourceTime=next;if(changed)refreshSnapshot();},context:()=>({strategy:currentStrategy(),matches:state.matches,saved:state.strategies,hits:state.hits,snapshot:state.snapshot,marketSourceTime:state.marketSourceTime,aligned:!state.marketSourceTime||String(state.snapshot?.sourceTime||'')===String(state.marketSourceTime)})};
})();