from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "forecast-final.html"
MAIN = ROOT / "forecast-final-v12.js"
AI = ROOT / "solution-ai-v17.js"
FRONTEND_TEST = ROOT / "scripts/solution_ai_frontend_v17_test.mjs"
BROWSER_TEST = ROOT / "scripts/forecast_v22_browser_e2e.mjs"

# --- HTML: load contextual deep-dive layer after SoluTION.AI ---
html = HTML.read_text(encoding="utf-8")
old = '<script src="./solution-ai-v17.js?release=20.2"></script>\n</body>'
new = '<script src="./solution-ai-v17.js?release=24.0"></script>\n<script src="./forecast-deep-dive-v24.js?release=24.0"></script>\n</body>'
if old not in html and 'forecast-deep-dive-v24.js' not in html:
    raise SystemExit("HTML script anchor missing")
if 'forecast-deep-dive-v24.js' not in html:
    html = html.replace(old, new, 1)
HTML.write_text(html, encoding="utf-8")

# --- Main dashboard: simplify source cards to high-value, actionable data ---
main = MAIN.read_text(encoding="utf-8")
source_fn = r'''function renderSource(B,sym){
  const box=$("#sourceAudit");box.replaceChildren();
  const z=B.dash.symbols?.[sym]||{},signal=B.market?.sources?.signalAudit||{},rumorAudit=B.market?.sources?.rumorAudit||{},flow=z.flow||{},fund=z.fundContext||{},financial=z.fundamentalContext||{},foreign=flow.foreign||{},prop=flow.proprietary||{};
  const flowValue=item=>item?.available&&finite(item.net1)?`${+item.net1>=0?"+":""}${(+item.net1/1e9).toFixed(1)} tỷ`:"Mở dữ liệu";
  const flowDetail=item=>item?.available?`${item.latestDate||"Phiên gần nhất"}${finite(item.net5)?` · 5P ${+item.net5>=0?"+":""}${(+item.net5/1e9).toFixed(1)} tỷ`:""}`:"Phiên gần nhất · lũy kế 5/20 phiên";
  const tracked=(z.rumorContext?.claimCount||0)+(z.evidence?.communityWatchlist?.length||0);
  const communitySource=rumorAudit.source?.publishers?.join(" · ")||"Nguồn cộng đồng";
  const priceDetail=z.priceSourceAgreement?.status==="PASS"?"Đã đối chiếu nguồn giá":z.dataFreshness==="CURRENT"?"Dữ liệu cùng phiên":"Cần làm mới dữ liệu";
  const fundValue=fund.available?`${fund.fundCount||0} quỹ`:"Mở dữ liệu quỹ";
  const fundDetail=fund.available&&finite(fund.weightedNavMomentum20)?`NAV 20P ${+fund.weightedNavMomentum20>=0?"+":""}${pct(fund.weightedNavMomentum20,1)}`:"Danh mục · tỷ trọng · NAV · biến động";
  const financialValue=financial.available?(financial.incomePeriod||financial.period||"BCTC gần nhất"):"Mở BCTC";
  const financialBits=[];
  if(financial.available&&finite(financial.profitQoQ))financialBits.push(`LN QoQ ${+financial.profitQoQ>=0?"+":""}${pct(financial.profitQoQ,1)}`);
  if(financial.available&&finite(financial.revenueQoQ))financialBits.push(`DT QoQ ${+financial.revenueQoQ>=0?"+":""}${pct(financial.revenueQoQ,1)}`);
  const rows=[
    ["Giá thị trường",z.date||"—",priceDetail],
    ["Tin đã đối chiếu",`${(+signal.acceptedEvents||0).toLocaleString("vi-VN")} bài`,`${signal.newsSymbols??"—"} mã cổ phiếu`],
    ["Dòng tiền khối ngoại",flowValue(foreign),flowDetail(foreign)],
    ["Dòng tiền tự doanh",flowValue(prop),flowDetail(prop)],
    ["Danh mục quỹ",fundValue,fundDetail],
    ["Tài chính doanh nghiệp",financialValue,financialBits.join(" · ")||"Doanh thu · lợi nhuận · dòng tiền · nợ · định giá"],
    ["Tín hiệu cộng đồng",`${tracked} tín hiệu`,rumorAudit.source?.articles?`${communitySource} · ${rumorAudit.source.articles} bài`:communitySource],
  ];
  for(const[label,value,detail]of rows){const e=document.createElement("article");e.className="sourceCard";e.dataset.deepTopic=label;e.innerHTML=`<span>${esc(label)}</span><b>${esc(value)}</b><small>${esc(detail)}</small>`;box.append(e)}
}

function renderEventImpact'''
main, count = re.subn(r'function renderSource\(B,sym\)\{.*?\}\n\nfunction renderEventImpact', source_fn, main, count=1, flags=re.S)
if count != 1:
    raise SystemExit(f"renderSource replacement count={count}")
MAIN.write_text(main, encoding="utf-8")

# --- SoluTION.AI: richer technical context, research routing, concise wording ---
ai = AI.read_text(encoding="utf-8")
ai = ai.replace(
    '      "Tỷ trọng quỹ là tỷ trọng trong danh mục từng quỹ, không phải tỷ lệ sở hữu doanh nghiệp và không chứng minh quỹ đang mua.",\n',
    '      "Với dữ liệu quỹ, tập trung vào quỹ đang nắm giữ, tỷ trọng trong danh mục, biến động NAV và thay đổi công bố có ý nghĩa; chỉ giải thích định nghĩa khi người dùng hỏi.",\n',
)

technical_fn = r'''  function technicalContext(history) {
    const rows = (history || []).filter(item => number(item?.rawClose ?? item?.close) !== null).slice(-90);
    const closes = rows.map(item => number(item.rawClose ?? item.close));
    const volumes = rows.map(item => number(item.rawVolume ?? item.volume));
    if (closes.length < 5) return null;
    const average = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
    const change = sessions => closes.length > sessions && closes.at(-(sessions + 1)) > 0 ? closes.at(-1) / closes.at(-(sessions + 1)) - 1 : null;
    const emaSeries = (values, period) => {
      if (!values.length) return [];
      const k = 2 / (period + 1); let current = values[0];
      return values.map((value, index) => { if (index) current = value * k + current * (1 - k); return current; });
    };
    const gains = [], losses = [];
    for (let index = Math.max(1, closes.length - 14); index < closes.length; index += 1) {
      const delta = closes[index] - closes[index - 1]; gains.push(Math.max(0, delta)); losses.push(Math.max(0, -delta));
    }
    const gain = average(gains) || 0, loss = average(losses) || 0;
    const rsi14 = !loss ? (gain ? 100 : 50) : 100 - 100 / (1 + gain / loss);
    const ema12 = emaSeries(closes, 12), ema26 = emaSeries(closes, 26);
    const macdSeries = closes.map((_, index) => ema12[index] - ema26[index]);
    const signalSeries = emaSeries(macdSeries, 9);
    const macd = macdSeries.at(-1), macdSignal = signalSeries.at(-1), macdHistogram = macd - macdSignal;
    const returns = closes.slice(1).map((value, index) => Math.log(value / closes[index])).filter(Number.isFinite);
    const variance = returns.length > 1 ? returns.reduce((sum, value) => sum + (value - average(returns)) ** 2, 0) / (returns.length - 1) : null;
    const last20 = closes.slice(-20), validVolumes = volumes.filter(value => value !== null && value >= 0);
    let obv = 0; const obvSeries = [0];
    for (let index = 1; index < closes.length; index += 1) {
      const volume = volumes[index] ?? 0;
      if (closes[index] > closes[index - 1]) obv += volume;
      else if (closes[index] < closes[index - 1]) obv -= volume;
      obvSeries.push(obv);
    }
    const lastVolume20 = volumes.slice(-20).filter(value => value !== null && value > 0);
    const averageVolume20 = average(lastVolume20);
    const latestVolume = volumes.at(-1);
    return {
      observationCount: closes.length,
      from: rows[0]?.date || null,
      to: rows.at(-1)?.date || null,
      return5: change(5), return20: change(20),
      sma20: average(last20), sma50: average(closes.slice(-50)),
      high20: Math.max(...last20), low20: Math.min(...last20),
      realizedVolatility20Annualized: variance === null ? null : Math.sqrt(variance) * Math.sqrt(252),
      rsi14,
      macd, macdSignal, macdHistogram,
      obv: validVolumes.length >= 10 ? obv : null,
      obvChange5: validVolumes.length >= 10 && obvSeries.length > 5 ? obvSeries.at(-1) - obvSeries.at(-6) : null,
      latestVolume,
      averageVolume20,
      volumeRatio20: latestVolume !== null && averageVolume20 ? latestVolume / averageVolume20 : null,
      volumeObservations: validVolumes.length,
      priceSeriesUsesRawMarketClose: true,
      volumeSeriesUsesObservedMarketVolume: validVolumes.length >= 10,
    };
  }

  function belongsToIssuer'''
ai, count = re.subn(r'  function technicalContext\(history\) \{.*?\n  \}\n\n  function belongsToIssuer', technical_fn, ai, count=1, flags=re.S)
if count != 1:
    raise SystemExit(f"technicalContext replacement count={count}")

# Expand stock/research detection for deep-dive financial and technical questions.
ai = ai.replace(
    'const explicitStockQuestion = mentionsSelected || /mã đang xem|mã này|cổ phiếu này|cổ phiếu đang xem|danh mục quỹ|quỹ đang|khối ngoại|tự doanh|vùng giá|dự báo t\\s*\\+|top vn30|mã vn30/i.test(text);',
    'const explicitStockQuestion = mentionsSelected || /mã đang xem|mã này|cổ phiếu này|cổ phiếu đang xem|danh mục quỹ|quỹ đang|khối ngoại|tự doanh|vùng giá|dự báo t\\s*\\+|top vn30|mã vn30|tài chính|bctc|báo cáo tài chính|doanh thu|lợi nhuận|dòng tiền|nợ vay|định giá|p\\/e|p\\/b|roe|rsi|macd|obv|khối lượng|technical|hỗ trợ|kháng cự/i.test(text);'
)
ai = ai.replace(
    'const currentQuestion = urls.length > 0 || /mới nhất|tin mới|thông tin mới|hiện nay|hiện tại|hôm nay|gần đây|cập nhật|thời sự|vĩ mô|kinh tế|lãi suất|lạm phát|tỷ giá|chính sách|triển vọng ngành|tìm kiếm|tra cứu|nghiên cứu|nguồn mở|open source|website|bài báo|đọc link|đọc trang|phân tích đầy đủ|đối chiếu|xác minh/i.test(text);',
    'const currentQuestion = urls.length > 0 || /mới nhất|tin mới|thông tin mới|hiện nay|hiện tại|hôm nay|gần đây|cập nhật|thời sự|vĩ mô|kinh tế|lãi suất|lạm phát|tỷ giá|chính sách|triển vọng ngành|tìm kiếm|tra cứu|nghiên cứu|nguồn mở|open source|website|bài báo|đọc link|đọc trang|phân tích đầy đủ|đối chiếu|xác minh|bctc|báo cáo tài chính|định giá|dòng tiền kinh doanh|nợ vay/i.test(text);'
)
ai = ai.replace(
    'const shouldSearch = !snapshotOnly && (currentQuestion || (stockQuestion && wantsSynthesis) || (!stockQuestion && !evergreenQuestion && text.length >= 12));',
    'const financialResearch = stockQuestion && /tài chính|bctc|báo cáo tài chính|doanh thu|lợi nhuận|dòng tiền kinh doanh|nợ vay|định giá|p\\/e|p\\/b|roe/i.test(text);\n    const shouldSearch = !snapshotOnly && (financialResearch || currentQuestion || (stockQuestion && wantsSynthesis) || (!stockQuestion && !evergreenQuestion && text.length >= 12));'
)

old_fund = '        lines.push("### Quỹ và dòng tiền", `Có ${context.fund.fundCount} quỹ đang nắm giữ, tỷ trọng bình quân ${(context.fund.averageWeight * 100).toFixed(2)}% trong từng danh mục quỹ; NAV 20 phiên ${pct(context.fund.navMomentum20)}${number(contribution) === null ? "" : `; mức điều chỉnh trong kịch bản tham khảo T+5 ${pct(contribution)}`}. Dữ liệu quỹ chưa điều chỉnh giá dự báo trung tâm. Tỷ trọng này không phải tỷ lệ sở hữu doanh nghiệp và không chứng minh quỹ đang mua trong phiên.`);'
new_fund = '        const topHolders = context.fund.holders.slice(0, 4).map(holder => `${holder.code || holder.name} ${(holder.weight * 100).toFixed(2)}%`).join("; ");\n        lines.push("### Quỹ nắm giữ", `Có ${context.fund.fundCount} quỹ trong dữ liệu hiện có; NAV 20 phiên ${pct(context.fund.navMomentum20)}${topHolders ? `; tỷ trọng nổi bật: ${topHolders}` : ""}${number(contribution) === null ? "" : `; tín hiệu quỹ trong kịch bản T+5 ${pct(contribution)}`}.`);'
if old_fund not in ai:
    raise SystemExit("fund wording anchor missing")
ai = ai.replace(old_fund, new_fund, 1)
ai = ai.replace(
    '      } else if (fundQuestion) lines.push("Mã này chưa có công bố danh mục quỹ đủ lịch sử để đánh giá riêng; giá dự báo trung tâm không bị thay đổi.");',
    '      } else if (fundQuestion) lines.push("Snapshot hiện tại chưa có đủ chi tiết danh mục quỹ; câu hỏi sâu về quỹ sẽ ưu tiên truy vấn công bố và nguồn công khai mới nhất khi kết nối AI khả dụng.");'
)

financial_anchor = '''    if (context.financial && /tài chính|lợi nhuận|định giá|đầy đủ|phân tích|kết hợp|tổng hợp|forecast/.test(question)) {
      lines.push("### Nền tảng doanh nghiệp", `Kỳ ${context.financial.incomePeriod || "gần nhất"}: lợi nhuận thay đổi ${pct(context.financial.profitGrowth)} và doanh thu ${pct(context.financial.revenueGrowth)} so với quý trước. Chỉ tiêu này cần đọc cùng tính mùa vụ và kỳ công bố, không tự suy ra xu hướng dài hạn từ một quý.`);
    }
'''
financial_new = '''    if (context.financial && /tài chính|bctc|doanh thu|lợi nhuận|dòng tiền|nợ|định giá|đầy đủ|phân tích|kết hợp|tổng hợp|forecast/.test(question)) {
      const ratioEntries = Object.entries(context.financial.ratios || {}).slice(0, 5).map(([key, value]) => `${key.toUpperCase()} ${number(value?.value ?? value) === null ? "—" : number(value?.value ?? value, 2)}`).join(" · ");
      lines.push("### Tài chính doanh nghiệp", `Kỳ ${context.financial.incomePeriod || "gần nhất"}: lợi nhuận ${pct(context.financial.profitGrowth)} QoQ, doanh thu ${pct(context.financial.revenueGrowth)} QoQ${ratioEntries ? ` · ${ratioEntries}` : ""}.`);
    } else if (!context.financial && /tài chính|bctc|báo cáo tài chính|doanh thu|lợi nhuận|dòng tiền|nợ|định giá|p\/e|p\/b|roe/.test(question)) {
      lines.push("### Tài chính doanh nghiệp", "Snapshot tích hợp chưa chứa kỳ BCTC đủ chi tiết cho câu hỏi này. SoluTION.AI sẽ ưu tiên truy vấn báo cáo/công bố công khai mới nhất khi kết nối nghiên cứu web khả dụng.");
    }
'''
if financial_anchor not in ai:
    raise SystemExit("financial local analysis anchor missing")
ai = ai.replace(financial_anchor, financial_new, 1)

# Add technical indicator detail to local detailed analysis.
tech_old = '        lines.push("### Giá và kỹ thuật từ dữ liệu thật", `Giá hiện ${location} SMA20 ${money(tech.sma20)}; SMA50 ${money(tech.sma50)}; biến động 5 phiên ${pct(tech.return5)} và 20 phiên ${pct(tech.return20)}. Biên 20 phiên là ${money(tech.low20)}–${money(tech.high20)}; chuỗi dùng giá đóng cửa thị trường, không làm mượt hay thay đổi dữ liệu.`);'
tech_new = '        const indicators = [`RSI14 ${number(tech.rsi14, 1)}`, `MACD hist ${number(tech.macdHistogram, 1)}`];\n        if (number(tech.obv) !== null) indicators.push(`OBV ${money(tech.obv)}`, `OBV 5P ${number(tech.obvChange5) >= 0 ? "+" : ""}${money(tech.obvChange5)}`);\n        if (number(tech.volumeRatio20) !== null) indicators.push(`KL/20P ${number(tech.volumeRatio20, 2)}x`);\n        lines.push("### Giá, động lượng & khối lượng", `Giá hiện ${location} SMA20 ${money(tech.sma20)}; SMA50 ${money(tech.sma50)}; 5 phiên ${pct(tech.return5)}, 20 phiên ${pct(tech.return20)}; ${indicators.join(" · ")}. Biên 20 phiên ${money(tech.low20)}–${money(tech.high20)}.`);'
if tech_old not in ai:
    raise SystemExit("technical local wording anchor missing")
ai = ai.replace(tech_old, tech_new, 1)

# Replace persistent large handoff card with a compact auto-dismissing toast.
handoff_replacement = r'''  function mountGeminiHandoffUi() {
    if (handoffUiMounted) return;
    handoffUiMounted = true;
    const button = $("#solutionAiGeminiWeb");
    if (button) {
      button.textContent = "Tiếp tục trên Gemini Web ↗";
      button.setAttribute?.("title", "Mang forecast và câu hỏi hiện tại sang Gemini Web");
    }
    const panel = $("#solutionAiPanel");
    if (!panel || typeof document.createElement !== "function") return;
    handoffCard = document.createElement("section");
    handoffCard.id = "solutionAiHandoffCard";
    handoffCard.className = "aiHandoffToast";
    handoffCard.hidden = true;
    const title = document.createElement("strong");
    title.textContent = "Đã chuẩn bị phiên Gemini";
    handoffStatusNode = document.createElement("span");
    handoffStatusNode.className = "aiHandoffStatus";
    handoffDetailNode = document.createElement("small");
    handoffDetailNode.className = "aiHandoffDetail";
    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.className = "aiHandoffCopy";
    copyButton.textContent = "Sao chép lại";
    copyButton.addEventListener("click", async () => {
      const copied = await copyHandoffText(lastGeminiHandoffText);
      if (handoffStatusNode) handoffStatusNode.textContent = copied ? "Đã sao chép · dán vào Gemini để tiếp tục." : "Clipboard đang bị chặn.";
    });
    handoffCard.append(title, handoffStatusNode, handoffDetailNode, copyButton);
    panel.append?.(handoffCard);
    if (document.head && !document.getElementById?.("solutionAiHandoffStyle")) {
      const style = document.createElement("style");
      style.id = "solutionAiHandoffStyle";
      style.textContent = `.aiHandoffToast{position:absolute;z-index:8;top:78px;right:12px;width:min(350px,calc(100% - 24px));padding:10px 11px;border:1px solid rgba(168,235,101,.46);border-radius:11px;background:rgba(10,18,9,.96);box-shadow:0 14px 34px rgba(0,0,0,.34);display:grid;grid-template-columns:1fr auto;gap:3px 9px;align-items:center}.aiHandoffToast[hidden]{display:none}.aiHandoffToast strong{font-size:12px}.aiHandoffStatus,.aiHandoffDetail{grid-column:1/2;font-size:10.5px;line-height:1.35;color:#b9c7b5}.aiHandoffCopy{grid-column:2;grid-row:1/4;border:1px solid rgba(168,235,101,.32);background:rgba(168,235,101,.08);color:#cbedaa;border-radius:8px;padding:6px 8px;cursor:pointer;font-size:10px}@media(max-width:520px){.aiHandoffToast{top:72px;right:8px;width:calc(100% - 16px)}}`;
      document.head.append(style);
    }
  }

  function renderGeminiHandoffState(context, text, copied, popupOpened) {
    mountGeminiHandoffUi();
    lastGeminiHandoffText = text;
    lastGeminiHandoffContext = context;
    if (handoffCard) handoffCard.hidden = false;
    const mode = number(context?.session?.liveClose) > 0 ? "SESSION" : "EOD";
    if (handoffStatusNode) handoffStatusNode.textContent = copied
      ? "Đã sao chép ngữ cảnh · dán vào Gemini để tiếp tục."
      : "Gemini đã mở · clipboard đang bị chặn.";
    if (handoffDetailNode) handoffDetailNode.textContent = `${context?.symbol || "Mã hiện tại"} · ${mode} · T+1→T+5 · dữ liệu cốt lõi`;
    window.setTimeout?.(() => { if (handoffCard) handoffCard.hidden = true; }, copied ? 5500 : 11000);
  }

  async function openGeminiWeb() {
    const popup = typeof window.open === "function" ? window.open("https://gemini.google.com/app", "_blank", "noopener,noreferrer") : null;
    const label = $("#solutionAiConnectionState");
    const button = $("#solutionAiGeminiWeb");
    if (button) { button.disabled = true; button.textContent = "Đang chuẩn bị…"; }
    try {
      let context = state.context;
      try { context = await buildContext(); updateContextBar(context); } catch { context = state.context || {}; }
      const text = externalGeminiPrompt("", context);
      const copied = await copyHandoffText(text);
      renderGeminiHandoffState(context, text, copied, Boolean(popup));
      if (label) label.textContent = copied ? "Forecast và câu hỏi hiện tại đã được sao chép sang phiên Gemini." : "Gemini đã mở; trình duyệt đang chặn clipboard.";
      return Boolean(popup);
    } finally {
      if (button) { button.disabled = false; button.textContent = "Tiếp tục trên Gemini Web ↗"; }
    }
  }

  function disconnectGemini'''
ai, count = re.subn(r'  function mountGeminiHandoffUi\(\) \{.*?\n  function disconnectGemini', handoff_replacement, ai, count=1, flags=re.S)
if count != 1:
    raise SystemExit(f"handoff UI replacement count={count}")

# Export contextual ask and diagnostics for the deep-dive layer/tests.
export_anchor = '    window.__SOLUTION_AI_BUILD_CONTEXT__ = buildContext;\n'
export_new = '    window.__SOLUTION_AI_BUILD_CONTEXT__ = buildContext;\n    window.__SOLUTION_AI_ASK__ = async question => { await open(); return ask(question); };\n    window.__SOLUTION_AI_RESEARCH_INTENT__ = (question, context = state.context || {}) => researchIntent(question, context);\n    window.__SOLUTION_AI_LOCAL_ANALYSIS__ = (question, context = state.context || {}) => localAnalysis(question, context);\n'
if export_anchor not in ai:
    raise SystemExit("AI export anchor missing")
ai = ai.replace(export_anchor, export_new, 1)
AI.write_text(ai, encoding="utf-8")

# --- VM tests: provide volume history and assert technical + tone + research routing ---
test = FRONTEND_TEST.read_text(encoding="utf-8")
old_dash = '    dash: { symbols: { FPT: fpt }, marketForecast: { decisionAt: "2026-08-23T10:00:00+07:00" } },'
new_dash = '''    dash: {
      symbols: { FPT: fpt }, marketForecast: { decisionAt: "2026-08-23T10:00:00+07:00" },
      charts: { FPT: Array.from({ length: 65 }, (_, index) => ({
        date: `2026-06-${String(index + 1).padStart(2, "0")}`,
        rawClose: 68000 + index * 70 + (index % 4) * 45,
        close: 68000 + index * 70 + (index % 4) * 45,
        volume: 900000 + index * 12000 + (index % 5) * 40000,
      })) },
    },'''
if old_dash not in test:
    raise SystemExit("frontend test dashboard anchor missing")
test = test.replace(old_dash, new_dash, 1)
extra_tests = r'''

test("technical context carries real RSI MACD OBV and volume evidence", async () => {
  const { window } = await setup();
  const context = await window.__SOLUTION_AI_BUILD_CONTEXT__();
  assert.ok(context.technical.rsi14 >= 0 && context.technical.rsi14 <= 100);
  assert.equal(Number.isFinite(context.technical.macd), true);
  assert.equal(Number.isFinite(context.technical.macdHistogram), true);
  assert.equal(Number.isFinite(context.technical.obv), true);
  assert.equal(Number.isFinite(context.technical.obvChange5), true);
  assert.equal(context.technical.volumeSeriesUsesObservedMarketVolume, true);
  assert.ok(context.technical.volumeRatio20 > 0);
});

test("financial deep-dive routes to research and local wording stays decision-focused", async () => {
  const { window, source } = await setup();
  const context = await window.__SOLUTION_AI_BUILD_CONTEXT__();
  const intent = window.__SOLUTION_AI_RESEARCH_INTENT__("Đọc BCTC mới nhất, phân tích dòng tiền và nợ vay của FPT", context);
  assert.equal(intent.useSnapshot, true);
  assert.equal(intent.shouldSearch, true);
  assert.equal(intent.mode, "FORECAST_RESEARCH");
  const fundAnswer = window.__SOLUTION_AI_LOCAL_ANALYSIS__("Phân tích quỹ và danh mục FPT", context);
  assert.match(fundAnswer, /Quỹ nắm giữ/);
  assert.doesNotMatch(fundAnswer, /không phải tỷ lệ sở hữu doanh nghiệp|không chứng minh quỹ đang mua|chưa điều chỉnh giá dự báo trung tâm/i);
  const technical = window.__SOLUTION_AI_LOCAL_ANALYSIS__("Phân tích đầy đủ kỹ thuật FPT", context);
  assert.match(technical, /RSI14/);
  assert.match(technical, /OBV/);
  assert.match(technical, /MACD/);
  assert.doesNotMatch(source, /Tỷ trọng quỹ là tỷ trọng trong danh mục từng quỹ, không phải tỷ lệ sở hữu doanh nghiệp/);
});
'''
if 'technical context carries real RSI MACD OBV' not in test:
    test = test.rstrip() + extra_tests + "\n"
FRONTEND_TEST.write_text(test, encoding="utf-8")

# --- Browser E2E: deep-dive UX, concise source cards, mobile safety ---
browser = BROWSER_TEST.read_text(encoding="utf-8")
insert_anchor = '  assert.match(handoff.prompt, /validation/);\n'
insert = '''  assert.match(handoff.prompt, /validation/);
  assert.equal(await page.evaluate(() => typeof window.__VMEWS_OPEN_DEEP_DIVE__), "function");
  assert.equal(await page.evaluate(() => typeof window.__SOLUTION_AI_ASK__), "function");
  const sourceText = await page.locator("#sourceAudit").innerText();
  assert.doesNotMatch(sourceText, /CHƯA CÓ|Đang mở rộng nguồn|Bối cảnh tham khảo|chưa điều chỉnh giá trung tâm/i);
  assert.doesNotMatch(sourceText, /Độ phủ HOSE|Rổ VN30/);
  const financeCard = page.locator("#sourceAudit .sourceCard", { hasText: "Tài chính doanh nghiệp" }).first();
  await financeCard.locator(".deepDiveMini").click();
  await page.waitForSelector("#vmewsDeepDive:not([hidden])");
  assert.match(await page.locator("#vmewsDeepDiveTitle").innerText(), /Tài chính FPT/);
  assert.ok(await page.locator("#vmewsDeepDive .vmewsDeepDivePrompt").count() >= 4);
  assert.match(await page.locator("#vmewsDeepDive").evaluate(node => getComputedStyle(node.querySelector(".vmewsDeepDiveDialog")).borderColor), /rgb/);
  await page.locator("#vmewsDeepDive .vmewsDeepDiveClose").click();
  await page.locator("#forecast .deepDiveHeader").click();
  await page.waitForSelector("#vmewsDeepDive:not([hidden])");
  assert.match(await page.locator("#vmewsDeepDiveTitle").innerText(), /Kỹ thuật FPT/);
  const techPromptText = await page.locator("#vmewsDeepDive .vmewsDeepDivePrompts").innerText();
  assert.match(techPromptText, /RSI14/);
  assert.match(techPromptText, /MACD/);
  assert.match(techPromptText, /OBV/);
  await page.locator("#vmewsDeepDive .vmewsDeepDiveClose").click();
  assert.equal(await page.locator("#solutionAiHandoffCard pre").count(), 0);
'''
if insert_anchor not in browser:
    raise SystemExit("browser handoff insertion anchor missing")
browser = browser.replace(insert_anchor, insert, 1)
browser = browser.replace('console.log("V23 Gemini handoff + V22 browser E2E PASS");', 'console.log("V24 deep-dive + technical + AI browser E2E PASS");')
BROWSER_TEST.write_text(browser, encoding="utf-8")

# one-time patch scaffolding should disappear from the production commit
Path(__file__).unlink()
print("V24 UX/AI patch applied")
