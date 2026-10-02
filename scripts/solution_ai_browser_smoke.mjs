import { chromium } from 'playwright';

const base = process.env.SOLUTION_AI_BROWSER_URL
  || process.env.V12_BROWSER_URL
  || 'http://127.0.0.1:8000/forecast-final.html?symbol=FPT';

const symbols = (process.env.SOLUTION_AI_SYMBOLS || 'FPT,ACB,HPG,VIC')
  .split(',')
  .map(x => x.trim().toUpperCase())
  .filter(Boolean);

const browser = await chromium.launch({ headless: true });
const results = [];

function solutionAiConsoleErrors(messages, failedRequests = []) {
  const liveMarketFailed = failedRequests.some(line => /vmews-risk-analytics-sojd\.vercel\.app\/api\/live_market/i.test(line));
  return messages.filter(message => {
    if (/vmews-risk-analytics-sojd\.vercel\.app\/api\/live_market|Access to fetch at .*\/api\/live_market/i.test(message)) return false;
    if (liveMarketFailed && /Failed to load resource:\s*net::ERR_FAILED/i.test(message)) return false;
    return true;
  });
}

function solutionAiFailedRequests(lines) {
  return lines.filter(line => !/cloudflareinsights|favicon|google-analytics|vmews-risk-analytics-sojd\.vercel\.app\/api\/live_market/i.test(line));
}

function withSymbol(url, symbol) {
  const target = new URL(url);
  target.searchParams.set('symbol', symbol);
  return target.href;
}

try {
  for (const symbol of symbols) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const consoleErrors = [];
    const failed = [];
    page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
    page.on('pageerror', error => consoleErrors.push(String(error)));
    page.on('requestfailed', request => failed.push(`${request.method()} ${request.url()} ${request.failure()?.errorText || ''}`));

    const url = withSymbol(base, symbol);
    await page.goto(url, { waitUntil: 'networkidle', timeout: 70000 });
    await page.waitForFunction(() => Boolean(
      window.__SOLUTION_AI_BUILD_CONTEXT__
      && window.__SOLUTION_AI_LOCAL_ANALYSIS__
      && window.__SOLUTION_AI_BUILD_GEMINI_HANDOFF__
      && window.__SOLUTION_AI_ASK__
      && window.__SOLUTION_AI_HEALTH__
      && window.__SOLUTION_AI_REFRESH_LIVE__
      && window.__VMEWS_LOAD_BASE__
    ), null, { timeout: 30000 });

    await page.waitForFunction(() => document.querySelectorAll('#forecastCards .forecastCard').length === 5, null, { timeout: 30000 });

    await page.evaluate(async () => window.__SOLUTION_AI_REFRESH_LIVE__(true));
    const liveHealth = await page.evaluate(() => window.__SOLUTION_AI_HEALTH__());
    if (liveHealth.liveHealth !== 'OK' || !Number.isFinite(Number(liveHealth.livePrice)) || Number(liveHealth.livePrice) <= 0) {
      throw new Error(`${symbol}: independent SoluTION.AI live feed unavailable: ${JSON.stringify(liveHealth)}`);
    }
    const context = await page.evaluate(async () => window.__SOLUTION_AI_BUILD_CONTEXT__());
    if (context.symbol !== symbol) throw new Error(`SoluTION.AI context symbol mismatch: expected ${symbol}, got ${context.symbol}`);
    if (!context.session || Number(context.session.liveClose) !== Number(liveHealth.livePrice)) {
      throw new Error(`${symbol}: context did not adopt independent live price: ${JSON.stringify({ context: context.session, health: liveHealth })}`);
    }

    const labels = Object.keys(context.horizons || {}).sort();
    const expectedLabels = ['T+1', 'T+2', 'T+3', 'T+4', 'T+5'];
    if (JSON.stringify(labels) !== JSON.stringify(expectedLabels)) {
      throw new Error(`${symbol}: AI context must preserve all five horizon states, got ${labels.join(',')}`);
    }

    if (context.forecastFresh === false) {
      if (!Array.isArray(context.publishedHorizons) || context.publishedHorizons.length !== 0) {
        throw new Error(`${symbol}: stale forecast must not expose published point prices`);
      }
      const staleQuestion = 'Chỉ dùng dữ liệu mô hình, phân tích đường forecast T+1 đến T+5 của mã đang xem.';
      const staleLocal = await page.evaluate(({ q, ctx }) => window.__SOLUTION_AI_LOCAL_ANALYSIS__(q, ctx), { q: staleQuestion, ctx: context });
      if (typeof staleLocal !== 'string' || staleLocal.length < 250 || !staleLocal.includes(symbol)) {
        throw new Error(`${symbol}: stale-mode local AI is not useful: ${String(staleLocal).slice(0, 240)}`);
      }
      for (const label of expectedLabels) {
        if (!staleLocal.includes(label)) throw new Error(`${symbol}: stale-mode AI missing ${label}`);
      }
      if (!/REVIEW|chưa phát hành|abstention|đang cập nhật/i.test(staleLocal)) {
        throw new Error(`${symbol}: stale-mode AI does not communicate gated forecast state`);
      }
      const cards = await page.locator('#forecastCards .forecastCard').allInnerTexts();
      if (!cards.some(text => /ĐANG CẬP NHẬT|CHƯA ĐẠT KIỂM ĐỊNH HORIZON|CHƯA CÓ DỮ LIỆU/.test(text))) {
        throw new Error(`${symbol}: stale forecast UI does not expose update/review state`);
      }
      const relevantConsoleErrors = solutionAiConsoleErrors(consoleErrors, failed);
      if (relevantConsoleErrors.length) throw new Error(`${symbol}: console errors: ${relevantConsoleErrors.join(' | ')}`);
      results.push({
        symbol,
        preferredHorizon: context.preferredHorizon,
        publishedHorizons: context.publishedHorizons,
        reviewHorizons: context.reviewHorizons,
        forecastFresh: false,
        liveHealth: liveHealth.liveHealth,
        livePrice: liveHealth.livePrice,
        liveSource: liveHealth.liveSource,
        localChars: staleLocal.length,
      });
      await page.close();
      continue;
    }

    if (!Array.isArray(context.publishedHorizons) || context.publishedHorizons.length < 1) {
      throw new Error(`${symbol}: no published forecast horizon available to AI`);
    }
    if (!context.preferredHorizon || !context.publishedHorizons.includes(context.preferredHorizon)) {
      throw new Error(`${symbol}: preferred horizon is not a published horizon: ${JSON.stringify({ preferred: context.preferredHorizon, published: context.publishedHorizons })}`);
    }

    const preferred = context.horizons[context.preferredHorizon];
    if (!preferred || preferred.releaseStatus !== 'PUBLISHED' || !Number.isFinite(Number(preferred.price))) {
      throw new Error(`${symbol}: preferred horizon has no released point price`);
    }

    const question = 'Chỉ dùng dữ liệu mô hình, phân tích đầy đủ forecast T+1 đến T+5 của mã đang xem.';
    const local = await page.evaluate(({ q, ctx }) => window.__SOLUTION_AI_LOCAL_ANALYSIS__(q, ctx), { q: question, ctx: context });
    if (typeof local !== 'string' || local.length < 300) {
      throw new Error(`${symbol}: local AI answer too short: ${String(local).length}`);
    }
    if (!local.includes(symbol) || !local.includes(context.preferredHorizon)) {
      throw new Error(`${symbol}: local AI answer is not anchored to symbol/preferred horizon`);
    }
    for (const label of expectedLabels) {
      if (!local.includes(label)) throw new Error(`${symbol}: local AI full-path answer missing ${label}`);
    }
    if (/Chưa có đủ đường forecast|Chưa thể tải dữ liệu phân tích/.test(local)) {
      throw new Error(`${symbol}: local AI still falls into generic forecast error: ${local.slice(0, 240)}`);
    }

    const preferredPrice = Number(preferred.price).toLocaleString('vi-VN');
    if (!local.includes(preferredPrice)) {
      throw new Error(`${symbol}: local AI answer does not contain preferred released price ${preferredPrice}`);
    }

    // User-facing no-key path must answer locally instead of requiring Gemini.
    await page.evaluate(() => sessionStorage.removeItem('vmews_solution_ai_browser_session'));
    await page.evaluate(async q => { await window.__SOLUTION_AI_ASK__(q); }, question);
    await page.waitForFunction(() => {
      const items = [...document.querySelectorAll('#solutionAiMessages .aiMessage')];
      return items.length >= 3 && !items.at(-1)?.classList.contains('aiThinking');
    }, null, { timeout: 20000 });

    const ui = await page.evaluate(() => {
      const items = [...document.querySelectorAll('#solutionAiMessages .aiMessage')];
      const last = items.at(-1);
      return {
        text: last?.textContent?.trim() || '',
        className: last?.className || '',
        status: document.querySelector('#solutionAiStatus')?.textContent?.trim() || '',
        health: window.__SOLUTION_AI_HEALTH__(),
      };
    });
    if (ui.className.includes('aiError')) throw new Error(`${symbol}: no-key AI rendered aiError: ${ui.text}`);
    if (ui.text.length < 250 || !ui.text.includes(symbol) || !ui.text.includes(context.preferredHorizon)) {
      throw new Error(`${symbol}: no-key UI answer is not useful/anchored: ${JSON.stringify(ui)}`);
    }
    if (!/forecast|dữ liệu VMEWS|SoluTION\.AI local|Phân tích từ dữ liệu/i.test(ui.status)) {
      throw new Error(`${symbol}: no-key status does not communicate local readiness: ${ui.status}`);
    }

    // Gemini upstream failure must still render a local answer instead of hanging/erroring.
    const syntheticConsoleStart = consoleErrors.length;
    await page.route('https://generativelanguage.googleapis.com/**', async route => {
      const requestUrl = route.request().url();
      if (/\/models\?/.test(requestUrl)) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            models: [{ name: 'models/gemini-2.5-flash', supportedGenerationMethods: ['generateContent'] }],
          }),
        });
        return;
      }
      if (/:generateContent/.test(requestUrl)) {
        const body = route.request().postData() || '';
        if (body.includes('Reply with exactly OK')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ candidates: [{ content: { parts: [{ text: 'OK' }] } }] }),
          });
          return;
        }
      }
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ error: { message: 'synthetic upstream outage' } }),
      });
    });
    await page.evaluate(() => {
      sessionStorage.setItem('vmews_solution_ai_browser_session', 'AIzaSyntheticRegressionKey1234567890');
    });
    const beforeFailureCount = await page.locator('#solutionAiMessages .aiMessage').count();
    const failureQuestion = 'Dựa trên forecast hiện có, nếu Gemini đang lỗi thì vẫn phân tích mã đang xem.';
    await page.evaluate(async q => { await window.__SOLUTION_AI_ASK__(q); }, failureQuestion);
    await page.waitForFunction(count => {
      const items = [...document.querySelectorAll('#solutionAiMessages .aiMessage')];
      return items.length > count && !items.at(-1)?.classList.contains('aiThinking');
    }, beforeFailureCount, { timeout: 20000 });
    const degraded = await page.evaluate(() => {
      const items = [...document.querySelectorAll('#solutionAiMessages .aiMessage')];
      const last = items.at(-1);
      return {
        text: last?.textContent?.trim() || '',
        className: last?.className || '',
        status: document.querySelector('#solutionAiStatus')?.textContent?.trim() || '',
      };
    });
    if (degraded.className.includes('aiError')) throw new Error(`${symbol}: Gemini 503 produced aiError instead of local fallback: ${degraded.text}`);
    if (degraded.text.length < 220 || !degraded.text.includes(symbol) || !degraded.text.includes(context.preferredHorizon)) {
      throw new Error(`${symbol}: Gemini 503 fallback is not useful/anchored: ${JSON.stringify(degraded)}`);
    }
    const syntheticErrors = consoleErrors.slice(syntheticConsoleStart);
    const unexpectedSyntheticErrors = syntheticErrors.filter(message => !/status of 503|503 \(Service Unavailable\)/i.test(message));
    if (unexpectedSyntheticErrors.length) {
      throw new Error(`${symbol}: unexpected console errors during synthetic Gemini outage: ${unexpectedSyntheticErrors.join(' | ')}`);
    }
    // The expected synthetic 503 is already validated by the local-fallback assertions above.
    consoleErrors.splice(syntheticConsoleStart);
    await page.unroute('https://generativelanguage.googleapis.com/**');
    await page.evaluate(() => sessionStorage.removeItem('vmews_solution_ai_browser_session'));

    const handoffQuestion = `Tiếp tục phân tích ${symbol} và giải thích kỳ ${context.preferredHorizon}.`;
    const handoff = await page.evaluate(({ q, ctx }) => window.__SOLUTION_AI_BUILD_GEMINI_HANDOFF__(q, ctx), { q: handoffQuestion, ctx: context });
    for (const token of [symbol, handoffQuestion, context.preferredHorizon, 'publishedHorizons', 'reviewHorizons']) {
      if (!handoff.includes(token)) throw new Error(`${symbol}: Gemini handoff missing ${token}`);
    }

    const cards = await page.locator('#forecastCards .forecastCard').allInnerTexts();
    const publishedCards = cards.filter(text => /Giá dự báo (?:của mô hình|trung tâm)/.test(text));
    const reviewCards = cards.filter(text => /CHƯA ĐẠT KIỂM ĐỊNH HORIZON|CHƯA CÓ DỮ LIỆU|ĐANG CẬP NHẬT/.test(text));
    const publishedHorizons = Array.isArray(context.publishedHorizons) ? context.publishedHorizons : [];
    if (publishedHorizons.length && publishedCards.length < 1) {
      throw new Error(`${symbol}: validated forecast exists in context but UI exposes no published point forecast`);
    }
    if (!publishedHorizons.length && reviewCards.length < 1) {
      throw new Error(`${symbol}: no validated forecast is published, but UI does not expose the validation-gated review state`);
    }

    const relevantConsoleErrors = solutionAiConsoleErrors(consoleErrors, failed);
    if (relevantConsoleErrors.length) throw new Error(`${symbol}: console errors: ${relevantConsoleErrors.join(' | ')}`);
    const relevantFailed = solutionAiFailedRequests(failed);
    if (relevantFailed.length) throw new Error(`${symbol}: failed requests: ${relevantFailed.join(' | ')}`);

    results.push({
      symbol,
      preferredHorizon: context.preferredHorizon,
      publishedHorizons: context.publishedHorizons,
      reviewHorizons: context.reviewHorizons,
      liveHealth: liveHealth.liveHealth,
      livePrice: liveHealth.livePrice,
      liveSource: liveHealth.liveSource,
      localChars: local.length,
      uiChars: ui.text.length,
    });
    await page.close();
  }

  console.log(JSON.stringify({ solutionAiBrowserSmoke: 'PASS', base, results }, null, 2));
} finally {
  await browser.close();
}
