const fs=require('fs');
const model=JSON.parse(fs.readFileSync('data/forecast-model-v10.json','utf8'));
const news=JSON.parse(fs.readFileSync('data/research-news-v10.json','utf8'));
const sent=JSON.parse(fs.readFileSync('data/sentiment-v10.json','utf8'));
const ev=JSON.parse(fs.readFileSync('data/news-event-study.json','utf8'));
const html=fs.readFileSync('forecast-final.html','utf8'),ui=fs.readFileSync('forecast-final-v10.js','utf8');
if(model.version!=='VMEWS-FORECAST-10.0.0'||model.promotion?.status!=='PASS')throw Error('model');
if(model.universe?.symbols<250||model.universe?.rows<100000)throw Error('HOSE universe coverage');
if(model.governance?.crossSectionalFeaturesInNumericalModel!==false)throw Error('parity');
for(const h of ['3','5']){const z=model.horizons[h];if(z.status!=='PASS'||!z.gates.rankingApproved||!z.gates.bucketApproved||!z.sealedAudit?.bootstrap?.ic95)throw Error('audit '+h)}
if(news.version!=='VMEWS-NEWS-10.0.0'||news.universe<300||news.coverage?.FRT?.used<5)throw Error('news');
if(sent.version!=='VMEWS-SENTIMENT-10.0.0'||!sent.symbols?.FRT)throw Error('sentiment');
if(ev.version!=='VMEWS-NEWS-EVENT-STUDY-1.1.0'||ev.events<50||ev.pointInTimeEligibleForForecast!==false||!ev.rumorStudy?.preEvent?.['2'])throw Error('events');
for(const s of ['Đọc hướng đi ngắn hạn cùng trạng thái rủi ro','Hệ thống tách riêng khả năng xếp hạng tương đối','Mô hình chỉ vẽ các horizon','Khối ngoại / tự doanh'])if(html.includes(s))throw Error('copy');
if(ui.includes('/flow?')||ui.includes('P(tăng)'))throw Error('deprecated-ui');
if(!ui.includes("x!==null&&x!==undefined&&x!==''")||!ui.includes('Math.abs(z)>.22')||!ui.includes('displayClose'))throw Error('chart-guard');
console.log(JSON.stringify({ok:true,model:model.version,symbols:model.universe.symbols,rows:model.universe.rows,featureCount:model.featureNames.length,T3:model.horizons['3'].sealedAudit,T5:model.horizons['5'].sealedAudit,FRTNews:news.coverage.FRT,eventStudy:ev.events,rumorStudy:ev.rumorStudy}));
