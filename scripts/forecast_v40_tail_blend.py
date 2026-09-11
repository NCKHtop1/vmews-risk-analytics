"""Leakage-safe tail-aware selector for the VMEWS directional/magnitude blend.

The selector is calibration-only. It never reads sealed holdout labels. Its goal
is to reduce systematic under-amplitude on large moves without sacrificing the
ordinary-case MAE edge that protects the production model from over-trading.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np


def _blend(point: np.ndarray, probability: np.ndarray, magnitude: np.ndarray, weight: float, margin: float) -> np.ndarray:
    point = np.asarray(point, dtype=float)
    probability = np.asarray(probability, dtype=float)
    magnitude = np.asarray(magnitude, dtype=float)
    if weight <= 0:
        return point.copy()
    direction = np.where(probability >= .5, 1.0, -1.0)
    active = np.abs(probability - .5) >= margin
    target = direction * np.maximum(magnitude, 0.0)
    return np.where(active, (1.0 - weight) * point + weight * target, point)


def _clustered_summary(improvement: np.ndarray, dates: np.ndarray) -> tuple[float, float, int, list[float]]:
    dates = np.asarray(dates)
    unique_dates = np.sort(np.unique(dates))
    daily = np.asarray([float(np.mean(improvement[dates == d])) for d in unique_dates], dtype=float)
    se = float(np.std(daily, ddof=1) / math.sqrt(len(daily))) if len(daily) > 1 else 0.0
    blocks = [b for b in np.array_split(unique_dates, 4) if len(b)]
    block_improvements = [float(np.mean(improvement[np.isin(dates, b)])) for b in blocks]
    return float(np.mean(improvement)), se, sum(x > 0 for x in block_improvements), block_improvements


def select_tail_guarded_directional_blend(
    actual: np.ndarray,
    point: np.ndarray,
    probability: np.ndarray,
    magnitude: np.ndarray,
    dates: np.ndarray,
) -> dict[str, Any]:
    """Select a blend that must help large moves and remain safe overall.

    Design principles:
    - calibration-only selection; holdout remains sealed;
    - large-move threshold is the calibration 75th percentile of |return|;
    - candidate must preserve positive all-row MAE evidence across time blocks;
    - candidate must improve tail MAE by more than one clustered standard error;
    - candidate cannot materially reduce tail directional accuracy;
    - among statistically similar candidates, prefer the smaller amplitude change.
    """
    actual = np.asarray(actual, dtype=float)
    point = np.asarray(point, dtype=float)
    probability = np.asarray(probability, dtype=float)
    magnitude = np.asarray(magnitude, dtype=float)
    dates = np.asarray(dates)

    baseline_loss = np.abs(actual - point)
    tail_threshold = float(np.quantile(np.abs(actual), .75))
    tail_mask = np.abs(actual) >= tail_threshold
    baseline_tail_direction = (
        float(np.mean(np.sign(actual[tail_mask]) == np.sign(point[tail_mask])))
        if tail_mask.any() else None
    )

    trials: list[dict[str, Any]] = []
    for margin in (.03, .05, .07, .10, .12, .15):
        for weight in (.10, .20, .30, .40, .50):
            candidate = _blend(point, probability, magnitude, weight, margin)
            improvement = baseline_loss - np.abs(actual - candidate)
            mean_imp, se, positive_blocks, block_imp = _clustered_summary(improvement, dates)

            tail_imp = improvement[tail_mask]
            tail_dates = dates[tail_mask]
            tail_mean, tail_se, tail_positive_blocks, tail_blocks = _clustered_summary(tail_imp, tail_dates)
            tail_direction = float(np.mean(np.sign(actual[tail_mask]) == np.sign(candidate[tail_mask])))
            dispersion_ratio = float(np.std(candidate) / max(np.std(actual), 1e-12))
            trials.append({
                "weight": weight,
                "probabilityMargin": margin,
                "meanPairedMAEImprovement": mean_imp,
                "pairedStandardError": se,
                "positiveChronologicalBlocks": positive_blocks,
                "chronologicalBlockImprovements": block_imp,
                "tailThreshold": tail_threshold,
                "tailMeanPairedMAEImprovement": tail_mean,
                "tailPairedStandardError": tail_se,
                "tailPositiveChronologicalBlocks": tail_positive_blocks,
                "tailChronologicalBlockImprovements": tail_blocks,
                "tailDirectionalAccuracy": tail_direction,
                "baselineTailDirectionalAccuracy": baseline_tail_direction,
                "dispersionRatio": dispersion_ratio,
                "medianAbsForecast": float(np.median(np.abs(candidate))),
            })

    eligible = [
        t for t in trials
        if t["positiveChronologicalBlocks"] >= 3
        and t["meanPairedMAEImprovement"] > max(0.0, .50 * t["pairedStandardError"])
        and t["tailPositiveChronologicalBlocks"] >= 3
        and t["tailMeanPairedMAEImprovement"] > max(0.0, t["tailPairedStandardError"])
        and (
            baseline_tail_direction is None
            or t["tailDirectionalAccuracy"] >= baseline_tail_direction - .005
        )
        and t["dispersionRatio"] <= 1.05
    ]

    if not eligible:
        return {
            "status": "ABSTAIN",
            "method": "V40_TAIL_GUARDED_DIRECTIONAL_MAGNITUDE_BLEND",
            "weight": 0.0,
            "probabilityMargin": 1.0,
            "baselineMAE": float(np.mean(baseline_loss)),
            "selectedMAE": float(np.mean(baseline_loss)),
            "meanPairedMAEImprovement": 0.0,
            "pairedStandardError": 0.0,
            "positiveChronologicalBlocks": 0,
            "tailThreshold": tail_threshold,
            "tailMeanPairedMAEImprovement": 0.0,
            "tailPairedStandardError": 0.0,
            "tailPositiveChronologicalBlocks": 0,
            "baselineTailDirectionalAccuracy": baseline_tail_direction,
            "candidateCount": len(trials),
            "eligibleCount": 0,
            "sealedLabelsUsed": 0,
        }

    # Primary objective: tail recovery. Secondary: ordinary-case MAE. We keep
    # smaller blend weights when candidates are statistically indistinguishable.
    best = max(
        eligible,
        key=lambda t: (
            t["tailMeanPairedMAEImprovement"] + .35 * t["meanPairedMAEImprovement"],
            -t["weight"],
            t["probabilityMargin"],
        ),
    )
    tolerance = max(best["tailPairedStandardError"], 1e-12)
    near = [
        t for t in eligible
        if t["tailMeanPairedMAEImprovement"] >= best["tailMeanPairedMAEImprovement"] - tolerance
    ]
    selected = min(near, key=lambda t: (t["weight"], -t["probabilityMargin"]))
    selected_prediction = _blend(
        point, probability, magnitude,
        float(selected["weight"]), float(selected["probabilityMargin"]),
    )
    return {
        "status": "ACTIVE",
        "method": "V40_TAIL_GUARDED_DIRECTIONAL_MAGNITUDE_BLEND",
        **selected,
        "baselineMAE": float(np.mean(baseline_loss)),
        "selectedMAE": float(np.mean(np.abs(actual - selected_prediction))),
        "candidateCount": len(trials),
        "eligibleCount": len(eligible),
        "sealedLabelsUsed": 0,
    }
