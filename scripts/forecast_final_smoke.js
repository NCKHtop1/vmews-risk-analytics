const fs=require('fs'),crypto=require('crypto');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const model=read('data/forecast-model-v9.json');
if(model.version!=='VMEWS-FORECAST-9.0.0'||model.promotion?.status!=='PASS')throw Error('V9 contract');
if((model.universe?.rows||0)<80000||(model.universe?.symbols||0)<50)throw Error('V9 panel');
for(const h of ['3','5']){const z=model.horizons[h];if(z.status!=='PASS'||!z.gates.rankingApproved||!z.gates.directionApproved)throw Error('V9 gate '+h);if(z.gates.positiveRecommendationApproved||z.gates.negativeRecommendationApproved)throw Error('recommendation gate '+h);}
const html=fs.readFileSync('forecast-final.html','utf8'),ui=fs.readFileSync('forecast-final-v5.js','utf8');
for(const id of ['symbol','run','error','stance','chart','interestList','yellowList','redList','detailBtn','pup3','pup5'])if(!html.includes(`id="${id}"`))throw Error('DOM '+id);
for(const s of ['forecast-model-v9.json','sentiment-v8.json','/flow?'])if(!ui.includes(s))throw Error('UI source '+s);
const sent=read('data/sentiment-v8.json'),fpt=sent.symbols?.FPT;
if(sent.version!=='VMEWS-SENTIMENT-8.0.1'||Object.keys(sent.symbols||{}).length<20||!fpt?.available||fpt.n<10)throw Error('sentiment contract');
const live=read('data/forecast-live/integrity.json'),ev=read('data/forecast-live/evaluation.json'),mf=read('data/forecast-live/manifest.json');
if(live.version!=='VMEWS-FORECAST-LIVE-1.0.0'||live.status!=='PASS'||live.modelVersion!=='VMEWS-FORECAST-9.0.0'||live.symbols<8||mf.count<1)throw Error('live contract');
for(const x of mf.snapshots){const raw=fs.readFileSync(x.file),z=JSON.parse(raw);if(crypto.createHash('sha256').update(raw).digest('hex')!==x.sha256||z.snapshotHash!==x.snapshotHash||z.governance.futureLabelsPresent!==false||z.governance.automaticPromotion!==false)throw Error('live hash/governance '+x.file);}
for(const h of ['3','5'])if(!['IMMATURE','EARLY','MATURE'].includes(ev.summary[h].evidenceState))throw Error('live evidence '+h);
const risk=read('data/live-track/integrity.json');if(!['PASS','WAITING_OR_REVIEW'].includes(risk.status)||risk.marketContextImputed!==false)throw Error('risk live contract');
console.log(JSON.stringify({ok:true,model:model.version,rows:model.universe.rows,symbols:model.universe.symbols,sentiment:sent.version,sentimentSymbols:Object.keys(sent.symbols).length,forecastLive:{asOf:live.asOf,coverage:live.coverageState,symbols:live.symbols,T3:ev.summary['3'].evidenceState,T5:ev.summary['5'].evidenceState},riskLive:risk.status}));
