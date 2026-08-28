const fs = require('fs');

const model = JSON.parse(fs.readFileSync('data/forecast-model-v10.json', 'utf8'));
const news = JSON.parse(fs.readFileSync('data/research-news-v10.json', 'utf8'));
const sent = JSON.parse(fs.readFileSync('data/sentiment-v10.json', 'utf8'));
const ev = JSON.parse(fs.readFileSync('data/news-event-study.json', 'utf8'));
const html = fs.readFileSync('forecast-final.html', 'utf8');
const ui = fs.readFileSync('forecast-final-v10.js', 'utf8');

let passed = 0;
const ok = (cond, msg) => { if (!cond) throw new Error(msg); passed++; };
const finite = x => x !== null && x !== undefined && x !== '' && Number.isFinite(Number(x));

// V10 remains a compatibility artifact, not the publication authority. Keep
// its numerical and UI contracts strict while current full-HOSE news breadth,
// point-in-time identity and freshness are governed by the V20 release audit.
ok(/^VMEWS-FORECAST-10\./.test(model.version || '') && model.promotion?.status === 'PASS', 'V10 model/promotion');
ok(model.universe?.symbols >= 250 && model.universe?.rows >= 100000, 'V10 universe');

for (const h of ['3', '5']) {
  const z = model.horizons?.[h];
  ok(z?.status === 'PASS', `V10 horizon ${h}`);
  for (const k of ['impute', 'mean', 'std']) {
    ok(Array.isArray(z[k]) && z[k].length === model.featureNames.length && z[k].every(finite), `V10 ${h} ${k}`);
  }
  ok(z.alphaModel?.coef?.length === model.featureNames.length, `V10 alpha coef ${h}`);
  ok(z.directionModel?.coef?.length === model.featureNames.length, `V10 direction coef ${h}`);
}

// Legacy news is checked for structural integrity and issuer-local dedupe only.
// Do not force an arbitrary ticker/article count after the current pipeline has
// intentionally removed stale and issuer-mismatched publications.
ok(news && typeof news === 'object' && news.coverage && news.symbols, 'V10 news artifact');
const sources = new Set(['OFFICIAL', 'MAINSTREAM', 'RUMOR_UNVERIFIED', 'CLARIFICATION']);
const events = new Set(['REGULATORY', 'EARNINGS', 'OWNERSHIP', 'CORPORATE_ACTION', 'FINANCING', 'OPERATIONS_MA', 'ANALYST', 'GENERAL']);
let newsItems = 0;
for (const [sym, items] of Object.entries(news.symbols || {})) {
  const titles = items.map(x => String(x.title || '').replace(/\s+/g, ' ').trim().toLowerCase());
  ok(titles.length === new Set(titles).size, `V10 duplicate news ${sym}`);
  for (const x of items) {
    newsItems++;
    ok(sources.has(x.sourceClass) && events.has(x.event), `V10 news taxonomy ${sym}`);
    ok(finite(x.sourceQuality) && +x.sourceQuality >= 0 && +x.sourceQuality <= 1, `V10 news quality ${sym}`);
    ok(finite(x.materiality) && +x.materiality >= 0 && +x.materiality <= 1, `V10 news materiality ${sym}`);
  }
}
ok(newsItems > 0, 'V10 news nonempty');

ok(sent && typeof sent === 'object' && sent.symbols, 'V10 sentiment artifact');
ok(!model.featureNames.some(k => /sentiment|news/i.test(k)), 'V10 no news/sentiment leakage');
ok(ev && typeof ev === 'object' && ev.pointInTimeEligibleForForecast === false, 'V10 event governance');

for (const text of ['Đọc hướng đi ngắn hạn cùng trạng thái rủi ro', 'Hệ thống tách riêng khả năng xếp hạng tương đối', 'Mô hình chỉ vẽ các horizon', 'Khối ngoại / tự doanh']) {
  ok(!html.includes(text), `V10 removed filler ${text}`);
}
ok(!ui.includes('/flow?') && !ui.includes('P(tăng)'), 'V10 deprecated UI removed');
ok(ui.includes('directionCalibrationBuckets') && ui.includes('alphaCalibrationBuckets'), 'V10 calibration UI');

console.log(JSON.stringify({
  ok: true,
  compatibility: 'V10 legacy numerical/UI + structural data integrity; V20 owns current publication coverage',
  assertions: passed,
  model: model.version,
  symbols: model.universe.symbols,
  rows: model.universe.rows,
  newsCoverageEntries: Object.keys(news.coverage || {}).length,
  newsSymbols: Object.keys(news.symbols || {}).length,
  newsItems,
}));
