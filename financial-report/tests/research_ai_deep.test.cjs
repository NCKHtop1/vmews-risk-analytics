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

test('deep research exposes explicit academic reasoning contract',()=>{
 assert.match(src,/const ACADEMIC_LENSES=/);
 assert.match(src,/academicContext:\{policy:'FRAMEWORK_ONLY_NOT_COMPANY_EVIDENCE'/);
 assert.match(src,/\[ACADEMIC\]/);
 assert.match(src,/luận điểm → bằng chứng → cơ chế tài chính\/kinh tế → phản biện hoặc giới hạn → hàm ý cần theo dõi/);
 assert.match(src,/counter-thesis/);
 assert.match(src,/Khung học thuật tham chiếu/);
});

test('academic references are canonical and scoped with caveats',()=>{
 for(const needle of [
  'Ohlson (1995)',
  'Sloan (1996)',
  'Dechow & Dichev (2002)',
  'Piotroski (2000)',
  'Modigliani & Miller (1958)',
  'Fama & French (2015)',
  'Ho & Saunders (1981)',
  'Jegadeesh & Titman (1993)',
  'Lo, Mamaysky & Wang (2000)'
 ])assert.ok(src.includes(needle),needle);
 assert.match(src,/không phải công thức dự báo giá ngắn hạn/);
 assert.match(src,/không được đồng nhất máy móc momentum 5 phiên/);
 assert.match(src,/không thay thế bằng chứng doanh nghiệp/);
});

test('academic layer is passed through context and rendered separately',()=>{
 assert.match(src,/academic=academicLenses\(question,knowledge,deep\)/);
 assert.match(src,/academicSources:\(agentContext\?\.academicContext\?\.references\|\|\[\]\)/);
 assert.match(src,/WEB\|ACADEMIC/);
});

test('deep answers have deterministic quality audit and bounded repair pass',()=>{
 assert.match(src,/function auditDeepAnswer\(/);
 assert.match(src,/missingEvidenceTags/);
 assert.match(src,/academicRequired/);
 assert.match(src,/hasCounter/);
 assert.match(src,/hasMechanism/);
 assert.match(src,/async function repairDeepAnswer\(/);
 assert.match(src,/Đang rà soát chất lượng lập luận và biên tập vòng cuối/);
 assert.match(src,/qualityRepair=\{status:'not_needed'\}/);
 assert.match(src,/repairedAudit\.score>=qualityAudit\.score/);
 assert.match(src,/kiểm định lập luận/);
});

test('deep quality repair cannot invent a new analytical basis',()=>{
 assert.match(src,/giữ nguyên mọi số liệu đã được neo/);
 assert.match(src,/không tự tính\/thêm số mới nếu context không có/);
 assert.match(src,/không biến tương quan thành nhân quả/i);
 assert.match(src,/không đưa khuyến nghị mua\/bán/i);
});
