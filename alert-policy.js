(()=>{
'use strict';
const FALLBACK={version:'VMEWS-ALERT-POLICY-4.0.0',riskIndexBands:{red:78,yellow:65,watch:50},marketConfirmation:{redMinIndependentStressSignals:3,yellowMinIndependentStressSignals:2,watchMinIndependentStressSignals:1},eligibility:{minCompletedSessionsForStructuralDetail:240,minCompletedSessionsForDeepResearch:420},eventDefinitions:{primaryCrash:{horizonSessions:20,forwardDrawdownThreshold:-.12},primaryRebound:{horizonSessions:20,forwardGainThreshold:.12}},validation:{purgeSessions:20,missedEventCost:2,falseAlertCost:1,minimumOutOfSampleEventsForModerateEvidence:10,minimumOutOfSampleEventsForStrongEvidence:20},corporateActionGuard:{oneDayAbsoluteLogReturnThreshold:.22}};
const URL=new URL('./data/alert-policy.json',location.href).href;
let value=FALLBACK;
const ready=fetch(`${URL}?t=${Date.now()}`,{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(Error(`Alert policy HTTP ${r.status}`))).then(p=>{value=p;return p}).catch(()=>FALLBACK);
window.VMEWSAlertPolicy={get value(){return value},ready,url:URL,fallback:FALLBACK};
})();
