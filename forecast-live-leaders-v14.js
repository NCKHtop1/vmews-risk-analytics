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
    SECTOR: "Luân chuyển ngành", EVENT: "Tin tức / sự kiện", FLOW: "Dòng tiền tổ chức",
  };
  const issuerAliases = {
    VCB: ["vietcombank"], BID: ["bidv"], CTG: ["vietinbank"], TCB: ["techcombank"],
    MBB: ["mb bank", "mbbank", "ngân hàng quân đội"], VPB: ["vpbank"], TPB: ["tpbank"],
    STB: ["sacombank"], HDB: ["hdbank"], VNM: ["vinamilk"], HPG: ["hòa phát", "hoà phát", "hoa phat"],
    VIC: ["vingroup"], VHM: ["vinhomes"], VRE: ["vincom retail"], VJC: ["vietjet"],
    SAB: ["sabeco"], MSN: ["masan"], PLX: ["petrolimex"], GAS: ["pv gas", "pvgas"],
    MWG: ["thế giới di động"], BCM: ["becamex"], NLG: ["nam long"], DIG: ["dic corp", "dic group"],
  };
  const state = { base: null, universe: [], rows: [], index: 0, filter: "all", paused: reducedMotion, timer: 0 };

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

  function buildLeaderboard(base, options = {}) {
    const snapshots = base?.dash?.symbols || {};
    const histories = base?.dash?.charts || {};
    const rows = [];

    for (const [symbol, snapshot] of Object.entries(snapshots)) {
      const forecast = snapshot?.horizons?.["5"] || {};
      const close = number(snapshot.close);
      const target = number(forecast.expectedPrice);
      const tickSize = number(forecast.tickSize);
      if (snapshot.exchange !== "HOSE" || snapshot.dataFreshness !== "CURRENT"
          || forecast.priceValidated !== true || forecast.validationStatus !== "PASS"
          || !close || !target || target <= close || !tickSize || target % tickSize !== 0) continue;

      const sessions = (histories[symbol] || []).slice(-20);
      const volumes = sessions.map(session => number(session.volume)).filter(volume => volume !== null && volume >= 0);
      const avgVolume20 = volumes.length ? volumes.reduce((sum, volume) => sum + volume, 0) / volumes.length : 0;
      const tradedValue20 = avgVolume20 * close;
      const news = snapshot.newsFeatures || {};
      const flow = snapshot.flow || {};
      const row = {
        symbol,
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
        newsCount: number(news.count5) || 0,
        officialNews: number(news.official5) || 0,
        flowFresh: flow.stale !== true && (flow.foreignAvailable || flow.propAvailable),
        flowAge: number(flow.sessionsSinceObservation),
        risk: snapshot.riskStatus || "UNKNOWN",
        sector: snapshot.sector && snapshot.sector !== "UNKNOWN" ? snapshot.sector : "Chưa phân loại ngành",
        volatility: number(snapshot.dailyVolatility),
        targetDate: forecast.targetDate,
      };

      if (options.filter === "liquid" && row.tradedValue20 < 1e9) continue;
      if (options.filter === "green" && row.risk !== "GREEN") continue;
      row.quality = qualityScore(row);
      rows.push(row);
    }

    rows.sort((left, right) => right.upside - left.upside || (right.probUp || 0) - (left.probUp || 0) || left.symbol.localeCompare(right.symbol));
    return options.all ? rows : rows.slice(0, 10);
  }

  window.__VMEWS_BUILD_LEADERBOARD__ = buildLeaderboard;

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
    const advancing = symbols.filter(snapshot => number(snapshot.lastSessionReturn) > 0).length;
    const falling = symbols.filter(snapshot => number(snapshot.lastSessionReturn) < 0).length;
    const positive = state.universe.length;
    const top = state.universe[0];
    const cards = [
      { label: "HOSE đủ dữ liệu", value: symbols.length, format: value => `${Math.round(value)}`, detail: "snapshot CURRENT đã kiểm định", tone: "" },
      { label: "T+5 nghiêng tăng", value: positive, format: value => `${Math.round(value)}`, detail: `${symbols.length - positive} mã còn lại / không tăng`, tone: "up" },
      { label: "Phiên gần nhất", value: advancing, format: value => `${Math.round(value)} ↑`, detail: `${falling} giảm · ${symbols.length - advancing - falling} đi ngang`, tone: "" },
      { label: "Upside cao nhất", value: (top?.upside || 0) * 100, format: value => `+${value.toFixed(2)}%`, detail: top ? `${top.symbol} · ${money(top.target)} đ T+5` : "Chưa có forecast hợp lệ", tone: "up" },
    ];

    $("#marketPulse").innerHTML = cards.map((card, index) => `<article class="pulseCard"><span>${escapeHTML(card.label)}</span><strong class="${card.tone}" data-pulse="${index}">—</strong><small>${escapeHTML(card.detail)}</small><i class="pulseTrace" aria-hidden="true"></i></article>`).join("");
    cards.forEach((card, index) => animateValue($(`[data-pulse="${index}"]`), card.value, card.format));
  }

  function riskLabel(row) {
    return row.risk === "GREEN" ? "GREEN" : row.risk === "RED" ? "RED · RỦI RO" : `${row.risk} · THEO DÕI`;
  }

  function riskClass(row) {
    return row.risk === "GREEN" ? "riskGreen" : row.risk === "RED" ? "riskRed" : "riskWatch";
  }

  function issuerNewsMatches(row, item) {
    const title = String(item?.title || "");
    const lower = title.toLocaleLowerCase("vi-VN");
    if (row.symbol === "GTA" && /\bgta\s*(?:\d+|[ivx]{1,4})\b|\bgameplay\b|\brockstar\b|\btake[\s-]?two\b|\bplaystation\b|\bxbox\b/i.test(title)) return false;
    if (row.symbol === "VSI" && /smart\s+indexing|\bvps\b.{0,55}\bvsi\b|\bvsi\b.{0,55}\bvps\b/i.test(title)) return false;
    if (row.symbol === "ASP" && /\basp\s+shipping\b/i.test(title) && !/dầu\s+khí\s+an\s+pha/i.test(title)) return false;
    if (row.symbol === "FPT" && /\bfpt\s+(retail|long\s+châu|online)\b|chứng\s+khoán\s+fpt/i.test(title)) return false;
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
      deck.innerHTML = '<div class="deckEmpty">Không có forecast tăng đáp ứng bộ lọc đang chọn.</div>';
      $("#leaderDots").replaceChildren();
      $("#leaderDetail").innerHTML = '<div class="deckEmpty">Hãy đổi bộ lọc để tiếp tục kiểm tra tín hiệu.</div>';
      $("#carouselPosition").textContent = "00 / 00";
      return;
    }

    deck.innerHTML = state.rows.map((row, index) => {
      const illiquid = row.tradedValue20 < 1e9;
      const probability = row.directionValidated ? percent(row.probUp, 1) : "REVIEW";
      return `<article class="signalCard ${riskClass(row)}" data-card="${index}" data-symbol="${escapeHTML(row.symbol)}" aria-label="${escapeHTML(row.symbol)}, dự báo tăng ${percent(row.upside, 2)} trong 5 phiên" tabindex="-1"><div class="signalCardTop"><span class="signalRank">#${String(index + 1).padStart(2, "0")} / HOSE</span><span class="signalRisk ${riskClass(row)}">${escapeHTML(riskLabel(row))}</span></div><div class="signalIdentity"><div><h3>${escapeHTML(row.symbol)}</h3><span>${escapeHTML(row.sector)}</span></div><span class="qualityOrbit" style="--quality:${row.quality}%"><b>${row.quality}</b><small>quality</small></span></div><div class="signalReturn"><strong>+${percent(row.upside, 2)}</strong><span>UPSIDE DỰ BÁO · T+5</span></div><canvas class="leaderSpark" data-spark="${index}" aria-label="Biểu đồ giá EOD thực tế của ${escapeHTML(row.symbol)}"></canvas><div class="signalPrices"><span>${money(row.close)} <i>→</i> <b>${money(row.target)}</b></span><span>${shortDate(row.targetDate)}</span></div><div class="signalFacts"><span>P↑ ${probability}</span><span>${row.newsCount} tin / 5P</span><span class="${illiquid ? "factWarning" : ""}">${valueLabel(row.tradedValue20)} / phiên</span></div>${illiquid ? '<div class="liquidityWarning">⚠ Thanh khoản bình quân 20 phiên thấp</div>' : ""}<button class="cardAction" type="button" data-analyze="${escapeHTML(row.symbol)}">Phân tích ${escapeHTML(row.symbol)} <span>↗</span></button></article>`;
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
    window.__VMEWS_LEADERBOARD__ = { filter: state.filter, selected: state.rows[state.index].symbol, rows: state.rows.map(row => ({ symbol: row.symbol, upside: row.upside, quality: row.quality, tradedValue20: row.tradedValue20, risk: row.risk })) };
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
    const entries = Object.entries(row.forecast.expertContributions || {}).sort((left, right) => Math.abs(number(right[1]) || 0) - Math.abs(number(left[1]) || 0));
    const maximum = Math.max(...entries.map(([, value]) => Math.abs(number(value) || 0)), .00001);
    if (!entries.length) return '<div class="detailEmpty">Không có contribution đủ điều kiện.</div>';
    return entries.map(([name, value]) => `<div class="factorRow"><span>${escapeHTML(expertNames[name] || name)}</span><div class="factorTrack"><i class="${number(value) < 0 ? "factorDown" : "factorUp"}" style="width:${Math.abs(number(value) || 0) / maximum * 100}%"></i></div><strong class="${number(value) < 0 ? "factorNegative" : "factorPositive"}">${signed(value, 2)}</strong></div>`).join("");
  }

  function newsMarkup(row) {
    const recent = (row.snapshot.evidence?.recent || []).filter(item => issuerNewsMatches(row, item) && belongsToLastFiveSessions(row, item)).slice(0, 2);
    if (!recent.length) return '<p class="detailEmpty">Không có bài trong 5 phiên gần nhất vừa đạt point-in-time vừa xác minh đúng mã/doanh nghiệp.</p>';
    return recent.map(item => `<article class="detailNewsItem"><span>${escapeHTML(item.publisher || item.source || "Nguồn đã đối chiếu")} · ${escapeHTML(shortDate(item.availableDate || item.publishedAt || item.date))}</span><strong>${escapeHTML(item.title || "Sự kiện chưa có tiêu đề")}</strong></article>`).join("");
  }

  function corridorMarkup(row) {
    if (!row.q20 || !row.q80 || row.q80 <= row.q20) return '<div class="detailEmpty">Khoảng dự báo chưa đủ dữ liệu.</div>';
    const span = row.q80 - row.q20;
    const current = clamp((row.close - row.q20) / span * 100, 0, 100);
    const target = clamp((row.target - row.q20) / span * 100, 0, 100);
    return `<div class="corridorNumbers"><span>Q20 <b>${money(row.q20)}</b></span><span>Q80 <b>${money(row.q80)}</b></span></div><div class="priceCorridor"><i class="corridorCurrent" style="left:${current}%" title="Giá hiện tại ${money(row.close)}"></i><i class="corridorTarget" style="left:${target}%" title="Dự báo ${money(row.target)}"></i></div><div class="corridorLegend"><span><i></i>Hiện tại</span><span><i></i>Mục tiêu T+5</span></div>`;
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
    if (!row.directionValidated) warnings.push("Xác suất hướng chưa PASS");
    else if (row.probUp < .5) warnings.push("P(tăng) dưới 50%");
    if (!row.flowFresh) warnings.push("Dòng tiền tổ chức chưa mới");
    if (!row.newsCount) warnings.push("Không có tin trong 5 phiên");
    else if (!(row.snapshot.evidence?.recent || []).some(item => issuerNewsMatches(row, item) && belongsToLastFiveSessions(row, item))) warnings.push("Chưa có headline gần đây khớp đúng doanh nghiệp");

    $("#leaderDetail").innerHTML = `<div class="detailTopline"><div><span class="detailIndex">SIGNAL BREAKDOWN / ${escapeHTML(row.symbol)}</span><h3>${escapeHTML(row.symbol)} <span>· cơ sở dự báo</span></h3></div><button class="detailAnalyze" type="button" data-analyze="${escapeHTML(row.symbol)}">Mở phân tích đầy đủ ↗</button></div><div class="detailLayout"><div class="detailColumn"><div class="detailLabel">ĐÓNG GÓP THỰC TỪ MÔ HÌNH · T+5</div><div class="factorList">${contributionsMarkup(row)}</div><div class="corridorBlock"><div class="detailLabel">VÙNG KỊCH BẢN Q20 — Q80</div>${corridorMarkup(row)}</div></div><div class="detailColumn"><div class="evidenceTiles"><article><span>P(tăng) T+5</span><b>${row.directionValidated ? percent(row.probUp, 1) : "REVIEW"}</b><small>${row.directionValidated ? "direction validation PASS" : "không hiển thị xác suất chưa validate"}</small></article><article><span>Rủi ro về Q20</span><b class="${downside < 0 ? "factorNegative" : "factorPositive"}">${signed(downside, 1)}</b><small>kịch bản thấp so với EOD</small></article><article><span>GTGD 20 phiên</span><b>${valueLabel(row.tradedValue20)}</b><small>${money(Math.round(row.avgVolume20))} cổ phiếu/phiên</small></article><article><span>Biến động ngày</span><b>${percent(row.volatility, 1)}</b><small>${escapeHTML(flowStatus)} · foreign ${flow.foreignAvailable ? "có" : "thiếu"}</small></article></div><div class="evidenceNews"><div class="detailLabel">TIN ĐÃ KIỂM TRA POINT-IN-TIME · ${row.newsCount} / 5 PHIÊN</div>${newsMarkup(row)}</div></div></div>${warnings.length ? `<div class="signalWarnings"><span>ĐIỂM CẦN LƯU Ý</span>${warnings.map(warning => `<i>${escapeHTML(warning)}</i>`).join("")}</div>` : '<div class="signalWarnings clear"><span>KIỂM TRA CHẤT LƯỢNG</span><i>Thanh khoản, rủi ro và xác suất đã được hiển thị minh bạch.</i></div>'}<div class="qualityFootnote">Điểm ${row.quality}/100 là thước đo tổng hợp về xác suất đã kiểm định, thanh khoản 20 phiên, độ rộng Q20–Q80, tin tức, rủi ro và độ mới dòng tiền; không phải xác suất sinh lời.</div>`;
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
    }, 4600);
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
      state.rows = buildLeaderboard(state.base, { filter: state.filter });
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
  }

  async function init() {
    try {
      state.base = await window.__VMEWS_LOAD_BASE__();
      if (state.base.gates?.status !== "PASS" || state.base.model?.promotion?.status !== "PASS") throw new Error("Model promotion chưa PASS; bảng xếp hạng bị khóa.");
      state.universe = buildLeaderboard(state.base, { all: true });
      state.rows = state.universe.slice(0, 10);
      $("#snapshotDate").textContent = `AS-OF ${state.base.dash.asOf || "—"}`;
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
