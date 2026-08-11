(()=>{
'use strict';
const NEWS='https://cdn.githubraw.com/NCKHtop1/vmews-risk-analytics/main/data/research-news.json';
const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x));
let snapP=null;
const snapshot=()=>snapP||(snapP=fetch(`${NEWS}?t=${Date.now()}`,{cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null));
function vw(m){
  const a=Number(m?.auc),p=Number(m?.precision),r=Number(m?.recall);
  if(!Number.isFinite(a))return .15;
  let w=a>=.65?1:a>=.58?.75:a>=.52?.45:a>=.48?.20:.08;
  if((Number.isFinite(p)&&p===0)&&(Number.isFinite(r)&&r===0))w*=.4;
  return w;
}
function vlabel(m){const a=Number(m?.auc);return !Number.isFinite(a)?'INSUFFICIENT':a>=.65?'STRONG':a>=.58?'MODERATE':a>=.52?'LIMITED':'WEAK'}
function newsFactor(c){if(!c)return .15;const n=+c.used||0,p=+c.publishers||0;return clamp(.65*clamp(n/40)+.35*clamp(p/8),.1,1)}
function weighted(rows){let n=0,d=0;for(const [v,w] of rows)if(Number.isFinite(+v)&&w>0){n+=+v*w;d+=w}return d?n/d:null}
function assess(out,detail,cov){
  const c=out.current||{},v=out.validation?.aggregate||{};
  const models=[
    ['Structural EWS',c.structural,v.structural],['Random Forest',c.randomForest,v.rf],['ANFIS',c.anfis,v.anfis],['VAE anomaly',c.vae,v.vae],['LSTM crash',c.lstmCrash,v.lstm]
  ].map(([name,value,metric])=>({name,value:+value,metric,weight:vw(metric),validation:vlabel(metric)}));
  if(Number.isFinite(+c.regime))models.push({name:'Regime model',value:+c.regime,metric:null,weight:.20,validation:'UNVALIDATED_COMPONENT'});
  const accepted=models.filter(x=>Number.isFinite(x.value)&&x.weight>=.15);
  const validatedRisk=weighted(accepted.map(x=>[x.value,x.weight]));
  const nf=newsFactor(cov),m=detail?.modules||{},fund=out.fundamental||m.fundamental;
  const contextRows=[];
  if(m.market?.available!==false&&Number.isFinite(+m.market?.score))contextRows.push([+m.market.score/100,.30]);
  if(m.macro?.available!==false&&Number.isFinite(+m.macro?.score))contextRows.push([+m.macro.score/100,.20]);
  if(out.news?.score!=null)contextRows.push([+out.news.score/100,.25*nf]);
  if(fund?.available!==false&&Number.isFinite(+fund?.score))contextRows.push([+fund.score/100,.25*(fund?.sector==='Bank'?.7:1)]);
  const context=weighted(contextRows);
  const ensMetric=v.ensemble||null,vl=vlabel(ensMetric),auc=Number(ensMetric?.auc);
  const sessions=+out.data?.sessions||0,samples=+out.data?.samples||0;
  const historyFactor=.55*clamp(sessions/1200)+.45*clamp(samples/140);
  const validationFactor=!Number.isFinite(auc)?.25:clamp((auc-.45)/.25,.1,1);
  const marketFactor=m.market?.available===false?0:1;
  const fundFactor=fund?.available===false?0:(fund?.sector==='Bank'?.7:1);
  let suff=100*(.32*validationFactor+.23*historyFactor+.15*marketFactor+.15*nf+.15*fundFactor);
  let grade=suff>=78?'STRONG':suff>=62?'MODERATE':suff>=45?'LIMITED':'THIN';
  if(vl==='WEAK'&&grade==='STRONG')grade='LIMITED';
  if(vl==='WEAK'&&grade==='MODERATE')grade='LIMITED';
  const contextWeight=grade==='STRONG'?.20:grade==='MODERATE'?.15:grade==='LIMITED'?.10:.05;
  const currentRisk=validatedRisk==null?(out.currentRisk||0):context==null?validatedRisk:(1-contextWeight)*validatedRisk+contextWeight*context;
  const band=currentRisk>=.70?'HIGH':currentRisk>=.55?'ELEVATED':currentRisk>=.40?'WATCH':'LOW';
  let use='Routine monitoring';
  if((band==='HIGH'||band==='ELEVATED')&&(vl==='STRONG'||vl==='MODERATE')&&(grade==='STRONG'||grade==='MODERATE'))use='Escalate for formal risk review';
  else if(vl==='WEAK')use='Screening evidence only; security-level validation is weak';
  else if(grade==='THIN'||grade==='LIMITED')use='Monitor; evidence coverage is not sufficient for strong escalation';
  return {models,validatedRisk,rawEnsemble:c.ensemble,context,currentRisk,band,validation:vl,evidenceGrade:grade,evidenceScore:suff,newsFactor:nf,newsCoverage:cov||null,use};
}
function render(out,a){
  const root=document.getElementById('researchConclusion');
  if(root)root.innerHTML=`<div class="eyebrow">RESEARCH CONCLUSION</div><div class="conclusionGrid"><div><span>Validation-aware risk</span><b>${Math.round(a.currentRisk*100)}/100 · ${a.band}</b></div><div><span>Evidence sufficiency</span><b>${a.evidenceGrade} · ${Math.round(a.evidenceScore)}/100</b></div><div><span>Validation quality</span><b>${a.validation}</b></div><div><span>Risk-review use</span><b>${a.use}</b></div></div><p>Model contributions are weighted by out-of-sample validation. Weak models are down-weighted rather than treated as equally reliable. News contribution is scaled by independent headline and publisher coverage.</p><small>Risk scores are research indicators, not calibrated probabilities or investment recommendations.</small>`;
  const meta=document.getElementById('newsMeta'),c=a.newsCoverage;
  if(meta&&c)meta.textContent=`${c.used||0} unique headlines used · ${c.publishers||0} publishers · ${c.material||0} material events · coverage ${c.coverageGrade} · NLP risk ${out.news?.score==null?'N/A':Math.round(out.news.score)+'/100'}`;
  const audit=document.getElementById('dataAudit');
  if(audit&&c&&!audit.querySelector('[data-news-audit]'))audit.insertAdjacentHTML('beforeend',`<span data-news-audit>News pipeline <b>${c.collected||0}→${c.relevant||0}→${c.unique||0}→${c.used||0}</b></span><span data-news-audit>News coverage <b>${c.coverageGrade}</b></span>`);
}
function patch(){
  const R=window.VMEWSResearch;if(!R||R.__evidencePatched)return false;const base=R.run.bind(R);
  R.run=async(detail,onProgress)=>{const [out,s]=await Promise.all([base(detail,onProgress),snapshot()]);const cov=s?.coverage?.[String(detail?.symbol||'').toUpperCase()]||null;const a=assess(out,detail,cov);out.trust=a;out.current.rawEnsemble=out.current.ensemble;out.current.ensemble=a.validatedRisk??out.current.ensemble;out.context=a.context??out.context;out.currentRisk=a.currentRisk;out.news.coverage=cov;setTimeout(()=>render(out,a),0);return out};
  R.__evidencePatched=true;return true;
}
if(!patch())window.addEventListener('DOMContentLoaded',()=>{let n=0;const t=setInterval(()=>{if(patch()||++n>120)clearInterval(t)},50)});
})();
