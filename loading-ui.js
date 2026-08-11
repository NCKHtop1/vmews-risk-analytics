(()=>{
const STYLE=`
#vmewsBusy{position:fixed;right:22px;bottom:22px;z-index:9999;display:none;align-items:center;gap:12px;padding:12px 16px;border:1px solid rgba(72,217,255,.28);border-radius:12px;background:rgba(5,17,28,.94);box-shadow:0 14px 40px rgba(0,0,0,.35);backdrop-filter:blur(12px);font:12px/1.35 ui-monospace,SFMono-Regular,Consolas,monospace;color:#d9f7ff;max-width:min(420px,calc(100vw - 32px))}
#vmewsBusy.show{display:flex}
#vmewsBusy .spin{width:20px;height:20px;border:2px solid rgba(72,217,255,.18);border-top-color:#48d9ff;border-radius:50%;animation:vmewsSpin .75s linear infinite;flex:0 0 auto}
#vmewsBusy b{display:block;color:#fff;font-size:12px;margin-bottom:2px}#vmewsBusy small{color:#8ca9bc}
.vmews-running{position:relative;pointer-events:none;opacity:.76}.vmews-running::before{content:'';display:inline-block;width:12px;height:12px;margin-right:8px;vertical-align:-2px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:vmewsSpin .7s linear infinite}
@keyframes vmewsSpin{to{transform:rotate(360deg)}}
`;
const style=document.createElement('style');style.textContent=STYLE;document.head.appendChild(style);
const busy=document.createElement('div');busy.id='vmewsBusy';busy.setAttribute('role','status');busy.setAttribute('aria-live','polite');busy.innerHTML='<span class="spin"></span><div><b>VMEWS is running</b><small id="vmewsBusyText">Loading market data and risk modules…</small></div>';document.body.appendChild(busy);
let active=0,hideTimer=null;
function start(msg,btn){
  active++;clearTimeout(hideTimer);busy.classList.add('show');document.getElementById('vmewsBusyText').textContent=msg||'Loading market data and risk modules…';
  if(btn){btn.dataset.vmewsLabel=btn.textContent;btn.classList.add('vmews-running');btn.disabled=true;btn.textContent='Running…'}
}
function stop(btn){
  active=Math.max(0,active-1);if(btn){btn.classList.remove('vmews-running');btn.disabled=false;if(btn.dataset.vmewsLabel)btn.textContent=btn.dataset.vmewsLabel}
  if(!active)hideTimer=setTimeout(()=>busy.classList.remove('show'),350);
}
function bindButton(id,msg){
  document.addEventListener('click',e=>{const btn=e.target.closest('#'+id);if(!btn)return;start(msg,btn);setTimeout(()=>stop(btn),59000)},true);
}
bindButton('radarRefresh','Fetching Vnstock history and ranking the watchlist…');
bindButton('runStockBtn','Loading the selected stock, evidence modules and risk state…');
bindButton('runValidationBtn','Running chronological holdout validation…');
bindButton('fptReplay','Loading FPT point-in-time case…');
bindButton('pnjReplay','Loading PNJ point-in-time case…');
const observer=new MutationObserver(()=>{
  const s=document.getElementById('radarStatus');if(!s)return;
  const text=(s.textContent||'').toLowerCase();
  if(text.includes('requesting')||text.includes('running')||text.includes('loading')){if(!busy.classList.contains('show')){active=1;busy.classList.add('show');document.getElementById('vmewsBusyText').textContent=s.textContent}}
  else if(busy.classList.contains('show')&&(s.classList.contains('ok')||s.classList.contains('error'))){active=0;document.querySelectorAll('.vmews-running').forEach(btn=>{btn.classList.remove('vmews-running');btn.disabled=false;if(btn.dataset.vmewsLabel)btn.textContent=btn.dataset.vmewsLabel});hideTimer=setTimeout(()=>busy.classList.remove('show'),500)}
});
observer.observe(document.documentElement,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['class']});
})();
