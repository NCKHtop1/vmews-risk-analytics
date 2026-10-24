(function(){'use strict';
/* One task per workspace. Tabs hide other panels without destroying state. */
const $=id=>document.getElementById(id);
const allowed={
 market:['stocks','futures','ownership','news'],
 macro:['overview','on','vbma','swap','esg']
};
const state={market:'stocks',macro:'overview'};
function activate(kind,value,focus=false){
 if(!allowed[kind]?.includes(value))return false;
 const root=$(kind==='market'?'market-primary-tabs':'macro-primary-tabs');
 if(!root)return false;
 state[kind]=value;
 const buttons=[...root.querySelectorAll('[role="tab"]')];
 for(const b of buttons){
  const active=b.dataset[kind==='market'?'marketSpace':'macroSpace']===value;
  b.classList.toggle('active',active);
  b.setAttribute('aria-selected',String(active));
  b.tabIndex=active?0:-1;
  if(active&&focus)b.focus({preventScroll:true});
 }
 if(kind==='market'){
  const market=$('market');if(market)market.dataset.marketSpace=value;
  const grid=$('market-stock-view');
  if(grid)grid.hidden=value==='futures'||value==='ownership';
  const futures=$('market-futures-workspace'),owners=$('market-ownership-workspace');
  if(futures)futures.hidden=value!=='futures';
  if(owners)owners.hidden=value!=='ownership';
  // Underlying stock-chart and quotes stay mounted; no loss of state.
  if(value==='stocks')requestAnimationFrame(()=>window.dispatchEvent(new Event('resize')));
  if(value==='futures')window.FinDerivativeQuotes?.refresh?.();
  if(value==='ownership')window.FinOwnership?.refresh?.();
 }else{
  for(const id of allowed.macro){
   const panel=$('macro-panel-'+id);
   if(panel)panel.hidden=id!==value;
  }
  if(value==='on'||value==='vbma'||value==='swap')window.FinLiquidityDerivatives?.refresh?.();
  requestAnimationFrame(()=>window.dispatchEvent(new Event('resize')));
 }
 return true;
}
function bind(kind){
 const root=$(kind==='market'?'market-primary-tabs':'macro-primary-tabs');
 if(!root)return;
 const key=kind==='market'?'marketSpace':'macroSpace';
 root.addEventListener('click',e=>{
  const b=e.target.closest?.('[role="tab"]');
  if(!b||!root.contains(b))return;
  activate(kind,b.dataset[key]);
 });
 root.addEventListener('keydown',e=>{
  if(!['ArrowRight','ArrowLeft','Home','End'].includes(e.key))return;
  const current=allowed[kind].indexOf(state[kind]);
  let next=e.key==='Home'?0:e.key==='End'?allowed[kind].length-1:
    (current+(e.key==='ArrowRight'?1:-1)+allowed[kind].length)%allowed[kind].length;
  e.preventDefault();activate(kind,allowed[kind][next],true);
 });
}
bind('market');bind('macro');activate('market','stocks');activate('macro','overview');
window.FinWorkspaceTabs={openMarket:key=>activate('market',key),openMacro:key=>activate('macro',key),current:()=>({...state})};
})();