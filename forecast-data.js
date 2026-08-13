(()=>{
'use strict';
const API=['/api/ews?mode=full','https://vmews-risk-analytics-sojd.vercel.app/api/ews?mode=full'];
async function load(){let err;for(const url of API){try{const c=new AbortController(),t=setTimeout(()=>c.abort(),45000);const r=await fetch(url+(url.includes('?')?'&':'?')+'t='+Date.now(),{cache:'no-store',signal:c.signal});clearTimeout(t);if(!r.ok)throw Error('HTTP '+r.status);const j=await r.json();if(!Array.isArray(j.rows)||j.rows.length<500)throw Error('Insufficient completed-EOD history');return j}catch(e){err=e}}throw err||Error('EOD data unavailable')}
window.VMEWSForecastData={load};
})();
