const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const js=fs.readFileSync(path.join(root,'frontend/market.js'),'utf8');
const html=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8');
const pipeline=fs.readFileSync(path.join(root,'scripts/refresh_market.py'),'utf8');
const news=fs.readFileSync(path.join(root,'scripts/news_intelligence.py'),'utf8');
assert.doesNotMatch(js,/function exposureExplanation\(r\)/);
assert.doesNotMatch(js,/\+exposureExplanation\(r\)/);
assert.match(html,/Tiêu chí kiểm chứng/);
assert.match(html,/data-news-tab="impact"[^>]*>Tin đáng chú ý/);
assert.match(pipeline,/nit\.attach_collector_receipts\(rows, retained, current\)/);
assert.match(pipeline,/nit\.exposure_hypothesis\(row\)/);
assert.match(news,/collectorFirstSeenBasis/);
assert.match(news,/earliestPublishedAt/);
assert.doesNotMatch(js,/historicalImpactCertified\s*=\s*true/);
console.log('NEWS IMPACT EVIDENCE-ONLY UI CONTRACT PASS');

const reviewModule=require('../frontend/news-impact-reviewed.js');
const manifest=JSON.parse(fs.readFileSync(path.join(root,'data/news-impact-reviewed.json'),'utf8'));
const css=fs.readFileSync(path.join(root,'frontend/market.css'),'utf8');
const bundleScript=fs.readFileSync(path.join(root,'scripts/build_cdn.py'),'utf8');
assert.equal(reviewModule.inspectRelease(manifest).eligibleCount,0);
assert.equal(reviewModule.canNotify(),false);
const dummyShadow={
 schema:'FINQUERY_HYBRID_NEWS_IMPACT_SHADOW_V2',status:'SHADOW_ONLY',
 checkedAt:'2026-11-03T09:55:00Z',
 counts:{deduplicatedStories:100,classifiedEventStories:60,
 directIssuerMentionStories:14,storiesWithEligibleBusinessFacts:0,
 storiesWithoutCertifiedCollectorTime:65,eligibleNotifications:0,verifiedImpactRelations:0},
 publicationPolicy:{killSwitch:'LOCKED_OFF',verifiedTickerAlerts:false,
 verifiedSectorAlerts:false,noAlertFromSentimentOrNewsPriority:true}
};
const clock=Date.parse('2026-11-03T10:00:00Z');
assert.equal(reviewModule.inspectShadow(dummyShadow,clock).classifiedEventStories,60);
assert.equal(reviewModule.inspectShadow({...dummyShadow,counts:{...dummyShadow.counts,eligibleNotifications:1}},clock),null);
assert.equal(reviewModule.inspectShadow({...dummyShadow,publicationPolicy:{...dummyShadow.publicationPolicy,killSwitch:'OPEN'}},clock),null);
assert.equal(reviewModule.inspectShadow({...dummyShadow,checkedAt:'2026-11-03T06:00:00Z'},clock),null);
assert.deepEqual(reviewModule.reviewedImpacts(),[]);
assert.equal(reviewModule.inspectRelease({...manifest,status:'PRODUCTION_APPROVED'}),null);
assert.equal(reviewModule.inspectRelease({...manifest,notificationsEnabled:true}),null);
assert.equal(reviewModule.inspectRelease({...manifest,verifiedImpacts:[{symbol:'FPT',status:'CONFIRMED'}]}),null);
assert.match(js,/state\.newsMode==='verified'/);
assert.match(js,/Chưa có sự kiện đạt chuẩn tác động/);
assert.doesNotMatch(js,/new Notification\('FinQuery · Tin mới Watchlist'/);
assert.match(js,/function newsAlertsEnabled\(\)\{return false;/);
assert.match(html,/data-news-tab="verified"/);
assert.match(html,/id="news-impact-reviewed-panel"/);
assert.match(html,/id="news-alert-toggle"[^>]*disabled hidden/);
assert.match(css,/\.news-impact-reviewed-panel/);
assert.match(css,/@media\(max-width:760px\)/);
assert.match(bundleScript,/news-impact-reviewed\.js/);

assert.doesNotMatch(js,/Phản ứng giá:/);
assert.match(js,/ƯU TIÊN TIN/);

assert.match(js,/0 tác động đạt chuẩn/);
