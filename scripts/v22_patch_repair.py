from pathlib import Path
import re

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

# One small leaderboard statement exists twice in the V21 source. Convert only
# the first call; the community-refresh block is handled by the larger patch.
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

# The original patcher accidentally included one trailing space in the exact
# local-AI summary target. Replace the two assignments with exact source text.
summary_pattern = re.compile(r"old_summary = .*?\nnew_summary = .*?\nreplace_once\(\"solution-ai-v17\.js\", old_summary, new_summary\)", re.S)
summary_replacement = '''old_summary = ''' + "'''" + '''        `${context.symbol} đang có đường dự báo ${stance}: giá đóng cửa ${money(context.close)}, trọng tâm T+5 ${money(five.price)} (${pct(five.expectedReturn)}) và vùng bất định ${money(five.lowerPrice)}–${money(five.upperPrice)}. Đây là dự báo đã niêm phong theo dữ liệu ngày ${context.asOf || "chưa rõ"}; thông tin mới chỉ dùng để diễn giải hoặc kiểm tra luận điểm, không tự sửa các con số này.`,`''' + "'''" + '''
new_summary = ''' + "'''" + '''        `${context.symbol} đang có đường dự báo ${stance}: ${context.session ? `giá phiên ${money(activeClose)} (${context.session.session || "session"})` : `giá đóng cửa ${money(context.close)}`}, trọng tâm T+5 ${money(five.price)}; khoảng cách còn lại ${pct(remainingT5)} và vùng bất định ${money(five.lowerPrice)}–${money(five.upperPrice)}. Core forecast được niêm phong theo dữ liệu ngày ${context.asOf || "chưa rõ"}; giá phiên chỉ dùng để đo lại khoảng cách tới mục tiêu, không tự sửa mô hình.`,`''' + "'''" + '''
replace_once("solution-ai-v17.js", old_summary, new_summary)'''
text, count = summary_pattern.subn(summary_replacement, text, count=1)
if count != 1:
    raise SystemExit(f"V22 local AI summary assignment repair count={count}")

path.write_text(text, encoding="utf-8")
print("V22 patcher repaired")
