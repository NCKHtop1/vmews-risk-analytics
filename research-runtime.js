(()=>{
'use strict';
function patch(){
  if(!window.VMEWSResearch||window.VMEWSResearch.__runtimePatched)return false;
  const base=window.VMEWSResearch.run.bind(window.VMEWSResearch);
  window.VMEWSResearch.run=async(detail,onProgress)=>{
    if(window.tf){
      try{
        if(tf.getBackend()!=='cpu')await tf.setBackend('cpu');
        await tf.ready();
      }catch(_){ }
    }
    return base(detail,onProgress);
  };
  window.VMEWSResearch.__runtimePatched=true;
  return true;
}
if(!patch())window.addEventListener('DOMContentLoaded',()=>{let n=0;const t=setInterval(()=>{if(patch()||++n>80)clearInterval(t)},50)});
})();
