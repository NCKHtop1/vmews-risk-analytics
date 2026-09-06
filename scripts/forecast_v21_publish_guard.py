import argparse
import json
from datetime import date, datetime
from pathlib import Path

PUBLISH = 0
SKIP = 10
MIN_COVERAGE = 0.90


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_date(value, field):
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise RuntimeError(f"Invalid {field}: {value!r}") from exc


def parse_datetime(value, field):
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise RuntimeError(f"Invalid {field}: {value!r}") from exc
    if parsed.tzinfo is None:
        raise RuntimeError(f"{field} must be timezone-aware: {value!r}")
    return parsed


def validate_candidate(candidate, dashboard):
    if candidate.get("status") != "PASS":
        raise RuntimeError(f"Candidate status is not PASS: {candidate.get('status')!r}")
    if candidate.get("coreForecastUnchanged") is not True:
        raise RuntimeError("Candidate attempted to mutate the sealed core forecast")

    candidate_core = parse_date(candidate.get("coreAsOf"), "candidate coreAsOf")
    dashboard_core = parse_date(dashboard.get("asOf"), "dashboard asOf")
    if candidate_core != dashboard_core:
        return {
            "decision": "SKIP",
            "reason": "candidate_core_is_not_latest_checked_out_dashboard",
            "candidateCoreAsOf": candidate_core.isoformat(),
            "dashboardAsOf": dashboard_core.isoformat(),
        }

    coverage = candidate.get("coverage") or {}
    for field in ("coverageRatio", "currentCoverageRatio", "cutoffFreshCoverageRatio"):
        try:
            value = float(coverage.get(field))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Candidate {field} is invalid: {coverage.get(field)!r}") from exc
        if value < MIN_COVERAGE:
            raise RuntimeError(f"Candidate {field} below {MIN_COVERAGE:.2f}: {value:.6f}")

    promotion = dashboard.get("promotion") or {}
    promoted = {int(value) for value in promotion.get("directPriceHorizons") or []}
    preferred = int(promotion.get("preferredRankingHorizon") or 0)
    if preferred not in promoted:
        raise RuntimeError(f"Dashboard preferred horizon {preferred} is not promoted: {sorted(promoted)}")
    if int(candidate.get("rankingHorizon") or 0) != preferred:
        raise RuntimeError(
            f"Candidate ranking horizon {candidate.get('rankingHorizon')} != dashboard preferred {preferred}"
        )

    return None


def snapshot_key(snapshot):
    coverage = snapshot.get("coverage") or {}
    return {
        "quoteDate": parse_date(coverage.get("expectedQuoteDate"), "expectedQuoteDate"),
        "coreDate": parse_date(snapshot.get("coreAsOf"), "coreAsOf"),
        "generatedAt": parse_datetime(snapshot.get("generatedAt"), "generatedAt"),
    }


def decide(candidate, published, dashboard):
    candidate_problem = validate_candidate(candidate, dashboard)
    if candidate_problem:
        return candidate_problem

    candidate_key = snapshot_key(candidate)
    if not published or published.get("status") != "PASS":
        return {
            "decision": "PUBLISH",
            "reason": "no_validated_published_snapshot",
            "candidateKey": {key: value.isoformat() for key, value in candidate_key.items()},
        }

    published_key = snapshot_key(published)
    candidate_json = {key: value.isoformat() for key, value in candidate_key.items()}
    published_json = {key: value.isoformat() for key, value in published_key.items()}

    if candidate_key["quoteDate"] < published_key["quoteDate"]:
        return {
            "decision": "SKIP",
            "reason": "published_quote_session_is_newer",
            "candidateKey": candidate_json,
            "publishedKey": published_json,
        }
    if candidate_key["quoteDate"] > published_key["quoteDate"]:
        return {
            "decision": "PUBLISH",
            "reason": "candidate_quote_session_is_newer",
            "candidateKey": candidate_json,
            "publishedKey": published_json,
        }

    if candidate_key["coreDate"] < published_key["coreDate"]:
        return {
            "decision": "SKIP",
            "reason": "published_core_is_newer_for_same_quote_session",
            "candidateKey": candidate_json,
            "publishedKey": published_json,
        }
    if candidate_key["coreDate"] > published_key["coreDate"]:
        return {
            "decision": "PUBLISH",
            "reason": "candidate_core_is_newer_for_same_quote_session",
            "candidateKey": candidate_json,
            "publishedKey": published_json,
        }

    if candidate_key["generatedAt"] <= published_key["generatedAt"]:
        return {
            "decision": "SKIP",
            "reason": "published_snapshot_is_same_or_newer",
            "candidateKey": candidate_json,
            "publishedKey": published_json,
        }

    return {
        "decision": "PUBLISH",
        "reason": "candidate_is_newer_within_same_quote_and_core_session",
        "candidateKey": candidate_json,
        "publishedKey": published_json,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--published", required=True)
    parser.add_argument("--dashboard", required=True)
    args = parser.parse_args()

    candidate = load_json(args.candidate)
    dashboard = load_json(args.dashboard)
    published_path = Path(args.published)
    published = load_json(published_path) if published_path.exists() else None
    result = decide(candidate, published, dashboard)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return PUBLISH if result["decision"] == "PUBLISH" else SKIP


if __name__ == "__main__":
    raise SystemExit(main())
