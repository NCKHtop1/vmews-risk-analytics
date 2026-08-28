#!/usr/bin/env python3
"""Prepare the market scan for the sealed EOD forecast pipeline.

The market-wide scanner may run before the opening auction. In that case its
`reviewDate` is the current calendar/trading day while `modelDate` and the
actual TradingView quote rows still refer to the latest completed session.
The EOD forecast must cross-check like-for-like completed sessions, so this
adapter makes that session explicit without changing any quote or forecast.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCAN = ROOT / "data" / "market-scan.json"


def prepare(path: Path) -> dict:
    scan = json.loads(path.read_text(encoding="utf-8"))
    review_date = str(scan.get("reviewDate") or "")[:10]
    model_date = str(scan.get("modelDate") or "")[:10]
    if len(model_date) != 10:
        raise RuntimeError(f"market scan has no completed modelDate: {model_date!r}")

    rows = [row for row in (scan.get("ranking") or []) if isinstance(row, dict)]
    row_dates = Counter(str(row.get("date") or "")[:10] for row in rows if row.get("date"))
    model_rows = row_dates.get(model_date, 0)
    if not rows or model_rows / len(rows) < 0.55:
        raise RuntimeError(
            f"market scan does not cover the completed session {model_date}: "
            f"{model_rows}/{len(rows)} ranking rows"
        )

    scan["forecastReviewDateOriginal"] = review_date or None
    scan["forecastEodSession"] = model_date
    scan["reviewDate"] = model_date
    path.write_text(json.dumps(scan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "status": "PASS",
        "originalReviewDate": review_date or None,
        "forecastEodSession": model_date,
        "rankingRows": len(rows),
        "sameSessionRows": model_rows,
        "sameSessionCoverage": model_rows / len(rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_SCAN))
    args = parser.parse_args()
    result = prepare(Path(args.input))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
