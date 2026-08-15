import { chromium } from 'playwright';

const base=process.env.V12_BROWSER_URL || 'http://127.0.0.1:8000/forecast-final.html?symbol=FPT';
const allowedOrigin=new URL(base).origin;
const browser=await chromium.launch({headless:true});
const errors=[];const failed=[];const external=[];
const page=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
page.on('console',msg=>{if(msg.type()==='error')errors.push(msg.text())});
page.on('pageerror',err=>errors.push(String(err)));
page.on('requestfailed',req=>failed.push(`${req.method()} ${req.url()} ${req.failure()?.errorText||''}`));
page.on('request',req=>{const u=req.url();if(/^https?:/.test(u)&&new URL(u).origin!==allowedOrigin)external.push(u)});
await page.goto(base,{waitUntil:'networkidle',timeout:60000});
await page.waitForFunction(()=>document.querySelectorAll('#forecastCards .forecastCard').length===5&&document.querySelector('#modelBadge')?.textContent?.includes('PASS'),null,{timeout:30000});
await page.waitForFunction(()=>document.querySelectorAll('#methodProof .proofCard').length===4,null,{timeout:10000});
const badge=(await page.locator('#modelBadge').innerText()).trim();if(!badge.includes('PASS'))throw new Error(`model badge not PASS: ${badge}`);
const decision=(await page.locator('#decision').innerText()).trim();if(!decision||decision==='—'||decision.includes('LOCKED'))throw new Error(`decision invalid: ${decision}`);
for(const id of ['#close','#t1','#t3','#t5','#risk']){const t=(await page.locator(id).innerText()).trim();if(!t||t==='—')throw new Error(`${id} empty`)}
const cards=page.locator('#forecastCards .forecastCard');if(await cards.count()!==5)throw new Error(`expected 5 forecast cards, got ${await cards.count()}`);
// Direct-price promotion and direction-probability promotion are independent. T+4/T+5 may
// legitimately abstain on P↑ while their direct price horizon remains validated.
for(let i=0;i<5;i++){
  const t=(await cards.nth(i).innerText()).trim();
  const lines=t.split(/\n+/).map(x=>x.trim()).filter(Boolean);
  const hasHorizon=lines.some(x=>x===`T+${i+1}`);
  const hasPrice=lines.some(x=>/^\d{1,3}(?:\.\d{3})+$/.test(x));
  if(!hasHorizon||!hasPrice||t.includes('LOCKED'))throw new Error(`forecast card ${i+1} price not released: ${t}`);
}
const proofText=await page.locator('#methodProof').innerText();for(const token of ['Nhìn trước tương lai','0 dòng','Sealed holdout','Walk-forward & embargo','T+1 · T+2 · T+3 · T+4 · T+5'])if(!proofText.includes(token))throw new Error(`method proof missing ${token}: ${proofText}`);
const visible=await page.locator('body').innerText();for(const banned of ['VNStock ưu tiên cho OHLCV Việt Nam','không nội suy','whisker =','Completed EOD snapshot','không phát lệnh mua/bán','Missing rumor không được coi là neutral signal'])if(visible.includes(banned))throw new Error(`banned visible copy: ${banned}`);
const canvas=page.locator('#chart');const box=await canvas.boundingBox();if(!box)throw new Error('chart canvas has no box');
if(await page.locator('#tooltip').count()!==1)throw new Error('chart tooltip surface missing');
const newsCount=await page.locator('#news .newsItem').count();
const newsText=(await page.locator('#news').innerText()).trim();
if(newsCount<1&&!/Chưa ghi nhận|Không có event|Không có sự kiện/i.test(newsText))throw new Error(`event intelligence neither rendered items nor a valid empty state: ${newsText}`);
const sourceText=await page.locator('#sourceAudit').innerText();for(const token of ['Nguồn giá','VNStock','Độ phủ HOSE hiện tại','Kho sự kiện','Dữ liệu dòng tiền','Kiểm định mô hình'])if(!sourceText.includes(token))throw new Error(`source audit missing ${token}: ${sourceText}`);
const btRows=page.locator('#btRows tr');if(await btRows.count()<1)throw new Error('backtest rows missing');
await page.locator('#tabs button').nth(2).click();await page.waitForTimeout(180);if(!(await page.locator('#btMeta').innerText()).includes('mẫu OOS='))throw new Error('backtest T+3 did not render polished OOS meta');
const firstRow=page.locator('#btRows tr').first();const title=await firstRow.getAttribute('title');if(title&&!title.includes('Prior20'))throw new Error(`backtest T0 trace malformed: ${title}`);
const vcb=page.locator('#quick button',{hasText:'VCB'});if(await vcb.count()){await vcb.first().click();await page.waitForFunction(()=>document.querySelector('#chartTitle')?.textContent?.startsWith('VCB'));if(new URL(page.url()).searchParams.get('symbol')!=='VCB')throw new Error('symbol navigation did not update URL')}
await page.screenshot({path:'v12-browser-desktop.png',fullPage:true});
if(errors.length)throw new Error(`browser console errors: ${errors.join(' | ')}`);
if(failed.length)throw new Error(`failed requests: ${failed.join(' | ')}`);
if(external.length)throw new Error(`unexpected external runtime requests: ${external.join(' | ')}`);
const mobile=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:1});const mobileErrors=[];mobile.on('console',m=>{if(m.type()==='error')mobileErrors.push(m.text())});mobile.on('pageerror',e=>mobileErrors.push(String(e)));await mobile.goto(base,{waitUntil:'networkidle',timeout:60000});await mobile.waitForFunction(()=>document.querySelectorAll('#forecastCards .forecastCard').length===5,null,{timeout:30000});
const dims=await mobile.evaluate(()=>({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth,chart:document.querySelector('#chart')?.getBoundingClientRect().width,wrap:document.querySelector('.chartWrap')?.getBoundingClientRect().width,proof:document.querySelector('#methodProof')?.getBoundingClientRect().width}));if(dims.sw>dims.cw+3)throw new Error(`mobile document horizontal overflow ${JSON.stringify(dims)}`);if(!dims.chart||dims.chart>dims.cw+3)throw new Error(`mobile chart overflow ${JSON.stringify(dims)}`);if(await mobile.locator('#forecastCards .forecastCard').count()!==5)throw new Error('mobile forecast cards missing');await mobile.screenshot({path:'v12-browser-mobile.png',fullPage:true});if(mobileErrors.length)throw new Error(`mobile console errors: ${mobileErrors.join(' | ')}`);
console.log(JSON.stringify({browserSmoke:'PASS',url:base,allowedOrigin,badge,decision,newsCount,proof:proofText,desktop:{width:1440,height:1000},mobile:dims,externalRuntimeRequests:external.length,consoleErrors:errors.length},null,2));
await browser.close();
