from pathlib import Path
import re

JS = Path("solution-ai-v17.js")
FRONTEND_TEST = Path("scripts/solution_ai_frontend_v17_test.mjs")
BROWSER_TEST = Path("scripts/forecast_v22_browser_e2e.mjs")

source = JS.read_text(encoding="utf-8")

# Keep canonical leaderboard order instead of re-sorting handoff context by raw upside.
source, count = re.subn(
    r'(\.filter\(row => row\.close > 0 && row\.forecast > row\.close && number\(row\.return\) !== null\)\n)\s*\.sort\(\(left, right\) => right\.return - left\.return\)\n\s*(\.slice\(0, 10\);)',
    r'\1      \2',
    source,
    count=1,
)
if count != 1:
    raise SystemExit(f"expected one top-mover sort replacement, got {count}")

old = '''    const modelAudit = base.model.horizons?.["5"] || {};
    const chartHistory = base.dash.charts?.[symbol] || [];
    return {
'''
new = '''    const modelAudit = base.model.horizons?.["5"] || {};
    const chartHistory = base.dash.charts?.[symbol] || [];
    const currentRankIndex = ranked.findIndex(row => String(row?.symbol || "").toUpperCase() === symbol);
    const currentRankRow = currentRankIndex >= 0 ? ranked[currentRankIndex] : null;
    const fiveSnapshot = snapshot.horizons?.["5"] || {};
    return {
'''
if old not in source:
    raise SystemExit("buildContext rank insertion anchor missing")
source = source.replace(old, new, 1)

old = '''      topMovers: top,
    };
  }
'''
new = '''      marketRanking: {
        scope: "HOSE",
        canonicalVisibleRank: currentRankIndex >= 0 ? currentRankIndex + 1 : null,
        leaderboardRows: ranked.length,
        isTop10: currentRankIndex >= 0 && currentRankIndex < 10,
        rankScore: number(currentRankRow?.rankScore),
        liveUpside: number(currentRankRow?.upside),
        modelRankPercentile: number(fiveSnapshot.crossSectionalRankPercentile),
        modelRankUniverse: number(fiveSnapshot.crossSectionalRankUniverse),
        modelRankValidated: fiveSnapshot.crossSectionalRankValidated === true,
      },
      topMovers: top,
    };
  }
'''
if old not in source:
    raise SystemExit("topMovers return anchor missing")
source = source.replace(old, new, 1)

handoff_block = r'''
  let lastGeminiHandoffText = "";
  let lastGeminiHandoffContext = null;
  let handoffUiMounted = false;
  let handoffCard = null;
  let handoffStatusNode = null;
  let handoffDetailNode = null;
  let handoffPreviewNode = null;
  let handoffPreviewButton = null;

  function redactHandoffText(value) {
    return String(value ?? "")
      .replace(/\bAIza[0-9A-Za-z_-]{20,}\b/g, "[REDACTED_GOOGLE_KEY]")
      .replace(/\bAQ\.[0-9A-Za-z._-]{16,}\b/g, "[REDACTED_AUTH_KEY]")
      .replace(/((?:api[_ -]?key|authorization|bearer|token|secret)\s*[:=]?\s*)([A-Za-z0-9._-]{16,})/gi, "$1[REDACTED_SECRET]");
  }

  function sanitizeForHandoff(value, depth = 0) {
    if (depth > 8 || value === undefined) return null;
    if (value === null || typeof value === "number" || typeof value === "boolean") return value;
    if (typeof value === "string") return redactHandoffText(value).slice(0, 5000);
    if (Array.isArray(value)) return value.slice(0, 30).map(item => sanitizeForHandoff(item, depth + 1));
    if (typeof value !== "object") return String(value);
    const result = {};
    for (const [key, item] of Object.entries(value)) {
      if (/(?:api.?key|secret|credential|authorization|access.?token|refresh.?token)/i.test(key)) {
        result[key] = "[REDACTED]";
        continue;
      }
      result[key] = sanitizeForHandoff(item, depth + 1);
    }
    return result;
  }

  function handoffConversation() {
    return (state.messages || []).slice(-8).map(message => ({
      role: message.role === "assistant" ? "assistant" : "user",
      content: redactHandoffText(message.content).slice(0, 2200),
    }));
  }

  function resolveHandoffQuestion(explicitQuestion = "") {
    const explicit = redactHandoffText(explicitQuestion).trim();
    if (explicit) return explicit.slice(0, 2200);
    const draft = redactHandoffText($("#solutionAiInput")?.value || "").trim();
    if (draft) return draft.slice(0, 2200);
    const lastUser = [...(state.messages || [])].reverse().find(message => message.role === "user");
    if (lastUser?.content) return redactHandoffText(lastUser.content).slice(0, 2200);
    return "Phân tích toàn bộ forecast hiện tại, ưu tiên điều gì đáng chú ý nhất và điều kiện nào làm thay đổi kết luận?";
  }

  function geminiHandoffPayload(context = state.context || {}, explicitQuestion = "") {
    const question = resolveHandoffQuestion(explicitQuestion);
    const liveClose = number(context.session?.liveClose);
    const mode = liveClose !== null && liveClose > 0 ? "SESSION" : "EOD";
    const activePrice = mode === "SESSION" ? liveClose : number(context.close);
    const payload = {
      handoff: {
        version: "VMEWS-GEMINI-HANDOFF-23.0",
        source: "SoluTION.AI",
        generatedAt: new Date().toISOString(),
        continuity: "CONTINUE_CURRENT_SESSION",
        dataMode: mode,
        rule: "EOD forecast is sealed; session price may only recompute remaining distance to the sealed target.",
      },
      userIntent: {
        currentQuestion: question,
        recentConversation: handoffConversation(),
        instruction: "Continue from this exact state. Do not ask the user to re-enter forecast facts already present here.",
      },
      forecast: {
        symbol: context.symbol || null,
        asOf: context.asOf || null,
        decisionAt: context.decisionAt || null,
        sector: context.sector || null,
        riskStatus: context.riskStatus || null,
        dataFreshness: context.dataFreshness || null,
        dailyVolatility: context.dailyVolatility ?? null,
        sealedCoreClose: number(context.close),
        activePrice,
        session: context.session || null,
        horizons: context.horizons || {},
        marketRanking: context.marketRanking || null,
        topHOSECandidates: context.topMovers || [],
      },
      evidence: {
        technical: context.technical || null,
        flow: context.flow || null,
        fund: context.fund || null,
        financial: context.financial || null,
        issuerNews: context.news || [],
        communitySignals: context.communitySignals || [],
        communityMonitoring: context.communityMonitoring || [],
        marketContext: context.marketContext || [],
        communityUpdatedAt: context.communityUpdatedAt || null,
      },
      validation: context.validation || null,
    };
    return sanitizeForHandoff(payload);
  }

  function externalGeminiPrompt(explicitQuestion = "", context = state.context || {}) {
    const payload = geminiHandoffPayload(context, explicitQuestion);
    return [
      "SoluTION.AI → Gemini Web | CONTINUATION HANDOFF",
      "Bạn đang tiếp tục đúng phiên phân tích từ SoluTION.AI. Không yêu cầu người dùng nhập lại dữ liệu đã có trong payload.",
      "Dữ liệu forecast EOD/core là snapshot đã niêm phong: không tự sửa close, target, interval, probability hay validation.",
      "Nếu dataMode=SESSION, liveClose chỉ là giá quan sát mới nhất để đánh giá khoảng cách còn lại tới target đã niêm phong; không được biến live price thành một forecast mới.",
      "Hãy đọc toàn bộ T+1→T+5, ranking HOSE, technical, dòng tiền, quỹ, tài chính, tin doanh nghiệp, tín hiệu cộng đồng và validation trước khi kết luận.",
      "Ưu tiên trả lời currentQuestion. Nếu câu hỏi rộng, cấu trúc: (1) kết luận hiện tại, (2) đường T+1→T+5, (3) vị thế/ranking thị trường, (4) technical + flow + fund + financial, (5) news/community, (6) độ tin cậy và phần chưa được kiểm định, (7) điều kiện xác nhận và vô hiệu.",
      "Không dùng disclaimer chung; nói rõ dữ liệu nào là EOD, dữ liệu nào là SESSION và dữ liệu nào thiếu/stale.",
      "PAYLOAD JSON:",
      JSON.stringify(payload, null, 2),
    ].join("\n");
  }

  async function copyHandoffText(text) {
    const content = String(text || "");
    if (!content) return false;
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(content);
        return true;
      }
    } catch { /* fall through */ }
    if (!document?.body || typeof document.createElement !== "function") return false;
    const textarea = document.createElement("textarea");
    textarea.value = content;
    textarea.setAttribute?.("readonly", "");
    if (textarea.style) textarea.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0";
    document.body.append?.(textarea);
    textarea.select?.();
    let copied = false;
    try { copied = Boolean(document.execCommand?.("copy")); } catch { copied = false; }
    textarea.remove?.();
    return copied;
  }

  function mountGeminiHandoffUi() {
    if (handoffUiMounted) return;
    handoffUiMounted = true;
    const button = $("#solutionAiGeminiWeb");
    if (button) {
      button.textContent = "Tiếp tục trên Gemini Web ↗";
      button.setAttribute?.("title", "Mang toàn bộ forecast, ranking, dữ liệu phiên và câu hỏi hiện tại sang Gemini Web");
    }
    const panel = $("#solutionAiPanel");
    if (!panel || typeof document.createElement !== "function") return;
    handoffCard = document.createElement("section");
    handoffCard.id = "solutionAiHandoffCard";
    handoffCard.className = "aiHandoffCard";
    handoffCard.hidden = true;
    const title = document.createElement("strong");
    title.textContent = "Phiên Gemini đã được chuẩn bị";
    handoffStatusNode = document.createElement("span");
    handoffStatusNode.className = "aiHandoffStatus";
    handoffDetailNode = document.createElement("small");
    handoffDetailNode.className = "aiHandoffDetail";
    const actions = document.createElement("div");
    actions.className = "aiHandoffActions";
    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.textContent = "Sao chép lại";
    const previewButton = document.createElement("button");
    previewButton.type = "button";
    previewButton.textContent = "Xem gói chuyển";
    handoffPreviewButton = previewButton;
    handoffPreviewNode = document.createElement("pre");
    handoffPreviewNode.className = "aiHandoffPreview";
    handoffPreviewNode.hidden = true;
    copyButton.addEventListener("click", async () => {
      const copied = await copyHandoffText(lastGeminiHandoffText);
      if (handoffStatusNode) handoffStatusNode.textContent = copied ? "Đã sao chép lại — chỉ cần dán vào Gemini." : "Trình duyệt chặn clipboard — mở phần xem gói chuyển để sao chép.";
    });
    previewButton.addEventListener("click", () => {
      if (!handoffPreviewNode) return;
      handoffPreviewNode.hidden = !handoffPreviewNode.hidden;
      previewButton.textContent = handoffPreviewNode.hidden ? "Xem gói chuyển" : "Ẩn gói chuyển";
    });
    actions.append(copyButton, previewButton);
    handoffCard.append(title, handoffStatusNode, handoffDetailNode, actions, handoffPreviewNode);
    const connect = $("#solutionAiConnect");
    if (connect?.insertAdjacentElement) connect.insertAdjacentElement("afterend", handoffCard);
    else panel.append?.(handoffCard);
    if (document.head && !document.getElementById?.("solutionAiHandoffStyle")) {
      const style = document.createElement("style");
      style.id = "solutionAiHandoffStyle";
      style.textContent = `.aiHandoffCard{margin:10px 14px;padding:10px 12px;border:1px solid rgba(90,150,255,.24);border-radius:12px;background:rgba(25,48,82,.36);display:grid;gap:6px}.aiHandoffCard[hidden]{display:none}.aiHandoffStatus{font-size:12px;font-weight:700}.aiHandoffDetail{opacity:.8;line-height:1.45}.aiHandoffActions{display:flex;gap:8px;flex-wrap:wrap}.aiHandoffActions button{border:1px solid rgba(255,255,255,.16);background:rgba(255,255,255,.07);color:inherit;border-radius:9px;padding:6px 9px;cursor:pointer}.aiHandoffPreview{max-height:220px;overflow:auto;white-space:pre-wrap;word-break:break-word;margin:4px 0 0;padding:8px;border-radius:9px;background:rgba(0,0,0,.2);font-size:10px;line-height:1.35}@media(max-width:520px){.aiHandoffCard{margin:8px 10px}.aiHandoffActions button{flex:1}}`;
      document.head.append(style);
    }
  }

  function renderGeminiHandoffState(context, text, copied, popupOpened) {
    mountGeminiHandoffUi();
    lastGeminiHandoffText = text;
    lastGeminiHandoffContext = context;
    if (handoffCard) handoffCard.hidden = false;
    const mode = number(context?.session?.liveClose) > 0 ? "SESSION" : "EOD";
    const rank = context?.marketRanking?.canonicalVisibleRank;
    const rankText = rank ? ` · rank hiển thị #${rank}` : "";
    if (handoffStatusNode) handoffStatusNode.textContent = copied
      ? popupOpened ? "Đã sao chép toàn bộ phiên — dán một lần vào Gemini để tiếp tục." : "Đã sao chép toàn bộ phiên; popup bị chặn, bấm lại để mở Gemini."
      : "Gemini đã mở nhưng clipboard bị chặn — dùng ‘Xem gói chuyển’ để sao chép.";
    if (handoffDetailNode) handoffDetailNode.textContent = `${context?.symbol || "Mã hiện tại"} · ${mode}${rankText} · T+1→T+5 · technical · flow · quỹ · tài chính · news · validation · hội thoại`;
    if (handoffPreviewNode) {
      handoffPreviewNode.textContent = text;
      handoffPreviewNode.hidden = true;
    }
    if (handoffPreviewButton) handoffPreviewButton.textContent = "Xem gói chuyển";
  }

  async function openGeminiWeb() {
    const popup = typeof window.open === "function" ? window.open("https://gemini.google.com/app", "_blank", "noopener,noreferrer") : null;
    const label = $("#solutionAiConnectionState");
    const button = $("#solutionAiGeminiWeb");
    const previousText = button?.textContent || "Tiếp tục trên Gemini Web ↗";
    if (button) {
      button.disabled = true;
      button.textContent = "Đang đóng gói phiên…";
    }
    try {
      let context = state.context;
      try {
        context = await buildContext();
        updateContextBar(context);
      } catch {
        context = state.context || {};
      }
      const text = externalGeminiPrompt("", context);
      const copied = await copyHandoffText(text);
      renderGeminiHandoffState(context, text, copied, Boolean(popup));
      if (label) {
        label.textContent = copied
          ? "Đã chuyển đầy đủ forecast + dữ liệu phiên + ranking + bằng chứng + câu hỏi. Sang Gemini và dán một lần để tiếp tục."
          : "Gemini Web đã mở; clipboard bị chặn. Mở ‘Xem gói chuyển’ ngay bên dưới để sao chép toàn bộ phiên.";
      }
      return Boolean(popup);
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = previousText.includes("Gemini") ? "Tiếp tục trên Gemini Web ↗" : previousText;
      }
    }
  }
'''

pattern = re.compile(r'\n  function externalGeminiPrompt\(\) \{.*?\n  function disconnectGemini\(\)', re.S)
replacement = "\n" + handoff_block + "\n  function disconnectGemini()"
source, count = pattern.subn(lambda _: replacement, source, count=1)
if count != 1:
    raise SystemExit(f"expected one Gemini handoff block, got {count}")

old = '''  function init() {
    if (!$("#solutionAiPanel")) return;
    for (const selector of ["#solutionAiLauncher", "#solutionAiTop", "#solutionAiNav"]) $(selector)?.addEventListener("click", open);
'''
new = '''  function init() {
    if (!$("#solutionAiPanel")) return;
    mountGeminiHandoffUi();
    for (const selector of ["#solutionAiLauncher", "#solutionAiTop", "#solutionAiNav"]) $(selector)?.addEventListener("click", open);
'''
if old not in source:
    raise SystemExit("init anchor missing")
source = source.replace(old, new, 1)

old = '''    window.__SOLUTION_AI_BUILD_CONTEXT__ = buildContext;
    window.__SOLUTION_AI_CHECK_CONNECTION__ = checkConnection;
'''
new = '''    window.__SOLUTION_AI_BUILD_CONTEXT__ = buildContext;
    window.__SOLUTION_AI_BUILD_GEMINI_HANDOFF__ = (question = "", context = state.context || {}) => externalGeminiPrompt(question, context);
    window.__SOLUTION_AI_GEMINI_HANDOFF_PAYLOAD__ = (question = "", context = state.context || {}) => geminiHandoffPayload(context, question);
    window.__SOLUTION_AI_LAST_GEMINI_HANDOFF__ = () => ({ text: lastGeminiHandoffText, context: lastGeminiHandoffContext });
    window.__SOLUTION_AI_CHECK_CONNECTION__ = checkConnection;
'''
if old not in source:
    raise SystemExit("export anchor missing")
source = source.replace(old, new, 1)

JS.write_text(source, encoding="utf-8")

# Extend browser-VM tests with EOD/SESSION completeness, question continuity and secret redaction.
test_source = FRONTEND_TEST.read_text(encoding="utf-8")
append_tests = r'''

test("Gemini Web handoff carries the full EOD decision state and redacts credentials", async () => {
  const { source, window, nodes } = await setup();
  const context = await window.__SOLUTION_AI_BUILD_CONTEXT__();
  nodes.get("#solutionAiInput").value = "Tôi nên chú ý điều gì ở FPT? AIza123456789012345678901234567890";
  const payload = window.__SOLUTION_AI_GEMINI_HANDOFF_PAYLOAD__("", context);
  const prompt = window.__SOLUTION_AI_BUILD_GEMINI_HANDOFF__("", context);
  assert.equal(payload.handoff.version, "VMEWS-GEMINI-HANDOFF-23.0");
  assert.equal(payload.handoff.dataMode, "EOD");
  assert.equal(payload.forecast.symbol, "FPT");
  assert.equal(payload.forecast.sealedCoreClose, 72000);
  assert.equal(payload.forecast.marketRanking.canonicalVisibleRank, 1);
  assert.equal(payload.forecast.topHOSECandidates[0].symbol, "FPT");
  assert.equal(payload.evidence.fund.fundCount, 17);
  assert.equal(payload.evidence.flow.foreign.net5, 40);
  assert.equal(payload.evidence.financial.profitGrowth, .2);
  assert.equal(payload.evidence.issuerNews[0].title, "FPT công bố tăng trưởng");
  assert.match(payload.userIntent.currentQuestion, /Tôi nên chú ý/);
  assert.doesNotMatch(JSON.stringify(payload), /AIza123456789012345678901234567890/);
  assert.match(prompt, /technical/);
  assert.match(prompt, /dòng tiền/);
  assert.match(prompt, /ranking HOSE/);
  assert.match(prompt, /CONTINUE_CURRENT_SESSION/);
  assert.match(source, /state\.messages \|\| \[\]/);
  assert.match(source, /Tiếp tục trên Gemini Web/);
});

test("Gemini Web handoff distinguishes a fresh SESSION quote from the sealed EOD forecast", async () => {
  const { window } = await setup();
  window.__VMEWS_SESSION__ = {
    status: "PASS", session: "PM", cutoffAt: "2026-08-25T14:30:00+07:00",
    symbols: [{ symbol: "FPT", quoteCurrent: true, freshForCutoff: true, liveClose: 72500, change: .0069, updateAt: "2026-08-25T14:31:00+07:00", updateMode: "delayed_streaming_900" }],
  };
  const context = await window.__SOLUTION_AI_BUILD_CONTEXT__();
  const payload = window.__SOLUTION_AI_GEMINI_HANDOFF_PAYLOAD__("Đánh giá lại khoảng cách tới target", context);
  assert.equal(payload.handoff.dataMode, "SESSION");
  assert.equal(payload.forecast.sealedCoreClose, 72000);
  assert.equal(payload.forecast.activePrice, 72500);
  assert.equal(payload.forecast.session.liveClose, 72500);
  assert.equal(payload.forecast.session.sourceMode, "delayed_streaming_900");
  assert.equal(payload.forecast.horizons["T+5"].price, 73000);
  assert.ok(Math.abs(payload.forecast.horizons["T+5"].remainingReturnFromSession - (73000 / 72500 - 1)) < 1e-12);
  assert.match(payload.userIntent.currentQuestion, /khoảng cách tới target/);
});
'''
if 'Gemini Web handoff carries the full EOD decision state' in test_source:
    raise SystemExit("frontend V23 handoff tests already present")
FRONTEND_TEST.write_text(test_source.rstrip() + append_tests + "\n", encoding="utf-8")

# Extend real Chromium desktop/mobile E2E without opening an external Gemini tab.
browser_source = BROWSER_TEST.read_text(encoding="utf-8")
old = '''  await page.locator("#solutionAiNav").click();
  assert.equal(await page.locator("#solutionAiPanel").isVisible(), true);
  if (label === "desktop" && cards > 1) {
'''
new = '''  await page.locator("#solutionAiNav").click();
  assert.equal(await page.locator("#solutionAiPanel").isVisible(), true);
  assert.match(await page.locator("#solutionAiGeminiWeb").innerText(), /Tiếp tục trên Gemini Web/);
  await page.locator("#solutionAiInput").fill("Kiểm tra chuyển phiên đầy đủ sang Gemini");
  const handoff = await page.evaluate(() => {
    const contextPromise = window.__SOLUTION_AI_BUILD_CONTEXT__();
    return contextPromise.then(context => ({
      payload: window.__SOLUTION_AI_GEMINI_HANDOFF_PAYLOAD__("", context),
      prompt: window.__SOLUTION_AI_BUILD_GEMINI_HANDOFF__("", context),
    }));
  });
  assert.equal(handoff.payload.handoff.version, "VMEWS-GEMINI-HANDOFF-23.0");
  assert.equal(handoff.payload.forecast.symbol, "FPT");
  assert.ok(Object.keys(handoff.payload.forecast.horizons).length >= 1);
  assert.ok(Array.isArray(handoff.payload.forecast.topHOSECandidates));
  assert.match(handoff.payload.userIntent.currentQuestion, /Kiểm tra chuyển phiên/);
  assert.match(handoff.prompt, /ranking HOSE/);
  assert.match(handoff.prompt, /validation/);
  if (label === "desktop" && cards > 1) {
'''
if old not in browser_source:
    raise SystemExit("browser E2E insertion anchor missing")
browser_source = browser_source.replace(old, new, 1)
browser_source = browser_source.replace('console.log("V22 browser E2E PASS");', 'console.log("V23 Gemini handoff + V22 browser E2E PASS");')
BROWSER_TEST.write_text(browser_source, encoding="utf-8")

# The patch script is one-time scaffolding and must not land in the production commit.
Path(__file__).unlink()
print("V23 Gemini Web continuity patch applied")
