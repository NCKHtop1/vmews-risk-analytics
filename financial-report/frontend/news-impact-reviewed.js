/* FinQuery evidence review: conservative, no notification based on news relevance. */
(function(root){
'use strict';
const SCHEMA='FINQUERY_NEWS_IMPACT_REVIEW_V1';
const REQUIRED=['HISTORICAL_SECTOR_MEMBERSHIP_NOT_POINT_IN_TIME','HISTORICAL_FIRST_SEEN_NOT_COLLECTOR_CERTIFIED','NO_INDEPENDENT_ISSUER_SPECIFIC_IMPACT_EVIDENCE','NO_FORWARD_PROSPECTIVE_IMPACT_STUDY','HISTORICAL_PRE_NEWS_CONFOUNDING'];
const state={status:'LOADING',manifest:null,shadow:null};
const SHADOW_SCHEMA='FINQUERY_HYBRID_NEWS_IMPACT_SHADOW_V2';
function inspectRelease(raw){
 if(!raw||raw.schema!==SCHEMA||raw.status!=='RESEARCH_ONLY'||raw.notificationsEnabled!==false||raw.historicalImpactCertified!==false)return null;
 if(!Array.isArray(raw.verifiedImpacts)||raw.verifiedImpacts.length!==0)return null;
 if(!Array.isArray(raw.blockers)||REQUIRED.some(x=>!raw.blockers.includes(x)))return null;
 const n=raw.research||{};
 if(n.retrospectiveTickerCohorts!==0||n.historicalCollectorReceipts!==0||!Number.isInteger(n.independentEpisodes)||n.independentEpisodes<0)return null;
 if(!/^\d{4}-\d{2}-\d{2}$/.test(String(raw.reviewAsOf||'')))return null;
 return {status:'RESEARCH_ONLY',reviewAsOf:raw.reviewAsOf,eligibleCount:0,independentEpisodes:n.independentEpisodes};
}
function inspectShadow(raw,clock=Date.now()){
 if(!raw||raw.schema!==SHADOW_SCHEMA||raw.status!=='SHADOW_ONLY')return null;
 const count=raw.counts||{},p=raw.publicationPolicy||{},t=Date.parse(raw.checkedAt||'');
 if(!Number.isFinite(t)||t>clock+5*60000||clock-t>120*60000)return null;
 if(p.killSwitch!=='LOCKED_OFF'||p.verifiedTickerAlerts!==false||
    p.verifiedSectorAlerts!==false||p.noAlertFromSentimentOrNewsPriority!==true)return null;
 if(count.eligibleNotifications!==0||count.verifiedImpactRelations!==0)return null;
 const fields=['deduplicatedStories','classifiedEventStories','directIssuerMentionStories',
               'storiesWithEligibleBusinessFacts','storiesWithoutCertifiedCollectorTime'];
 if(fields.some(key=>!Number.isInteger(count[key])||count[key]<0))return null;
 if(count.classifiedEventStories>count.deduplicatedStories||count.storiesWithEligibleBusinessFacts>count.classifiedEventStories)return null;
 return{checkedAt:raw.checkedAt,classifiedEventStories:count.classifiedEventStories,
        storiesWithEligibleBusinessFacts:count.storiesWithEligibleBusinessFacts,
        directIssuerMentionStories:count.directIssuerMentionStories,
        withoutCollectorTime:count.storiesWithoutCertifiedCollectorTime,
        prospectiveLedgerRecords:Number.isInteger(count.prospectiveLedgerRecords)&&count.prospectiveLedgerRecords>=0&&count.prospectiveLedgerRecords<=8000?count.prospectiveLedgerRecords:null};
}
function summary(){return{...(state.manifest||{status:state.status,eligibleCount:0,reviewAsOf:null}),shadow:state.shadow};}
function canNotify(){return false;} // Intentionally requires a separate reviewed code release.
function reviewedImpacts(){return [];} // Never import labels from newsPriority or RSS feed.
async function load(){
 if(typeof root.location==='undefined'||typeof root.fetch!=='function')return summary();
 try{
  const rel=String(root.location.pathname||'').includes('/frontend/')?'../data/':'data/';
  const url=new URL(rel+'news-impact-reviewed.json',root.location.href);
  const response=await root.fetch(url.href,{cache:'no-store'});
  if(!response.ok)throw Error('Impact review manifest not available');
  const reviewed=inspectRelease(await response.json());
  state.manifest=reviewed;
  state.status=reviewed?'RESEARCH_ONLY':'INVALID';
 }catch(_error){state.status='UNAVAILABLE';state.manifest=null;}
 state.shadow=null;
 if(state.manifest&&root.FinMarketData&&typeof root.FinMarketData.get==='function'){
  try{
   const candidate=await root.FinMarketData.get('news-impact-shadow-v2.json',{timeout:8500});
   state.shadow=inspectShadow(candidate);
  }catch(_error){state.shadow=null;}
 }
 if(root.document&&typeof root.CustomEvent==='function'){
  root.document.dispatchEvent(new root.CustomEvent('finquery:news-impact-review-ready'));
 }
 return summary();
}
const api={inspectRelease,inspectShadow,summary,canNotify,reviewedImpacts,load};
if(root&&root.document){root.FinNewsImpactReview=api;void load();}
if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window!=='undefined'?window:{});
