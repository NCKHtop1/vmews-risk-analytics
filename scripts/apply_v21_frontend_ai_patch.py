from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path, old, new, label):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def insert_before_once(path, marker, content, label):
    text = path.read_text(encoding="utf-8")
    count = text.count(marker)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one marker, found {count}")
    path.write_text(text.replace(marker, content + marker, 1), encoding="utf-8")


leaders = ROOT / "forecast-live-leaders-v14.js"
solution = ROOT / "solution-ai-v17.js"
html = ROOT / "forecast-final.html"
api = ROOT / "api" / "solution-ai.js"

# 1) Full-HOSE leaderboard by default. VN30 membership remains available as an explicit scope.
replace_once(
    leaders,
    'if (!members.has(symbol) || snapshot.exchange !== "HOSE" || snapshot.dataFreshness !== "CURRENT"',
    'if ((options.scope === "vn30" && !members.has(symbol)) || snapshot.exchange !== "HOSE" || snapshot.dataFreshness !== "CURRENT"',
    "leaderboard scope",
)
replace_once(leaders, '"VN30 · TRẠNG THÁI PHÒNG THỦ" : "VN30 · 5 PHIÊN TỚI"', '"HOSE · TRẠNG THÁI PHÒNG THỦ" : "HOSE · 5 PHIÊN TỚI"', "leaderboard heading")
replace_once(leaders, '"Chưa có mã VN30 dự báo tăng; đang hiển thị nhóm giảm ít nhất để theo dõi rủi ro."', '"Chưa có mã HOSE đủ điều kiện có mục tiêu T+5 cao hơn giá tham chiếu; đang hiển thị nhóm giảm ít nhất để theo dõi rủi ro."', "defensive summary")
replace_once(leaders, '"Những cổ phiếu VN30 có triển vọng tăng nổi bật."', '"Top 10 toàn HOSE theo forecast T+5 đã kiểm định, chất lượng tín hiệu và dữ liệu phiên mới nhất."', "positive summary")
replace_once(leaders, 'defensive ? "VN30 phòng thủ" : "VN30 tăng giá"', 'defensive ? "HOSE phòng thủ" : "HOSE forecast tăng"', "filter label")
replace_once(leaders, '"Các cổ phiếu VN30 có mức giảm dự báo T+5 thấp nhất"', '"Các cổ phiếu HOSE có mức giảm dự báo T+5 thấp nhất"', "defensive aria")
replace_once(leaders, '"Các cổ phiếu VN30 có mức tăng dự báo T+5 cao nhất"', '"Các cổ phiếu HOSE có mức tăng dự báo T+5 cao nhất"', "positive aria")
replace_once(leaders, 'const members = state.base?.dash?.lists?.vn30?.symbols || currentVN30;\n    const covered = members.filter(symbol => symbols.some(snapshot => snapshot.symbol === symbol)).length;', 'const covered = state.candidates.length;', "pulse coverage")
replace_once(leaders, '{ label: "VN30 dự báo tăng", value: positive, format: value => `${Math.round(value)} / ${covered}`, detail: `${Math.max(covered - positive, 0)} mã chưa có tín hiệu tăng`, tone: "up" },', '{ label: "HOSE forecast tăng", value: positive, format: value => `${Math.round(value)} / ${covered}`, detail: `${Math.max(covered - positive, 0)} mã chưa có tín hiệu tăng`, tone: "up" },', "pulse label")
replace_once(leaders, "Chưa có cổ phiếu VN30 hợp lệ phù hợp bộ lọc.", "Chưa có cổ phiếu HOSE hợp lệ phù hợp bộ lọc.", "empty state")
replace_once(leaders, 'state.defensive ? "GIẢM ÍT NHẤT TRONG VN30" : "TRIỂN VỌNG 5 PHIÊN"', 'state.defensive ? "GIẢM ÍT NHẤT TRÊN HOSE" : "TRIỂN VỌNG 5 PHIÊN"', "card defensive label")
replace_once(leaders, '/ VN30</span>', '/ HOSE</span>', "card rank scope")
replace_once(leaders, '}, 4600);', '}, 3000);', "three-second rotation")

# 2) Session overlay: use same-ref data when available, but never mix a session file from another sealed core snapshot.
session_helpers = r'''
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
      return payload;
    } catch {
      return null;
    }
  }

  function applySessionOverlay(rows) {
    const session = state.session;
    if (!session?.symbols?.length) return rows;
    const live = new Map(session.symbols.filter(item => item.quoteCurrent).map(item => [item.symbol, item]));
    return rows.map(row => {
      const quote = live.get(row.symbol);
      if (!quote || number(quote.liveClose) === null || number(quote.liveClose) <= 0) return row;
      const next = { ...row, coreClose: row.close, close: number(quote.liveClose), sessionChange: number(quote.change), sessionAt: quote.updateAt };
      next.upside = next.target / next.close - 1;
      next.tradedValue20 = next.avgVolume20 * next.close;
      next.quality = qualityScore(next);
      return next;
    }).sort((left, right) => right.upside - left.upside || right.quality - left.quality || left.symbol.localeCompare(right.symbol));
  }

  function sessionStamp() {
    if (!state.session?.cutoffAt) return "";
    const date = new Date(state.session.cutoffAt);
    if (Number.isNaN(+date)) return "";
    const time = new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Ho_Chi_Minh" }).format(date);
    return ` · ${state.session.session} ${time}`;
  }

'''
insert_before_once(leaders, "  function refreshMode() {", session_helpers, "session helpers")
replace_once(
    leaders,
    'const state = { base: null, universe: [], candidates: [], rows: [], defensive: false, index: 0, filter: "all", paused: reducedMotion, timer: 0 };',
    'const state = { base: null, session: null, universe: [], candidates: [], rows: [], defensive: false, index: 0, filter: "all", paused: reducedMotion, timer: 0 };',
    "session state",
)
replace_once(
    leaders,
    'state.base = await load();\n      if (state.base.gates?.status !== "PASS" || state.base.model?.promotion?.status !== "PASS") throw new Error("Model promotion chưa PASS; bảng xếp hạng bị khóa.");\n      state.universe = buildLeaderboard(state.base, { all: true });\n      state.candidates = buildLeaderboard(state.base, { all: true, includeNonPositive: true });',
    'state.base = await load();\n      if (state.base.gates?.status !== "PASS" || state.base.model?.promotion?.status !== "PASS") throw new Error("Model promotion chưa PASS; bảng xếp hạng bị khóa.");\n      state.session = await loadSessionOverlay(state.base);\n      state.universe = applySessionOverlay(buildLeaderboard(state.base, { all: true }));\n      state.candidates = applySessionOverlay(buildLeaderboard(state.base, { all: true, includeNonPositive: true }));',
    "session init",
)
replace_once(leaders, '$("#snapshotDate").textContent = state.base.dash.asOf || "—";', '$("#snapshotDate").textContent = `${state.base.dash.asOf || "—"}${sessionStamp()}`;', "session timestamp")
replace_once(
    leaders,
    'state.rows = buildLeaderboard(state.base, { filter: state.filter, includeNonPositive: state.defensive });',
    'state.rows = applySessionOverlay(buildLeaderboard(state.base, { filter: state.filter, includeNonPositive: state.defensive }));',
    "filtered session overlay first occurrence",
)
# The same expression occurs in the community refresh path after the first replacement; patch it too.
replace_once(
    leaders,
    'state.universe = buildLeaderboard(state.base, { all: true });\n      state.candidates = buildLeaderboard(state.base, { all: true, includeNonPositive: true });',
    'state.universe = applySessionOverlay(buildLeaderboard(state.base, { all: true }));\n      state.candidates = applySessionOverlay(buildLeaderboard(state.base, { all: true, includeNonPositive: true }));',
    "community session overlay",
)
replace_once(
    leaders,
    'state.rows = buildLeaderboard(state.base, { filter: state.filter, includeNonPositive: state.defensive });',
    'state.rows = applySessionOverlay(buildLeaderboard(state.base, { filter: state.filter, includeNonPositive: state.defensive }));',
    "filtered session overlay second occurrence",
)

# 3) AI answer policy: direct thesis -> evidence -> confirmation/invalidation; no generic boilerplate disclaimer.
replace_once(
    solution,
    '"Luôn trả lời bằng tiếng Việt, đi thẳng vào đúng câu hỏi, có lập luận và đủ chiều sâu; không sử dụng một khuôn trả lời cố định.",',
    '"Luôn trả lời bằng tiếng Việt, đi thẳng vào đúng câu hỏi, có lập luận và đủ chiều sâu; không sử dụng một khuôn trả lời cố định.",\n      "Không mở đầu hoặc kết thúc bằng disclaimer chung kiểu lời khuyên/khuyến nghị. Chỉ nêu một giới hạn dữ liệu khi giới hạn đó trực tiếp làm thay đổi kết luận.",\n      "Với forecast, ưu tiên cấu trúc tư duy: kết luận hiện tại → bằng chứng mạnh nhất → bằng chứng mâu thuẫn → điều kiện xác nhận → điều kiện vô hiệu; tránh nhắc lại cùng một cảnh báo dưới nhiều cách diễn đạt.",',
    "frontend AI policy",
)
replace_once(
    solution,
    '4) nêu rủi ro, điều cần theo dõi và độ trễ dữ liệu; 5) không đưa khuyến nghị mua/bán.',
    '4) nêu rủi ro và độ trễ chỉ khi có tác động thực; 5) kết thúc bằng điều kiện xác nhận và điều kiện vô hiệu của luận điểm, không chèn disclaimer chung.',
    "frontend answer contract",
)
replace_once(
    solution,
    'Forecast là phân bố bất định, không phải cam kết giá hoặc khuyến nghị mua/bán.',
    'Đọc vùng bất định cùng điều kiện xác nhận/vô hiệu; nếu dữ liệu còn thiếu, nêu đúng phần thiếu và tác động của nó lên kết luận.',
    "local fallback disclaimer",
)
replace_once(
    solution,
    '"Danh sách nổi bật chỉ gồm thành viên VN30 hiện hành có dự báo T+5 tăng.",',
    '"Bảng nổi bật mặc định xếp hạng toàn bộ HOSE đủ điều kiện kiểm định; khi người dùng yêu cầu VN30 thì mới giới hạn vào rổ VN30 hiện hành.",',
    "AI market scope",
)

# Server-side provider path follows the same response policy.
replace_once(
    api,
    '"Luôn trả lời bằng tiếng Việt, rõ ràng, chuyên nghiệp, ngắn gọn nhưng đủ cơ sở.",',
    '"Luôn trả lời bằng tiếng Việt, rõ ràng, chuyên nghiệp, ngắn gọn nhưng đủ cơ sở.",\n    "Không chèn disclaimer chung về lời khuyên/khuyến nghị. Chỉ nói giới hạn dữ liệu khi nó trực tiếp ảnh hưởng kết luận; ưu tiên kết luận, bằng chứng, mâu thuẫn, điều kiện xác nhận và điều kiện vô hiệu.",',
    "backend AI policy",
)
replace_once(
    api,
    '"Bảng cổ phiếu nổi bật chỉ gồm thành viên VN30 hiện hành có dự báo T+5 tăng; không đưa mã ngoài rổ vào bảng này.",',
    '"Bảng nổi bật mặc định có thể xếp hạng toàn HOSE đủ điều kiện kiểm định; chỉ giới hạn VN30 khi câu hỏi hoặc ngữ cảnh yêu cầu rõ VN30.",',
    "backend market scope",
)

# 4) Make normal Gemini Web a first-class fallback. The dashboard copies an analysis prompt then opens Gemini.
replace_once(
    html,
    '<div class="aiConnectActions"><button id="solutionAiRetry" class="aiConnectPrimary" type="button">Kết nối Gemini</button><a id="solutionAiGoogle" href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener noreferrer">Lấy khóa ↗</a><button id="solutionAiDisconnect" type="button" hidden>Ngắt kết nối</button></div>',
    '<div class="aiConnectActions"><button id="solutionAiGeminiWeb" class="aiConnectPrimary" type="button">Mở Gemini Web ↗</button><button id="solutionAiRetry" type="button">Kết nối bằng API key</button><a id="solutionAiGoogle" href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener noreferrer">Quản lý key ↗</a><button id="solutionAiDisconnect" type="button" hidden>Ngắt kết nối</button></div>',
    "Gemini Web button",
)
replace_once(
    html,
    '<small id="solutionAiConnectionState">Khóa chỉ lưu tạm trong tab này; không ghi lên GitHub.</small>',
    '<small id="solutionAiConnectionState">Ưu tiên Gemini Web nếu chỉ cần chat như bình thường; API key là chế độ nâng cao và chỉ lưu tạm trong tab.</small>',
    "Gemini connection copy",
)

web_helpers = r'''
  function externalGeminiPrompt() {
    const context = state.context || {};
    const compact = {
      symbol: context.symbol,
      asOf: context.asOf,
      close: context.close,
      horizons: context.horizons,
      factors: context.factors,
      riskStatus: context.riskStatus,
      dataFreshness: context.dataFreshness,
      validation: context.validation,
    };
    return [
      "Hãy đóng vai nhà phân tích phản biện. Trả lời bằng tiếng Việt, không dùng disclaimer chung.",
      "Đọc dữ liệu VMEWS dưới đây như snapshot đã niêm phong; không tự sửa số forecast.",
      "Hãy kết luận theo 5 phần: luận điểm hiện tại; đường T+1→T+5; bằng chứng ủng hộ; bằng chứng mâu thuẫn; điều kiện xác nhận và điều kiện vô hiệu.",
      JSON.stringify(compact),
    ].join("\n");
  }

  function openGeminiWeb() {
    const popup = window.open("https://gemini.google.com/app", "_blank", "noopener,noreferrer");
    const text = externalGeminiPrompt();
    const label = $("#solutionAiConnectionState");
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        if (label) label.textContent = "Đã sao chép ngữ cảnh forecast. Dán vào Gemini Web vừa mở để tiếp tục chat.";
      }).catch(() => {
        if (label) label.textContent = "Gemini Web đã mở. Có thể sao chép dữ liệu forecast đang xem và dán vào cuộc chat.";
      });
    } else if (label) label.textContent = "Gemini Web đã mở. Có thể sao chép dữ liệu forecast đang xem và dán vào cuộc chat.";
    return Boolean(popup);
  }

'''
insert_before_once(solution, "  function disconnectGemini() {", web_helpers, "Gemini web helpers")
replace_once(
    solution,
    '$("#solutionAiRetry")?.addEventListener("click", () => connectGemini());',
    '$("#solutionAiGeminiWeb")?.addEventListener("click", openGeminiWeb);\n    $("#solutionAiRetry")?.addEventListener("click", () => connectGemini());',
    "Gemini web binding",
)

print("V21 frontend/AI patch applied successfully")
