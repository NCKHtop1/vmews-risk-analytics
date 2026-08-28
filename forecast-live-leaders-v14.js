(() => {
  "use strict";

  const $ = selector => document.querySelector(selector);
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const number = value => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value)) ? Number(value) : null;
  const money = value => number(value)?.toLocaleString("vi-VN", { maximumFractionDigits: 0 }) || "—";
  const percent = (value, digits = 1) => number(value) === null ? "—" : `${(number(value) * 100).toFixed(digits)}%`;
  const signed = (value, digits = 1) => number(value) === null ? "—" : `${number(value) >= 0 ? "+" : ""}${percent(value, digits)}`;
  const escapeHTML = value => String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const expertNames = {
    NUMERICAL: "Giá / kỹ thuật", REGIME: "Trạng thái thị trường", VOLATILITY: "Biến động thực tế",
    SECTOR: "Luân chuyển ngành", EVENT: "Tin tức / sự kiện", FLOW: "Dòng tiền tổ chức", FUND: "Danh mục quỹ", FUNDAMENTAL: "Tài chính doanh nghiệp", RUMOR: "Tín hiệu cộng đồng",
  };
  // HOSE's July 2026 review became effective on 03/08/2026: MCH and
  // TCX replaced PLX and TPB.  Dashboard metadata remains authoritative.
  const currentVN30 = Object.freeze([
    "ACB", "BID", "BSR", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG", "LPB",
    "MBB", "MCH", "MSN", "MWG", "SAB", "SHB", "SSB", "SSI", "STB", "TCB",
    "TCX", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VPL", "VRE",
  ]);
  const issuerAliases = {
    VCB: ["vietcombank"], BID: ["bidv"], CTG: ["vietinbank"], TCB: ["techcombank"],
    MBB: ["mb bank", "mbbank", "ngân hàng quân đội"], VPB: ["vpbank"], TPB: ["tpbank"],
    STB: ["sacombank"], HDB: ["hdbank"], VNM: ["vinamilk"], HPG: ["hòa phát", "hoà phát", "hoa phat"],
    VIC: ["vingroup"], VHM: ["vinhomes"], VRE: ["vincom retail"], VJC: ["vietjet"],
    SAB: ["sabeco"], MSN: ["masan"], PLX: ["petrolimex"], GAS: ["pv gas", "pvgas"],
    MWG: ["thế giới di động"], BCM: ["becamex"], NLG: ["nam long"], DIG: ["dic corp", "dic group"],
  };
  const state = { base: null, session: null, universe: [], candidates: [], rows: [], defensive: false, index: 0, filter: "all", paused: reducedMotion, timer: 0 };

  function valueLabel(value) {
    if (!Number.isFinite(value) || value <= 0) return "Chưa có";
    if (value >= 1e12) return `${(value / 1e12).toFixed(1)} nghìn tỷ`;
    if (value >= 1e9) return `${(value / 1e9).toFixed(value >= 10e9 ? 0 : 1)} tỷ`;
    return `${(value / 1e6).toFixed(value >= 100e6 ? 0 : 1)} triệu`;
  }

  function shortDate(value) {
    if (!value) return "—";
    const date = new Date(`${String(value).slice(0, 10)}T00:00:00`);
    return Number.isNaN(+date) ? "—" : date.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
  }

  function qualityScore(row) {
    const probability = row.directionValidated ? clamp((row.probUp - .44) / .18, 0, 1) : .25;
    const liquidity = clamp(Math.log10(Math.max(row.tradedValue20, 1)) / 11, 0, 1);
    const interval = clamp(row.upside / Math.max(row.intervalWidth, .012), 0, 1);
    const evidence = clamp(row.newsCount / 6, 0, 1);
    const risk = row.risk === "GREEN" ? 1 : row.risk === "WATCH" || row.risk === "YELLOW" ? .52 : .12;
    const flow = row.flowFresh ? 1 : 0;
    return Math.round(100 * (.28 * probability + .24 * liquidity + .16 * interval + .12 * evidence + .14 * risk + .06 * flow));
  }

  function forecastQuality(row) {
    const probability = row.directionValidated && number(row.probUp) !== null ? clamp((row.probUp - .44) / .18, 0, 1) : .45;
    const interval = clamp(Math.max(row.upside, 0) / Math.max(row.intervalWidth, .012), 0, 1);
    const risk = row.risk === "GREEN" ? 1 : row.risk === "WATCH" || row.risk === "YELLOW" ? .55 : .15;
    return .42 * probability + .38 * interval + .20 * risk;
  }

  function rankingScore(row) {
    const quality = number(row.forecastQuality) ?? forecastQuality(row);
    return row.upside * (.68 + .32 * quality);
  }

  function rankingHorizon(base) {
    const promotion = base?.model?.promotion || base?.dash?.promotion || {};
    const promoted = new Set((promotion.directPriceHorizons || []).map(Number));
    const preferred = Number(promotion.preferredRankingHorizon || 5);
    if (!promoted.size || promoted.has(preferred)) return preferred;
    return [3, 4, 5, 2, 1].find(horizon => promoted.has(horizon)) || 5;
  }

  function buildLeaderboard(base, options = {}) {
    const snapshots = base?.dash?.symbols || {};
    const histories = base?.dash?.charts || {};
    const disclosed = base?.dash?.lists?.vn30?.symbols;
    const members = new Set(Array.isArray(disclosed) && disclosed.length === 30 ? disclosed : currentVN30);
    const selectedHorizon = rankingHorizon(base);
    const rows = [];

    for (const [symbol, snapshot] of Object.entries(snapshots)) {
      const forecast = snapshot?.horizons?.[String(selectedHorizon)] || {};
      const close = number(snapshot.close);
      const target = number(forecast.expectedPrice);
      const tickSize = number(forecast.tickSize);
      if ((options.scope === "vn30" && !members.has(symbol)) || snapshot.exchange !== "HOSE" || snapshot.dataFreshness !== "CURRENT"
          || forecast.priceValidated !== true || forecast.validationStatus !== "PASS"
          || forecast.pointDirectionValidated !== true || forecast.magnitudeValidated !== true
          || !close || !target || (!options.includeNonPositive && target <= close)
          || !tickSize || target % tickSize !== 0) continue;

      const sessions = (histories[symbol] || []).slice(-20);
      const volumes = sessions.map(session => number(session.volume)).filter(volume => volume !== null && volume >= 0);
      const avgVolume20 = volumes.length ? volumes.reduce((sum, volume) => sum + volume, 0) / volumes.length : 0;
      const tradedValue20 = avgVolume20 * close;
      const news = snapshot.newsFeatures || {};
      const flow = snapshot.flow || {};
      const fund = snapshot.fundContext || {};
      const row = {
        symbol,
        horizon: selectedHorizon,
        snapshot,
        forecast,
        history: histories[symbol] || [],
        close,
        target,
        upside: target / close - 1,
        probUp: number(forecast.probUp),
        directionValidated: forecast.directionValidated === true && number(forecast.probUp) !== null,
        q20: number(forecast.q20Price),
        q80: number(forecast.q80Price),
        intervalWidth: (number(forecast.q80Price) - number(forecast.q20Price)) / close,
        avgVolume20,
        tradedValue20,
        newsCount: (number(news.count5) || 0) + (number(news.pendingDecisionEvents) || 0),
        officialNews: number(news.official5) || 0,
        flowFresh: flow.stale !== true && (flow.foreignAvailable || flow.propAvailable),
        flowAge: number(flow.sessionsSinceObservation),
        fundAvailable: fund.available === true,
        fundCount: number(fund.fundCount) || 0,
        fundWeight: number(fund.averageReportedWeight),
        fundModelEligible: fund.usedByForecast === true,
        risk: snapshot.riskStatus || "UNKNOWN",
        sector: snapshot.sector && snapshot.sector !== "UNKNOWN" ? snapshot.sector : "Chưa phân loại ngành",
        volatility: number(snapshot.dailyVolatility),
        targetDate: forecast.targetDate,
      };

      if (options.filter === "liquid" && row.tradedValue20 < 1e9) continue;
      if (options.filter === "green" && row.risk !== "GREEN") continue;
      row.quality = qualityScore(row);
      row.forecastQuality = forecastQuality(row);
      row.rankScore = rankingScore(row);
      rows.push(row);
    }

    rows.sort((left, right) => right.rankScore - left.rankScore || right.upside - left.upside || (right.probUp || 0) - (left.probUp || 0) || left.symbol.localeCompare(right.symbol));
    return options.all ? rows : rows.slice(0, 10);
  }

  window.__VMEWS_BUILD_LEADERBOARD__ = buildLeaderboard;
  window.__VMEWS_RANKING_HORIZON__ = rankingHorizon;
  window.__VMEWS_VN30_MEMBERS__ = currentVN30;


  function vnDateKey(value) {
    const date = new Date(value);
    if (Number.isNaN(+date)) return "";
    return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh", year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
  }

  function sessionUsableNow(payload) {
    const cutoff = new Date(payload?.cutoffAt || payload?.generatedAt || "");
    if (Number.isNaN(+cutoff)) return false;
    const age = Date.now() - +cutoff;
    if (age < -15 * 60_000 || age > 80 * 60 * 60_000) return false;
    const now = new Date();
    const weekday = new Intl.DateTimeFormat("en-US", { timeZone: "Asia/Ho_Chi_Minh", weekday: "short" }).format(now);
    const hour = Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Ho_Chi_Minh", hour: "2-digit", hour12: false }).format(now));
    if (!["Sat", "Sun"].includes(weekday) && hour >= 10 && vnDateKey(cutoff) !== vnDateKey(now)) return false;
    return true;
  }

  async function loadSessionOverlay(base) {
    try {
      const root = window.__VMEWS_DATA_ROOT__ || "./data";
      const revision = Math.floor(Date.now() / 60000);
      const response = await fetch(`${root}/forecast-session-v21.json?refresh=${revision}`, { cache: "no-store" });
      if (!response.ok) return null;
      const payload = await response.json();
      if (payload?.status !== "PASS" || payload?.coreForecastUnchanged !== true) return null;
      if (String(payload.coreAsOf || "") !== String(base?.dash?.asOf || "")) return null;
      if (!Array.isArray(payload.symbols) || !payload.symbols.length) return null;
      if (number(payload.rankingHorizon) !== rankingHorizon(base)) return null;
      const coverage = payload.coverage || {};
      if (number(coverage.coverageRatio) < .90 || number(coverage.currentCoverageRatio) < .90 || number(coverage.cutoffFreshCoverageRatio) < .90) return null;
      if (!sessionUsableNow(payload)) return null;
      return payload;
    } catch {
      return null;
    }
  }

  function applySessionOverlay(rows, session = state.session) {
    if (!session?.symbols?.length) return rows.slice();
    const live = new Map(session.symbols.filter(item => item.quoteCurrent && item.freshForCutoff !== false).map(item => [item.symbol, item]));
    return rows.map(row => {
      const quote = live.get(row.symbol);
      if (!quote || number(quote.liveClose) === null || number(quote.liveClose) <= 0) return row;
      if (number(quote.rankingHorizon) !== null && number(quote.rankingHorizon) !== row.horizon) return row;
      const next = { ...row, coreClose: row.close, close: number(quote.liveClose), sessionChange: number(quote.change), sessionAt: quote.updateAt };
      next.upside = next.target / next.close - 1;
      next.tradedValue20 = next.avgVolume20 * next.close;
      next.quality = qualityScore(next);
      next.forecastQuality = number(quote.quality) ?? forecastQuality(next);
      next.rankScore = number(quote.conviction) ?? rankingScore(next);
      return next;
    }).sort((left, right) => right.rankScore - left.rankScore || right.upside - left.upside || right.quality - left.quality || left.symbol.localeCompare(right.symbol));
  }

  function finalLeaderboard(base, session = state.session, options = {}) {
    let rows = applySessionOverlay(buildLeaderboard(base, { all: true, scope: options.scope, includeNonPositive: true }), session);
    if (!options.includeNonPositive) rows = rows.filter(row => row.upside > 0);
    if (options.filter === "liquid") rows = rows.filter(row => row.tradedValue20 >= 1e9);
    if (options.filter === "green") rows = rows.filter(row => row.risk === "GREEN");
    return options.all ? rows : rows.slice(0, 10);
  }

  window.__VMEWS_APPLY_SESSION_OVERLAY__ = applySessionOverlay;
  window.__VMEWS_FINAL_LEADERBOARD__ = finalLeaderboard;

  function sessionStamp() {
    if (!state.session?.cutoffAt) return " · EOD đã kiểm định";
    const date = new Date(state.session.cutoffAt);
    if (Number.isNaN(+date)) return "";
    const time = new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Ho_Chi_Minh" }).format(date);
    return ` · ${state.session.session} ${time}`;
  }

  function refreshMode() {
    const defensive = state.defensive;
    const horizon = state.rows[0]?.horizon || rankingHorizon(state.base);
    const command = $("#leaders .commandIndex");
    const summary = $("#leaderSummary");
    const primaryFilter = $('[data-filter="all"]');
    const deck = $("#signalDeck");
    if (command) command.textContent = defensive ? "HOSE · TRẠNG THÁI PHÒNG THỦ" : `HOSE · T+${horizon}`;
    if (summary) summary.textContent = defensive
      ? `Chưa có mã HOSE đủ điều kiện có mục tiêu T+${horizon} cao hơn giá tham chiếu; đang hiển thị nhóm giảm ít nhất để theo dõi rủi ro.`
      : `Top 10 toàn HOSE theo forecast T+${horizon} đã kiểm định, chất lượng tín hiệu và dữ liệu phiên mới nhất.`;
    if (primaryFilter) primaryFilter.textContent = defensive ? "HOSE phòng thủ" : "HOSE forecast tăng";
    if (deck) deck.setAttribute("aria-label", defensive
      ? `Các cổ phiếu HOSE có mức giảm dự báo T+${horizon} thấp nhất`
      : `Các cổ phiếu HOSE có mức tăng dự báo T+${horizon} cao nhất`);
  }

  function animateValue(element, target, format) {
    if (!element) return;
    if (reducedMotion) { element.textContent = format(target); return; }
    const start = performance.now();
    const duration = 920;
    function frame(time) {
      const progress = clamp((time - start) / duration, 0, 1);
      element.textContent = format(target * (1 - (1 - progress) ** 3));
      if (progress < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  function renderPulse() {
    const symbols = Object.values(state.base?.dash?.symbols || {});
    const advancing = number(state.session?.market?.advancing) ?? symbols.filter(snapshot => number(snapshot.lastSessionReturn) > 0).length;
    const falling = number(state.session?.market?.falling) ?? symbols.filter(snapshot => number(snapshot.lastSessionReturn) < 0).length;
    const positive = state.universe.length;
    const covered = state.candidates.length;
    const top = state.universe[0] || state.candidates[0];
    const topIsPositive = Boolean(top && top.upside > 0);
    const cards = [
      { label: "Cổ phiếu được theo dõi", value: symbols.length, format: value => `${Math.round(value)}`, detail: "toàn sàn HOSE", tone: "" },
      { label: "HOSE forecast tăng", value: positive, format: value => `${Math.round(value)} / ${covered}`, detail: `${Math.max(covered - positive, 0)} mã chưa có tín hiệu tăng`, tone: "up" },
      { label: state.session ? "Phiên hiện tại" : "Phiên EOD gần nhất", value: advancing, format: value => `${Math.round(value)} ↑`, detail: `${falling} giảm · ${symbols.length - advancing - falling} đi ngang`, tone: "" },
      { label: topIsPositive ? "Tăng nổi bật nhất" : `Xếp hạng T+${top?.horizon || rankingHorizon(state.base)} cao nhất`, value: (top?.upside || 0) * 100, format: value => `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`, detail: top ? `${top.symbol} · trọng tâm ${money(top.target)}` : "Chưa có dữ liệu", tone: topIsPositive ? "up" : "down" },
    ];

    $("#marketPulse").innerHTML = cards.map((card, index) => `<article class="pulseCard"><span>${escapeHTML(card.label)}</span><strong class="${card.tone}" data-pulse="${index}">—</strong><small>${escapeHTML(card.detail)}</small><i class="pulseTrace" aria-hidden="true"></i></article>`).join("");
    cards.forEach((card, index) => animateValue($(`[data-pulse="${index}"]`), card.value, card.format));
  }

  function riskLabel(row) {
    return row.risk === "GREEN" ? "RỦI RO THẤP" : row.risk === "RED" ? "RỦI RO CAO" : "CẦN THEO DÕI";
  }

  function riskClass(row) {
    return row.risk === "GREEN" ? "riskGreen" : row.risk === "RED" ? "riskRed" : "riskWatch";
  }

  function issuerNewsMatches(row, item) {
    const title = String(item?.title || "");
    const lower = title.toLocaleLowerCase("vi-VN");
    const primary = /^\s*(?:(?:HOSE|HSX|HNX|UPCOM)\s*[:/\-]\s*)?\$?([A-Z][A-Z0-9]{2,4})\s*[:\-–|]/i.exec(title);
    if (primary && primary[1].toUpperCase() !== row.symbol && state.base?.dash?.symbols?.[primary[1].toUpperCase()]) return false;
    if (row.symbol === "GTA" && /\bgta\s*(?:\d+|[ivx]{1,4})\b|\bgameplay\b|\brockstar\b|\btake[\s-]?two\b|\bplaystation\b|\bxbox\b/i.test(title)) return false;
    if (row.symbol === "VSI" && /smart\s+indexing|\bvps\b.{0,55}\bvsi\b|\bvsi\b.{0,55}\bvps\b/i.test(title)) return false;
    if (row.symbol === "ASP" && /\basp\s+shipping\b/i.test(title) && !/dầu\s+khí\s+an\s+pha/i.test(title)) return false;
    if (row.symbol === "FPT" && /\bfpt\s+(retail|long\s+châu|online)\b|chứng\s+khoán\s+fpt|bán\s+lẻ\s+kỹ\s+thuật\s+số\s+fpt/i.test(title)) return false;
    const exact = new RegExp(`(^|[^A-Za-z0-9])${row.symbol}([^A-Za-z0-9]|$)`, "i").test(title);
    return exact || (issuerAliases[row.symbol] || []).some(alias => lower.includes(alias));
  }

  function belongsToLastFiveSessions(row, item) {
    const tradingDates = row.history.slice(-5).map(session => String(session.date || "").slice(0, 10)).filter(Boolean);
    const available = String(item?.availableDate || item?.publishedAt || "").slice(0, 10);
    return Boolean(available && tradingDates.length && available >= tradingDates[0] && available <= tradingDates.at(-1));
  }

  function renderCards() {
    const deck = $("#signalDeck");
    if (!state.rows.length) {
      deck.innerHTML = '<div class="deckEmpty">Chưa có cổ phiếu HOSE hợp lệ phù hợp bộ lọc.</div>';
      $("#leaderDots").replaceChildren();
      $("#leaderDetail").innerHTML = '<div class="deckEmpty">Hãy đổi bộ lọc để tiếp tục kiểm tra.</div>';
      $("#carouselPosition").textContent = "00 / 00";
      return;
    }

    deck.innerHTML = state.rows.map((row, index) => {
      const illiquid = row.tradedValue20 < 1e9;
      const probability = row.directionValidated ? percent(row.probUp, 1) : "—";
      const direction = row.upside > 0 ? "tăng" : "giảm";
      const returnTone = row.upside > 0 ? "signalUp" : "signalDown";
      const returnLabel = state.defensive ? "GIẢM ÍT NHẤT TRÊN HOSE" : `TRIỂN VỌNG T+${row.horizon}`;
      return `<article class="signalCard ${riskClass(row)}" data-card="${index}" data-symbol="${escapeHTML(row.symbol)}" aria-label="${escapeHTML(row.symbol)}, dự báo ${direction} ${percent(Math.abs(row.upside), 2)} tại T+${row.horizon}" tabindex="-1"><div class="signalCardTop"><span class="signalRank">#${String(index + 1).padStart(2, "0")} / HOSE</span><span class="signalRisk ${riskClass(row)}">${escapeHTML(riskLabel(row))}</span></div><div class="signalIdentity"><div><h3>${escapeHTML(row.symbol)}</h3><span>${escapeHTML(row.sector)}</span></div><span class="qualityOrbit" style="--quality:${row.quality}%"><b>${row.quality}</b><small>điểm</small></span></div><div class="signalReturn"><strong class="${returnTone}">${signed(row.upside, 2)}</strong><span>${returnLabel}</span></div><canvas class="leaderSpark" data-spark="${index}" aria-label="Biểu đồ giá của ${escapeHTML(row.symbol)}"></canvas><div class="signalPrices"><span>${money(row.close)} <i>→</i> <b>${money(row.target)}</b></span><span>${shortDate(row.targetDate)}</span></div><div class="signalBand"><span>VÙNG GIÁ</span><b>${money(row.q20)} – ${money(row.q80)}</b></div><div class="signalFacts">${row.directionValidated ? `<span>P↑ ${probability}</span>` : ""}<span>${row.newsCount} tin / 5 phiên</span><span class="${illiquid ? "factWarning" : ""}">${valueLabel(row.tradedValue20)} / phiên</span></div>${illiquid ? '<div class="liquidityWarning">Thanh khoản thấp</div>' : ""}<button class="cardAction" type="button" data-analyze="${escapeHTML(row.symbol)}">Phân tích ${escapeHTML(row.symbol)} <span>↗</span></button></article>`;
    }).join("");

    $("#leaderDots").innerHTML = state.rows.map((row, index) => `<button type="button" class="leaderDot" data-dot="${index}" aria-label="Xem ${escapeHTML(row.symbol)}" title="${escapeHTML(row.symbol)}"></button>`).join("");
    positionCards();
    state.rows.forEach((row, index) => drawSparkline($(`[data-spark="${index}"]`), row.history));
    renderDetail();
  }

  function positionCards() {
    const count = state.rows.length;
    if (!count) return;
    state.index = ((state.index % count) + count) % count;
    const narrow = $("#signalDeck").clientWidth < 650;
    const shift = narrow ? 215 : 295;
    document.querySelectorAll(".signalCard").forEach((card, index) => {
      let delta = index - state.index;
      if (delta > count / 2) delta -= count;
      if (delta < -count / 2) delta += count;
      const distance = Math.abs(delta);
      const visible = distance <= (narrow ? 1 : 2);
      card.style.setProperty("--deck-shift", `${delta * shift}px`);
      card.style.setProperty("--deck-depth", `${-distance * (narrow ? 135 : 150)}px`);
      card.style.setProperty("--deck-rotate", `${-delta * (narrow ? 16 : 19)}deg`);
      card.style.setProperty("--deck-scale", String(1 - distance * .105));
      card.style.setProperty("--deck-opacity", visible ? String(distance === 0 ? 1 : Math.max(.14, .73 - distance * .24)) : "0");
      card.style.zIndex = String(12 - distance);
      card.classList.toggle("selected", delta === 0);
      card.setAttribute("aria-hidden", delta === 0 ? "false" : "true");
      card.inert = delta !== 0;
    });

    document.querySelectorAll(".leaderDot").forEach((dot, index) => {
      dot.classList.toggle("active", index === state.index);
      dot.setAttribute("aria-pressed", String(index === state.index));
    });
    $("#carouselPosition").textContent = `${String(state.index + 1).padStart(2, "0")} / ${String(count).padStart(2, "0")}`;
    window.__VMEWS_LEADERBOARD__ = { mode: state.defensive ? "defensive" : "positive", filter: state.filter, selected: state.rows[state.index].symbol, session: state.session?.session || "EOD", rows: state.rows.map(row => ({ symbol: row.symbol, close: row.close, coreClose: row.coreClose || row.close, target: row.target, upside: row.upside, rankScore: row.rankScore, quality: row.quality, tradedValue20: row.tradedValue20, risk: row.risk, sessionAt: row.sessionAt || null })) };
  }

  function drawSparkline(canvas, history) {
    if (!canvas || !history?.length) return;
    const rectangle = canvas.getBoundingClientRect();
    const width = rectangle.width || 385;
    const height = rectangle.height || 55;
    const density = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * density);
    canvas.height = Math.round(height * density);
    const context = canvas.getContext("2d");
    context.setTransform(density, 0, 0, density, 0, 0);
    const values = history.slice(-34).map(point => number(point.rawClose ?? point.close)).filter(value => value !== null);
    if (values.length < 2) return;
    const min = Math.min(...values), max = Math.max(...values), spread = Math.max(max - min, 1);
    const points = values.map((value, index) => ({ x: 2 + index * (width - 4) / (values.length - 1), y: 6 + (max - value) / spread * (height - 15) }));
    context.beginPath();
    context.moveTo(points[0].x, points[0].y);
    for (let index = 1; index < points.length - 1; index++) {
      context.quadraticCurveTo(points[index].x, points[index].y, (points[index].x + points[index + 1].x) / 2, (points[index].y + points[index + 1].y) / 2);
    }
    context.lineTo(points.at(-1).x, points.at(-1).y);
    context.strokeStyle = "rgba(168,235,101,.9)";
    context.lineWidth = 1.7;
    context.stroke();
    context.lineTo(width - 2, height);
    context.lineTo(2, height);
    context.closePath();
    const gradient = context.createLinearGradient(0, 3, 0, height);
    gradient.addColorStop(0, "rgba(168,235,101,.16)");
    gradient.addColorStop(1, "rgba(168,235,101,0)");
    context.fillStyle = gradient;
    context.fill();
    const last = points.at(-1);
    context.beginPath();
    context.arc(last.x, last.y, 3, 0, Math.PI * 2);
    context.fillStyle = "#c9ff9a";
    context.fill();
  }

  function contributionsMarkup(row) {
    const entries = Object.entries(row.forecast.expertContributions || {}).filter(([, value]) => Math.abs(number(value) || 0) > 1e-7).sort((left, right) => Math.abs(number(right[1]) || 0) - Math.abs(number(left[1]) || 0));
    const maximum = Math.max(...entries.map(([, value]) => Math.abs(number(value) || 0)), .00001);
    if (!entries.length) return '<div class="detailEmpty">Chưa có yếu tố đủ nổi bật.</div>';
    return entries.map(([name, value]) => `<div class="factorRow"><span>${escapeHTML(expertNames[name] || name)}</span><div class="factorTrack"><i class="${number(value) < 0 ? "factorDown" : "factorUp"}" style="width:${Math.abs(number(value) || 0) / maximum * 100}%"></i></div><strong class="${number(value) < 0 ? "factorNegative" : "factorPositive"}">${signed(value, 2)}</strong></div>`).join("");
  }

  function newsMarkup(row) {
    const recent = (row.snapshot.evidence?.decisionRecent || row.snapshot.evidence?.recent || []).filter(item => issuerNewsMatches(row, item) && (item.decisionTimeEligible || belongsToLastFiveSessions(row, item))).slice(0, 2);
    if (!recent.length) return '<p class="detailEmpty">Chưa có tin mới đáng chú ý.</p>';
    return recent.map(item => `<article class="detailNewsItem"><span>${escapeHTML(item.publisher || item.source || "Nguồn đã đối chiếu")} · ${escapeHTML(shortDate(item.availableDate || item.publishedAt || item.date))}</span><strong>${escapeHTML(item.title || "Sự kiện chưa có tiêu đề")}</strong></article>`).join("");
  }

  function corridorMarkup(row) {
    if (!row.q20 || !row.q80 || row.q80 <= row.q20) return '<div class="detailEmpty">Khoảng dự báo chưa đủ dữ liệu.</div>';
    const span = row.q80 - row.q20;
    const current = clamp((row.close - row.q20) / span * 100, 0, 100);
    const target = clamp((row.target - row.q20) / span * 100, 0, 100);
    return `<div class="corridorNumbers"><span>Q20 <b>${money(row.q20)}</b></span><span>Q80 <b>${money(row.q80)}</b></span></div><div class="priceCorridor"><i class="corridorCurrent" style="left:${current}%" title="Giá hiện tại ${money(row.close)}"></i><i class="corridorTarget" style="left:${target}%" title="Dự báo ${money(row.target)}"></i></div><div class="corridorLegend"><span><i></i>Hiện tại</span><span><i></i>Mục tiêu T+${row.horizon}</span></div>`;
  }

  function renderDetail() {
    const row = state.rows[state.index];
    if (!row) return;
    const downside = row.q20 ? row.q20 / row.close - 1 : null;
    const flow = row.snapshot.flow || {};
    const flowStatus = row.flowFresh ? "Dữ liệu mới" : row.flowAge !== null ? `Cũ ${row.flowAge} phiên` : "Chưa xác minh mới";
    const warnings = [];
    if (row.tradedValue20 < 1e9) warnings.push("Thanh khoản dưới 1 tỷ đồng/phiên");
    if (row.risk !== "GREEN") warnings.push(`Trạng thái ${row.risk}`);
    if (!row.directionValidated) warnings.push("Chưa đủ cơ sở cho xác suất hướng");
    else if (row.probUp < .5) warnings.push("P(tăng) dưới 50%");
    if (!row.flowFresh) warnings.push("Dòng tiền tổ chức chưa mới");
    if (row.fundAvailable && !row.fundModelEligible) warnings.push("Dữ liệu quỹ chưa đủ điều kiện sử dụng");
    if (!row.newsCount) warnings.push("Không có tin trong 5 phiên");
    else if (!(row.snapshot.evidence?.decisionRecent || row.snapshot.evidence?.recent || []).some(item => issuerNewsMatches(row, item) && (item.decisionTimeEligible || belongsToLastFiveSessions(row, item)))) warnings.push("Chưa có tin gần đây khớp doanh nghiệp");

    $("#leaderDetail").innerHTML = `<div class="detailTopline"><div><span class="detailIndex">${escapeHTML(row.symbol)} · T+${row.horizon}</span><h3>${escapeHTML(row.symbol)} <span>· cơ sở dự báo</span></h3></div><button class="detailAnalyze" type="button" data-analyze="${escapeHTML(row.symbol)}">Xem đầy đủ ↗</button></div><div class="detailLayout"><div class="detailColumn"><div class="detailLabel">CÁC YẾU TỐ CHÍNH</div><div class="factorList">${contributionsMarkup(row)}</div><div class="corridorBlock"><div class="detailLabel">VÙNG GIÁ T+${row.horizon}</div>${corridorMarkup(row)}</div></div><div class="detailColumn"><div class="evidenceTiles"><article><span>P(tăng) T+${row.horizon}</span><b>${row.directionValidated ? percent(row.probUp, 1) : "—"}</b></article><article><span>Biên dưới</span><b class="${downside < 0 ? "factorNegative" : "factorPositive"}">${signed(downside, 1)}</b><small>${money(row.q20)}</small></article><article><span>Thanh khoản 20 phiên</span><b>${valueLabel(row.tradedValue20)}</b><small>${money(Math.round(row.avgVolume20))} cp/phiên</small></article><article><span>Quỹ nắm giữ</span><b>${row.fundAvailable ? `${row.fundCount} quỹ` : "—"}</b><small>${row.fundAvailable && row.fundWeight !== null ? `Bình quân ${percent(row.fundWeight, 1)}/quỹ` : escapeHTML(flowStatus)}</small></article></div><div class="evidenceNews"><div class="detailLabel">TIN GẦN ĐÂY · ${row.newsCount} BÀI</div>${newsMarkup(row)}</div></div></div>${warnings.length ? `<div class="signalWarnings"><span>LƯU Ý</span>${warnings.map(warning => `<i>${escapeHTML(warning)}</i>`).join("")}</div>` : ""}`;
  }

  function select(index, manual = false) {
    if (!state.rows.length) return;
    state.index = index;
    positionCards();
    renderDetail();
    if (manual) scheduleRotation();
  }

  function scheduleRotation() {
    window.clearInterval(state.timer);
    if (state.paused || reducedMotion || state.rows.length < 2) return;
    state.timer = window.setInterval(() => {
      if (!document.hidden && !$("#leaders").matches(":hover, :focus-within")) select(state.index + 1);
    }, 3000);
  }

  function updateClock() {
    const formatter = new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "Asia/Ho_Chi_Minh" });
    $("#vnClock").textContent = `GIỜ VIỆT NAM ${formatter.format(new Date())}`;
  }

  async function openSymbol(symbol) {
    const input = $("#symbol");
    if (input) input.value = symbol;
    if (typeof window.__VMEWS_RENDER_SYMBOL__ === "function") await window.__VMEWS_RENDER_SYMBOL__(symbol);
    $("#overview")?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
  }

  function bindControls() {
    $("#carouselPrev").addEventListener("click", () => select(state.index - 1, true));
    $("#carouselNext").addEventListener("click", () => select(state.index + 1, true));
    $("#carouselAutoplay").addEventListener("click", event => {
      state.paused = !state.paused;
      event.currentTarget.textContent = state.paused ? "▶" : "❚❚";
      event.currentTarget.setAttribute("aria-label", state.paused ? "Tiếp tục carousel" : "Tạm dừng carousel");
      event.currentTarget.setAttribute("aria-pressed", String(state.paused));
      scheduleRotation();
    });

    $("#leaders").addEventListener("click", event => {
      const analyze = event.target.closest("[data-analyze]");
      if (analyze) { openSymbol(analyze.dataset.analyze).catch(console.error); return; }
      const dot = event.target.closest("[data-dot]");
      if (dot) { select(Number(dot.dataset.dot), true); return; }
      const card = event.target.closest("[data-card]");
      if (card) { select(Number(card.dataset.card), true); return; }
      const filter = event.target.closest("[data-filter]");
      if (!filter) return;
      state.filter = filter.dataset.filter;
      state.index = 0;
      state.rows = finalLeaderboard(state.base, state.session, { filter: state.filter, includeNonPositive: state.defensive });
      document.querySelectorAll("[data-filter]").forEach(button => {
        button.classList.toggle("active", button === filter);
        button.setAttribute("aria-pressed", String(button === filter));
      });
      renderCards();
      scheduleRotation();
    });

    $("#signalDeck").addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      if (event.key === "Home") select(0, true);
      else if (event.key === "End") select(state.rows.length - 1, true);
      else select(state.index + (event.key === "ArrowRight" ? 1 : -1), true);
    });

    let pointerStart = null;
    $("#signalDeck").addEventListener("pointerdown", event => { pointerStart = event.clientX; }, { passive: true });
    $("#signalDeck").addEventListener("pointerup", event => {
      if (pointerStart === null) return;
      const difference = event.clientX - pointerStart;
      pointerStart = null;
      if (Math.abs(difference) > 52) select(state.index + (difference < 0 ? 1 : -1), true);
    }, { passive: true });

    let resizeFrame = 0;
    window.addEventListener("resize", () => {
      window.cancelAnimationFrame(resizeFrame);
      resizeFrame = window.requestAnimationFrame(() => {
        positionCards();
        state.rows.forEach((row, index) => drawSparkline($(`[data-spark="${index}"]`), row.history));
      });
    }, { passive: true });
    window.addEventListener("vmews:community-updated", event => {
      if (!event.detail?.forecastUpdates || !state.base) return;
      const selected = state.rows[state.index]?.symbol;
      state.candidates = finalLeaderboard(state.base, state.session, { all: true, includeNonPositive: true });
      state.universe = finalLeaderboard(state.base, state.session, { all: true });
      state.defensive = state.universe.length === 0;
      state.rows = finalLeaderboard(state.base, state.session, { filter: state.filter, includeNonPositive: state.defensive });
      state.index = Math.max(0, state.rows.findIndex(row => row.symbol === selected));
      refreshMode();
      renderPulse();
      renderCards();
      scheduleRotation();
    });
  }

  async function init() {
    try {
      const load = window.__VMEWS_LOAD_LEADER_BASE__ || window.__VMEWS_LOAD_BASE__;
      state.base = await load();
      if (state.base.gates?.status !== "PASS" || state.base.model?.promotion?.status !== "PASS") throw new Error("Model promotion chưa PASS; bảng xếp hạng bị khóa.");
      state.session = await loadSessionOverlay(state.base);
      window.__VMEWS_SESSION__ = state.session;
      window.dispatchEvent(new CustomEvent("vmews:session-updated", { detail: { session: state.session } }));
      state.candidates = finalLeaderboard(state.base, state.session, { all: true, includeNonPositive: true });
      state.universe = finalLeaderboard(state.base, state.session, { all: true });
      state.defensive = state.universe.length === 0;
      state.rows = finalLeaderboard(state.base, state.session, { filter: state.filter, includeNonPositive: state.defensive });
      $("#snapshotDate").textContent = `${state.base.dash.asOf || "—"}${sessionStamp()}`;
      refreshMode();
      updateClock();
      window.setInterval(() => { if (!document.hidden) updateClock(); }, 1000);
      renderPulse();
      renderCards();
      bindControls();
      scheduleRotation();
    } catch (error) {
      console.error("VMEWS leaderboard:", error);
      $("#signalDeck").innerHTML = `<div class="deckEmpty">${escapeHTML(error?.message || error)}</div>`;
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
