from pathlib import Path
import re
import textwrap

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def write(path, text):
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path, old, new):
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise AssertionError(f"{path}: expected 1 exact match, got {count}: {old[:100]!r}")
    write(path, text.replace(old, new, 1))


def regex_once(path, pattern, replacement, flags=re.S):
    text = read(path)
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise AssertionError(f"{path}: expected 1 regex match, got {count}: {pattern[:100]!r}")
    write(path, updated)


# ---------------------------------------------------------------------------
# Delivery: immutable CDN assets read live data from main.
# ---------------------------------------------------------------------------
replace_once(
    "forecast-final-v12.js",
    'const CDN_PATH=location.pathname.split("/").filter(Boolean),CDN_REF=location.hostname==="cdn.githubraw.com"&&CDN_PATH.length>=4?CDN_PATH[2]:"",ROOT=CDN_REF?`https://raw.githubusercontent.com/${encodeURIComponent(CDN_PATH[0])}/${encodeURIComponent(CDN_PATH[1])}/${encodeURIComponent(CDN_REF)}/data`:"./data",CDN_REVISION=Math.floor(Date.now()/300000);',
    'const CDN_PATH=location.pathname.split("/").filter(Boolean),CDN_REF=location.hostname==="cdn.githubraw.com"&&CDN_PATH.length>=4?CDN_PATH[2]:"";\nconst DATA_QUERY=new URLSearchParams(location.search||""),safeDataRef=value=>{const ref=String(value||"").trim();return ref&&/^[A-Za-z0-9._/-]{1,120}$/.test(ref)&&!ref.includes("..")?ref:""},encodeRef=ref=>String(ref).split("/").map(encodeURIComponent).join("/");\nconst DATA_REF=CDN_REF?(safeDataRef(DATA_QUERY.get("dataRef"))||"main"):"LOCAL_DEPLOYMENT",ROOT=CDN_REF?`https://raw.githubusercontent.com/${encodeURIComponent(CDN_PATH[0])}/${encodeURIComponent(CDN_PATH[1])}/${encodeRef(DATA_REF)}/data`:"./data",CDN_REVISION=Math.floor(Date.now()/60000);',
)
replace_once(
    "forecast-final-v12.js",
    'window.__VMEWS_DATA_ROOT__=ROOT;\nwindow.__VMEWS_ASSET_REF__=CDN_REF||"LOCAL_DEPLOYMENT";',
    'window.__VMEWS_DATA_ROOT__=ROOT;\nwindow.__VMEWS_DATA_REF__=DATA_REF;\nwindow.__VMEWS_ASSET_REF__=CDN_REF||"LOCAL_DEPLOYMENT";',
)

bootstrap = """<script>
(()=>{
  const parts=location.pathname.split("/").filter(Boolean);
  if(location.hostname!=="cdn.githubraw.com"||parts.length<4||parts[2]!=="main") return;
  const owner=parts[0],repo=parts[1],file=parts.slice(3).join("/")||"forecast-final.html";
  const revision=Math.floor(Date.now()/60000);
  fetch(`https://raw.githubusercontent.com/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/main/data/release-pointer-v22.json?refresh=${revision}`,{cache:"no-store"})
    .then(response=>response.ok?response.json():null)
    .then(pointer=>{
      const ref=String(pointer?.assetRef||"").trim();
      if(!/^[0-9a-f]{40}$/i.test(ref)) return;
      const target=`https://cdn.githubraw.com/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/${ref}/${file}${location.search}${location.hash}`;
      if(target!==location.href) location.replace(target);
    })
    .catch(()=>{});
})();
</script>"""
replace_once(
    "forecast-final.html",
    '<meta name="description" content="Dự báo cổ phiếu HOSE T+1 đến T+5 với trọng tâm giá, vùng dự báo và dữ liệu kiểm định.">',
    '<meta name="description" content="Dự báo cổ phiếu HOSE T+1 đến T+5 với trọng tâm giá, vùng dự báo và dữ liệu kiểm định.">\n' + bootstrap,
)
replace_once("forecast-final.html", "KHÓA GOOGLE AI STUDIO", "GEMINI AUTH KEY · NÂNG CAO")
replace_once(
    "forecast-final.html",
    "Ưu tiên Gemini Web nếu chỉ cần chat như bình thường; API key là chế độ nâng cao và chỉ lưu tạm trong tab.",
    "Ưu tiên Gemini Web hoặc máy chủ AI. Auth key trên trình duyệt chỉ là chế độ nâng cao và chỉ lưu tạm trong tab.",
)

pointer_workflow = """name: V22 immutable asset release pointer

on:
  push:
    branches: [main]
    paths:
      - "forecast-final.html"
      - "forecast-final-v12.js"
      - "forecast-live-leaders-v14.js"
      - "forecast-polish-v12.js"
      - "forecast-portfolio-v14.css"
      - "forecast-portfolio-v14.js"
      - "solution-ai-v17.js"
      - "api/solution-ai.js"

permissions:
  contents: write

concurrency:
  group: forecast-release-pointer
  cancel-in-progress: false

jobs:
  publish-pointer:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Point stable main URL to the exact immutable asset commit
        env:
          ASSET_REF: ${{ github.sha }}
        run: |
          python - <<'PY'
          import json, os
          from datetime import datetime, timezone
          from pathlib import Path
          payload={
            "version":"VMEWS-RELEASE-POINTER-22.0",
            "assetRef":os.environ["ASSET_REF"],
            "generatedAt":datetime.now(timezone.utc).isoformat(),
            "dataRef":"main",
            "policy":"IMMUTABLE_ASSETS_LIVE_MAIN_DATA"
          }
          Path("data/release-pointer-v22.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")
          PY
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/release-pointer-v22.json
          if git diff --cached --quiet; then exit 0; fi
          git commit -m "Publish V22 immutable asset pointer [data-only]"
          git pull --rebase origin main
          git push origin HEAD:main
"""
write(".github/workflows/release-pointer-v22.yml", pointer_workflow)


# ---------------------------------------------------------------------------
# Session data: require broad coverage and quotes fresh enough for cutoff.
# ---------------------------------------------------------------------------
replace_once(
    "scripts/forecast_v21_session_snapshot.py",
    "MIN_COVERAGE = 0.70\nMIN_CURRENT_COVERAGE = 0.65",
    "MIN_COVERAGE = 0.90\nMIN_CURRENT_COVERAGE = 0.90\nMIN_CUTOFF_FRESH_COVERAGE = 0.90",
)
replace_once(
    "scripts/forecast_v21_session_snapshot.py",
    '''def session_name(now):
    minutes = now.hour * 60 + now.minute
    if minutes < 12 * 60 + 45:
        return "AM"
    if minutes < 17 * 60 + 30:
        return "PM"
    return "POST_CLOSE"
''',
    '''def session_name(now):
    minutes = now.hour * 60 + now.minute
    if minutes < 12 * 60 + 45:
        return "AM"
    if minutes < 17 * 60 + 30:
        return "PM"
    return "POST_CLOSE"


def cutoff_floor(now):
    session = session_name(now)
    hour, minute = (11, 15) if session == "AM" else (14, 30)
    floor = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if floor > now:
        return now - timedelta(minutes=20)
    return floor
''',
)
replace_once(
    "scripts/forecast_v21_session_snapshot.py",
    "    now = now or datetime.now(VN_TZ)\n    core = eligible_core_symbols(dashboard)",
    "    now = now or datetime.now(VN_TZ)\n    fresh_floor = cutoff_floor(now)\n    core = eligible_core_symbols(dashboard)",
)
replace_once(
    "scripts/forecast_v21_session_snapshot.py",
    "    current_quotes = 0\n    dated = []\n    symbols = []",
    "    current_quotes = 0\n    cutoff_fresh_quotes = 0\n    dated = []\n    update_modes = []\n    quote_ages = []\n    symbols = []",
)
replace_once(
    "scripts/forecast_v21_session_snapshot.py",
    '''        is_current = quote_date == now.date().isoformat()
        current_quotes += int(is_current)
        change_pct = (num(row.get("change"), 0.0) or 0.0) / 100.0''',
    '''        is_current = quote_date == now.date().isoformat()
        fresh_for_cutoff = bool(updated_at and fresh_floor <= updated_at <= now + timedelta(minutes=5))
        current_quotes += int(is_current)
        cutoff_fresh_quotes += int(fresh_for_cutoff)
        update_mode = str(row.get("update_mode") or "UNKNOWN")
        update_modes.append(update_mode)
        quote_age = max(0.0, (now - updated_at).total_seconds() / 60.0) if updated_at else None
        if quote_age is not None:
            quote_ages.append(quote_age)
        change_pct = (num(row.get("change"), 0.0) or 0.0) / 100.0''',
)
replace_once(
    "scripts/forecast_v21_session_snapshot.py",
    '            "updateAt": updated_at.isoformat() if updated_at else None,\n            "quoteCurrent": is_current,',
    '            "updateAt": updated_at.isoformat() if updated_at else None,\n            "quoteCurrent": is_current,\n            "freshForCutoff": fresh_for_cutoff,\n            "updateMode": update_mode,\n            "quoteAgeMinutes": round(quote_age, 2) if quote_age is not None else None,',
)
replace_once(
    "scripts/forecast_v21_session_snapshot.py",
    '''    current_coverage = current_quotes / eligible_count if eligible_count else 0.0
    dominant_quote_date = Counter(dated).most_common(1)[0][0] if dated else None
    status = "PASS" if coverage >= MIN_COVERAGE and current_coverage >= MIN_CURRENT_COVERAGE else "DEGRADED"''',
    '''    current_coverage = current_quotes / eligible_count if eligible_count else 0.0
    cutoff_fresh_coverage = cutoff_fresh_quotes / eligible_count if eligible_count else 0.0
    dominant_quote_date = Counter(dated).most_common(1)[0][0] if dated else None
    mode_counts = dict(Counter(update_modes))
    dominant_mode = Counter(update_modes).most_common(1)[0][0] if update_modes else None
    status = "PASS" if (
        coverage >= MIN_COVERAGE
        and current_coverage >= MIN_CURRENT_COVERAGE
        and cutoff_fresh_coverage >= MIN_CUTOFF_FRESH_COVERAGE
    ) else "DEGRADED"''',
)
replace_once(
    "scripts/forecast_v21_session_snapshot.py",
    '''            "currentCoverageRatio": round(current_coverage, 6),
            "dominantQuoteDate": dominant_quote_date,
            "duplicatesIgnored": duplicates,''',
    '''            "currentCoverageRatio": round(current_coverage, 6),
            "cutoffFresh": cutoff_fresh_quotes,
            "cutoffFreshCoverageRatio": round(cutoff_fresh_coverage, 6),
            "freshnessFloor": fresh_floor.isoformat(),
            "dominantQuoteDate": dominant_quote_date,
            "dominantUpdateMode": dominant_mode,
            "updateModeCounts": mode_counts,
            "medianQuoteAgeMinutes": round(sorted(quote_ages)[len(quote_ages)//2], 2) if quote_ages else None,
            "maxQuoteAgeMinutes": round(max(quote_ages), 2) if quote_ages else None,
            "duplicatesIgnored": duplicates,''',
)
replace_once(
    "scripts/forecast_v21_session_snapshot.py",
    '            "A session snapshot is publishable only when quote coverage and same-day quote coverage pass explicit gates; otherwise the prior last-known-good file is retained.",',
    '            "A session snapshot is publishable only when universe coverage, same-day coverage and cutoff freshness all pass strict gates; otherwise the prior last-known-good file is retained.",',
)

# Workflow writers share one lock; EOD rebases before publish.
replace_once(
    ".github/workflows/forecast-v21-session-refresh.yml",
    "concurrency:\n  group: forecast-v21-session-overlay\n  cancel-in-progress: true",
    "concurrency:\n  group: forecast-data-publisher\n  cancel-in-progress: false",
)
replace_once(
    ".github/workflows/forecast-v21-session-refresh.yml",
    "          assert c['coverageRatio']>=0.70,c\n          assert c['currentCoverageRatio']>=0.65,c",
    "          assert c['coverageRatio']>=0.90,c\n          assert c['currentCoverageRatio']>=0.90,c\n          assert c['cutoffFreshCoverageRatio']>=0.90,c",
)
replace_once(
    ".github/workflows/forecast-v13-daily-refresh.yml",
    "concurrency:\n  group: forecast-v14-daily-refresh\n  cancel-in-progress: false",
    "concurrency:\n  group: forecast-data-publisher\n  cancel-in-progress: false",
)
replace_once(
    ".github/workflows/forecast-v13-daily-refresh.yml",
    '          git commit -m "Refresh validated HOSE forecast, dated VN30 leaders and verified market intelligence [data-only]"\n          git push',
    '          git commit -m "Refresh validated HOSE forecast, dated VN30 leaders and verified market intelligence [data-only]"\n          git pull --rebase origin main\n          git push origin HEAD:main',
)


# ---------------------------------------------------------------------------
# Leaderboard: canonical score and re-filter after live overlay.
# ---------------------------------------------------------------------------
old_quality = '''  function qualityScore(row) {
    const probability = row.directionValidated ? clamp((row.probUp - .44) / .18, 0, 1) : .25;
    const liquidity = clamp(Math.log10(Math.max(row.tradedValue20, 1)) / 11, 0, 1);
    const interval = clamp(row.upside / Math.max(row.intervalWidth, .012), 0, 1);
    const evidence = clamp(row.newsCount / 6, 0, 1);
    const risk = row.risk === "GREEN" ? 1 : row.risk === "WATCH" || row.risk === "YELLOW" ? .52 : .12;
    const flow = row.flowFresh ? 1 : 0;
    return Math.round(100 * (.28 * probability + .24 * liquidity + .16 * interval + .12 * evidence + .14 * risk + .06 * flow));
  }
'''
new_quality = old_quality + '''
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
'''
replace_once("forecast-live-leaders-v14.js", old_quality, new_quality)
replace_once(
    "forecast-live-leaders-v14.js",
    '          || forecast.priceValidated !== true || forecast.validationStatus !== "PASS"\n          || !close || !target || (!options.includeNonPositive && target <= close)',
    '          || forecast.priceValidated !== true || forecast.validationStatus !== "PASS"\n          || forecast.pointDirectionValidated !== true || forecast.magnitudeValidated !== true\n          || !close || !target || (!options.includeNonPositive && target <= close)',
)
replace_once(
    "forecast-live-leaders-v14.js",
    "      row.quality = qualityScore(row);\n      rows.push(row);",
    "      row.quality = qualityScore(row);\n      row.forecastQuality = forecastQuality(row);\n      row.rankScore = rankingScore(row);\n      rows.push(row);",
)
replace_once(
    "forecast-live-leaders-v14.js",
    "    rows.sort((left, right) => right.upside - left.upside || (right.probUp || 0) - (left.probUp || 0) || left.symbol.localeCompare(right.symbol));",
    "    rows.sort((left, right) => right.rankScore - left.rankScore || right.upside - left.upside || (right.probUp || 0) - (left.probUp || 0) || left.symbol.localeCompare(right.symbol));",
)

leader_core = '''  function vnDateKey(value) {
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

'''
regex_once(
    "forecast-live-leaders-v14.js",
    r"  async function loadSessionOverlay\(base\) \{.*?(?=  function sessionStamp\(\))",
    leader_core,
)
replace_once(
    "forecast-live-leaders-v14.js",
    '      state.rows = applySessionOverlay(buildLeaderboard(state.base, { filter: state.filter, includeNonPositive: state.defensive }));',
    '      state.rows = finalLeaderboard(state.base, state.session, { filter: state.filter, includeNonPositive: state.defensive });',
)
replace_once(
    "forecast-live-leaders-v14.js",
    '''      state.universe = applySessionOverlay(buildLeaderboard(state.base, { all: true }));
      state.candidates = applySessionOverlay(buildLeaderboard(state.base, { all: true, includeNonPositive: true }));
      state.defensive = state.universe.length === 0;
      state.rows = applySessionOverlay(buildLeaderboard(state.base, { filter: state.filter, includeNonPositive: state.defensive }));''',
    '''      state.candidates = finalLeaderboard(state.base, state.session, { all: true, includeNonPositive: true });
      state.universe = finalLeaderboard(state.base, state.session, { all: true });
      state.defensive = state.universe.length === 0;
      state.rows = finalLeaderboard(state.base, state.session, { filter: state.filter, includeNonPositive: state.defensive });''',
)
replace_once(
    "forecast-live-leaders-v14.js",
    '''      state.session = await loadSessionOverlay(state.base);
      state.universe = applySessionOverlay(buildLeaderboard(state.base, { all: true }));
      state.candidates = applySessionOverlay(buildLeaderboard(state.base, { all: true, includeNonPositive: true }));
      state.defensive = state.universe.length === 0;
      state.rows = (state.defensive ? state.candidates : state.universe).slice(0, 10);''',
    '''      state.session = await loadSessionOverlay(state.base);
      window.__VMEWS_SESSION__ = state.session;
      state.candidates = finalLeaderboard(state.base, state.session, { all: true, includeNonPositive: true });
      state.universe = finalLeaderboard(state.base, state.session, { all: true });
      state.defensive = state.universe.length === 0;
      state.rows = finalLeaderboard(state.base, state.session, { filter: state.filter, includeNonPositive: state.defensive });''',
)
replace_once(
    "forecast-live-leaders-v14.js",
    '    window.__VMEWS_LEADERBOARD__ = { mode: state.defensive ? "defensive" : "positive", filter: state.filter, selected: state.rows[state.index].symbol, rows: state.rows.map(row => ({ symbol: row.symbol, upside: row.upside, quality: row.quality, tradedValue20: row.tradedValue20, risk: row.risk })) };',
    '    window.__VMEWS_LEADERBOARD__ = { mode: state.defensive ? "defensive" : "positive", filter: state.filter, selected: state.rows[state.index].symbol, session: state.session?.session || "EOD", rows: state.rows.map(row => ({ symbol: row.symbol, close: row.close, coreClose: row.coreClose || row.close, target: row.target, upside: row.upside, rankScore: row.rankScore, quality: row.quality, tradedValue20: row.tradedValue20, risk: row.risk, sessionAt: row.sessionAt || null })) };',
)
replace_once(
    "forecast-live-leaders-v14.js",
    '    const advancing = symbols.filter(snapshot => number(snapshot.lastSessionReturn) > 0).length;\n    const falling = symbols.filter(snapshot => number(snapshot.lastSessionReturn) < 0).length;',
    '    const advancing = number(state.session?.market?.advancing) ?? symbols.filter(snapshot => number(snapshot.lastSessionReturn) > 0).length;\n    const falling = number(state.session?.market?.falling) ?? symbols.filter(snapshot => number(snapshot.lastSessionReturn) < 0).length;',
)
replace_once(
    "forecast-live-leaders-v14.js",
    '      { label: "Phiên gần nhất", value: advancing, format: value => `${Math.round(value)} ↑`, detail: `${falling} giảm · ${symbols.length - advancing - falling} đi ngang`, tone: "" },',
    '      { label: state.session ? "Phiên hiện tại" : "Phiên EOD gần nhất", value: advancing, format: value => `${Math.round(value)} ↑`, detail: `${falling} giảm · ${symbols.length - advancing - falling} đi ngang`, tone: "" },',
)
replace_once(
    "forecast-live-leaders-v14.js",
    '    if (!state.session?.cutoffAt) return "";',
    '    if (!state.session?.cutoffAt) return " · EOD đã kiểm định";',
)


# ---------------------------------------------------------------------------
# AI: session-aware, HOSE-aware, current model preference, less boilerplate.
# ---------------------------------------------------------------------------
replace_once(
    "solution-ai-v17.js",
    'for (const preferred of ["gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3-flash", "gemini-2.5-flash"])',
    'for (const preferred of ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash"])',
)
replace_once(
    "solution-ai-v17.js",
    '      "Với forecast, ưu tiên cấu trúc tư duy: kết luận hiện tại → bằng chứng mạnh nhất → bằng chứng mâu thuẫn → điều kiện xác nhận → điều kiện vô hiệu; tránh nhắc lại cùng một cảnh báo dưới nhiều cách diễn đạt.",',
    '      "Với forecast, ưu tiên cấu trúc tư duy: kết luận hiện tại → bằng chứng mạnh nhất → bằng chứng mâu thuẫn → điều kiện xác nhận → điều kiện vô hiệu; tránh nhắc lại cùng một cảnh báo dưới nhiều cách diễn đạt.",\n      "Nếu có dữ liệu session, phân biệt rõ giá phiên hiện tại với giá đóng cửa EOD đã dùng để niêm phong forecast; chỉ tính lại khoảng cách còn lại tới mục tiêu, tuyệt đối không gọi đó là forecast mới.",',
)
replace_once(
    "solution-ai-v17.js",
    '    const snapshot = base.dash.symbols?.[symbol];\n    if (!snapshot) throw new Error(`Chưa có dữ liệu cho ${symbol}.`);',
    '    const snapshot = base.dash.symbols?.[symbol];\n    if (!snapshot) throw new Error(`Chưa có dữ liệu cho ${symbol}.`);\n    const sessionQuote = (window.__VMEWS_SESSION__?.symbols || []).find(item => item.symbol === symbol && item.quoteCurrent && item.freshForCutoff !== false) || null;',
)
replace_once(
    "solution-ai-v17.js",
    '        price: forecast.expectedPrice, expectedReturn: forecast.expectedReturn,',
    '        price: forecast.expectedPrice, expectedReturn: forecast.expectedReturn,\n        remainingReturnFromSession: sessionQuote && number(sessionQuote.liveClose) > 0 ? forecast.expectedPrice / number(sessionQuote.liveClose) - 1 : null,',
)
regex_once(
    "solution-ai-v17.js",
    r'    const ranked = typeof window\.__VMEWS_BUILD_LEADERBOARD__.*?    const modelAudit = base\.model\.horizons\?\.\["5"\] \|\| \{\};',
    '''    const ranked = window.__VMEWS_LEADERBOARD__?.rows?.length
      ? window.__VMEWS_LEADERBOARD__.rows
      : typeof window.__VMEWS_FINAL_LEADERBOARD__ === "function"
        ? window.__VMEWS_FINAL_LEADERBOARD__(base, window.__VMEWS_SESSION__, { all: true })
        : typeof window.__VMEWS_BUILD_LEADERBOARD__ === "function"
          ? window.__VMEWS_BUILD_LEADERBOARD__(base)
          : [];
    const top = ranked
      .map(row => ({
        symbol: row.symbol,
        close: row.close,
        forecast: row.target || row.horizons?.["5"]?.expectedPrice,
        return: row.upside ?? row.horizons?.["5"]?.expectedReturn,
      }))
      .filter(row => row.close > 0 && row.forecast > row.close && number(row.return) !== null)
      .sort((left, right) => right.return - left.return)
      .slice(0, 10);
    const modelAudit = base.model.horizons?.["5"] || {};''',
)
replace_once(
    "solution-ai-v17.js",
    '      dailyVolatility: snapshot.dailyVolatility, horizons,',
    '      dailyVolatility: snapshot.dailyVolatility, horizons,\n      session: sessionQuote ? { session: window.__VMEWS_SESSION__?.session || null, cutoffAt: window.__VMEWS_SESSION__?.cutoffAt || null, liveClose: number(sessionQuote.liveClose), change: number(sessionQuote.change), updateAt: sessionQuote.updateAt || null, sourceMode: sessionQuote.updateMode || null } : null,',
)
replace_once(
    "solution-ai-v17.js",
    '    const five = context.horizons["T+5"];\n    const lines = [];',
    '    const five = context.horizons["T+5"];\n    const activeClose = number(context.session?.liveClose) ?? number(context.close);\n    const remainingT5 = five && activeClose > 0 ? five.price / activeClose - 1 : five?.expectedReturn;\n    const lines = [];',
)
replace_once(
    "solution-ai-v17.js",
    '      lines.push("### Xếp hạng VN30", "Các mã VN30 có mức dự báo tăng T+5 cao nhất hiện tại:");',
    '      lines.push("### Xếp hạng HOSE", "Các mã HOSE có mức dự báo T+5 nổi bật nhất sau khi áp dữ liệu phiên hợp lệ:");',
)
replace_once(
    "solution-ai-v17.js",
    '      const stance = five.expectedReturn > .003 ? "nghiêng tăng" : five.expectedReturn < -.003 ? "nghiêng giảm" : "gần như đi ngang";',
    '      const stance = remainingT5 > .003 ? "nghiêng tăng" : remainingT5 < -.003 ? "nghiêng giảm" : "gần như đi ngang";',
)
old_summary = '        `${context.symbol} đang có đường dự báo ${stance}: giá đóng cửa ${money(context.close)}, trọng tâm T+5 ${money(five.price)} (${pct(five.expectedReturn)}) và vùng bất định ${money(five.lowerPrice)}–${money(five.upperPrice)}. Đây là dự báo đã niêm phong theo dữ liệu ngày ${context.asOf || "chưa rõ"}; thông tin mới chỉ dùng để diễn giải hoặc kiểm tra luận điểm, không tự sửa các con số này.`, '
new_summary = '        `${context.symbol} đang có đường dự báo ${stance}: ${context.session ? `giá phiên ${money(activeClose)} (${context.session.session || "session"})` : `giá đóng cửa ${money(context.close)}`}, trọng tâm T+5 ${money(five.price)}; khoảng cách còn lại ${pct(remainingT5)} và vùng bất định ${money(five.lowerPrice)}–${money(five.upperPrice)}. Core forecast được niêm phong theo dữ liệu ngày ${context.asOf || "chưa rõ"}; giá phiên chỉ dùng để đo lại khoảng cách tới mục tiêu, không tự sửa mô hình.`, '
replace_once("solution-ai-v17.js", old_summary, new_summary)
replace_once(
    "solution-ai-v17.js",
    '}. Đây không phải tín hiệu mua hoặc cam kết lợi nhuận.`,
    '}. Khi lợi thế sau phí chưa được xác nhận, trạng thái phù hợp là theo dõi điều kiện xác nhận thay vì suy diễn thêm từ một con số đơn lẻ.`,
)
replace_once(
    "solution-ai-v17.js",
    '      validation: context.validation,\n    };',
    '      validation: context.validation,\n      session: context.session,\n    };',
)
replace_once(
    "api/solution-ai.js",
    '    "Giá dự báo, dòng tiền, danh mục quỹ và chỉ tiêu mô hình phải lấy đúng từ ngữ cảnh; không tự tạo giá hoặc thay đổi dự báo.",',
    '    "Giá dự báo, dòng tiền, danh mục quỹ và chỉ tiêu mô hình phải lấy đúng từ ngữ cảnh; không tự tạo giá hoặc thay đổi dự báo.",\n    "Nếu ngữ cảnh có session/liveClose, phân biệt nó với coreClose/EOD; chỉ dùng liveClose để tính khoảng cách còn lại tới mục tiêu đã niêm phong.",',
)


# ---------------------------------------------------------------------------
# Regression tests: split refs, sign flip, same-day stale cutoff.
# ---------------------------------------------------------------------------
replace_once(
    "scripts/forecast_v18_frontend_runtime_test.mjs",
    '  const location = { pathname: "/NCKHtop1/vmews-risk-analytics/hash/forecast-final.html", hostname: "cdn.githubraw.com" };',
    '  const location = { pathname: "/NCKHtop1/vmews-risk-analytics/hash/forecast-final.html", hostname: "cdn.githubraw.com", search: "" };',
)
replace_once(
    "scripts/forecast_v18_frontend_runtime_test.mjs",
    '        tickSize: 100, priceValidated: true, validationStatus: "PASS", directionValidated: false,',
    '        tickSize: 100, priceValidated: true, validationStatus: "PASS", directionValidated: false, pointDirectionValidated: true, magnitudeValidated: true,',
)
replace_once(
    "scripts/forecast_v18_frontend_runtime_test.mjs",
    '''test("commit-pinned CDN loads data from the same immutable ref", async () => {
  const { window } = await loadMarketDashboard();
  assert.equal(window.__VMEWS_ASSET_REF__, "hash");
  assert.equal(
    window.__VMEWS_DATA_ROOT__,
    "https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/hash/data",
  );
});''',
    '''test("commit-pinned CDN keeps immutable assets while live data comes from main", async () => {
  const { window } = await loadMarketDashboard();
  assert.equal(window.__VMEWS_ASSET_REF__, "hash");
  assert.equal(window.__VMEWS_DATA_REF__, "main");
  assert.equal(
    window.__VMEWS_DATA_ROOT__,
    "https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/main/data",
  );
});''',
)
sign_flip_test = '''

test("session overlay re-filters EOD positives that turn negative at the live cutoff", async () => {
  const window = await loadLeaderboard();
  const items = [snapshot("FPT", 72_000, 73_000), snapshot("MCH", 128_000, 130_000)];
  const session = {
    symbols: [
      { symbol: "FPT", liveClose: 74_000, change: .02, quoteCurrent: true, freshForCutoff: true, quality: .55, conviction: -.009 },
      { symbol: "MCH", liveClose: 129_000, change: .01, quoteCurrent: true, freshForCutoff: true, quality: .70, conviction: .006 },
    ],
  };
  const positive = window.__VMEWS_FINAL_LEADERBOARD__(base(items), session, { all: true });
  assert.deepEqual(Array.from(positive, row => row.symbol), ["MCH"]);
  assert.ok(positive.every(row => row.upside > 0));
  const defensive = window.__VMEWS_FINAL_LEADERBOARD__(base([items[0]]), { symbols: [session.symbols[0]] }, { all: true, includeNonPositive: true });
  assert.equal(defensive[0].symbol, "FPT");
  assert.ok(defensive[0].upside < 0);
});
'''
replace_once(
    "scripts/forecast_v18_frontend_runtime_test.mjs",
    '\ntest("VN30 scope rejects nonmembers, removed names, downtrends and nonexecutable prices", async () => {',
    sign_flip_test + '\ntest("VN30 scope rejects nonmembers, removed names, downtrends and nonexecutable prices", async () => {',
)
stale_test = '''

    def test_rejects_same_day_quotes_that_are_stale_for_the_session_cutoff(self):
        now = datetime(2026, 8, 25, 15, 25, tzinfo=VN_TZ)
        stale = datetime(2026, 8, 25, 10, 30, tzinfo=VN_TZ)
        payload = build_payload(self.dashboard(), self.frame(now=stale), now)
        self.assertEqual(payload["status"], "DEGRADED")
        self.assertEqual(payload["coverage"]["currentQuoteDate"], 120)
        self.assertEqual(payload["coverage"]["cutoffFresh"], 0)
        self.assertLess(payload["coverage"]["cutoffFreshCoverageRatio"], 0.90)
'''
replace_once(
    "scripts/forecast_v21_session_snapshot_test.py",
    '\n    def test_falls_back_to_defensive_ranking_when_live_price_exceeds_all_targets(self):',
    stale_test + '\n    def test_falls_back_to_defensive_ranking_when_live_price_exceeds_all_targets(self):',
)

replace_once(
    ".github/workflows/cdn-smoke.yml",
    "          ! grep -Fq '/main/data' /tmp/forecast-final-v12.js",
    "          grep -Fq 'DATA_REF' /tmp/forecast-final-v12.js\n          grep -Fq 'release-pointer-v22.json' /tmp/forecast-final.html",
)
replace_once(
    "scripts/forecast_v14_frontend_contract_test.py",
    '        self.assertIn("right.upside - left.upside", leaders)',
    '        self.assertIn("right.rankScore - left.rankScore", leaders)\n        self.assertIn("__VMEWS_FINAL_LEADERBOARD__", leaders)\n        self.assertIn("release-pointer-v22.json", self.html)',
)

# E2E browser check.
e2e = r'''import assert from "node:assert/strict";
import { chromium } from "playwright";

const browser = await chromium.launch({ headless: true });
const issues = [];

async function verify(viewport, label) {
  const page = await browser.newPage({ viewport });
  page.on("pageerror", error => issues.push(`${label}: pageerror ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error" && !message.text().includes("forecast-session-v21.json")) issues.push(`${label}: console ${message.text()}`);
  });
  await page.goto("http://127.0.0.1:8765/forecast-final.html?symbol=FPT", { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.waitForSelector("#signalDeck .signalCard", { timeout: 120000 });
  const cards = await page.locator("#signalDeck .signalCard").count();
  assert.ok(cards >= 1 && cards <= 10, `${label}: cards=${cards}`);
  assert.match(await page.locator("#leaders .commandIndex").innerText(), /HOSE/);
  assert.doesNotMatch(await page.locator("#snapshotDate").innerText(), /ĐANG TẢI/);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert.ok(overflow <= 2, `${label}: horizontal overflow ${overflow}px`);
  assert.ok(await page.locator("#solutionAiGeminiWeb").count());
  await page.locator("#solutionAiNav").click();
  assert.equal(await page.locator("#solutionAiPanel").isVisible(), true);
  if (label === "desktop" && cards > 1) {
    const before = await page.locator("#carouselPosition").innerText();
    await page.waitForTimeout(3400);
    const after = await page.locator("#carouselPosition").innerText();
    assert.notEqual(after, before, "carousel should rotate close to 3 seconds");
  }
  await page.close();
}

await verify({ width: 1440, height: 1000 }, "desktop");
await verify({ width: 390, height: 844 }, "mobile");
await browser.close();
assert.deepEqual(issues, []);
console.log("V22 browser E2E PASS");
'''
write("scripts/forecast_v22_browser_e2e.mjs", e2e)

print("V22 hardening patch applied")
