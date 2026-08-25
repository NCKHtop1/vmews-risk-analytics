from pathlib import Path

path = Path(__file__).resolve().with_name("v22_hardening_patch.py")
text = path.read_text(encoding="utf-8")

# Repair the one malformed quoted replacement in the standalone patcher.
old = """    '}. Đây không phải tín hiệu mua hoặc cam kết lợi nhuận.`,
    '}. Khi lợi thế sau phí chưa được xác nhận, trạng thái phù hợp là theo dõi điều kiện xác nhận thay vì suy diễn thêm từ một con số đơn lẻ.`,
"""
new = """    "}. Đây không phải tín hiệu mua hoặc cam kết lợi nhuận.` ,",
    "}. Khi lợi thế sau phí chưa được xác nhận, trạng thái phù hợp là theo dõi điều kiện xác nhận thay vì suy diễn thêm từ một con số đơn lẻ.` ,",
"""
if old not in text:
    raise SystemExit("V22 syntax target not found")
text = text.replace(old, new, 1)

# One small leaderboard statement exists twice in V21. Convert only the first;
# the community-refresh block is patched later as one larger guarded block.
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

# The local-AI summary sentence is semantically stable but whitespace-sensitive.
old_call = 'replace_once("solution-ai-v17.js", old_summary, new_summary)'
new_call = '''regex_once(
    "solution-ai-v17.js",
    r'        `\\$\\{context\\.symbol\\} đang có đường dự báo \\$\\{stance\\}: giá đóng cửa [^\\n]*?không tự sửa các con số này\\.`,',
    new_summary,
)'''
if text.count(old_call) != 1:
    raise SystemExit(f"V22 local AI call repair count={text.count(old_call)}")
text = text.replace(old_call, new_call, 1)

# Upgrade the permanent release audit to validate the new delivery architecture.
audit_patch = r'''
replace_once(
    "scripts/forecast_v20_release_audit.py",
    '''    require("CDN_PATH[2]" in frontend_text, "commit-pinned CDN does not derive data from its own release ref")
    require("/main/data" not in frontend_text, "commit-pinned CDN still mixes immutable code with mutable main data")''',
    '''    require("CDN_PATH[2]" in frontend_text, "commit-pinned CDN does not derive its immutable asset ref")
    require("DATA_REF" in frontend_text and "__VMEWS_DATA_REF__" in frontend_text, "frontend does not separate asset and data refs")
    require("release-pointer-v22.json" in frontend_text, "stable main URL lacks an immutable release pointer")
    require("raw.githubusercontent.com" in frontend_text and "/data`" in frontend_text, "live data root is not explicit")
    require("<script src=\\\"https://raw.githubusercontent.com" not in frontend_text, "mutable main code is loaded into the immutable asset page")''',
)
replace_once(
    "scripts/forecast_v20_release_audit.py",
    '''        "delivery": {
            "assetDataRefPolicy": "SAME_REF",
            "mutableMainFallback": False,
        },''',
    '''        "delivery": {
            "assetDataRefPolicy": "IMMUTABLE_ASSETS_LIVE_MAIN_DATA",
            "assetPointer": "data/release-pointer-v22.json",
            "liveMainData": True,
            "mutableMainFallback": False,
        },''',
)
'''
text += "\n" + audit_patch

path.write_text(text, encoding="utf-8")
print("V22 patcher repaired")
