(()=>{
'use strict';
function mergeThresholdMetrics(folds,key,base){let tp=0,fp=0,tn=0,fn=0,seen=0;for(const f of folds||[]){const m=f?.[key];if(!m)continue;tp+=+m.tp||0;fp+=+m.fp||0;tn+=+m.tn||0;fn+=+m.fn||0;seen++}if(!seen)return base;const precision=tp+fp?tp/(tp+fp):null,recall=tp+fn?tp/(tp+fn):null,n=tp+fp+tn+fn;return{...base,tp,fp,tn,fn,precision,recall,fpr:fp+tn?fp/(fp+tn):null,f1:precision!=null&&recall!=null&&precision+recall?2*precision*recall/(precision+recall):null,alertRate:n?(tp+fp)/n:null,missRate:tp+fn?fn/(tp+fn):null,thresholdPolicy:'fold-specific calibration-window threshold'}}
function patch(){
  if(!window.VMEWSResearch||window.VMEWSResearch.__runtimePatched)return false;
  const base=window.VMEWSResearch.run.bind(window.VMEWSResearch);
  window.VMEWSResearch.run=async(detail,onProgress)=>{
    if(window.tf){
      try{if(tf.getBackend()!=='cpu')await tf.setBackend('cpu');await tf.ready()}catch(_){ }
    }
    const out=await base(detail,onProgress),v=out?.validation;
    if(v?.status==='OK'&&v.aggregate){
      for(const k of ['ensemble','structural','rf','anfis','regime','vae','lstm'])if(v.aggregate[k])v.aggregate[k]=mergeThresholdMetrics(v.folds,k,v.aggregate[k]);
      v.thresholdGovernance='Each OOS fold is classified with a threshold selected only on its preceding chronological calibration window; aggregate confusion metrics sum those fold decisions.';
    }
    return out;
  };
  window.VMEWSResearch.__runtimePatched=true;
  return true;
}
if(!patch())window.addEventListener('DOMContentLoaded',()=>{let n=0;const t=setInterval(()=>{if(patch()||++n>80)clearInterval(t)},50)});
})();
