(()=>{
'use strict';
const pct=x=>Number.isFinite(+x)?`${(+x*100).toFixed(1)}%`:'N/A';
const idx=x=>Number.isFinite(+x)?`${Math.round(+x*100)}/100`:'N/A';
function mergeThresholdMetrics(folds,key,base){let tp=0,fp=0,tn=0,fn=0,seen=0;for(const f of folds||[]){const m=f?.[key];if(!m)continue;tp+=+m.tp||0;fp+=+m.fp||0;tn+=+m.tn||0;fn+=+m.fn||0;seen++}if(!seen)return base;const precision=tp+fp?tp/(tp+fp):null,recall=tp+fn?tp/(tp+fn):null,n=tp+fp+tn+fn;return{...base,tp,fp,tn,fn,precision,recall,fpr:fp+tn?fp/(fp+tn):null,f1:precision!=null&&recall!=null&&precision+recall?2*precision*recall/(precision+recall):null,alertRate:n?(tp+fp)/n:null,missRate:tp+fn?fn/(tp+fn):null,thresholdPolicy:'fold-specific calibration-window threshold'}}
function upgradeUi(out){setTimeout(()=>{if(window.__VMEWS_LAST_RESEARCH__!==out)return;const c=out.current||{},r=document.getElementById('researchScore');if(r)r.innerHTML=`<div><span>HISTORICAL RISK PERCENTILE</span><b>${idx(c.ensemble)}</b><small>Current calibrated crash estimate ranked against OOS historical states</small></div><div><span>CALIBRATED 20D CRASH ESTIMATE</span><b>${pct(c.calibratedCrashProbability)}</b><small>OOS historical base rate ${pct(c.baseRate)} · shown separately from the risk index</small></div><div><span>CURRENT RESEARCH RISK INDEX</span><b>${idx(out.currentRisk)}</b><small>Historical percentile plus limited current-context overlay</small></div>`;const cards=[...document.querySelectorAll('#modelGrid .metric')],notes=['Calibrated structural event estimate','Calibrated Random Forest event estimate','Calibrated ANFIS event estimate','Calibrated regime event estimate','Calibrated VAE anomaly-to-event estimate','Calibrated LSTM crash estimate','LSTM rebound sequence score; separate outcome'];cards.forEach((el,i)=>{const s=el.querySelector('small');if(s&&notes[i])s.textContent=notes[i]});const nm=document.getElementById('newsMeta');if(nm&&out.news){const cov=out.news.coverage;nm.textContent=`${out.news.articleCount||0} unique headlines · ${out.news.sourceCount||0} publishers · NLP risk ${out.news.score==null?'N/A':Math.round(out.news.score)+'/100'}${cov?` · coverage ${cov.coverageGrade||'audited'}`:''} · weighted statistical NLP baseline`}},60)}
function patch(){
  if(!window.VMEWSResearch||window.VMEWSResearch.__runtimePatched)return false;
  const base=window.VMEWSResearch.run.bind(window.VMEWSResearch);
  window.VMEWSResearch.run=async(detail,onProgress)=>{
    if(window.tf){try{if(tf.getBackend()!=='cpu')await tf.setBackend('cpu');await tf.ready()}catch(_){ }}
    const out=await base(detail,onProgress),v=out?.validation;
    if(v?.status==='OK'&&v.aggregate){for(const k of ['ensemble','structural','rf','anfis','regime','vae','lstm'])if(v.aggregate[k])v.aggregate[k]=mergeThresholdMetrics(v.folds,k,v.aggregate[k]);v.thresholdGovernance='Each OOS fold is classified with a threshold selected only on its preceding chronological calibration window; aggregate confusion metrics sum those fold decisions.'}
    window.__VMEWS_LAST_RESEARCH__=out;upgradeUi(out);return out;
  };
  window.VMEWSResearch.__runtimePatched=true;return true;
}
if(!patch())window.addEventListener('DOMContentLoaded',()=>{let n=0;const t=setInterval(()=>{if(patch()||++n>80)clearInterval(t)},50)});
})();
