(() => {
  "use strict";

  const $ = selector => document.querySelector(selector);
  const number = value => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value)) ? Number(value) : null;
  const money = value => number(value) === null ? "chưa có dữ liệu" : Number(value).toLocaleString("vi-VN");
  const pct = (value, digits = 2) => number(value) === null ? "chưa có dữ liệu" : `${Number(value) >= 0 ? "+" : ""}${(Number(value) * 100).toFixed(digits)}%`;
  const factorNames = {
    NUMERICAL: "giá và kỹ thuật", REGIME: "trạng thái thị trường", VOLATILITY: "biến động",
    SECTOR: "luân chuyển ngành", EVENT: "tin tức", FLOW: "dòng tiền tổ chức",
    FUND: "danh mục quỹ", FUNDAMENTAL: "tài chính doanh nghiệp",
  };
  const state = { opened: false, busy: false, messages: [], context: null };

  function endpoint() {
    const declared = $('meta[name="solution-ai-endpoint"]')?.content?.trim();
    const configured = localStorage.getItem("vmews_solution_ai_endpoint")?.trim();
    if (configured || declared) return configured || declared;
    return location.hostname.endsWith("githubraw.com") ? "" : "/api/solution-ai";
  }

  function flowContext(source) {
    if (!source?.available) return null;
    return {
      latestDate: source.latestDate, ageSessions: source.ageSessions,
      net1: source.net1, net5: source.net5, net20: source.net20,
    };
  }

  async function buildContext() {
    const base = await window.__VMEWS_LOAD_BASE__();
    const symbol = String($("#symbol")?.value || new URLSearchParams(location.search).get("symbol") || "FPT").trim().toUpperCase();
    const snapshot = base.dash.symbols?.[symbol];
    if (!snapshot) throw new Error(`Chưa có dữ liệu cho ${symbol}.`);
    const horizons = {};
    for (const [key, forecast] of Object.entries(snapshot.horizons || {})) {
      if (forecast.priceValidated !== true) continue;
      horizons[`T+${key}`] = {
        price: forecast.expectedPrice, expectedReturn: forecast.expectedReturn,
        lowerPrice: forecast.q20Price, upperPrice: forecast.q80Price,
        probabilityUp: forecast.directionValidated === true ? forecast.probUp : null,
        factors: forecast.expertContributions || {},
        liveEvidence: forecast.liveEvidence?.components || {},
        targetDate: forecast.targetDate,
      };
    }
    const fund = snapshot.fundContext || {};
    const finances = snapshot.fundamentalContext || {};
    const top = Object.values(base.dash.symbols || {})
      .map(row => ({
        symbol: row.symbol, close: row.close, forecast: row.horizons?.["5"]?.expectedPrice,
        return: row.horizons?.["5"]?.expectedReturn,
        validated: row.horizons?.["5"]?.priceValidated === true,
      }))
      .filter(row => row.validated && row.close > 0 && row.forecast > 0)
      .sort((left, right) => right.return - left.return)
      .slice(0, 10)
      .map(({ validated, ...row }) => row);
    const modelAudit = base.model.horizons?.["5"] || {};
    return {
      brand: "SoluTION.AI", symbol, asOf: snapshot.date, decisionAt: base.dash.marketForecast?.decisionAt,
      close: snapshot.close, sector: snapshot.sector, riskStatus: snapshot.riskStatus,
      dailyVolatility: snapshot.dailyVolatility, horizons,
      fund: fund.available ? {
        fundCount: fund.fundCount, averageWeight: fund.averageReportedWeight,
        navMomentum20: fund.weightedNavMomentum20, usedByForecast: fund.usedByForecast === true,
        disclosedAt: fund.asOf,
        holders: (fund.holdings || []).slice(0, 12).map(item => ({
          name: item.fundName || item.fundCode, code: item.fundCode, weight: item.weight,
        })),
      } : null,
      flow: {
        foreign: flowContext(snapshot.flow?.foreign),
        proprietary: flowContext(snapshot.flow?.proprietary),
      },
      financial: finances.available ? {
        incomePeriod: finances.incomePeriod, profitGrowth: finances.profitQoQ,
        revenueGrowth: finances.revenueQoQ, ratios: finances.ratios,
        usedByForecast: finances.usedByForecast === true,
      } : null,
      news: (snapshot.evidence?.decisionRecent || snapshot.evidence?.recent || []).slice(0, 6).map(item => ({
        title: item.title, publisher: item.publisher, date: item.publishedAt || item.availableDate,
        label: item.label, event: item.event,
      })),
      validation: {
        priceValidated: modelAudit.priceStatus === "PASS",
        directionValidated: modelAudit.directionStatus === "PASS",
        holdoutRows: modelAudit.sealedAudit?.n,
        executableSkill: modelAudit.sealedAudit?.executableMAESkill,
        fundPriorIndependentlyBacktested: base.model.governance?.livePriorIndependentlyBacktested === true,
      },
      topMovers: top,
    };
  }

  function updateContextBar(context) {
    if (!context) return;
    const holder = $("#solutionAiContext");
    holder.querySelector("strong").textContent = context.symbol;
    const five = context.horizons["T+5"];
    holder.querySelector("small").textContent = five
      ? `${money(context.close)} → ${money(five.price)} · ${pct(five.expectedReturn)}`
      : `Giá hiện tại ${money(context.close)}`;
    state.context = context;
  }

  function setStatus(text) {
    const status = $("#solutionAiStatus");
    if (status) status.textContent = text;
  }

  function message(role, body, tone = "") {
    const item = document.createElement("article");
    item.className = `aiMessage ${role === "user" ? "aiUser" : "aiAssistant"}${tone ? ` ${tone}` : ""}`;
    const label = document.createElement("span");
    label.className = "aiRole";
    label.textContent = role === "user" ? "BẠN" : "SoluTION.AI";
    item.append(label);
    for (const paragraph of String(body).split(/\n{1,2}/)) {
      if (!paragraph.trim()) continue;
      const line = document.createElement("p");
      line.textContent = paragraph;
      item.append(line);
    }
    $("#solutionAiMessages").append(item);
    item.scrollIntoView({ block: "nearest", behavior: "smooth" });
    return item;
  }

  function primaryDrivers(horizon) {
    return Object.entries(horizon?.factors || {})
      .filter(([, value]) => Math.abs(Number(value) || 0) > .00005)
      .sort((left, right) => Math.abs(right[1]) - Math.abs(left[1]))
      .slice(0, 5)
      .map(([name, value]) => `${factorNames[name] || name} ${pct(value)}`);
  }

  function knowledgeAnswer(question) {
    if (/\brsi\b/.test(question)) return "RSI đo động lượng giá trên thang 0–100. Vùng dưới 30 thường cho thấy trạng thái quá bán, trên 70 thường cho thấy quá mua; cần đối chiếu xu hướng, thanh khoản và biến động thay vì sử dụng RSI đơn lẻ.";
    if (/\b(macd)\b/.test(question)) return "MACD phản ánh tương quan giữa hai đường trung bình động và động lượng giá. Khi MACD vượt đường tín hiệu, động lượng ngắn hạn thường cải thiện; độ tin cậy phụ thuộc xu hướng, thanh khoản và vị trí giá.";
    if (/\b(p\/e|pe|p\/b|pb|roe|roa|eps)\b/.test(question)) return "P/E so sánh giá với lợi nhuận; P/B so sánh giá với giá trị sổ sách; ROE và ROA phản ánh hiệu quả sử dụng vốn và tài sản; EPS là lợi nhuận trên mỗi cổ phiếu. Các tỷ lệ cần được đối chiếu ngành, tăng trưởng và chu kỳ kinh doanh.";
    if (/\b(q20|q80|vùng giá|khoảng giá)\b/.test(question)) return "Vùng giá dự báo thể hiện khoảng kết quả có cơ sở từ phân phối sai số lịch sử, không phải cam kết giá sẽ nằm trong vùng. Biên rộng cho thấy bất định lớn hơn; trọng tâm là mức dự báo trung tâm trên lưới giá giao dịch hợp lệ.";
    return "";
  }

  function localAnalysis(input, context) {
    const question = input.toLowerCase();
    const five = context.horizons["T+5"];
    const lines = [];
    const knowledge = knowledgeAnswer(question);
    if (knowledge) lines.push(knowledge);
    if (/top|xếp hạng|tăng mạnh|so sánh/.test(question)) {
      lines.push("Các mã có mức dự báo T+5 cao nhất hiện tại:");
      for (const [index, row] of context.topMovers.slice(0, 7).entries()) {
        lines.push(`${index + 1}. ${row.symbol}: ${money(row.close)} → ${money(row.forecast)} (${pct(row.return)}).`);
      }
      return lines.join("\n");
    }
    if (five) lines.push(`${context.symbol}: giá hiện tại ${money(context.close)}; dự báo T+5 ${money(five.price)} (${pct(five.expectedReturn)}), vùng giá ${money(five.lowerPrice)}–${money(five.upperPrice)}.`);
    if (/quỹ|danh mục|nắm giữ/.test(question) || !knowledge) {
      if (context.fund) {
        const contribution = five?.liveEvidence?.FUND;
        lines.push(`Danh mục quỹ: ${context.fund.fundCount} quỹ đang nắm giữ, tỷ trọng bình quân ${(context.fund.averageWeight * 100).toFixed(2)}% mỗi quỹ; NAV 20 phiên ${pct(context.fund.navMomentum20)}${number(contribution) === null ? "" : `; tác động vào dự báo T+5 ${pct(contribution)}`}.`);
        if (/quỹ|danh mục|nắm giữ/.test(question)) lines.push(`Các quỹ có tỷ trọng cao: ${context.fund.holders.slice(0, 5).map(holder => `${holder.code || holder.name} ${(holder.weight * 100).toFixed(2)}%`).join("; ")}.`);
      } else if (/quỹ|danh mục|nắm giữ/.test(question)) lines.push("Mã này chưa có công bố danh mục quỹ đủ điều kiện để đưa vào dự báo.");
    }
    if (/dòng tiền|ngoại|tự doanh|đầy đủ|phân tích/.test(question)) {
      if (context.flow.foreign) lines.push(`Khối ngoại ${context.flow.foreign.latestDate}: ròng ${money(context.flow.foreign.net1)} đồng; cộng dồn 5 quan sát ${money(context.flow.foreign.net5)} đồng.`);
      if (context.flow.proprietary) lines.push(`Tự doanh ${context.flow.proprietary.latestDate}: ròng ${money(context.flow.proprietary.net1)} đồng; cộng dồn 5 quan sát ${money(context.flow.proprietary.net5)} đồng.`);
    }
    if (context.financial && /tài chính|lợi nhuận|định giá|đầy đủ|phân tích/.test(question)) {
      lines.push(`Tài chính doanh nghiệp: tăng trưởng lợi nhuận ${pct(context.financial.profitGrowth)}, tăng trưởng doanh thu ${pct(context.financial.revenueGrowth)} so với quý trước.`);
    }
    const drivers = primaryDrivers(five);
    if (drivers.length && !/chỉ.*quỹ/.test(question)) lines.push(`Các yếu tố tác động mạnh nhất: ${drivers.join("; ")}.`);
    if (context.news.length && /tin|đầy đủ|phân tích/.test(question)) lines.push(`Tin gần đây: ${context.news.slice(0, 2).map(item => item.title).join("; ")}.`);
    if (/rủi ro|lưu ý|an toàn|đầy đủ|phân tích/.test(question)) lines.push(`Trạng thái rủi ro: ${context.riskStatus || "chưa xác định"}. ${context.validation.directionValidated ? "Xác suất hướng đã qua kiểm định." : "Xác suất hướng T+5 chưa đủ độ tin cậy nên không được công bố."}`);
    return lines.join("\n");
  }

  async function remoteAnalysis(input, context, address) {
    const response = await fetch(address, {
      method: "POST", mode: "cors", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: input, context,
        history: state.messages.slice(-8).map(item => ({ role: item.role, content: item.content.slice(0, 2400) })),
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.answer) throw new Error(payload.message || `Kết nối AI chưa sẵn sàng (${response.status}).`);
    return payload.answer;
  }

  async function ask(input) {
    const question = String(input || "").trim().slice(0, 1800);
    if (!question || state.busy) return;
    state.busy = true;
    $("#solutionAiInput").value = "";
    $("#solutionAiSend").disabled = true;
    message("user", question);
    setStatus("Đang phân tích dữ liệu…");
    const waiting = message("assistant", "Đang đối chiếu giá, dòng tiền và các yếu tố dự báo…", "aiThinking");
    try {
      const context = await buildContext();
      updateContextBar(context);
      const address = endpoint();
      let answer;
      if (address) {
        try {
          answer = await remoteAnalysis(question, context, address);
          setStatus("Gemini · phân tích theo dữ liệu thực");
        } catch {
          answer = localAnalysis(question, context);
          setStatus("Phân tích từ dữ liệu hiện có");
        }
      } else {
        answer = localAnalysis(question, context);
        setStatus("Phân tích từ dữ liệu hiện có");
      }
      waiting.remove();
      message("assistant", answer);
      state.messages.push({ role: "user", content: question }, { role: "assistant", content: answer });
    } catch (error) {
      waiting.remove();
      message("assistant", error?.message || "Chưa thể tải dữ liệu phân tích.", "aiError");
      setStatus("Chưa tải được dữ liệu");
    } finally {
      state.busy = false;
      $("#solutionAiSend").disabled = false;
      $("#solutionAiInput").focus();
    }
  }

  async function open() {
    state.opened = true;
    $("#solutionAiPanel").classList.add("open");
    $("#solutionAiPanel").setAttribute("aria-hidden", "false");
    $("#solutionAiLauncher").setAttribute("aria-expanded", "true");
    try { updateContextBar(await buildContext()); } catch { /* dashboard is still loading */ }
    $("#solutionAiInput").focus();
  }

  function close() {
    state.opened = false;
    $("#solutionAiPanel").classList.remove("open");
    $("#solutionAiPanel").setAttribute("aria-hidden", "true");
    $("#solutionAiLauncher").setAttribute("aria-expanded", "false");
  }

  function configure() {
    const value = window.prompt("Nhập địa chỉ backend SoluTION.AI đã cấu hình Gemini. Không nhập API key.", endpoint());
    if (value === null) return;
    const address = value.trim();
    if (!address) {
      localStorage.removeItem("vmews_solution_ai_endpoint");
      setStatus("Phân tích từ dữ liệu hiện có");
      return;
    }
    try {
      const url = new URL(address, location.origin);
      if (url.protocol !== "https:" && !["localhost", "127.0.0.1"].includes(url.hostname)) throw new Error("Cần sử dụng kết nối HTTPS.");
      localStorage.setItem("vmews_solution_ai_endpoint", url.toString());
      setStatus("Đã thiết lập backend AI");
    } catch (error) { window.alert(error?.message || "Địa chỉ backend không hợp lệ."); }
  }

  function init() {
    if (!$("#solutionAiPanel")) return;
    for (const selector of ["#solutionAiLauncher", "#solutionAiTop", "#solutionAiNav"]) $(selector)?.addEventListener("click", open);
    $("#solutionAiClose").addEventListener("click", close);
    $("#solutionAiSettings").addEventListener("click", configure);
    $("#solutionAiForm").addEventListener("submit", event => { event.preventDefault(); ask($("#solutionAiInput").value); });
    $("#solutionAiInput").addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); ask(event.currentTarget.value); }
    });
    $("#solutionAiSuggestions").addEventListener("click", event => {
      const button = event.target.closest("[data-ai-prompt]");
      if (button) ask(button.dataset.aiPrompt);
    });
    document.addEventListener("keydown", event => { if (event.key === "Escape" && state.opened) close(); });
    window.addEventListener("vmews:symbol-changed", async () => {
      try { updateContextBar(await buildContext()); } catch { /* selected symbol unavailable */ }
    });
    window.__SOLUTION_AI_BUILD_CONTEXT__ = buildContext;
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
