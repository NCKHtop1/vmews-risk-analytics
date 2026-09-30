(function(){'use strict';
const $=id=>document.getElementById(id),KEY='finquery-saved-screens-v1',HIT_KEY='finquery-alert-hits-v1';
const state={rules:[],hits:[],lastKeys:new Set()};
const METRICS={changePct:{label:'Thay đổi giá (%)',unit:'%'},price:{label:'Giá (đ)',unit:'đ'},volumeRatio20:{label:'KL / TB20 (x)',unit:'x',scanner:true},rsi14:{label:'RSI14',unit:'',scanner:true},priority:{label:'Rule priority scanner',unit:'/100',scanner:true}};
function load(){try{const x=JSON.parse(localStorage.getItem(KEY)||'[]');if(Array.isArray(x))state.rules=x;}catch{}try{const x=JSON.parse(localStorage.getItem(HIT_KEY)||'[]');if(Array.isArray(x))state.hits=x.slice(0,80);}catch{}}
function save(){try{localStorage.setItem(KEY,JSON.stringify(state.rules));localStorage.setItem(HIT_KEY,JSON.stringify(state.hits.slice(0,80)));}catch{}}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function cmp(a,op,b){return op==='>'?a>b:op==='>='?a>=b:op==='<'?a<b:a<=b;}
function valueFor(metric,q,row){if(metric==='changePct')return Number(q?.changePct);if(metric==='price')return Number(q?.price);return Number(row?.[metric]);}
function renderRules(){
 const host=$('alert-rules');if(!host)return;
 host.innerHTML=state.rules.length?state.rules.map(r=>'<div class="alert-rule '+(r.enabled===false?'disabled':'')+'"><button type="button" data-alert-toggle="'+esc(r.id)+'" aria-pressed="'+String(r.enabled!==false)+'">'+(r.enabled===false?'○':'●')+'</button><span><strong>'+esc(r.name||METRICS[r.metric]?.label||r.metric)+'</strong><small>'+esc((r.scope==='watch'?'Watchlist':'Core + Liquid')+' · '+(METRICS[r.metric]?.label||r.metric)+' '+r.op+' '+r.value+(METRICS[r.metric]?.unit||''))+'</small></span><button type="button" data-alert-delete="'+esc(r.id)+'" aria-label="Xóa">×</button></div>').join(''):'<p class="alert-empty">Chưa có bộ lọc/cảnh báo đã lưu.</p>';
}
function renderHits(){
 const host=$('alert-hits');if(!host)return;
 host.innerHTML=state.hits.length?state.hits.slice(0,20).map(h=>'<button type="button" class="alert-hit" data-alert-symbol="'+esc(h.symbol)+'"><span><strong>'+esc(h.symbol)+'</strong> · '+esc(h.ruleName)+'</span><small>'+esc(h.valueText)+' · '+new Date(h.at).toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'})+'</small></button>').join(''):'<p class="alert-empty">Chưa có điều kiện nào vừa được kích hoạt.</p>';
}
function render(){renderRules();renderHits();const s=$('alert-center-status');if(s)s.textContent=state.rules.length?state.rules.filter(x=>x.enabled!==false).length+' rule đang theo dõi trên trình duyệt này':'Thiết lập được lưu cục bộ trên trình duyệt.';}
function ctx(){return window.FinancialMarket?.alertContext?.()||null;}
function evaluate(){
 const c=ctx();if(!c)return;const scanner=window.FinTechnicalScanner?.allContext?.()||{},rows=scanner.symbols||{},watch=new Set(c.watch||[]),now=Date.now(),newHits=[];
 for(const r of state.rules){if(r.enabled===false)continue;const metric=METRICS[r.metric];if(metric?.scanner&&!scanner.unlocked)continue;
  for(const company of c.companies||[]){const symbol=company.symbol;if(r.scope==='watch'&&!watch.has(symbol))continue;const q=c.quotes?.[symbol],row=rows[symbol];if(!q)continue;const v=valueFor(r.metric,q,row);if(!Number.isFinite(v)||!cmp(v,r.op,Number(r.value)))continue;
   const stamp=q.sourceTime||q.collectedAt||'';const key=r.id+'|'+symbol+'|'+stamp;if(state.lastKeys.has(key)||state.hits.some(h=>h.key===key))continue;state.lastKeys.add(key);
   newHits.push({key,symbol,ruleName:r.name||metric.label,valueText:metric.label+' '+v.toLocaleString('vi-VN',{maximumFractionDigits:2})+(metric.unit||''),at:now});
  }
 }
 if(newHits.length){state.hits=[...newHits,...state.hits].slice(0,80);save();render();}
}
function addRule(e){e.preventDefault();const metric=$('alert-metric')?.value,op=$('alert-op')?.value,value=Number($('alert-value')?.value),scope=$('alert-scope')?.value||'all',name=String($('alert-name')?.value||'').trim();if(!METRICS[metric]||!Number.isFinite(value))return;state.rules.unshift({id:String(Date.now())+Math.random().toString(16).slice(2),metric,op,value,scope,name:name||METRICS[metric].label,enabled:true});save();render();evaluate();if($('alert-name'))$('alert-name').value='';}
load();render();
$('alert-form')?.addEventListener('submit',addRule);
$('alert-rules')?.addEventListener('click',e=>{const d=e.target.closest('[data-alert-delete]'),t=e.target.closest('[data-alert-toggle]');if(d){state.rules=state.rules.filter(r=>r.id!==d.dataset.alertDelete);save();render();return;}if(t){const r=state.rules.find(x=>x.id===t.dataset.alertToggle);if(r)r.enabled=r.enabled===false;save();render();evaluate();}});
$('alert-hits')?.addEventListener('click',e=>{const b=e.target.closest('[data-alert-symbol]');if(!b)return;const ticker=$('ticker');if(ticker)ticker.value=b.dataset.alertSymbol;$('company-form')?.requestSubmit();document.getElementById('market')?.scrollIntoView({behavior:'smooth',block:'start'});});
document.addEventListener('finquery:market-refresh',evaluate);setInterval(()=>{if(!document.hidden)evaluate();},60000);
window.FinAlertCenter={evaluate,context:()=>({rules:state.rules,hits:state.hits})};
})();