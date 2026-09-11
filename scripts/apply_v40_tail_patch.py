#!/usr/bin/env python3
"""Apply the small V40 integration patch deterministically.

Kept separate so the statistical change is reviewable and reproducible without
rewriting the large production module by hand.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "scripts" / "forecast_v13_market_model.py"
AI = ROOT / "solution-ai-v17.js"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_model() -> None:
    text = MODEL.read_text(encoding="utf-8")
    import_anchor = "from forecast_v18_market_intelligence import community_events, community_watchlist, rumor_intelligence, vn30_metadata\n"
    import_new = import_anchor + "from forecast_v40_tail_blend import select_tail_guarded_directional_blend\n"
    if "from forecast_v40_tail_blend import" not in text:
        text = replace_once(text, import_anchor, import_new, "model import")

    call_old = """    directional_blend = select_directional_magnitude_blend(\n        cal_y,\n        cal_point_prediction,\n        cal_probability,\n        cal_magnitude,\n        calibration[\"date\"].dt.strftime(\"%Y-%m-%d\").to_numpy(),\n    )\n"""
    call_new = """    directional_blend = select_tail_guarded_directional_blend(\n        cal_y,\n        cal_point_prediction,\n        cal_probability,\n        cal_magnitude,\n        calibration[\"date\"].dt.strftime(\"%Y-%m-%d\").to_numpy(),\n    )\n"""
    if "directional_blend = select_tail_guarded_directional_blend(" not in text:
        text = replace_once(text, call_old, call_new, "tail selector integration")

    version_old = 'VERSION = "VMEWS-MARKET-FORECAST-39.0.0"'
    version_new = 'VERSION = "VMEWS-MARKET-FORECAST-40.0.0-TAIL-CANDIDATE"'
    if version_old in text:
        text = replace_once(text, version_old, version_new, "version")
    MODEL.write_text(text, encoding="utf-8")


def patch_ai() -> None:
    text = AI.read_text(encoding="utf-8")
    anchor = '      "Với forecast, ưu tiên cấu trúc tư duy: kết luận hiện tại → bằng chứng mạnh nhất → bằng chứng mâu thuẫn → điều kiện xác nhận → điều kiện vô hiệu; tránh nhắc lại cùng một cảnh báo dưới nhiều cách diễn đạt.",\n'
    addition = anchor + '      "Khi người dùng hỏi vì sao forecast sai hoặc không sát, phải chẩn đoán theo thứ tự: forecast tại T0 → actual khi đáo hạn → residual → đúng/sai hướng → thiếu/thừa biên độ → actual có nằm trong vùng dự báo hay không → lỗi có lặp lại trong audit hay chỉ là shock đơn lẻ; không được trả lời chung chung rằng thị trường biến động.",\n      "Phân biệt rõ direction miss với amplitude miss. Nếu đúng chiều nhưng độ lớn thực tế vượt xa forecast thì gọi là under-amplitude; nếu quá mạnh thì over-amplitude. Chỉ đề xuất sửa model khi audit nhiều trường hợp cho thấy lỗi lặp lại; tuyệt đối không dùng kết quả tương lai để biện minh rằng model tại T0 đáng lẽ phải biết.",\n'
    if "under-amplitude" not in text:
        text = replace_once(text, anchor, addition, "AI forecast-miss instruction")
    AI.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_model()
    patch_ai()
    print("V40 tail calibration patch applied")
