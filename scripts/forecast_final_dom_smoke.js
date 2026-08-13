const fs=require('fs');
const {JSDOM}=require('jsdom');
const html=fs.readFileSync('forecast-final.html','utf8');
const model=JSON.parse(fs.readFileSync('data/forecast-model-v4.json','utf8'));
const news=JSON.parse(fs.readFileSync('data/research-news.json','utf8'));
let payload=null;
for(const s of ['PNJ','HPG','VCB','FPT','MWG','DGC','SSI']){for(const dir of ['data/deep-alerts','data/hose-fallbacks']){const p=`${dir}/${s}.json`;if(fs.existsSync(p)){const d=JSON.parse(fs.readFileSync(p,'utf8'));if((d.history||[]).length>=520){payload={...d,symbol:'FPT'};break}}}if(payload)break}
if(!payload)throw new Error('no local detail payload');
const dom=new JSDOM(html,{url:'https://example.test/forecast-final.html?symbol=FPT',runScripts:'outside-only',pretendToBeVisual:true});
const w=dom.window;
w.HTMLCanvasElement.prototype.getBoundingClientRect=()=>({width:1000,height:420,left:0,top:0,right:1000,bottom:420});
w.HTMLCanvasElement.prototype.getContext=()=>({setTransform(){},clearRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){},fill(){},closePath(){},arc(){},fillText(){},setLineDash(){}});
w.devicePixelRatio=1;
w.fetch=async url=>{const u=String(url);let body;if(u.includes('forecast-model-v4.json'))body=model;else if(u.includes('research-news.json'))body=news;else if(u.includes('/radar?')||u.includes('/stocks?'))body=payload;else return{ok:false,status:404,json:async()=>({})};return{ok:true,status:200,json:async()=>body}};
w.eval(fs.readFileSync('forecast-v4-core.js','utf8'));
w.eval(fs.readFileSync('forecast-final-v5.js','utf8'));
setTimeout(()=>{const e=w.document.querySelector('#error'),stance=w.document.querySelector('#stance').textContent.trim(),chart=w.document.querySelector('#chartTitle').textContent.trim(),newsText=w.document.querySelector('#news').textContent.trim();if(!e.classList.contains('hidden')||e.textContent.trim())throw new Error(`frontend error: ${e.textContent}`);if(!stance||stance.includes('Đang tính'))throw new Error('recommendation did not render');if(!chart.includes('Giá thực tế'))throw new Error('chart did not render');if(!newsText)throw new Error('news did not render');if(/FPT Retail|Long Châu|FPT Shop/.test(newsText))throw new Error('sibling news leaked');console.log(JSON.stringify({ok:true,stance,chart,newsPreview:newsText.slice(0,160)}))},100);
