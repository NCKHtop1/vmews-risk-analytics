from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
patcher = ROOT / "scripts" / "v22_hardening_patch.py"
text = patcher.read_text(encoding="utf-8")

old = """    '}. Đây không phải tín hiệu mua hoặc cam kết lợi nhuận.`,
    '}. Khi lợi thế sau phí chưa được xác nhận, trạng thái phù hợp là theo dõi điều kiện xác nhận thay vì suy diễn thêm từ một con số đơn lẻ.`,
"""
new = """    "}. Đây không phải tín hiệu mua hoặc cam kết lợi nhuận.` ,",
    "}. Khi lợi thế sau phí chưa được xác nhận, trạng thái phù hợp là theo dõi điều kiện xác nhận thay vì suy diễn thêm từ một con số đơn lẻ.` ,",
"""
if old not in text:
    raise SystemExit("V22 syntax target not found")
text = text.replace(old, new, 1)

old_block = '''replace_once(
    "forecast-live-leaders-v14.js",
    '      state.rows = applySessionOverlay(buildLeaderboard(state.base, { filter: state.filter, includeNonPositive: state.defensive }));',
    '      state.rows = finalLeaderboard(state.base, state.session, { filter: state.filter, includeNonPositive: state.defensive });',
)
'''
new_block = '''_path = "forecast-live-leaders-v14.js"
_old = '      state.rows = applySessionOverlay(buildLeaderboard(state.base, { filter: state.filter, includeNonPositive: state.defensive }));'
_new = '      state.rows = finalLeaderboard(state.base, state.session, { filter: state.filter, includeNonPositive: state.defensive });'
_text = read(_path)
if _text.count(_old) != 2:
    raise AssertionError(f"{_path}: expected 2 filter/community matches, got {_text.count(_old)}")
write(_path, _text.replace(_old, _new, 1))
'''
if old_block not in text:
    raise SystemExit("V22 duplicate leaderboard patch target not found")
text = text.replace(old_block, new_block, 1)

old_call = 'replace_once("solution-ai-v17.js", old_summary, new_summary)'
new_call = '''regex_once(
    "solution-ai-v17.js",
    r'        `\\$\\{context\\.symbol\\} đang có đường dự báo \\$\\{stance\\}: giá đóng cửa [^\\n]*?không tự sửa các con số này\\.`,',
    new_summary,
)'''
if text.count(old_call) != 1:
    raise SystemExit(f"V22 local AI call repair count={text.count(old_call)}")
text = text.replace(old_call, new_call, 1)

old_console = '''  page.on("console", message => {
    if (message.type() === "error" && !message.text().includes("forecast-session-v21.json")) issues.push(`${label}: console ${message.text()}`);
  });'''
new_console = '''  page.on("response", response => {
    if (response.status() !== 404) return;
    const url = new URL(response.url());
    if (url.hostname === "127.0.0.1" && url.pathname === "/api/solution-ai") return;
    issues.push(`${label}: 404 ${response.url()}`);
  });
  page.on("console", message => {
    if (message.type() !== "error") return;
    if (message.text().includes("Failed to load resource")) return;
    issues.push(`${label}: console ${message.text()}`);
  });'''
if text.count(old_console) != 1:
    raise SystemExit(f"V22 E2E console hook count={text.count(old_console)}")
text = text.replace(old_console, new_console, 1)
patcher.write_text(text, encoding="utf-8")

audit_path = ROOT / "scripts" / "forecast_v20_release_audit.py"
audit = audit_path.read_text(encoding="utf-8")
old_delivery_checks = '''    require("CDN_PATH[2]" in frontend_text, "commit-pinned CDN does not derive data from its own release ref")
    require("/main/data" not in frontend_text, "commit-pinned CDN still mixes immutable code with mutable main data")'''
new_delivery_checks = '''    require("CDN_PATH[2]" in frontend_text, "commit-pinned CDN does not derive its immutable asset ref")
    require("DATA_REF" in frontend_text and "__VMEWS_DATA_REF__" in frontend_text, "frontend does not separate asset and data refs")
    require("release-pointer-v22.json" in frontend_text, "stable main URL lacks an immutable release pointer")
    require("raw.githubusercontent.com" in frontend_text, "live data origin is not explicit")
    require('<script src="https://raw.githubusercontent.com' not in frontend_text, "mutable main code is loaded into the immutable asset page")'''
if audit.count(old_delivery_checks) != 1:
    raise SystemExit(f"V22 delivery audit check count={audit.count(old_delivery_checks)}")
audit = audit.replace(old_delivery_checks, new_delivery_checks, 1)
old_report = '''        "delivery": {
            "assetDataRefPolicy": "SAME_REF",
            "mutableMainFallback": False,
        },'''
new_report = '''        "delivery": {
            "assetDataRefPolicy": "IMMUTABLE_ASSETS_LIVE_MAIN_DATA",
            "assetPointer": "data/release-pointer-v22.json",
            "liveMainData": True,
            "mutableMainFallback": False,
        },'''
if audit.count(old_report) != 1:
    raise SystemExit(f"V22 delivery report count={audit.count(old_report)}")
audit_path.write_text(audit.replace(old_report, new_report, 1), encoding="utf-8")

html_path = ROOT / "forecast-final.html"
html = html_path.read_text(encoding="utf-8")
icon = '<link rel="icon" href="data:,">'
if icon not in html:
    marker = '<meta name="description" content="Dự báo cổ phiếu HOSE T+1 đến T+5 với trọng tâm giá, vùng dự báo và dữ liệu kiểm định.">'
    if html.count(marker) != 1:
        raise SystemExit(f"V22 favicon marker count={html.count(marker)}")
    html = html.replace(marker, marker + "\n" + icon, 1)
    html_path.write_text(html, encoding="utf-8")

print("V22 patcher release audit and exact browser 404 instrumentation repaired")