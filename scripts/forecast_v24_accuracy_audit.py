#!/usr/bin/env python3
"""Leakage-safe diagnostics for the published VMEWS forecast.

This audit never rewrites the model. It measures recent/full performance and
runs a simple shrinkage challenger selected strictly before a sealed final date
window. The challenger is evidence only; production promotion requires the
normal model pipeline and release gates.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def rows_for(backtest: dict[str, Any], horizon: int) -> list[dict[str, Any]]:
    rows = []
    for item in (backtest.get("cases") or {}).get(str(horizon), []):
        predicted = finite(item.get("predictedReturn"))
        actual = finite(item.get("actualReturn"))
        origin = str(item.get("originDate") or "")[:10]
        if predicted is None or actual is None or len(origin) != 10:
            continue
        rows.append({**item, "originDate": origin, "predictedReturn": predicted, "actualReturn": actual})
    return sorted(rows, key=lambda row: (row["originDate"], str(row.get("symbol") or "")))


def metrics(rows: list[dict[str, Any]], alpha: float = 1.0) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    model_errors = []
    baseline_errors = []
    signed_errors = []
    direction = []
    interval_hits = []
    for row in rows:
        pred = alpha * row["predictedReturn"]
        actual = row["actualReturn"]
        model_errors.append(abs(pred - actual))
        baseline_errors.append(abs(actual))
        signed_errors.append(pred - actual)
        if pred != 0 and actual != 0:
            direction.append((pred > 0) == (actual > 0))
        if row.get("intervalHit") is not None:
            interval_hits.append(bool(row.get("intervalHit")))
    baseline = mean(baseline_errors)
    mae = mean(model_errors)
    return {
        "n": len(rows),
        "dates": len({row["originDate"] for row in rows}),
        "from": rows[0]["originDate"],
        "to": rows[-1]["originDate"],
        "maeReturn": mae,
        "baselineMAEReturn": baseline,
        "maeSkill": (baseline - mae) / baseline if baseline > 0 else None,
        "directionalAccuracy": mean(direction) if direction else None,
        "signedBias": mean(signed_errors),
        "medianAbsoluteError": median(model_errors),
        "intervalCoverage": mean(interval_hits) if interval_hits else None,
        "meanPredictedReturn": mean(alpha * row["predictedReturn"] for row in rows),
        "meanActualReturn": mean(row["actualReturn"] for row in rows),
    }


def last_dates(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    dates = sorted({row["originDate"] for row in rows})
    keep = set(dates[-count:])
    return [row for row in rows if row["originDate"] in keep]


def before_dates(rows: list[dict[str, Any]], holdout_count: int, dev_count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dates = sorted({row["originDate"] for row in rows})
    if len(dates) <= holdout_count + 20:
        split = max(1, int(len(dates) * 0.75))
        dev_dates, holdout_dates = dates[:split], dates[split:]
    else:
        holdout_dates = dates[-holdout_count:]
        dev_end = len(dates) - holdout_count
        dev_dates = dates[max(0, dev_end - dev_count):dev_end]
    dev_set, holdout_set = set(dev_dates), set(holdout_dates)
    return ([row for row in rows if row["originDate"] in dev_set], [row for row in rows if row["originDate"] in holdout_set])


def challenger(rows: list[dict[str, Any]], holdout_dates: int = 120, dev_dates: int = 360) -> dict[str, Any]:
    dev, holdout = before_dates(rows, holdout_dates, dev_dates)
    candidates = [0.25, 0.40, 0.55, 0.70, 0.85, 1.0, 1.15]
    dev_results = {str(alpha): metrics(dev, alpha) for alpha in candidates}
    eligible = [(alpha, result) for alpha, result in ((a, dev_results[str(a)]) for a in candidates) if result.get("n")]
    if not eligible:
        return {"status": "INSUFFICIENT_DATA"}
    chosen_alpha, chosen_dev = min(eligible, key=lambda pair: pair[1]["maeReturn"])
    baseline_holdout = metrics(holdout, 1.0)
    challenger_holdout = metrics(holdout, chosen_alpha)
    improvement = None
    if baseline_holdout.get("maeReturn"):
        improvement = (baseline_holdout["maeReturn"] - challenger_holdout["maeReturn"]) / baseline_holdout["maeReturn"]
    direction_delta = None
    if baseline_holdout.get("directionalAccuracy") is not None and challenger_holdout.get("directionalAccuracy") is not None:
        direction_delta = challenger_holdout["directionalAccuracy"] - baseline_holdout["directionalAccuracy"]
    promote = bool(
        improvement is not None and improvement >= 0.01
        and direction_delta is not None and direction_delta >= -0.005
        and challenger_holdout.get("maeSkill") is not None and challenger_holdout["maeSkill"] > 0
    )
    return {
        "status": "PASS" if promote else "NO_PROMOTION",
        "selection": "alpha chosen on pre-holdout dev dates only",
        "chosenAlpha": chosen_alpha,
        "dev": chosen_dev,
        "baselineHoldout": baseline_holdout,
        "challengerHoldout": challenger_holdout,
        "holdoutMAEImprovement": improvement,
        "holdoutDirectionDelta": direction_delta,
        "promotionRule": "MAE >=1% better, direction no worse than -0.5pp, positive MAE skill",
    }


def ranking_policy(horizons: dict[str, Any]) -> dict[str, Any]:
    """Select ranking authority without changing any sealed T+1..T+5 forecast.

    The dashboard may still display every horizon.  The leaderboard only uses
    the longest recent horizon with enough observations, positive MAE skill
    versus a zero-return baseline and directional accuracy above 52%.
    """
    minimum_samples = 300
    minimum_mae_skill = 0.0
    minimum_direction = 0.52
    evaluations: dict[str, Any] = {}
    selected = None

    for horizon in range(5, 0, -1):
        recent = (horizons.get(str(horizon)) or {}).get("recent120Dates") or {}
        n = int(recent.get("n") or 0)
        skill = finite(recent.get("maeSkill"))
        direction = finite(recent.get("directionalAccuracy"))
        reasons = []
        if n < minimum_samples:
            reasons.append(f"n<{minimum_samples}")
        if skill is None or skill <= minimum_mae_skill:
            reasons.append("maeSkill<=0")
        if direction is None or direction < minimum_direction:
            reasons.append(f"direction<{minimum_direction:.2f}")
        eligible = not reasons
        evaluations[str(horizon)] = {
            "n": n,
            "maeSkill": skill,
            "directionalAccuracy": direction,
            "eligible": eligible,
            "reasons": reasons,
        }
        if selected is None and eligible:
            selected = horizon

    degraded = False
    if selected is None:
        degraded = True
        fallback = []
        for horizon in range(1, 6):
            item = evaluations[str(horizon)]
            if item["n"] >= minimum_samples and item["directionalAccuracy"] is not None and item["directionalAccuracy"] >= 0.50:
                fallback.append((item["maeSkill"] if item["maeSkill"] is not None else -1e9, item["directionalAccuracy"], horizon))
        selected = max(fallback)[2] if fallback else 1

    rejected_longer = [f"T+{h}" for h in range(5, selected, -1) if not evaluations[str(h)]["eligible"]]
    reason = (
        f"Selected T+{selected} for leaderboard authority from recent out-of-sample evidence."
        + (f" Longer horizons withheld: {', '.join(rejected_longer)}." if rejected_longer else "")
        + (" No horizon met the strict gate; fallback policy is active." if degraded else "")
    )
    return {
        "selectedHorizon": selected,
        "degraded": degraded,
        "criteria": {
            "minimumSamples": minimum_samples,
            "minimumMAESkillExclusive": minimum_mae_skill,
            "minimumDirectionalAccuracy": minimum_direction,
            "window": "recent120Dates",
        },
        "evaluations": evaluations,
        "reason": reason,
        "coreForecastChanged": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DATA / "forecast-backtest-v12.json"))
    parser.add_argument("--output", default=str(DATA / "forecast-accuracy-v24.json"))
    args = parser.parse_args()
    backtest = json.loads(Path(args.input).read_text(encoding="utf-8"))
    report: dict[str, Any] = {
        "version": "VMEWS-FORECAST-ACCURACY-AUDIT-24.1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "method": "published backtest cases; chronological recent windows; leakage-safe shrinkage challenger",
        "horizons": {},
    }
    for horizon in range(1, 6):
        rows = rows_for(backtest, horizon)
        symbol_rows = [row for row in rows if str(row.get("symbol") or "").upper() == "FPT"]
        report["horizons"][str(horizon)] = {
            "full": metrics(rows),
            "recent120Dates": metrics(last_dates(rows, 120)),
            "recent60Dates": metrics(last_dates(rows, 60)),
            "FPT": metrics(symbol_rows),
            "FPTRecent60Dates": metrics(last_dates(symbol_rows, 60)),
            "shrinkageChallenger": challenger(rows),
        }
    policy = ranking_policy(report["horizons"])
    report["rankingPolicy"] = policy
    t5 = report["horizons"]["5"]
    report["summary"] = {
        "t5RecentSkill": t5["recent120Dates"].get("maeSkill"),
        "t5RecentDirection": t5["recent120Dates"].get("directionalAccuracy"),
        "t5RecentBias": t5["recent120Dates"].get("signedBias"),
        "rankingHorizon": policy["selectedHorizon"],
        "rankingDegraded": policy["degraded"],
        "challengerStatus": t5["shrinkageChallenger"].get("status"),
        "productionChanged": False,
        "note": "This audit does not alter sealed forecast parameters. Promotion requires independent evidence and normal release gates.",
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
