from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
AI = ROOT / "solution-ai-v17.js"
BACKEND = ROOT / "api/solution-ai.js"
DEEP = ROOT / "forecast-deep-dive-v24.js"
HTML = ROOT / "forecast-final.html"
FRONTEND_TEST = ROOT / "scripts/solution_ai_frontend_v17_test.mjs"
BROWSER_TEST = ROOT / "scripts/forecast_v22_browser_e2e.mjs"

# --- SoluTION.AI: free-form intent first; ranking only when explicitly requested ---
ai = AI.read_text(encoding="utf-8")

ai = ai.replace(
    '    required: ["direct_answer", "model_read", "external_evidence", "integrated_outlook", "risks", "watch_next", "limitations"],',
    '    required: ["direct_answer", "model_read", "external_evidence", "integrated_outlook"],',
    1,
)

ai = ai.replace(
    '      "Bảng nổi bật mặc định xếp hạng toàn bộ HOSE đủ điều kiện kiểm định; khi người dùng yêu cầu VN30 thì mới giới hạn vào rổ VN30 hiện hành.",',
    '      "Chỉ trả bảng xếp hạng HOSE/VN30 khi người dùng hỏi rõ top, xếp hạng, mã nào hoặc so sánh nhiều mã. Từ “so sánh” trong câu hỏi về đường forecast của một mã tuyệt đối không được hiểu là yêu cầu xếp hạng thị trường.",\n      "Khi người dùng hỏi T+1→T+5, tăng tốc, chững lại hoặc thiếu xác nhận, phải phân tích tuần tự từng nhịp của đúng mã đang xem; không chèn bảng top thị trường nếu không được hỏi.",\n      "Không tự chèn câu mẫu về xác suất, kiểm định hay giới hạn dữ liệu. Chỉ nói phần đó khi người dùng hỏi độ tin cậy/xác suất/kiểm định, hoặc khi một gate cụ thể trực tiếp giải thích vì sao kết luận còn yếu.",',
    1,
)

anchor = '    const flowQuestion = /dòng tiền|ngoại|tự doanh/.test(question);\n\n    if (/top|xếp hạng|tăng mạnh|so sánh/.test(question)) {'
replacement = r'''    const flowQuestion = /dòng tiền|ngoại|tự doanh/.test(question);
    const rankQuestion = /\btop\b\s*\d*|xếp hạng|(?:mã|cổ phiếu)\s+nào.*(?:tăng|dự báo|forecast|nổi bật)|(?:HOSE|VN30).*(?:top|xếp hạng|nổi bật)|so sánh\s+(?:các\s+)?(?:mã|cổ phiếu)/.test(question);
    const pathQuestion = !rankQuestion && /đường\s+(?:forecast|dự báo)|forecast.*t\+\d|t\+1.*t\+5|từ\s+t\+1|tăng tốc|chững(?:\s+lại)?|thiếu xác nhận|nhịp\s+(?:forecast|dự báo)|so sánh.*(?:forecast|dự báo)/.test(question);
    const validationQuestion = /kiểm định|độ tin cậy|xác suất|validation|backtest|thiếu xác nhận|đúng chiều|sai số/.test(question);

    if (pathQuestion) {
      const ordered = Object.entries(context.horizons || {})
        .filter(([label, horizon]) => /^T\+[1-5]$/.test(label) && number(horizon?.price) !== null)
        .sort((left, right) => Number(left[0].slice(2)) - Number(right[0].slice(2)));
      if (!ordered.length) return `Chưa có đủ đường forecast T+1→T+5 cho ${context.symbol}.`;
      const path = ordered.map(([label, horizon], index) => {
        const prior = index === 0 ? activeClose : number(ordered[index - 1][1]?.price);
        const price = number(horizon.price);
        const step = prior > 0 && price !== null ? price / prior - 1 : null;
        const missing = [];
        if (horizon.directionValidated === false || horizon.pointDirectionValidated === false) missing.push("chiều");
        if (horizon.magnitudeValidated === false) missing.push("độ lớn");
        return { label, horizon, price, step, missing };
      });
      lines.push(`### Đường forecast ${context.symbol}`);
      for (const row of path) {
        lines.push(`- **${row.label}:** ${money(row.price)} (${pct(row.horizon.expectedReturn)})${row.step === null ? "" : ` · nhịp từ mốc trước ${pct(row.step)}`}${number(row.horizon.lowerPrice) === null || number(row.horizon.upperPrice) === null ? "" : ` · vùng ${money(row.horizon.lowerPrice)}–${money(row.horizon.upperPrice)}`}.`);
      }
      const rhythm = [];
      for (let index = 1; index < path.length; index += 1) {
        const current = path[index], previous = path[index - 1];
        if (current.step === null) continue;
        let stateLabel = "giữ nhịp";
        if (Math.abs(current.step) < .0015) stateLabel = "chững lại";
        else if (previous.step !== null && current.step - previous.step > .0015) stateLabel = "tăng tốc";
        else if (previous.step !== null && current.step - previous.step < -.0015) stateLabel = "giảm tốc";
        rhythm.push(`- **${previous.label} → ${current.label}: ${stateLabel}** · bước ${pct(current.step)}${previous.step === null ? "" : ` so với ${pct(previous.step)} ở nhịp trước`}.`);
      }
      if (rhythm.length) lines.push("### Nhịp forecast", ...rhythm);
      const missingRows = path.filter(row => row.missing.length);
      const technical = context.technical || {};
      const confirmations = [];
      if (number(technical.rsi14) !== null) confirmations.push(`RSI14 ${Number(technical.rsi14).toFixed(1)}`);
      if (number(technical.macdHistogram) !== null) confirmations.push(`MACD histogram ${number(technical.macdHistogram) > 0 ? "dương" : number(technical.macdHistogram) < 0 ? "âm" : "trung tính"}`);
      if (number(technical.obvChange5) !== null) confirmations.push(`OBV 5 phiên ${number(technical.obvChange5) > 0 ? "đi lên" : number(technical.obvChange5) < 0 ? "đi xuống" : "đi ngang"}`);
      if (number(technical.volumeRatio20) !== null) confirmations.push(`khối lượng ${Number(technical.volumeRatio20).toFixed(2)}× MA20`);
      lines.push("### Xác nhận hiện tại");
      if (confirmations.length) lines.push(`- Kỹ thuật: ${confirmations.join(" · ")}.`);
      if (missingRows.length) {
        lines.push(`- Gate còn yếu: ${missingRows.map(row => `${row.label} (${row.missing.join(" + ")})`).join("; ")}. Đây là nơi cần thêm xác nhận từ giá/khối lượng/dòng tiền, không phải lý do để bỏ toàn bộ đường forecast.`);
      } else {
        lines.push("- Snapshot hiện tại không có kỳ nào bị đánh dấu fail rõ ở gate chiều/độ lớn; trọng tâm là xem các nhịp forecast có được giá, MACD/OBV và dòng tiền xác nhận hay không.");
      }
      if (context.flow?.foreign?.available || context.flow?.proprietary?.available) {
        const flowBits = [];
        if (context.flow.foreign?.available && number(context.flow.foreign.net5) !== null) flowBits.push(`ngoại 5P ${money(context.flow.foreign.net5)}`);
        if (context.flow.proprietary?.available && number(context.flow.proprietary.net5) !== null) flowBits.push(`tự doanh 5P ${money(context.flow.proprietary.net5)}`);
        if (flowBits.length) lines.push(`- Dòng tiền: ${flowBits.join(" · ")}.`);
      }
      return lines.join("\n");
    }

    if (rankQuestion) {'''
if anchor not in ai:
    raise SystemExit("localAnalysis ranking anchor missing")
ai = ai.replace(anchor, replacement, 1)

old_validation = '    if (/rủi ro|lưu ý|an toàn|đầy đủ|phân tích|kết hợp|tổng hợp|forecast/.test(question)) {'
if old_validation not in ai:
    raise SystemExit("generic validation trigger missing")
ai = ai.replace(old_validation, '    if (validationQuestion) {', 1)

old_sentence = '${five.directionValidated ? "Xác suất chiều đã vượt kiểm định." : "Chiều tăng/giảm chưa đủ độ tin cậy để công bố xác suất; không được diễn giải kịch bản tăng thành cam kết."}'
new_sentence = '${validationQuestion ? (five.directionValidated ? "Gate chiều T+5 đang PASS." : "Gate chiều T+5 hiện chưa PASS; phần xác nhận hướng vì vậy yếu hơn phần ước lượng biên độ.") : ""}'
if old_sentence not in ai:
    raise SystemExit("T+5 probability wording anchor missing")
ai = ai.replace(old_sentence, new_sentence, 1)

old_final = '${context.validation.directionValidated ? "Xác suất hướng đã qua kiểm định." : "Xác suất hướng T+5 chưa đủ độ tin cậy nên không được công bố."}'
new_final = '${context.validation.directionValidated ? "Gate chiều T+5: PASS." : "Gate chiều T+5: chưa PASS; cần đọc cùng kỹ thuật, dòng tiền và vùng bất định thay vì suy diễn thêm một xác suất."}'
if old_final not in ai:
    raise SystemExit("final canned probability anchor missing")
ai = ai.replace(old_final, new_final, 1)

new_focus = r'''  function enforceAnswerFocus(answer, question, context, intent) {
    const text = String(answer || "").trim();
    if (!intent.useSnapshot) return text;
    const hasSymbol = new RegExp(`(^|[^A-Za-z0-9])${context.symbol}([^A-Za-z0-9]|$)`, "i").test(text);
    const hasForecast = /T\+1|T\+2|T\+3|T\+4|T\+5|forecast|dự báo|vùng (?:giá|bất định)/i.test(text);
    const hasModelNumber = Object.values(context.horizons || {}).some(item => text.includes(money(item.price)));
    const genericEssay = /khung phân tích tích hợp|quy trình đa chiều|nguyên tắc kết hợp thông tin|để đánh giá toàn diện.*cần tiếp cận|phương pháp và khung phân tích/i.test(text);
    const forecastQuestion = /forecast|dự báo|T\+\d|target|mục tiêu|vùng giá|tăng tốc|chững|thiếu xác nhận|đường giá/i.test(question);
    if (genericEssay) return localAnalysis(question, context);
    if (!forecastQuestion) {
      // Financial/technical/flow/news deep-dives are allowed to answer their actual question.
      // Do not throw away good research simply because it does not repeat forecast numbers.
      return text || localAnalysis(question, context);
    }
    if ([hasSymbol, hasForecast, hasModelNumber].filter(Boolean).length < 2) return localAnalysis(question, context);
    const needsFullPath = /đầy đủ|toàn bộ|tổng hợp|kết hợp|kết quả phân tích|tình hình dự báo|forecast|các kỳ|T\+1.*T\+5|tăng tốc|chững|thiếu xác nhận/i.test(question);
    const missingPrices = Object.values(context.horizons || {}).filter(item => number(item?.price) !== null && !text.includes(money(item.price)));
    if (needsFullPath && missingPrices.length) {
      return [
        `### Snapshot forecast ${context.symbol}`,
        ...forecastPath(context),
        text,
      ].join("\n");
    }
    return text;
  }
'''
ai, count = re.subn(r'  function enforceAnswerFocus\(answer, question, context, intent\) \{.*?\n  \}\n\n  function sourceFallback', new_focus + '\n  function sourceFallback', ai, count=1, flags=re.S)
if count != 1:
    raise SystemExit(f"enforceAnswerFocus replacement count={count}")

AI.write_text(ai, encoding="utf-8")

# --- Server AI: same open-ended rules; remove boilerplate quỹ/validation bias ---
backend = BACKEND.read_text(encoding="utf-8")
backend = backend.replace(
    '    "Tỷ trọng quỹ là tỷ trọng trong danh mục từng quỹ, không phải tỷ lệ sở hữu doanh nghiệp và không chứng minh quỹ đang mua.",\n',
    '    "Với dữ liệu quỹ, chỉ tập trung vào quỹ nắm giữ, tỷ trọng danh mục, NAV và thay đổi có ý nghĩa; không giảng giải định nghĩa nếu người dùng không hỏi.",\n',
    1,
)
backend = backend.replace(
    '    "Bảng nổi bật mặc định có thể xếp hạng toàn HOSE đủ điều kiện kiểm định; chỉ giới hạn VN30 khi câu hỏi hoặc ngữ cảnh yêu cầu rõ VN30.",',
    '    "Chỉ trả bảng xếp hạng HOSE/VN30 khi người dùng hỏi rõ top, xếp hạng, mã nào hoặc so sánh nhiều mã; không coi từ “so sánh” trong câu hỏi về T+1→T+5 của một mã là yêu cầu ranking.",\n    "Nếu hỏi đường forecast T+1→T+5, hãy so từng nhịp liên tiếp, chỉ ra nơi tăng tốc/chững/giảm tốc và tín hiệu nào đang xác nhận hoặc mâu thuẫn.",\n    "Không tự thêm câu mẫu về xác suất, giới hạn hay kiểm định. Chỉ nêu một gate cụ thể khi câu hỏi hỏi độ tin cậy/thiếu xác nhận hoặc gate đó trực tiếp ảnh hưởng kết luận.",',
    1,
)
BACKEND.write_text(backend, encoding="utf-8")

# --- Deep-dive UI: three strategic AI entry points only; suggestions are optional ---
deep = DEEP.read_text(encoding="utf-8")

insert_topic = r'''  if(/forecast\s*&\s*kỹ thuật|forecast và kỹ thuật|phân tích ai/.test(lower))return{title:`Forecast & kỹ thuật ${symbol}`,summary:"Một cửa phân tích forecast và tín hiệu xác nhận. Gợi ý chỉ để bắt đầu — có thể hỏi tự do bất kỳ điều gì về mã đang xem.",prompts:[`So sánh đường forecast T+1 đến T+5 của ${symbol}; chỗ nào đang tăng tốc, chững lại hoặc thiếu xác nhận?`,`Đối chiếu forecast ${symbol} với RSI, MACD, OBV, khối lượng và dòng tiền; điểm nào đang xác nhận hoặc mâu thuẫn?`]};
  if(/dữ liệu\s*&\s*doanh nghiệp|dữ liệu doanh nghiệp|nguồn & độ phủ|nguồn và độ phủ/.test(lower))return{title:`Dữ liệu & doanh nghiệp ${symbol}`,summary:"Hỏi tự do về BCTC, dòng tiền, quỹ, định giá hoặc nguồn mới. AI ưu tiên đúng câu hỏi thay vì ép về forecast.",prompts:[`Tìm và phân tích BCTC mới nhất của ${symbol}: doanh thu, lợi nhuận, dòng tiền, nợ và điểm bất thường đáng chú ý.`,`Tổng hợp khối ngoại, tự doanh và quỹ của ${symbol}; chỉ ra tín hiệu dòng tiền thực sự có giá trị.`]};
'''
anchor_topic = '  if(/tài chính|bctc|doanh thu|lợi nhuận|định giá|roe|p\\/e|p\\/b/.test(lower))'
if anchor_topic not in deep:
    raise SystemExit("deep topic anchor missing")
deep = deep.replace(anchor_topic, insert_topic + anchor_topic, 1)

# Only show two optional suggestions; textarea stays free-form.
deep = deep.replace('config.prompts.forEach((prompt,index)=>{', 'config.prompts.slice(0,2).forEach((prompt,index)=>{', 1)
deep = deep.replace('placeholder="Chọn một gợi ý hoặc tự đặt câu hỏi sâu hơn…"', 'placeholder="Hỏi tự do về mã đang xem…"', 1)

deep = deep.replace(
    'function addHeader(selector,topic,label="Hỏi sâu ↗")',
    'function addHeader(selector,topic,label="Phân tích AI ↗")',
    1,
)
deep = deep.replace(
    'function addHeaderToPanel(panel,topic){if(panel.querySelector(":scope > .deepDiveHeader"))return;const button=document.createElement("button");button.type="button";button.className="deepDiveHeader";button.textContent="Hỏi sâu ↗";',
    'function addHeaderToPanel(panel,topic,label="Phân tích AI ↗"){if(panel.querySelector(":scope > .deepDiveHeader"))return;const button=document.createElement("button");button.type="button";button.className="deepDiveHeader";button.textContent=label;',
    1,
)

new_decorate = r'''function decorate(){
  // Keep AI discoverable without placing a button on every metric/card.
  $$(".deepDiveMini").forEach(button=>button.remove());
  $$(".deepQueryable").forEach(card=>{card.classList.remove("deepQueryable");delete card.dataset.deepDiveReady});
  addHeader("#forecast .chartTools","Forecast & kỹ thuật","AI phân tích ↗");
  const eventPanels=$$("#events > .panel");
  if(eventPanels[0])addHeaderToPanel(eventPanels[0],"Tin & sự kiện","AI tin tức ↗");
  if(eventPanels[2])addHeaderToPanel(eventPanels[2],"Dữ liệu & doanh nghiệp","AI dữ liệu ↗");
}
'''
deep, count = re.subn(r'function decorate\(\)\{.*?\n\}', new_decorate.rstrip(), deep, count=1, flags=re.S)
if count != 1:
    raise SystemExit(f"decorate replacement count={count}")

DEEP.write_text(deep, encoding="utf-8")

# --- Cache bust assets ---
html = HTML.read_text(encoding="utf-8")
html = html.replace('solution-ai-v17.js?release=24.0', 'solution-ai-v17.js?release=25.0')
html = html.replace('forecast-deep-dive-v24.js?release=24.0', 'forecast-deep-dive-v24.js?release=25.0')
HTML.write_text(html, encoding="utf-8")

# --- Tests: regression for the exact failure the user observed ---
test = FRONTEND_TEST.read_text(encoding="utf-8")
extra = r'''

test("single-symbol forecast comparison stays on that symbol instead of routing to HOSE ranking", async () => {
  const { window, source } = await setup();
  const context = await window.__SOLUTION_AI_BUILD_CONTEXT__();
  const answer = window.__SOLUTION_AI_LOCAL_ANALYSIS__("So sánh đường forecast T+1 đến T+5 của FPT; chỗ nào đang tăng tốc, chững lại hoặc thiếu xác nhận?", context);
  assert.match(answer, /Đường forecast FPT/);
  assert.match(answer, /T\+1/);
  assert.match(answer, /T\+5/);
  assert.match(answer, /Nhịp forecast/);
  assert.match(answer, /tăng tốc|giảm tốc|chững lại|giữ nhịp/);
  assert.doesNotMatch(answer, /Xếp hạng HOSE|Các mã HOSE có mức dự báo/);
  assert.doesNotMatch(answer, /Xác suất hướng T\+5 chưa đủ độ tin cậy nên không được công bố|Chiều tăng\/giảm chưa đủ độ tin cậy để công bố xác suất/);
  assert.match(source, /Chỉ trả bảng xếp hạng HOSE\/VN30 khi người dùng hỏi rõ/);
});

test("ranking still works only for an explicit ranking question", async () => {
  const { window } = await setup();
  const context = await window.__SOLUTION_AI_BUILD_CONTEXT__();
  const answer = window.__SOLUTION_AI_LOCAL_ANALYSIS__("Top 5 HOSE có forecast tăng nổi bật nhất", context);
  assert.match(answer, /Xếp hạng HOSE/);
});

test("ordinary forecast analysis does not append generic validation boilerplate", async () => {
  const { window } = await setup();
  const context = await window.__SOLUTION_AI_BUILD_CONTEXT__();
  const answer = window.__SOLUTION_AI_LOCAL_ANALYSIS__("Phân tích forecast FPT và các yếu tố chính", context);
  assert.doesNotMatch(answer, /Xác suất hướng T\+5 chưa đủ độ tin cậy nên không được công bố/);
  const validation = window.__SOLUTION_AI_LOCAL_ANALYSIS__("Kiểm định độ tin cậy forecast FPT", context);
  assert.match(validation, /Gate chiều T\+5|Kiểm định/);
});
'''
if 'single-symbol forecast comparison stays on that symbol' not in test:
    test = test.rstrip() + extra + "\n"
FRONTEND_TEST.write_text(test, encoding="utf-8")

browser = BROWSER_TEST.read_text(encoding="utf-8")
old_browser = r'''  const financeCard = page.locator("#sourceAudit .sourceCard", { hasText: "Tài chính doanh nghiệp" }).first();
  await financeCard.locator(".deepDiveMini").click();
  await page.waitForSelector("#vmewsDeepDive:not([hidden])");
  assert.match(await page.locator("#vmewsDeepDiveTitle").innerText(), /Tài chính FPT/);
  assert.ok(await page.locator("#vmewsDeepDive .vmewsDeepDivePrompt").count() >= 4);
  assert.match(await page.locator("#vmewsDeepDive").evaluate(node => getComputedStyle(node.querySelector(".vmewsDeepDiveDialog")).borderColor), /rgb/);
  await page.locator("#vmewsDeepDive .vmewsDeepDiveClose").click();
  await page.locator("#forecast .deepDiveHeader").click();
  await page.waitForSelector("#vmewsDeepDive:not([hidden])");
  assert.match(await page.locator("#vmewsDeepDiveTitle").innerText(), /Kỹ thuật FPT/);'''
new_browser = r'''  assert.equal(await page.locator(".deepDiveMini").count(), 0);
  const aiShortcuts = await page.locator(".deepDiveHeader").count();
  assert.ok(aiShortcuts >= 2 && aiShortcuts <= 3);
  const dataPanel = page.locator("#events > .panel").nth(2);
  await dataPanel.locator(".deepDiveHeader").click();
  await page.waitForSelector("#vmewsDeepDive:not([hidden])");
  assert.match(await page.locator("#vmewsDeepDiveTitle").innerText(), /Dữ liệu & doanh nghiệp FPT/);
  assert.ok(await page.locator("#vmewsDeepDive .vmewsDeepDivePrompt").count() <= 2);
  assert.match(await page.locator("#vmewsDeepDive .vmewsDeepDiveInput").getAttribute("placeholder"), /Hỏi tự do/);
  assert.match(await page.locator("#vmewsDeepDive").evaluate(node => getComputedStyle(node.querySelector(".vmewsDeepDiveDialog")).borderColor), /rgb/);
  await page.locator("#vmewsDeepDive .vmewsDeepDiveClose").click();
  await page.locator("#forecast .deepDiveHeader").click();
  await page.waitForSelector("#vmewsDeepDive:not([hidden])");
  assert.match(await page.locator("#vmewsDeepDiveTitle").innerText(), /Forecast & kỹ thuật FPT/);'''
if old_browser not in browser:
    raise SystemExit("V24 browser deep-dive block missing")
browser = browser.replace(old_browser, new_browser, 1)
BROWSER_TEST.write_text(browser, encoding="utf-8")

# One-time patch scaffold should not remain in production.
Path(__file__).unlink()
print("V25 open AI router patch applied")
