import { chromium } from 'playwright';

const url = process.env.SOLUTION_AI_FULL_AUDIT_URL
  || 'https://nckhtop1.github.io/vmews-risk-analytics/forecast-final.html?symbol=FPT';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
const consoleErrors = [];
const failedRequests = [];
page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
page.on('pageerror', error => consoleErrors.push(String(error)));
page.on('requestfailed', request => failedRequests.push(`${request.method()} ${request.url()} ${request.failure()?.errorText || ''}`));

const t0 = Date.now();

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
function finite(value) {
  return value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
}
function sameArray(a, b) {
  return JSON.stringify([...a].sort((x,y)=>Number(x)-Number(y))) === JSON.stringify([...b].sort((x,y)=>Number(x)-Number(y)));
}

try {
  await page.goto(url, { waitUntil: 'networkidle', timeout: 70000 });
  await page.waitForFunction(() => Boolean(
    window.__VMEWS_LOAD_BASE__
    && window.__VMEWS_FRESHNESS__
    && window.__VMEWS_PRIMARY_HORIZON__
    && window.__SOLUTION_AI_BUILD_CONTEXT__
    && window.__SOLUTION_AI_ASK__
    && window.__SOLUTION_AI_BUILD_GEMINI_HANDOFF__
  ), null, { timeout: 30000 });
  await page.waitForFunction(() => document.querySelectorAll('#forecastCards .forecastCard').length === 5, null, { timeout: 30000 });

  const structural = await page.evaluate(async () => {
    const finite = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
    const B = await window.__VMEWS_LOAD_BASE__();
    const root = window.__VMEWS_DATA_ROOT__;
    const release = await fetch(`${root}/release-audit-v20.json?audit=${Date.now()}`, { cache: 'no-store' }).then(r => {
      if (!r.ok) throw new Error(`release-audit-v20.json HTTP ${r.status}`);
      return r.json();
    });
    const session = window.__VMEWS_SESSION__ || null;
    const promotion = B.model?.promotion || B.dash?.promotion || {};
    const direct = (promotion.directPriceHorizons || []).map(Number).filter(Number.isFinite);
    const review = (promotion.reviewHorizons || []).map(Number).filter(Number.isFinite);
    const preferred = Number(promotion.preferredRankingHorizon || direct[0] || 0);
    const passFromRelease = Object.entries(release.horizons || {})
      .filter(([, item]) => item?.priceStatus === 'PASS')
      .map(([key]) => Number(key));
    const reviewFromRelease = Object.entries(release.horizons || {})
      .filter(([, item]) => item?.priceStatus !== 'PASS')
      .map(([key]) => Number(key));
    const errors = [];
    const warnings = [];
    const symbolStats = {
      total: 0,
      current: 0,
      stale: 0,
      publishedPointForecasts: 0,
      reviewHorizons: 0,
      directionProbabilities: 0,
      chartCurrent: 0,
    };
    const horizonCounts = Object.fromEntries([1,2,3,4,5].map(h => [h, { published: 0, review: 0, invalid: 0 }]));
    const targets = release.calendar?.certifiedTargetDates || {};

    if (B.gates?.status !== 'PASS') errors.push(`phase gates not PASS: ${B.gates?.status}`);
    if (promotion.status !== 'PASS') errors.push(`model promotion not PASS: ${promotion.status}`);
    const expectedSession = window.__VMEWS_FRESHNESS__.expectedSession();
    if (String(B.dash?.asOf || '') !== String(expectedSession || '')) errors.push(`dashboard stale: ${B.dash?.asOf} vs expected ${expectedSession}`);
    if (String(release.asOf || '') !== String(B.dash?.asOf || '')) errors.push(`release audit asOf mismatch: ${release.asOf} vs ${B.dash?.asOf}`);
    if (release.status !== 'PASS') errors.push(`release audit status ${release.status}`);
    if (JSON.stringify([...direct].sort()) !== JSON.stringify([...passFromRelease].sort())) errors.push(`promotion/release PASS mismatch: direct=${direct} release=${passFromRelease}`);
    if (review.length && JSON.stringify([...review].sort()) !== JSON.stringify([...reviewFromRelease].sort())) errors.push(`promotion/release REVIEW mismatch: review=${review} release=${reviewFromRelease}`);
    if (!direct.includes(preferred)) errors.push(`preferred horizon T+${preferred} is not a direct-price PASS horizon`);

    for (const [symbol, snapshot] of Object.entries(B.dash?.symbols || {})) {
      symbolStats.total += 1;
      if (snapshot?.dataFreshness === 'CURRENT') symbolStats.current += 1;
      else symbolStats.stale += 1;
      if (String(snapshot?.date || '') !== String(B.dash?.asOf || '')) errors.push(`${symbol}: snapshot date ${snapshot?.date} != ${B.dash?.asOf}`);
      if (snapshot?.staleForecast === true) errors.push(`${symbol}: staleForecast leaked into published universe`);
      const horizons = snapshot?.horizons || {};
      for (const h of [1,2,3,4,5]) {
        const q = horizons[String(h)];
        if (!q) {
          horizonCounts[h].invalid += 1;
          errors.push(`${symbol}: missing T+${h}`);
          continue;
        }
        const released = q.priceValidated === true && (q.validationStatus || 'PASS') === 'PASS';
        if (released) {
          horizonCounts[h].published += 1;
          symbolStats.publishedPointForecasts += 1;
          if (!direct.includes(h)) errors.push(`${symbol}: T+${h} published while global gate is REVIEW`);
          if (![q.expectedPrice,q.q20Price,q.q80Price].every(v => Number.isFinite(Number(v)))) errors.push(`${symbol}: T+${h} published with non-finite point/range`);
          if (finite(q.q20Price) && finite(q.expectedPrice) && finite(q.q80Price) && !(Number(q.q20Price) <= Number(q.expectedPrice) && Number(q.expectedPrice) <= Number(q.q80Price))) {
            errors.push(`${symbol}: T+${h} expected price outside Q20-Q80`);
          }
          if (targets[String(h)] && String(q.targetDate || '') !== String(targets[String(h)])) errors.push(`${symbol}: T+${h} targetDate ${q.targetDate} != ${targets[String(h)]}`);
          if (finite(q.tickSize) && finite(q.expectedPrice) && Math.abs(Number(q.expectedPrice) / Number(q.tickSize) - Math.round(Number(q.expectedPrice) / Number(q.tickSize))) > 1e-7) {
            errors.push(`${symbol}: T+${h} expected price violates tick grid`);
          }
        } else {
          horizonCounts[h].review += 1;
          symbolStats.reviewHorizons += 1;
          if (direct.includes(h)) warnings.push(`${symbol}: T+${h} global PASS but symbol-level point withheld`);
        }
        if (q.directionValidated === true) {
          symbolStats.directionProbabilities += 1;
          if (!finite(q.probUp) || Number(q.probUp) < 0 || Number(q.probUp) > 1) errors.push(`${symbol}: T+${h} invalid probUp`);
        }
      }
      const chart = B.dash?.charts?.[symbol] || [];
      if (chart.length && String(chart.at(-1)?.date || '') === String(B.dash?.asOf || '')) symbolStats.chartCurrent += 1;
    }

    const metrics = {};
    for (const h of [1,2,3,4,5]) {
      const audit = B.model?.horizons?.[String(h)] || {};
      const sealed = audit.sealedAudit || {};
      metrics[h] = {
        priceStatus: audit.priceStatus || null,
        directionStatus: audit.directionStatus || null,
        holdoutRows: sealed.n ?? null,
        maeSkill: sealed.maeSkill ?? audit.maeSkill ?? null,
        executableMAESkill: sealed.executableMAESkill ?? audit.executableMAESkill ?? release.horizons?.[String(h)]?.executableMAESkill ?? null,
        magnitudeMAESkill: sealed.magnitudeMAESkill ?? audit.magnitudeMAESkill ?? release.horizons?.[String(h)]?.magnitudeMAESkill ?? null,
        rankIC: sealed.rankIC ?? audit.rankIC ?? null,
        directionalAccuracy: sealed.directionalAccuracy ?? audit.directionalAccuracy ?? release.horizons?.[String(h)]?.directionalAccuracy ?? null,
        coverage20_80: sealed.coverage20_80 ?? audit.coverage20_80 ?? null,
        latestWalkForwardExecutableMAESkill: audit.walkForwardAudit?.latestExecutableMAESkill ?? audit.latestWalkForwardExecutableMAESkill ?? null,
        positiveChronologicalFolds: release.horizons?.[String(h)]?.positiveChronologicalFolds ?? null,
        afterCostStatus: release.horizons?.[String(h)]?.afterCostStatus ?? null,
        meanNetRealizedReturn: release.horizons?.[String(h)]?.meanNetRealizedReturn ?? null,
      };
      if (passFromRelease.includes(h) && Number(metrics[h].executableMAESkill || 0) <= 0) errors.push(`T+${h}: PASS but executable MAE skill is not positive`);
      if (passFromRelease.includes(h) && Number(metrics[h].directionalAccuracy || 0) <= 0.5) warnings.push(`T+${h}: point forecast PASS but directional accuracy <= 50%`);
    }

    if (session) {
      if (session.status !== 'PASS') errors.push(`session overlay status ${session.status}`);
      if (String(session.coreAsOf || '') !== String(B.dash?.asOf || '')) errors.push(`session coreAsOf ${session.coreAsOf} != dashboard ${B.dash?.asOf}`);
      if (Number(session.rankingHorizon || 0) !== preferred) errors.push(`session ranking T+${session.rankingHorizon} != preferred T+${preferred}`);
      if (session.coreForecastUnchanged !== true) errors.push('session overlay rewrites core forecast');
      if (Number(session.coverage?.coverageRatio || 0) < .9 || Number(session.coverage?.currentCoverageRatio || 0) < .9 || Number(session.coverage?.cutoffFreshCoverageRatio || 0) < .9) {
        errors.push(`session coverage below 90%: ${JSON.stringify(session.coverage)}`);
      }
      if (session.forecastAlignment?.rankingEligible !== true) errors.push(`session ranking not aligned: ${JSON.stringify(session.forecastAlignment)}`);
      for (const leader of session.leaders || []) {
        if (Number(leader.rankingHorizon || 0) !== preferred) errors.push(`leader ${leader.symbol} uses T+${leader.rankingHorizon} instead of T+${preferred}`);
      }
    } else {
      warnings.push('session overlay not loaded');
    }

    return {
      asOf: B.dash?.asOf,
      expectedSession,
      generatedAt: B.dash?.generatedAt || null,
      releaseVersion: release.version,
      releaseStatus: release.status,
      direct,
      review,
      preferred,
      releaseDirect: passFromRelease,
      releaseReview: reviewFromRelease,
      phaseGates: B.gates?.status,
      symbolStats,
      horizonCounts,
      metrics,
      session: session ? {
        version: session.version,
        status: session.status,
        session: session.session,
        generatedAt: session.generatedAt,
        coreAsOf: session.coreAsOf,
        rankingHorizon: session.rankingHorizon,
        coverage: session.coverage,
        alignment: session.forecastAlignment,
        leaders: (session.leaders || []).map(x => x.symbol),
      } : null,
      errors,
      warnings: warnings.slice(0, 50),
      warningCount: warnings.length,
    };
  });

  assert(structural.errors.length === 0, `structural/data audit failed: ${structural.errors.slice(0, 12).join(' | ')}`);
  assert(structural.symbolStats.total >= 350, `published universe unexpectedly small: ${structural.symbolStats.total}`);
  assert(structural.symbolStats.stale === 0, `stale symbols leaked: ${structural.symbolStats.stale}`);
  assert(structural.phaseGates === 'PASS' && structural.releaseStatus === 'PASS', 'gates/release are not PASS');
  assert(structural.direct.includes(structural.preferred), 'preferred horizon is not released');

  const primaryPrice = await page.evaluate(async () => {
    const ctx = await window.__SOLUTION_AI_BUILD_CONTEXT__();
    return { symbol: ctx.symbol, preferred: ctx.preferredHorizon, price: ctx.horizons?.[ctx.preferredHorizon]?.price };
  });
  const expectedPriceText = Number(primaryPrice.price).toLocaleString('vi-VN');
  const overview = await page.evaluate(() => ({
    decision: document.querySelector('#decision')?.textContent?.trim() || '',
    forecastLabel: document.querySelector('#primaryForecastLabel')?.textContent?.trim() || '',
    probabilityLabel: document.querySelector('#primaryProbabilityLabel')?.textContent?.trim() || '',
    scenarioLabel: document.querySelector('#scenarioHeadingLabel')?.textContent?.trim() || '',
    primaryValue: document.querySelector('#range5')?.textContent?.trim() || '',
    cards: [...document.querySelectorAll('#forecastCards .forecastCard')].map(x => x.textContent.trim()),
  }));
  assert(overview.decision.includes(primaryPrice.preferred), `decision not on preferred horizon: ${overview.decision}`);
  assert(overview.forecastLabel.includes(primaryPrice.preferred), `overview forecast label stale: ${overview.forecastLabel}`);
  assert(overview.probabilityLabel.includes(primaryPrice.preferred), `overview probability label stale: ${overview.probabilityLabel}`);
  assert(overview.scenarioLabel.includes(primaryPrice.preferred), `scenario label stale: ${overview.scenarioLabel}`);
  assert(overview.primaryValue.includes(expectedPriceText), `overview primary value ${overview.primaryValue} != ${expectedPriceText}`);
  for (const h of structural.review) {
    const card = overview.cards[h - 1] || '';
    assert(/CHƯA ĐẠT KIỂM ĐỊNH|CHƯA CÓ DỮ LIỆU|ĐANG CẬP NHẬT/.test(card), `T+${h} REVIEW leaks as published UI: ${card}`);
    assert(!/Giá dự báo của mô hình/.test(card), `T+${h} REVIEW exposes a point forecast`);
  }

  // Exercise actual launcher/form flow with no key.
  await page.click('#solutionAiLauncher');
  await page.waitForFunction(() => document.querySelector('#solutionAiPanel')?.classList.contains('open'));
  const localQuestion = 'Chỉ dùng dữ liệu mô hình, phân tích forecast đang xem và nêu kỳ ưu tiên.';
  const localStart = Date.now();
  await page.fill('#solutionAiInput', localQuestion);
  await page.click('#solutionAiSend');
  await page.waitForFunction(() => {
    const items = [...document.querySelectorAll('#solutionAiMessages .aiMessage')];
    return items.length >= 3 && !items.at(-1)?.classList.contains('aiThinking');
  }, null, { timeout: 12000 });
  const localLatencyMs = Date.now() - localStart;
  const localReply = await page.evaluate(() => [...document.querySelectorAll('#solutionAiMessages .aiMessage')].at(-1)?.textContent?.trim() || '');
  assert(localReply.includes('FPT') && localReply.includes(primaryPrice.preferred), `local form reply not grounded: ${localReply.slice(0,220)}`);
  assert(localLatencyMs < 10000, `local AI too slow: ${localLatencyMs}ms`);

  // Actual symbol-change UI must also refresh the AI context.
  const switchStart = Date.now();
  await page.fill('#symbol', 'HPG');
  await page.click('#go');
  await page.waitForFunction(() => document.querySelector('#solutionAiContext strong')?.textContent?.trim() === 'HPG', null, { timeout: 10000 });
  const switchLatencyMs = Date.now() - switchStart;
  const hpg = await page.evaluate(async () => window.__SOLUTION_AI_BUILD_CONTEXT__());
  assert(hpg.symbol === 'HPG', `symbol switch failed: ${hpg.symbol}`);
  assert(hpg.publishedHorizons.includes(hpg.preferredHorizon), 'HPG preferred horizon is not published');
  assert(switchLatencyMs < 10000, `symbol switch too slow: ${switchLatencyMs}ms`);

  // Suggestion button is a user-facing route, not a private helper.
  const beforeSuggestion = await page.locator('#solutionAiMessages .aiMessage').count();
  await page.click('#solutionAiSuggestions [data-ai-prompt*="kiểm định"], #solutionAiSuggestions [data-ai-prompt*="Kiểm định"]');
  await page.waitForFunction(count => {
    const items = [...document.querySelectorAll('#solutionAiMessages .aiMessage')];
    return items.length > count + 1 && !items.at(-1)?.classList.contains('aiThinking');
  }, beforeSuggestion, { timeout: 12000 });
  const suggestionReply = await page.evaluate(() => [...document.querySelectorAll('#solutionAiMessages .aiMessage')].at(-1)?.textContent?.trim() || '');
  assert(suggestionReply.includes('HPG') && suggestionReply.includes(hpg.preferredHorizon), 'forecast suggestion lost current symbol/horizon');

  // Exercise actual Gemini connection/success path with a deterministic provider stub.
  const hpgPriceText = Number(hpg.horizons[hpg.preferredHorizon].price).toLocaleString('vi-VN');
  await page.route('https://generativelanguage.googleapis.com/**', async route => {
    const requestUrl = route.request().url();
    const body = route.request().postData() || '';
    if (/\/models\?/.test(requestUrl)) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        models: [{ name: 'models/gemini-2.5-flash', supportedGenerationMethods: ['generateContent'] }],
      }) });
      return;
    }
    if (/:generateContent/.test(requestUrl) && body.includes('Reply with exactly OK')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        candidates: [{ content: { parts: [{ text: 'OK' }] } }],
      }) });
      return;
    }
    if (/:generateContent/.test(requestUrl)) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        candidates: [{ content: { parts: [{ text: `MOCK_GEMINI_SUCCESS HPG forecast ${hpg.preferredHorizon} ${hpgPriceText}. Phân tích bám đúng snapshot hiện tại.` }] } }],
      }) });
      return;
    }
    await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: { message: 'synthetic fallback route' } }) });
  });
  await page.click('#solutionAiSettings');
  await page.waitForFunction(() => !document.querySelector('#solutionAiConnect')?.hidden);
  await page.fill('#solutionAiKey', 'AIzaSyntheticFullAuditKey123456789012345');
  await page.click('#solutionAiRetry');
  await page.waitForFunction(() => /Đã kết nối/.test(document.querySelector('#solutionAiConnectionState')?.textContent || ''), null, { timeout: 8000 });
  const beforeGemini = await page.locator('#solutionAiMessages .aiMessage').count();
  await page.fill('#solutionAiInput', 'Chỉ dùng dữ liệu mô hình, phân tích forecast HPG hiện tại.');
  await page.click('#solutionAiSend');
  await page.waitForFunction(count => {
    const items = [...document.querySelectorAll('#solutionAiMessages .aiMessage')];
    return items.length > count + 1 && !items.at(-1)?.classList.contains('aiThinking');
  }, beforeGemini, { timeout: 10000 });
  const geminiReply = await page.evaluate(() => [...document.querySelectorAll('#solutionAiMessages .aiMessage')].at(-1)?.textContent?.trim() || '');
  assert(geminiReply.includes('MOCK_GEMINI_SUCCESS'), `Gemini success path did not surface provider answer: ${geminiReply.slice(0,220)}`);
  await page.click('#solutionAiDisconnect');
  await page.unroute('https://generativelanguage.googleapis.com/**');

  // Prove model failover before local fallback: first Gemini model fails, the
  // second model answers without surfacing an error to the user.
  await page.route('https://generativelanguage.googleapis.com/**', async route => {
    const requestUrl = route.request().url();
    const body = route.request().postData() || '';
    if (/\/models\?/.test(requestUrl)) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        models: [
          { name: 'models/gemini-3.7-flash', supportedGenerationMethods: ['generateContent'] },
          { name: 'models/gemini-3.5-flash', supportedGenerationMethods: ['generateContent'] },
        ],
      }) });
      return;
    }
    if (body.includes('Reply with exactly OK')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        candidates: [{ content: { parts: [{ text: 'OK' }] } }],
      }) });
      return;
    }
    if (requestUrl.includes('gemini-3.7-flash')) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({
        error: { message: 'synthetic primary model outage' },
      }) });
      return;
    }
    if (requestUrl.includes('gemini-3.5-flash')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        candidates: [{ content: { parts: [{ text: `MOCK_GEMINI_MODEL_FAILOVER HPG ${hpg.preferredHorizon}` }] } }],
      }) });
      return;
    }
    await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { message: 'unexpected synthetic route' } }) });
  });
  await page.click('#solutionAiSettings');
  await page.fill('#solutionAiKey', 'AIzaSyntheticFailoverAuditKey123456789012345');
  await page.click('#solutionAiRetry');
  await page.waitForFunction(() => /Đã kết nối/.test(document.querySelector('#solutionAiConnectionState')?.textContent || ''), null, { timeout: 8000 });
  const beforeFailover = await page.locator('#solutionAiMessages .aiMessage').count();
  await page.fill('#solutionAiInput', 'Chỉ dùng dữ liệu mô hình, kiểm tra đường gọi Gemini dự phòng cho HPG.');
  await page.click('#solutionAiSend');
  await page.waitForFunction(count => {
    const items = [...document.querySelectorAll('#solutionAiMessages .aiMessage')];
    return items.length > count + 1 && !items.at(-1)?.classList.contains('aiThinking');
  }, beforeFailover, { timeout: 12000 });
  const failoverReply = await page.evaluate(() => [...document.querySelectorAll('#solutionAiMessages .aiMessage')].at(-1)?.textContent?.trim() || '');
  assert(failoverReply.includes('MOCK_GEMINI_MODEL_FAILOVER'), `Gemini model failover did not recover: ${failoverReply.slice(0,220)}`);
  await page.click('#solutionAiDisconnect');
  await page.unroute('https://generativelanguage.googleapis.com/**');

  // Exercise actual Gemini Web handoff button without opening a real external tab.
  await page.evaluate(() => {
    window.__FULL_AUDIT_OPEN_URL__ = null;
    window.__FULL_AUDIT_CLIPBOARD__ = null;
    window.open = url => { window.__FULL_AUDIT_OPEN_URL__ = String(url); return {}; };
    try {
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText: async text => { window.__FULL_AUDIT_CLIPBOARD__ = String(text); } },
      });
    } catch {}
  });
  if (await page.locator('#solutionAiConnect').isHidden()) await page.click('#solutionAiSettings');
  await page.fill('#solutionAiInput', 'Tiếp tục kiểm tra HPG trên Gemini Web.');
  await page.click('#solutionAiGeminiWeb');
  const handoff = await page.evaluate(() => ({
    openUrl: window.__FULL_AUDIT_OPEN_URL__,
    clipboard: window.__FULL_AUDIT_CLIPBOARD__,
    last: window.__SOLUTION_AI_LAST_GEMINI_HANDOFF__?.(),
  }));
  assert(String(handoff.openUrl || '').includes('gemini.google.com'), `Gemini Web did not open: ${handoff.openUrl}`);
  const handoffText = handoff.clipboard || handoff.last?.text || '';
  assert(handoffText.includes('HPG') && handoffText.includes(hpg.preferredHorizon), 'Gemini handoff lost HPG/preferred horizon');
  assert(handoffText.includes('publishedHorizons') && handoffText.includes('reviewHorizons'), 'Gemini handoff lost release-state contract');

  const relevantFailed = failedRequests.filter(line => !/cloudflareinsights|favicon|google-analytics/i.test(line));
  assert(consoleErrors.length === 0, `browser console errors: ${consoleErrors.join(' | ')}`);
  assert(relevantFailed.length === 0, `failed requests: ${relevantFailed.join(' | ')}`);

  const report = {
    solutionAiFullSystemAudit: 'PASS',
    url,
    pageLoadMs: Date.now() - t0,
    localLatencyMs,
    switchLatencyMs,
    structural,
    ui: {
      initialSymbol: 'FPT',
      initialPreferred: primaryPrice.preferred,
      initialPreferredPrice: primaryPrice.price,
      switchedSymbol: hpg.symbol,
      switchedPreferred: hpg.preferredHorizon,
      geminiSuccessPath: 'PASS',
      geminiModelFailover: 'PASS',
      geminiWebHandoff: 'PASS',
    },
  };
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
}
