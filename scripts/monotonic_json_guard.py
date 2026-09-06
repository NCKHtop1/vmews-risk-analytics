import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

PUBLISH = 0
SKIP = 10


def load(path):
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def get_path(obj, dotted):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def parse_value(value, kind):
    if value is None:
        return None
    text = str(value).strip()
    if kind == "date":
        return date.fromisoformat(text[:10])
    if kind == "datetime":
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if kind == "int":
        return int(value)
    if kind == "float":
        return float(value)
    return text


def decide(candidate, current, field, kind, skip_equal=False):
    candidate_value = parse_value(get_path(candidate, field), kind)
    if candidate_value is None:
        raise RuntimeError(f"Candidate missing monotonic field {field}")
    if not current:
        return {"decision": "PUBLISH", "reason": "no_current_snapshot", "candidate": str(candidate_value)}

    current_raw = get_path(current, field)
    if current_raw is None:
        return {"decision": "PUBLISH", "reason": "current_missing_monotonic_field", "candidate": str(candidate_value)}
    current_value = parse_value(current_raw, kind)

    if candidate_value < current_value:
        return {
            "decision": "SKIP",
            "reason": "current_is_newer",
            "candidate": str(candidate_value),
            "current": str(current_value),
        }
    if candidate_value == current_value:
        if skip_equal:
            return {
                "decision": "SKIP",
                "reason": "current_same_logical_version_won_race",
                "candidate": str(candidate_value),
                "current": str(current_value),
            }
        return {
            "decision": "PUBLISH",
            "reason": "same_logical_version_revalidated",
            "candidate": str(candidate_value),
            "current": str(current_value),
        }
    return {
        "decision": "PUBLISH",
        "reason": "candidate_is_newer",
        "candidate": str(candidate_value),
        "current": str(current_value),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--current", required=True)
    parser.add_argument("--field", required=True)
    parser.add_argument("--kind", choices=["date", "datetime", "int", "float", "string"], default="string")
    parser.add_argument("--skip-equal", action="store_true")
    args = parser.parse_args()

    result = decide(load(args.candidate), load(args.current), args.field, args.kind, skip_equal=args.skip_equal)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return PUBLISH if result["decision"] == "PUBLISH" else SKIP


if __name__ == "__main__":
    raise SystemExit(main())
