const fs=require('fs');
const model=JSON.parse(fs.readFileSync('data/forecast-model-v4.json','utf8'));
if(model.promotion?.status!=='PASS') throw new Error('forecast model is not promoted');
if((model.universe?.rows||0)<50000 || (model.universe?.symbols||0)<50) throw new Error('forecast training panel is unexpectedly small');
const html=fs.readFileSync('forecast-final.html','utf8');
const ui=fs.readFileSync('forecast-final-v5.js','utf8');
for(const id of ['symbol','run','error','stance','reason','confidence','last','r3','p3','r5','p5','risk','riskText','chartTitle','asof','chart','h3','h4','h5','market','marketSub','macro','macroSub','sentiment','sentimentSub','fund','fundSub','analog','analogSub','bt','news','contextDetail']){
  if(!html.includes(`id="${id}"`)) throw new Error(`missing DOM id ${id}`);
}
if(!html.includes('./forecast-v4-core.js') || !html.includes('./forecast-final-v5.js')) throw new Error('final page scripts are not wired');
if(/\.map\(h=>fc\[h\]\)\.filter\(Boolean\)\.map\(z=>\(\{h,/.test(ui)) throw new Error('known chart scope bug reintroduced');
if(!ui.includes('h:fc[h].h') && !ui.includes('h,price:')) throw new Error('forecast horizon is not bound in chart data');
const news=JSON.parse(fs.readFileSync('data/research-news.json','utf8'));
const fpt=news.symbols?.FPT||[];
if(fpt.length<10) throw new Error('FPT research-news coverage too small');
const generated=Date.parse(news.generatedAt||'');
const newest=Math.max(...fpt.map(x=>Date.parse(x.published||'')).filter(Number.isFinite));
if(!Number.isFinite(generated)||!Number.isFinite(newest)||generated-newest>7*86400000) throw new Error('FPT research news is stale');
const bad=fpt.slice(0,10).filter(x=>/FPT Retail/i.test(x.title||''));
console.log(JSON.stringify({ok:true,model:model.version,rows:model.universe.rows,symbols:model.universe.symbols,newsFPT:fpt.length,newestFPT:new Date(newest).toISOString(),top10SiblingNoise:bad.length}));
