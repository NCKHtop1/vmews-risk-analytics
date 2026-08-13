const fs=require('fs');global.window=global;require('../forecast-v4-core.js');
const model=JSON.parse(fs.readFileSync('data/forecast-model-v4.json','utf8'));
if(model.promotion?.status!=='PASS')throw new Error('model promotion is not PASS');
const candidates=['PNJ','HPG','VCB','FPT','MWG','DGC','SSI'];let payload=null,symbol=null;
for(const s of candidates){for(const dir of ['data/deep-alerts','data/hose-fallbacks']){const p=`${dir}/${s}.json`;if(fs.existsSync(p)){const d=JSON.parse(fs.readFileSync(p,'utf8'));if((d.history||[]).length>=520){payload=d;symbol=s;break}}}if(payload)break}
if(!payload)throw new Error('no local stock cache with >=520 sessions');
const built=VMEWSForecastV4.features(payload.history);if(!built.fs.length)throw new Error('feature build failed');
const fc=VMEWSForecastV4.forecast(model,built.fs.at(-1),payload);for(const h of [3,4,5]){if(!fc[h]||![fc[h].value,fc[h].low,fc[h].high].every(Number.isFinite))throw new Error(`invalid T+${h} forecast`);if(fc[h].low>fc[h].high)throw new Error(`invalid T+${h} interval`)}
const an=VMEWSForecastV4.analog(built.rows,built.fs);const ns=VMEWSForecastV4.sentiment(payload.news||[]);const rec=VMEWSForecastV4.recommend(fc,payload,an,ns);if(!rec?.label||!rec?.text)throw new Error('recommendation failed');
const html=fs.readFileSync('forecast-v4.html','utf8');for(const id of ['symbol','run','stance','reason','confidence','last','r3','r5','risk','chart','h3','h4','h5','market','macro','sentiment','fund','analog','bt','news','contextDetail'])if(!html.includes(`id="${id}"`))throw new Error(`missing DOM id ${id}`);
for(const banned of ['1 · BUILD','2 · PURGE','3 · COMPETE','4 · AUDIT','AR-Ridge','VMEWS-Ridge'])if(html.includes(banned))throw new Error(`internal methodology leaked: ${banned}`);
console.log(JSON.stringify({ok:true,symbol,rows:payload.history.length,model:model.version,promotion:model.promotion,forecast:{t3:fc[3].value,t4:fc[4].value,t5:fc[5].value},recommendation:rec.label}));