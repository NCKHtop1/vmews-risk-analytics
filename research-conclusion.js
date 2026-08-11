(()=>{
'use strict';
const mean=a=>a.length?a.reduce((s,x)=>s+x,0)/a.length:0;
const sd=a=>{if(a.length<2)return 0;const m=mean(a);return Math.sqrt(a.reduce((s,x)=>s+(x-m)**2,0)/(a.length-1))};
const fmt=x=>Number.isFinite(+x)?Math.round(+x*100):null;
function validationLabel(m){const a=+m?.auc,p=+m?.precision,r=+m?.recall;if(!Number.isFinite(a))return'INSUFFICIENT';if(a>=.70&&p>=.35&&r>=.35)return'STRONG';if(a>=.60)return'MODERATE';if(a>=.52)return'LIMITED';return'WEAK'}
function assess(out){const c=out.current||{},vals=[c.structural,c.randomForest,c.anfis,c.regime,c.vae,c.lstmCrash].filter(Number.isFinite),ens=out.validation?.aggregate?.ensemble||null,v=validationLabel(ens),risk=+out.currentRisk||+c.ensemble||0,high=vals.filter(x=>x>=.55).length,low=vals.filter(x=>x<=.35).length,spread=sd(vals),consensus=vals.length?high/vals.length:0;
 let band=risk>=.70?'HIGH':risk>=.55?'ELEVATED':risk>=.40?'WATCH':'LOW';
 let action='Routine monitoring';
 if((band==='HIGH'||band==='ELEVATED')&&(v==='STRONG'||v==='MODERATE'))action='Escalate for formal risk review';
 else if(band==='HIGH'||band==='ELEVATED')action='Monitor closely; signal strength exceeds validation quality';
 else if(v==='WEAK')action='Use as screening evidence only; validation is weak for this security';
 const text=`Current research risk is ${Math.round(risk*100)}/100 (${band}). ${high} of ${vals.length} historical models are above the elevated-risk threshold. Ensemble validation is ${v.toLowerCase()}${Number.isFinite(+ens?.auc)?` (AUC ${(+ens.auc).toFixed(2)})`:''}. ${action}.`;
 return {risk,band,validation:v,action,text,modelCount:vals.length,elevatedModels:high,lowModels:low,consensus,dispersion:spread,ensembleMetrics:ens};
}
function render(a){const root=document.getElementById('researchConclusion');if(!root)return;root.innerHTML=`<div class="eyebrow">RESEARCH CONCLUSION</div><div class="conclusionGrid"><div><span>Current risk</span><b>${Math.round(a.risk*100)}/100 · ${a.band}</b></div><div><span>Validation quality</span><b>${a.validation}</b></div><div><span>Model agreement</span><b>${a.elevatedModels}/${a.modelCount} elevated</b></div><div><span>Risk-review use</span><b>${a.action}</b></div></div><p>${a.text}</p><small>This conclusion summarizes model evidence and validation quality. It is a research control, not an investment recommendation.</small>`}
function patch(){const R=window.VMEWSResearch;if(!R||R.__conclusionPatched)return false;const base=R.run.bind(R);R.run=async(...args)=>{const out=await base(...args);out.conclusion=assess(out);window.__VMEWS_LAST_RESEARCH__=out;render(out.conclusion);return out};R.__conclusionPatched=true;return true}
if(!patch())window.addEventListener('DOMContentLoaded',()=>{let n=0;const t=setInterval(()=>{if(patch()||++n>120)clearInterval(t)},50)});
})();
