"""Leakage-safe conditional tail-amplitude challenger for VMEWS forecasts.

The V13 conditional-median core remains the champion.  This module adds a
small, sign-preserving amplitude overlay only when the existing direction and
magnitude models agree strongly and the learned absolute move is materially
larger than the champion point.  Candidate parameters are selected on the
maturity-purged calibration partition and promoted only after a sealed
chronological holdout comparison.

The overlay is deliberately conservative:
* it never flips a forecast direction;
* it never uses same/future-session outcomes at inference time;
* it may abstain independently at every horizon;
* promotion requires improvement in executable MAE and large-move MAE,
  chronological stability, and non-degraded Q20-Q80 coverage.
"""
from __future__ import annotations

import math
import os
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error

VERSION = "VMEWS-TAIL-AMPLITUDE-40.0"


def _partition_calibration(panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    label = f"target{horizon}"
    maturity = f"maturity{horizon}"
    eligible = panel.loc[panel[label].notna() & panel[maturity].notna()].copy()
    unique_dates = np.sort(eligible["date"].unique())
    holdout_days = int(os.environ.get("V13_HOLDOUT_DAYS", "120"))
    calibration_days = int(os.environ.get("V13_CALIBRATION_DAYS", "100"))
    calibration_start = unique_dates[-(holdout_days + calibration_days)]
    holdout_start = unique_dates[-holdout_days]
    return eligible.loc[
        (eligible["date"] >= calibration_start)
        & (eligible["date"] < holdout_start)
        & (eligible[maturity] < holdout_start)
    ].copy()


def tail_amplitude_overlay(
    prediction: np.ndarray,
    probability: np.ndarray,
    magnitude: np.ndarray,
    volatility: np.ndarray,
    parameters: dict[str, float],
) -> tuple[np.ndarray, np.ndarray]:
    """Expand only high-conviction, magnitude-confirmed points without sign flips."""
    base = np.asarray(prediction, dtype=float)
    probability = np.asarray(probability, dtype=float)
    magnitude = np.maximum(np.asarray(magnitude, dtype=float), 0.0)
    volatility = np.maximum(np.asarray(volatility, dtype=float), .004)
    base_abs = np.abs(base)
    direction = np.sign(base)
    classifier_direction = np.sign(probability - .5)
    safe_denominator = np.maximum(base_abs, .02 * volatility)
    magnitude_ratio = magnitude / safe_denominator
    point_strength = base_abs / volatility
    active = (
        (direction != 0)
        & (direction == classifier_direction)
        & (np.abs(probability - .5) >= float(parameters["probabilityMargin"]))
        & (point_strength >= float(parameters["minimumPointVolatilityRatio"]))
        & (magnitude_ratio >= float(parameters["magnitudeRatioFloor"]))
        & (magnitude > base_abs)
    )
    capped_target = np.minimum(
        magnitude,
        float(parameters["maxExpansionRatio"]) * np.maximum(base_abs, .03 * volatility),
    )
    expanded_abs = base_abs + float(parameters["weight"]) * np.maximum(capped_target - base_abs, 0.0)
    candidate = np.where(active, direction * expanded_abs, base)
    return candidate, active


def _executable_returns(
    market_model: Any,
    rows: pd.DataFrame,
    prediction: np.ndarray,
    probability: np.ndarray,
    volatility: np.ndarray,
    horizon: int,
) -> tuple[np.ndarray, np.ndarray]:
    closes = rows["close"].to_numpy(dtype=float)
    venues = rows["exchange"].astype(str).to_numpy()
    prices = np.asarray(
        [
            market_model.tradable_forecast(close, point, prob, vol, horizon, venue)
            for close, point, prob, vol, venue in zip(
                closes, prediction, probability, volatility, venues
            )
        ],
        dtype=float,
    )
    return np.log(prices / closes), prices


def _paired_candidate_audit(
    actual: np.ndarray,
    baseline: np.ndarray,
    candidate: np.ndarray,
    dates: np.ndarray,
) -> dict[str, Any]:
    improvement = np.abs(actual - baseline) - np.abs(actual - candidate)
    unique_dates = np.sort(np.unique(dates))
    daily = np.asarray(
        [float(np.mean(improvement[dates == day])) for day in unique_dates], dtype=float
    )
    blocks = [block for block in np.array_split(unique_dates, 4) if len(block)]
    block_improvements = [
        float(np.mean(improvement[np.isin(dates, block)])) for block in blocks
    ]
    return {
        "meanImprovement": float(np.mean(improvement)),
        "dailyStandardError": (
            float(np.std(daily, ddof=1) / math.sqrt(len(daily))) if len(daily) > 1 else 0.0
        ),
        "positiveSessions": int(np.sum(daily > 0)),
        "sessions": int(len(daily)),
        "positiveChronologicalBlocks": sum(value > 0 for value in block_improvements),
        "chronologicalBlockImprovements": block_improvements,
    }


def _large_move_comparison(
    actual: np.ndarray,
    baseline: np.ndarray,
    candidate: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    mask = np.abs(actual) >= threshold
    if not mask.any():
        return {"observations": 0, "baselineMAE": None, "candidateMAE": None, "relativeImprovement": None}
    baseline_mae = float(mean_absolute_error(actual[mask], baseline[mask]))
    candidate_mae = float(mean_absolute_error(actual[mask], candidate[mask]))
    return {
        "observations": int(mask.sum()),
        "threshold": float(threshold),
        "baselineMAE": baseline_mae,
        "candidateMAE": candidate_mae,
        "relativeImprovement": (baseline_mae - candidate_mae) / max(baseline_mae, 1e-12),
        "directionalAccuracy": float(np.mean(np.sign(actual[mask]) == np.sign(candidate[mask]))),
    }


def _candidate_grid() -> list[dict[str, float]]:
    output: list[dict[str, float]] = []
    for margin in (.05, .08, .12):
        for ratio_floor in (1.35, 1.70, 2.10):
            for minimum_point in (.03, .06):
                for weight in (.20, .35, .50, .65):
                    output.append(
                        {
                            "probabilityMargin": margin,
                            "magnitudeRatioFloor": ratio_floor,
                            "minimumPointVolatilityRatio": minimum_point,
                            "weight": weight,
                            "maxExpansionRatio": 2.25,
                        }
                    )
    return output


def _select_on_calibration(
    market_model: Any,
    result: Any,
    calibration: pd.DataFrame,
    horizon: int,
    original_predict: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    features = calibration[market_model.FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    volatility = calibration["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
    actual = calibration[f"target{horizon}"].to_numpy(dtype=float)
    dates = calibration["date"].dt.strftime("%Y-%m-%d").to_numpy()
    base, _, magnitude, probability = original_predict(
        result, features, volatility, calibration["date"], use_inference=False
    )
    base_exec, _ = _executable_returns(
        market_model, calibration, base, probability, volatility, horizon
    )
    tail_threshold = float(np.quantile(np.abs(actual), .75))
    base_mae = float(mean_absolute_error(actual, base_exec))
    trials: list[dict[str, Any]] = []
    for parameters in _candidate_grid():
        candidate, active = tail_amplitude_overlay(
            base, probability, magnitude, volatility, parameters
        )
        candidate_exec, _ = _executable_returns(
            market_model, calibration, candidate, probability, volatility, horizon
        )
        paired = _paired_candidate_audit(actual, base_exec, candidate_exec, dates)
        large_move = _large_move_comparison(
            actual, base_exec, candidate_exec, tail_threshold
        )
        candidate_mae = float(mean_absolute_error(actual, candidate_exec))
        relative_improvement = (base_mae - candidate_mae) / max(base_mae, 1e-12)
        trial = {
            "parameters": parameters,
            "activationShare": float(np.mean(active)),
            "baselineExecutableMAE": base_mae,
            "candidateExecutableMAE": candidate_mae,
            "relativeExecutableMAEImprovement": relative_improvement,
            "largeMove": large_move,
            "paired": paired,
        }
        trials.append(trial)
    eligible = [
        trial
        for trial in trials
        if .003 <= trial["activationShare"] <= .30
        and trial["paired"]["positiveChronologicalBlocks"] >= 3
        and trial["paired"]["meanImprovement"] > .50 * trial["paired"]["dailyStandardError"]
        and trial["relativeExecutableMAEImprovement"] > 0
        and float((trial["largeMove"] or {}).get("relativeImprovement") or -1.0) > .005
    ]
    if not eligible:
        return {
            "status": "ABSTAIN",
            "method": "CALIBRATION_ONLY_CONDITIONAL_TAIL_EXPANSION",
            "candidateCount": len(trials),
            "eligibleCount": 0,
            "tailThreshold": tail_threshold,
            "sealedLabelsUsed": 0,
        }, {
            "base": base,
            "magnitude": magnitude,
            "probability": probability,
            "volatility": volatility,
            "actual": actual,
            "dates": dates,
        }
    best = max(
        eligible,
        key=lambda trial: (
            trial["relativeExecutableMAEImprovement"]
            + .35 * float(trial["largeMove"]["relativeImprovement"]),
            -trial["parameters"]["weight"],
            trial["parameters"]["probabilityMargin"],
        ),
    )
    selection = {
        "status": "SELECTED_FOR_SEALED_TEST",
        "method": "CALIBRATION_ONLY_CONDITIONAL_TAIL_EXPANSION",
        "candidateCount": len(trials),
        "eligibleCount": len(eligible),
        "tailThreshold": tail_threshold,
        "parameters": best["parameters"],
        "activationShare": best["activationShare"],
        "relativeExecutableMAEImprovement": best["relativeExecutableMAEImprovement"],
        "largeMove": best["largeMove"],
        "paired": best["paired"],
        "sealedLabelsUsed": 0,
    }
    return selection, {
        "base": base,
        "magnitude": magnitude,
        "probability": probability,
        "volatility": volatility,
        "actual": actual,
        "dates": dates,
    }


def _evaluate_holdout(
    market_model: Any,
    result: Any,
    horizon: int,
    selection: dict[str, Any],
    calibration_state: dict[str, Any],
) -> dict[str, Any]:
    rows = result.rows
    actual = rows[f"target{horizon}"].to_numpy(dtype=float)
    dates = rows["date"].dt.strftime("%Y-%m-%d").to_numpy()
    volatility = rows["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
    base = np.asarray(result.holdout_prediction, dtype=float)
    magnitude = np.asarray(result.holdout_magnitude, dtype=float)
    probability = np.asarray(result.holdout_probability, dtype=float)
    parameters = selection["parameters"]
    candidate, active = tail_amplitude_overlay(
        base, probability, magnitude, volatility, parameters
    )
    base_exec, _ = _executable_returns(
        market_model, rows, base, probability, volatility, horizon
    )
    candidate_exec, candidate_prices = _executable_returns(
        market_model, rows, candidate, probability, volatility, horizon
    )
    base_exec_mae = float(mean_absolute_error(actual, base_exec))
    candidate_exec_mae = float(mean_absolute_error(actual, candidate_exec))
    exec_improvement = (base_exec_mae - candidate_exec_mae) / max(base_exec_mae, 1e-12)
    paired = _paired_candidate_audit(actual, base_exec, candidate_exec, dates)
    large_move = _large_move_comparison(
        actual, base_exec, candidate_exec, float(selection["tailThreshold"])
    )

    calibration_candidate, _ = tail_amplitude_overlay(
        calibration_state["base"],
        calibration_state["probability"],
        calibration_state["magnitude"],
        calibration_state["volatility"],
        parameters,
    )
    normalized_residual = (
        calibration_state["actual"] - calibration_candidate
    ) / np.maximum(calibration_state["volatility"], .004)
    quantile_low = float(np.quantile(normalized_residual, .20))
    quantile_high = float(np.quantile(normalized_residual, .80))
    low = candidate + quantile_low * volatility
    high = candidate + quantile_high * volatility
    coverage = float(np.mean((actual >= low) & (actual <= high)))
    base_coverage = float(result.holdout.get("coverage20_80") or 0.0)
    candidate_metrics = market_model._metrics(actual, candidate, dates, probability)
    base_continuous_mae = float(result.holdout.get("mae") or mean_absolute_error(actual, base))
    continuous_improvement = (
        base_continuous_mae - candidate_metrics["mae"]
    ) / max(base_continuous_mae, 1e-12)
    activation_share = float(np.mean(active))
    magnitude_skill = float(result.holdout.get("magnitudeMAESkill") or -1.0)
    promote = bool(
        magnitude_skill > 0
        and activation_share <= .30
        and exec_improvement >= .005
        and continuous_improvement >= -.002
        and float(large_move.get("relativeImprovement") or -1.0) >= .02
        and paired["positiveChronologicalBlocks"] >= 3
        and paired["meanImprovement"] > paired["dailyStandardError"]
        and coverage >= max(.50, base_coverage - .015)
        and float(candidate_metrics.get("maeSkill") or -1.0) > 0
    )
    return {
        "status": "PASS" if promote else "NO_PROMOTION",
        "version": VERSION,
        "method": "SEALED_CHRONOLOGICAL_HOLDOUT_AFTER_CALIBRATION_SELECTION",
        "parameters": parameters,
        "activationShare": activation_share,
        "baselineExecutableMAE": base_exec_mae,
        "candidateExecutableMAE": candidate_exec_mae,
        "relativeExecutableMAEImprovement": exec_improvement,
        "continuousMAEImprovement": continuous_improvement,
        "largeMove": large_move,
        "paired": paired,
        "baselineCoverage20_80": base_coverage,
        "candidateCoverage20_80": coverage,
        "quantile20": quantile_low,
        "quantile80": quantile_high,
        "magnitudeMAESkill": magnitude_skill,
        "promotionRule": "magnitude skill >0; executable MAE >=0.5% better; tail MAE >=2% better; continuous MAE no worse than 0.2%; >=3/4 chronological blocks; paired gain > clustered daily SE; Q20-Q80 coverage no worse by >1.5pp and >=50%; candidate point retains positive no-change skill",
        "futureLabelsUsedForSelection": 0,
        "candidatePrediction": candidate,
        "candidateExecutableReturn": candidate_exec,
        "candidateExecutablePrice": candidate_prices,
        "candidateMetrics": candidate_metrics,
    }


def _activate_result(market_model: Any, result: Any, holdout_audit: dict[str, Any]) -> None:
    """Promote the sealed winner and refresh the metrics used by release gates."""
    horizon = result.horizon
    rows = result.rows
    actual = rows[f"target{horizon}"].to_numpy(dtype=float)
    dates = rows["date"].dt.strftime("%Y-%m-%d").to_numpy()
    probability = np.asarray(result.holdout_probability, dtype=float)
    volatility = rows["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
    candidate = np.asarray(holdout_audit.pop("candidatePrediction"), dtype=float)
    executable = np.asarray(holdout_audit.pop("candidateExecutableReturn"), dtype=float)
    executable_prices = np.asarray(holdout_audit.pop("candidateExecutablePrice"), dtype=float)
    candidate_metrics = dict(holdout_audit.pop("candidateMetrics"))
    old = dict(result.holdout)
    candidate_metrics["coverage20_80"] = float(holdout_audit["candidateCoverage20_80"])
    candidate_metrics["medianIntervalWidth"] = float(
        np.median((holdout_audit["quantile80"] - holdout_audit["quantile20"]) * volatility)
    )
    candidate_metrics["conditionalMedianMAE"] = old.get("conditionalMedianMAE")
    candidate_metrics["directionalBlendMAEImprovement"] = float(
        (old.get("conditionalMedianMAE") or candidate_metrics["mae"]) - candidate_metrics["mae"]
    )
    candidate_metrics["directionalBlendWeight"] = old.get("directionalBlendWeight")
    candidate_metrics["directionalBlendProbabilityMargin"] = old.get("directionalBlendProbabilityMargin")
    for key in (
        "magnitudeMAE", "magnitudeBaselineMAE", "magnitudeMAESkill",
        "medianExpectedAbsMove", "magnitudeScale", "magnitudeCalibrationRatio",
        "invalidExecutableQuotes", "architecture", "marketRegimeStatus",
        "regimeArchitectureStatus", "futureRowsUsedForTraining",
        "futureLabelsUsedForCalibration", "maturityEmbargoSessions",
        "selectionFrozenBeforeHoldout", "dateStart", "dateEnd",
    ):
        if key in old:
            candidate_metrics[key] = old[key]
    candidate_metrics["executableMAE"] = float(mean_absolute_error(actual, executable))
    candidate_metrics["executableMAESkill"] = 1.0 - candidate_metrics["executableMAE"] / max(candidate_metrics["baselineMAE"], 1e-12)
    candidate_metrics["executableMedianAbs"] = float(np.median(np.abs(executable)))
    venues = rows["exchange"].astype(str).to_numpy()
    candidate_metrics["medianExecutableTicks"] = float(
        np.median(
            np.abs(executable_prices - rows["close"].to_numpy(dtype=float))
            / np.asarray([market_model.tick_size(price, venue) for price, venue in zip(executable_prices, venues)])
        )
    )
    candidate_metrics["pointToRealizedMoveRatio"] = float(
        candidate_metrics["executableMedianAbs"] / max(candidate_metrics["realizedMedianAbs"], 1e-12)
    )
    candidate_metrics["pairedNoChangeAudit"] = market_model.paired_no_change_audit(
        actual, executable, dates
    )
    threshold = float(holdout_audit["largeMove"]["threshold"])
    tail_mask = np.abs(actual) >= threshold
    candidate_metrics["largeMoveAudit"] = {
        "method": "CALIBRATION_75TH_PERCENTILE_ABSOLUTE_RETURN_THRESHOLD_WITH_V40_OVERLAY",
        "threshold": threshold,
        "observations": int(tail_mask.sum()),
        "directionalAccuracy": float(np.mean(np.sign(actual[tail_mask]) == np.sign(executable[tail_mask]))) if tail_mask.any() else None,
        "mae": float(mean_absolute_error(actual[tail_mask], executable[tail_mask])) if tail_mask.any() else None,
        "baselineMAE": float(np.mean(np.abs(actual[tail_mask]))) if tail_mask.any() else None,
        "maeSkill": (
            1.0 - float(mean_absolute_error(actual[tail_mask], executable[tail_mask])) / max(float(np.mean(np.abs(actual[tail_mask]))), 1e-12)
            if tail_mask.any() else None
        ),
        "thresholdSelectedBeforeHoldout": True,
    }
    old_folds = old.get("chronologicalFolds") or []
    chronological_folds: list[dict[str, Any]] = []
    for index, fold_days in enumerate(np.array_split(np.sort(rows["date"].unique()), 4)):
        if not len(fold_days):
            continue
        mask = rows["date"].isin(fold_days).to_numpy()
        fold_metrics = market_model._metrics(actual[mask], candidate[mask], dates[mask], probability[mask])
        item = dict(old_folds[index] if index < len(old_folds) else {})
        item.update(
            {
                "start": str(pd.Timestamp(fold_days[0]).date()),
                "end": str(pd.Timestamp(fold_days[-1]).date()),
                "n": fold_metrics["n"],
                "maeSkill": fold_metrics["maeSkill"],
                "executableMAESkill": 1.0 - float(mean_absolute_error(actual[mask], executable[mask])) / max(fold_metrics["baselineMAE"], 1e-12),
                "rankIC": fold_metrics["rankIC"],
                "directionalAccuracy": fold_metrics["directionalAccuracy"],
            }
        )
        chronological_folds.append(item)
    candidate_metrics["chronologicalFolds"] = chronological_folds
    candidate_metrics["costAwareLongAudit"] = market_model.cost_aware_long_audit(
        actual,
        executable,
        np.asarray(result.holdout_magnitude, dtype=float),
        dates,
        round_trip_cost_bps=float(os.environ.get("V20_ROUND_TRIP_COST_BPS", "35")),
    )
    candidate_metrics["tailAmplitudeChallenger"] = holdout_audit
    result.holdout = candidate_metrics
    result.holdout_prediction = candidate
    result.quantile_low = float(holdout_audit["quantile20"])
    result.quantile_high = float(holdout_audit["quantile80"])
    setattr(result, "_v40_tail_overlay", dict(holdout_audit["parameters"]))


def install(market_model: Any) -> None:
    """Install the challenger around V13 without changing the V13 source file."""
    if getattr(market_model, "_v40_tail_installed", False):
        return
    original_fit = market_model.fit_horizon
    original_predict = market_model.predict_horizon_core

    def predict_with_tail(result: Any, features: np.ndarray, volatility: np.ndarray, dates: Any, use_inference: bool = False):
        prediction, point, magnitude, probability = original_predict(
            result, features, volatility, dates, use_inference=use_inference
        )
        parameters = getattr(result, "_v40_tail_overlay", None)
        if parameters:
            prediction, _ = tail_amplitude_overlay(
                prediction, probability, magnitude, volatility, parameters
            )
        return prediction, point, magnitude, probability

    def fit_with_tail(panel: pd.DataFrame, horizon: int, fast: bool = False):
        result = original_fit(panel, horizon, fast=fast)
        calibration = _partition_calibration(panel, horizon)
        selection, calibration_state = _select_on_calibration(
            market_model, result, calibration, horizon, original_predict
        )
        result.calibration["tailAmplitudeChallenger"] = selection
        if selection.get("status") != "SELECTED_FOR_SEALED_TEST":
            result.holdout["tailAmplitudeChallenger"] = {
                "status": "ABSTAIN",
                "version": VERSION,
                "reason": "NO_CALIBRATION_CANDIDATE_PASSED_STABILITY_GATE",
            }
            return result
        holdout_audit = _evaluate_holdout(
            market_model, result, horizon, selection, calibration_state
        )
        if holdout_audit["status"] == "PASS":
            _activate_result(market_model, result, holdout_audit)
        else:
            for transient in (
                "candidatePrediction", "candidateExecutableReturn",
                "candidateExecutablePrice", "candidateMetrics",
            ):
                holdout_audit.pop(transient, None)
            result.holdout["tailAmplitudeChallenger"] = holdout_audit
        return result

    market_model.fit_horizon = fit_with_tail
    market_model.predict_horizon_core = predict_with_tail
    market_model._v40_tail_installed = True
