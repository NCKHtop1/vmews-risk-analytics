const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {test}=require('node:test');

const src=fs.readFileSync(path.join(__dirname,'../frontend/research-ai.js'),'utf8');

test('deep research uses two-pass analyst architecture',()=>{
 assert.match(src,/async function callResearchDossier\(/);
 assert.match(src,/Research dossier xong/);
 assert.match(src,/researchPass:dossier\?/);
 assert.match(src,/RESEARCH DOSSIER TỪ VÒNG NGHIÊN CỨU TRƯỚC/);
 assert.match(src,/knowledgeBase:knowledge/);
});

test('deep mode prefers full Flash before Lite and has long-form budget',()=>{
 assert.match(src,/deep:\['gemini-3\.8-flash','gemini-3\.7-flash','gemini-3\.6-flash','gemini-3\.5-flash','gemini-3\.5-flash-lite'/);
 assert.match(src,/maxOutputTokens:deep\?7000:1800/);
 assert.match(src,/rowLimit=deep\?140:24/);
});

test('research frameworks include bank and corporate knowledge',()=>{
 assert.match(src,/framework:bank\?'bank':'corporate'/);
 assert.match(src,/\['nii','nim','casa','costOfFunds','ldr','npl','llr','creditCost','cir','car'/);
 assert.match(src,/\['grossMargin','netMargin','operatingMargin','ocf','fcf','capex'/);
});
