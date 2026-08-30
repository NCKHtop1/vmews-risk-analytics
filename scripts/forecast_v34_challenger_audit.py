#!/usr/bin/env python3
"""Leakage-safe challenger audit for economically useful T+1...T+5 points.

The production model is intentionally left untouched by this script.  It
measures whether a causal, online residual correction can recover a changing
market regime without using any outcome whose maturity is on or after the
forecast origin.  Hyperparameters are selected on the calibration partition;
the chronological holdout remains sealed until the final comparison.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from forecast_v13_market_model import (  # noqa: E402
    FEATURE_COLUMNS,
    _metrics,
    build_panel,
    fit_horizon,
    load_histories,
    load_signal_sources,
    predict_horizon_core,
)


@dataclass(frozen=True)
class CorrectionParameters:
    half_life: int
    market_weight: float
    symbol_weight: float
    volatility_clip: float = 1.0


def all_chronological_partitions(
    panel: pd.DataFrame, horizon: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Recreate the production calibration/holdout split exactly."""
    label = f"target{horizon}"
    maturity = f"maturity{horizon}"
    eligible = panel.loc[panel[label].notna() & panel[maturity].notna()].copy()
    unique_dates = np.sort(eligible["date"].unique())
    holdout_days = 120
    calibration_days = 100
    calibration_start = unique_dates[-(holdout_days + calibration_days)]
    holdout_start = unique_dates[-holdout_days]
    train = eligible.loc[
        (eligible["date"] < calibration_start)
        & (eligible[maturity] < calibration_start)
    ].copy()
    calibration = eligible.loc[
        (eligible["date"] >= calibration_start)
        & (eligible["date"] < holdout_start)
        & (eligible[maturity] < holdout_start)
    ].copy()
    holdout = eligible.loc[eligible["date"] >= holdout_start].copy()
    return train, calibration, holdout


def chronological_partitions(panel: pd.DataFrame, horizon: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    _, calibration, holdout = all_chronological_partitions(panel, horizon)
    return calibration, holdout


def base_predictions(result: Any, rows: pd.DataFrame, horizon: int) -> np.ndarray:
    features = rows[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    volatility = rows["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
    prediction, _, _, _ = predict_horizon_core(result, features, volatility, rows["date"])
    return prediction


def _weighted_average(values: list[float], half_life: int) -> float:
    if not values:
        return 0.0
    recent = np.asarray(values[-max(20, 6 * half_life):], dtype=float)
    age = np.arange(len(recent) - 1, -1, -1, dtype=float)
    weights = np.exp2(-age / max(1, half_life))
    return float(np.average(recent, weights=weights))


def causal_residual_correction(
    rows: pd.DataFrame,
    base_prediction: np.ndarray,
    horizon: int,
    parameters: CorrectionParameters,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Return origin-safe market plus issuer residual corrections.

    An origin-date residual becomes available only after its label maturity is
    strictly earlier than the next prediction origin.  This is deliberately
    stricter than allowing same-session closes to affect that session's quote.
    """
    frame = rows[["date", "symbol", "forward_vol", f"target{horizon}", f"maturity{horizon}"]].copy()
    frame["base"] = np.asarray(base_prediction, dtype=float)
    frame["residual"] = frame[f"target{horizon}"] - frame["base"]
    frame["_position"] = np.arange(len(frame))
    origins: list[dict[str, Any]] = []
    for origin, group in frame.groupby("date", sort=True, observed=True):
        origins.append(
            {
                "origin": pd.Timestamp(origin),
                "maturity": pd.Timestamp(group[f"maturity{horizon}"].max()),
                "market": float(group["residual"].median()),
                "symbols": dict(zip(group["symbol"].astype(str), group["residual"].astype(float))),
            }
        )

    output = np.zeros(len(frame), dtype=float)
    matured_market: list[float] = []
    matured_symbol: dict[str, list[float]] = {}
    next_origin = 0
    used_maturities = 0
    max_maturity_seen: pd.Timestamp | None = None
    for current_date, group in frame.groupby("date", sort=True, observed=True):
        current = pd.Timestamp(current_date)
        while next_origin < len(origins) and origins[next_origin]["maturity"] < current:
            available = origins[next_origin]
            matured_market.append(float(available["market"]))
            for symbol, residual in available["symbols"].items():
                matured_symbol.setdefault(symbol, []).append(float(residual))
            max_maturity_seen = available["maturity"]
            next_origin += 1
            used_maturities += 1

        market = _weighted_average(matured_market, parameters.half_life)
        positions = group["_position"].to_numpy(dtype=int)
        current_vol = group["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
        correction = np.full(len(group), parameters.market_weight * market, dtype=float)
        if parameters.symbol_weight > 0:
            symbol_estimates = np.asarray(
                [
                    _weighted_average(matured_symbol.get(str(symbol), []), parameters.half_life)
                    for symbol in group["symbol"]
                ],
                dtype=float,
            )
            correction += parameters.symbol_weight * (symbol_estimates - market)
        bound = parameters.volatility_clip * np.maximum(current_vol, .004)
        output[positions] = np.clip(correction, -bound, bound)

    return output, {
        "method": "CAUSAL_EWMA_MARKET_AND_ISSUER_RESIDUAL",
        "strictMaturityBeforeOrigin": True,
        "originGroupsMadeAvailable": used_maturities,
        "latestMaturityUsed": None if max_maturity_seen is None else str(max_maturity_seen.date()),
        "parameters": {
            "halfLifeSessions": parameters.half_life,
            "marketWeight": parameters.market_weight,
            "symbolWeight": parameters.symbol_weight,
            "volatilityClip": parameters.volatility_clip,
        },
    }


def causal_momentum_correction(
    rows: pd.DataFrame,
    base_prediction: np.ndarray,
    horizon: int,
    *,
    half_life: int,
    shrinkage: float,
    relative_weight: float,
    max_slope: float = .75,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Adapt continuation/reversal slopes using matured outcomes only."""
    columns = [
        "date", "symbol", "forward_vol", "market_ret5", "relative_ret5",
        f"target{horizon}", f"maturity{horizon}",
    ]
    frame = rows[columns].copy()
    frame["base"] = np.asarray(base_prediction, dtype=float)
    frame["residual"] = frame[f"target{horizon}"] - frame["base"]
    frame["_position"] = np.arange(len(frame))
    origins: list[dict[str, Any]] = []
    for origin, group in frame.groupby("date", sort=True, observed=True):
        relative_x = group["relative_ret5"].fillna(0).to_numpy(dtype=float)
        relative_y = group["residual"].to_numpy(dtype=float)
        denominator = float(np.dot(relative_x, relative_x))
        relative_slope = float(np.dot(relative_x, relative_y) / denominator) if denominator > 1e-10 else 0.0
        origins.append(
            {
                "maturity": pd.Timestamp(group[f"maturity{horizon}"].max()),
                "marketX": float(group["market_ret5"].median()),
                "marketY": float(group["residual"].median()),
                "relativeSlope": float(np.clip(relative_slope, -max_slope, max_slope)),
            }
        )

    available: list[dict[str, float]] = []
    output = np.zeros(len(frame), dtype=float)
    next_origin = 0
    slope_trace: list[dict[str, Any]] = []
    for current_date, group in frame.groupby("date", sort=True, observed=True):
        current = pd.Timestamp(current_date)
        while next_origin < len(origins) and origins[next_origin]["maturity"] < current:
            available.append(origins[next_origin])
            next_origin += 1
        recent = available[-max(20, 6 * half_life):]
        if len(recent) < max(8, horizon + 3):
            market_slope = 0.0
            relative_slope = 0.0
        else:
            age = np.arange(len(recent) - 1, -1, -1, dtype=float)
            weights = np.exp2(-age / max(1, half_life))
            market_x = np.asarray([item["marketX"] for item in recent], dtype=float)
            market_y = np.asarray([item["marketY"] for item in recent], dtype=float)
            denominator = float(np.sum(weights * np.square(market_x)))
            market_slope = float(np.sum(weights * market_x * market_y) / denominator) if denominator > 1e-10 else 0.0
            market_slope = float(np.clip(market_slope, -max_slope, max_slope))
            relative_slope = float(
                np.average([item["relativeSlope"] for item in recent], weights=weights)
            )
        market_slope *= shrinkage
        relative_slope *= shrinkage * relative_weight
        correction = (
            market_slope * group["market_ret5"].fillna(0).to_numpy(dtype=float)
            + relative_slope * group["relative_ret5"].fillna(0).to_numpy(dtype=float)
        )
        volatility = group["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
        positions = group["_position"].to_numpy(dtype=int)
        output[positions] = np.clip(correction, -volatility, volatility)
        slope_trace.append(
            {
                "date": str(current.date()),
                "marketSlope": market_slope,
                "relativeSlope": relative_slope,
                "maturedOrigins": len(available),
            }
        )
    return output, {
        "method": "CAUSAL_REGIME_ADAPTIVE_MARKET_AND_RELATIVE_MOMENTUM",
        "strictMaturityBeforeOrigin": True,
        "halfLifeSessions": half_life,
        "shrinkage": shrinkage,
        "relativeWeight": relative_weight,
        "maxSlope": max_slope,
        "latestSlopes": slope_trace[-5:],
    }


def select_dynamic_momentum(
    rows: pd.DataFrame,
    base_prediction: np.ndarray,
    horizon: int,
) -> tuple[dict[str, float], dict[str, Any]]:
    actual = rows[f"target{horizon}"].to_numpy(dtype=float)
    dates = rows["date"].dt.strftime("%Y-%m-%d").to_numpy()
    trials: list[dict[str, Any]] = []
    for half_life in (5, 10, 20, 40):
        for shrinkage in (.25, .50, .75, 1.0):
            for relative_weight in (0.0, .50, 1.0):
                correction, dynamic_audit = causal_momentum_correction(
                    rows,
                    base_prediction,
                    horizon,
                    half_life=half_life,
                    shrinkage=shrinkage,
                    relative_weight=relative_weight,
                )
                candidate = base_prediction + correction
                paired = _paired_audit(actual, base_prediction, candidate, dates)
                candidate_metrics = _metrics(actual, candidate, dates)
                trials.append(
                    {
                        "parameters": {
                            "halfLifeSessions": half_life,
                            "shrinkage": shrinkage,
                            "relativeWeight": relative_weight,
                        },
                        "audit": dynamic_audit,
                        **paired,
                        "mae": candidate_metrics["mae"],
                        "maeSkill": candidate_metrics["maeSkill"],
                    }
                )
    eligible = [
        trial
        for trial in trials
        if trial["positiveChronologicalBlocks"] >= 3
        and trial["meanPairedMAEImprovement"] > trial["pairedStandardError"]
    ]
    if not eligible:
        parameters = {"halfLifeSessions": 20, "shrinkage": 0.0, "relativeWeight": 0.0}
        return parameters, {
            "status": "ABSTAIN", "parameters": parameters,
            "candidateCount": len(trials), "eligibleCount": 0, "sealedLabelsUsed": 0,
        }
    selected = min(eligible, key=lambda item: item["mae"])
    return selected["parameters"], {
        "status": "ACTIVE",
        **{key: value for key, value in selected.items() if key not in {"audit"}},
        "candidateCount": len(trials),
        "eligibleCount": len(eligible),
        "sealedLabelsUsed": 0,
    }


def _paired_audit(
    actual: np.ndarray,
    baseline: np.ndarray,
    candidate: np.ndarray,
    dates: np.ndarray,
) -> dict[str, Any]:
    improvement = np.abs(actual - baseline) - np.abs(actual - candidate)
    unique_dates = np.sort(np.unique(dates))
    blocks = [block for block in np.array_split(unique_dates, 4) if len(block)]
    block_improvements = [
        float(np.mean(improvement[np.isin(dates, block)])) for block in blocks
    ]
    standard_error = float(np.std(improvement, ddof=1) / math.sqrt(len(improvement)))
    return {
        "meanPairedMAEImprovement": float(np.mean(improvement)),
        "pairedStandardError": standard_error,
        "positiveChronologicalBlocks": sum(value > 0 for value in block_improvements),
        "chronologicalBlockImprovements": block_improvements,
    }


def momentum_challenger(
    calibration: pd.DataFrame,
    holdout: pd.DataFrame,
    calibration_base: np.ndarray,
    holdout_base: np.ndarray,
    horizon: int,
) -> dict[str, Any]:
    """Test pre-specified continuation/reversal overlays without holdout tuning."""
    signal_names = ("ret1", "ret3", "ret5", "ret10", "ret20", "market_ret5", "relative_ret5")
    cal_y = calibration[f"target{horizon}"].to_numpy(dtype=float)
    hold_y = holdout[f"target{horizon}"].to_numpy(dtype=float)
    cal_dates = calibration["date"].dt.strftime("%Y-%m-%d").to_numpy()
    hold_dates = holdout["date"].dt.strftime("%Y-%m-%d").to_numpy()
    trials: list[dict[str, Any]] = []
    for signal_name in signal_names:
        cal_signal = calibration[signal_name].fillna(0).to_numpy(dtype=float)
        hold_signal = holdout[signal_name].fillna(0).to_numpy(dtype=float)
        for alpha in np.linspace(-.50, .50, 21):
            cal_candidate = calibration_base + float(alpha) * cal_signal
            cal_paired = _paired_audit(cal_y, calibration_base, cal_candidate, cal_dates)
            trials.append(
                {
                    "signal": signal_name,
                    "alpha": float(alpha),
                    "calibrationMAE": float(np.mean(np.abs(cal_y - cal_candidate))),
                    "calibrationPaired": cal_paired,
                    "holdoutSignal": hold_signal,
                }
            )
    eligible = [
        trial
        for trial in trials
        if trial["calibrationPaired"]["positiveChronologicalBlocks"] >= 3
        and trial["calibrationPaired"]["meanPairedMAEImprovement"]
        > trial["calibrationPaired"]["pairedStandardError"]
    ]
    if not eligible:
        return {"status": "ABSTAIN", "candidateCount": len(trials), "sealedLabelsUsedForSelection": 0}
    selected = min(eligible, key=lambda item: item["calibrationMAE"])
    candidate = holdout_base + selected["alpha"] * selected["holdoutSignal"]
    baseline_metrics = _metrics(hold_y, holdout_base, hold_dates)
    candidate_metrics = _metrics(hold_y, candidate, hold_dates)
    paired = _paired_audit(hold_y, holdout_base, candidate, hold_dates)
    return {
        "status": "ACTIVE",
        "signal": selected["signal"],
        "alpha": selected["alpha"],
        "calibrationPaired": selected["calibrationPaired"],
        "sealedMAESkillDelta": candidate_metrics["maeSkill"] - baseline_metrics["maeSkill"],
        "sealedDirectionDelta": (candidate_metrics["directionalAccuracy"] or 0.0)
        - (baseline_metrics["directionalAccuracy"] or 0.0),
        "sealedPaired": paired,
        "sealedMoveRatio": candidate_metrics["medianForecastAbs"]
        / max(candidate_metrics["realizedMedianAbs"], 1e-12),
        "candidateCount": len(trials),
        "sealedLabelsUsedForSelection": 0,
    }


def recent_training_challenger(
    panel: pd.DataFrame,
    horizon: int,
    *,
    fast: bool,
) -> dict[str, Any]:
    """Choose model recency/loss on calibration, then open the sealed holdout."""
    train, calibration, holdout = all_chronological_partitions(panel, horizon)
    label = f"target{horizon}"
    cal_y = calibration[label].to_numpy(dtype=float)
    hold_y = holdout[label].to_numpy(dtype=float)
    cal_x = calibration[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    hold_x = holdout[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    cal_vol = calibration["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
    hold_vol = holdout["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
    cal_dates = calibration["date"].dt.strftime("%Y-%m-%d").to_numpy()
    hold_dates = holdout["date"].dt.strftime("%Y-%m-%d").to_numpy()
    train_dates = np.sort(train["date"].unique())
    trials: list[dict[str, Any]] = []
    configurations = [
        ("absolute_error", 504, None),
        ("absolute_error", 756, None),
        ("absolute_error", 1008, None),
        ("absolute_error", None, 252),
        ("absolute_error", None, 504),
        ("squared_error", 504, None),
        ("squared_error", 756, None),
        ("squared_error", 1008, None),
        ("squared_error", None, 252),
        ("squared_error", None, 504),
    ]
    for trial_index, (loss, window_days, half_life) in enumerate(configurations):
        if window_days is None:
            fitted = train
        else:
            cutoff = train_dates[-min(window_days, len(train_dates))]
            fitted = train.loc[train["date"] >= cutoff]
        train_x = fitted[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        train_vol = fitted["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
        train_y = fitted[label].to_numpy(dtype=float)
        sample_weight = None
        if half_life is not None:
            date_positions = {date: position for position, date in enumerate(train_dates)}
            age = np.asarray(
                [len(train_dates) - 1 - date_positions[value] for value in fitted["date"].to_numpy()],
                dtype=float,
            )
            sample_weight = np.exp2(-age / half_life)
        model = HistGradientBoostingRegressor(
            loss=loss,
            learning_rate=.06,
            max_iter=55 if fast else 110,
            max_leaf_nodes=23,
            min_samples_leaf=180,
            l2_regularization=10.0,
            max_bins=128,
            early_stopping=False,
            random_state=7400 + 100 * horizon + trial_index,
        )
        model.fit(
            train_x,
            np.clip(train_y / np.maximum(train_vol, .004), -4.0, 4.0),
            sample_weight=sample_weight,
        )
        cal_raw = model.predict(cal_x) * cal_vol
        scale_trials = []
        for scale in np.linspace(.10, 1.60, 31):
            candidate = cal_raw * scale
            paired = _paired_audit(cal_y, np.zeros_like(cal_y), candidate, cal_dates)
            scale_trials.append(
                {
                    "scale": float(scale),
                    "mae": float(np.mean(np.abs(cal_y - candidate))),
                    "paired": paired,
                }
            )
        eligible_scales = [
            item for item in scale_trials
            if item["paired"]["positiveChronologicalBlocks"] >= 3
            and item["paired"]["meanPairedMAEImprovement"] > item["paired"]["pairedStandardError"]
        ]
        selected_scale = min(eligible_scales or scale_trials, key=lambda item: item["mae"])
        cal_prediction = cal_raw * selected_scale["scale"]
        cal_metrics = _metrics(cal_y, cal_prediction, cal_dates)
        trials.append(
            {
                "loss": loss,
                "windowDays": window_days,
                "halfLifeSessions": half_life,
                "trainingRows": len(fitted),
                "scale": selected_scale["scale"],
                "calibration": cal_metrics,
                "calibrationPairedVsZero": selected_scale["paired"],
                "model": model,
            }
        )
    eligible_models = [
        trial for trial in trials
        if trial["calibrationPairedVsZero"]["positiveChronologicalBlocks"] >= 3
        and trial["calibrationPairedVsZero"]["meanPairedMAEImprovement"]
        > trial["calibrationPairedVsZero"]["pairedStandardError"]
    ]
    selected = min(eligible_models or trials, key=lambda item: item["calibration"]["mae"])
    hold_prediction = selected["model"].predict(hold_x) * hold_vol * selected["scale"]
    hold_metrics = _metrics(hold_y, hold_prediction, hold_dates)
    paired_vs_zero = _paired_audit(hold_y, np.zeros_like(hold_y), hold_prediction, hold_dates)
    fpt_latest = holdout["symbol"].eq("FPT") & holdout["date"].eq(holdout["date"].max())
    serializable_trials = [
        {key: value for key, value in trial.items() if key != "model"}
        for trial in sorted(trials, key=lambda item: item["calibration"]["mae"])[:5]
    ]
    return {
        "status": "ACTIVE" if eligible_models else "REVIEW",
        "selection": {key: value for key, value in selected.items() if key != "model"},
        "topCalibrationTrials": serializable_trials,
        "sealed": hold_metrics,
        "sealedPairedVsZero": paired_vs_zero,
        "sealedPositiveVsZero": bool(
            paired_vs_zero["positiveChronologicalBlocks"] >= 3
            and paired_vs_zero["meanPairedMAEImprovement"] > paired_vs_zero["pairedStandardError"]
        ),
        "fptLatestReturn": None
        if not fpt_latest.any()
        else float(hold_prediction[fpt_latest.to_numpy()][0]),
        "sealedLabelsUsedForSelection": 0,
    }


def hierarchical_issuer_challenger(
    panel: pd.DataFrame,
    result: Any,
    horizon: int,
) -> dict[str, Any]:
    """Model the market level and each issuer's relative return separately."""
    train, calibration, holdout = all_chronological_partitions(panel, horizon)
    label = f"target{horizon}"
    compact_features = [
        name for name in FEATURE_COLUMNS
        if name not in {"day_of_week"}
        and not name.startswith(("news_", "flow_", "fund_"))
    ]
    market_features = [
        "market_ret1", "market_ret5", "market_ret20", "market_vol20",
        "breadth1", "breadth5", "breadth20", "day_of_week",
    ]

    train_market_target = train.groupby("date", observed=True)[label].transform("median")
    cal_market_target = calibration.groupby("date", observed=True)[label].transform("median")
    hold_market_target = holdout.groupby("date", observed=True)[label].transform("median")
    train_relative = train[label].to_numpy(dtype=float) - train_market_target.to_numpy(dtype=float)

    market_train = train.groupby("date", sort=True, observed=True).first()
    market_cal = calibration.groupby("date", sort=True, observed=True).first()
    market_hold = holdout.groupby("date", sort=True, observed=True).first()
    market_train_y = train.groupby("date", sort=True, observed=True)[label].median().to_numpy(dtype=float)
    market_scaler = StandardScaler()
    market_train_x = market_scaler.fit_transform(market_train[market_features].fillna(0))
    market_model = Ridge(alpha=20.0)
    market_model.fit(market_train_x, market_train_y)
    cal_market_by_date = dict(
        zip(market_cal.index, market_model.predict(market_scaler.transform(market_cal[market_features].fillna(0))))
    )
    hold_market_by_date = dict(
        zip(market_hold.index, market_model.predict(market_scaler.transform(market_hold[market_features].fillna(0))))
    )
    cal_market_prediction = calibration["date"].map(cal_market_by_date).to_numpy(dtype=float)
    hold_market_prediction = holdout["date"].map(hold_market_by_date).to_numpy(dtype=float)

    global_scaler = StandardScaler()
    train_x = global_scaler.fit_transform(train[compact_features].fillna(0))
    cal_x = global_scaler.transform(calibration[compact_features].fillna(0))
    hold_x = global_scaler.transform(holdout[compact_features].fillna(0))
    train_vol = train["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
    cal_vol = calibration["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
    hold_vol = holdout["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
    normalized_relative = np.clip(train_relative / np.maximum(train_vol, .004), -4.0, 4.0)
    cal_relative_prediction = np.zeros(len(calibration), dtype=float)
    hold_relative_prediction = np.zeros(len(holdout), dtype=float)
    fitted_symbols = 0
    for symbol in sorted(set(train["symbol"]) & set(calibration["symbol"]) & set(holdout["symbol"])):
        train_mask = train["symbol"].eq(symbol).to_numpy()
        cal_mask = calibration["symbol"].eq(symbol).to_numpy()
        hold_mask = holdout["symbol"].eq(symbol).to_numpy()
        if int(train_mask.sum()) < 500:
            continue
        issuer_model = Ridge(alpha=40.0)
        issuer_model.fit(train_x[train_mask], normalized_relative[train_mask])
        cal_relative_prediction[cal_mask] = issuer_model.predict(cal_x[cal_mask]) * cal_vol[cal_mask]
        hold_relative_prediction[hold_mask] = issuer_model.predict(hold_x[hold_mask]) * hold_vol[hold_mask]
        fitted_symbols += 1
    cal_relative_prediction -= (
        pd.Series(cal_relative_prediction, index=calibration.index)
        .groupby(calibration["date"], observed=True)
        .transform("median")
        .to_numpy(dtype=float)
    )
    hold_relative_prediction -= (
        pd.Series(hold_relative_prediction, index=holdout.index)
        .groupby(holdout["date"], observed=True)
        .transform("median")
        .to_numpy(dtype=float)
    )

    cal_base = base_predictions(result, calibration, horizon)
    hold_base = base_predictions(result, holdout, horizon)
    cal_y = calibration[label].to_numpy(dtype=float)
    hold_y = holdout[label].to_numpy(dtype=float)
    cal_dates = calibration["date"].dt.strftime("%Y-%m-%d").to_numpy()
    hold_dates = holdout["date"].dt.strftime("%Y-%m-%d").to_numpy()
    trials: list[dict[str, Any]] = []
    for base_weight in (0.0, .50, 1.0):
        for market_weight in (0.0, .25, .50, .75, 1.0):
            for issuer_weight in (.10, .25, .50, .75, 1.0):
                prediction = (
                    base_weight * cal_base
                    + market_weight * cal_market_prediction
                    + issuer_weight * cal_relative_prediction
                )
                paired = _paired_audit(cal_y, np.zeros_like(cal_y), prediction, cal_dates)
                trials.append(
                    {
                        "baseWeight": base_weight,
                        "marketWeight": market_weight,
                        "issuerWeight": issuer_weight,
                        "mae": float(np.mean(np.abs(cal_y - prediction))),
                        "pairedVsZero": paired,
                        "moveRatio": float(np.median(np.abs(prediction)))
                        / max(float(np.median(np.abs(cal_y))), 1e-12),
                    }
                )
    eligible = [
        trial for trial in trials
        if trial["pairedVsZero"]["positiveChronologicalBlocks"] >= 3
        and trial["pairedVsZero"]["meanPairedMAEImprovement"]
        > trial["pairedVsZero"]["pairedStandardError"]
    ]
    selected = min(eligible or trials, key=lambda item: item["mae"])
    hold_prediction = (
        selected["baseWeight"] * hold_base
        + selected["marketWeight"] * hold_market_prediction
        + selected["issuerWeight"] * hold_relative_prediction
    )
    metrics = _metrics(hold_y, hold_prediction, hold_dates)
    baseline_metrics = _metrics(hold_y, hold_base, hold_dates)
    paired_vs_base = _paired_audit(hold_y, hold_base, hold_prediction, hold_dates)
    fpt_latest = holdout["symbol"].eq("FPT") & holdout["date"].eq(holdout["date"].max())
    return {
        "status": "ACTIVE" if eligible else "REVIEW",
        "fittedSymbols": fitted_symbols,
        "features": compact_features,
        "selection": selected,
        "topCalibrationTrials": sorted(trials, key=lambda item: item["mae"])[:5],
        "sealed": metrics,
        "sealedMAEDeltaVsCurrent": metrics["maeSkill"] - baseline_metrics["maeSkill"],
        "sealedDirectionDeltaVsCurrent": (metrics["directionalAccuracy"] or 0.0)
        - (baseline_metrics["directionalAccuracy"] or 0.0),
        "sealedPairedVsCurrent": paired_vs_base,
        "fptLatestReturn": None if not fpt_latest.any() else float(hold_prediction[fpt_latest.to_numpy()][0]),
        "sealedLabelsUsedForSelection": 0,
        "futureLabelsUsed": 0,
    }


def select_parameters(
    rows: pd.DataFrame,
    base_prediction: np.ndarray,
    horizon: int,
) -> tuple[CorrectionParameters, dict[str, Any]]:
    actual = rows[f"target{horizon}"].to_numpy(dtype=float)
    dates = rows["date"].dt.strftime("%Y-%m-%d").to_numpy()
    trials: list[dict[str, Any]] = []
    for half_life in (5, 10, 20, 40):
        for market_weight in (.25, .50, .75, 1.0):
            for symbol_weight in (0.0, .10, .20):
                parameters = CorrectionParameters(half_life, market_weight, symbol_weight)
                correction, _ = causal_residual_correction(rows, base_prediction, horizon, parameters)
                candidate = base_prediction + correction
                paired = _paired_audit(actual, base_prediction, candidate, dates)
                metrics = _metrics(actual, candidate, dates)
                trials.append(
                    {
                        "parameters": parameters,
                        **paired,
                        "mae": metrics["mae"],
                        "maeSkill": metrics["maeSkill"],
                        "directionalAccuracy": metrics["directionalAccuracy"],
                        "pointToRealizedMoveRatio": metrics["medianForecastAbs"]
                        / max(metrics["realizedMedianAbs"], 1e-12),
                    }
                )
    eligible = [
        trial
        for trial in trials
        if trial["positiveChronologicalBlocks"] >= 3
        and trial["meanPairedMAEImprovement"] > trial["pairedStandardError"]
    ]
    if not eligible:
        selected_parameters = CorrectionParameters(20, 0.0, 0.0)
        status = "ABSTAIN"
        selected: dict[str, Any] = {
            "parameters": selected_parameters,
            "meanPairedMAEImprovement": 0.0,
            "pairedStandardError": 0.0,
            "positiveChronologicalBlocks": 0,
        }
    else:
        selected = max(eligible, key=lambda item: item["meanPairedMAEImprovement"])
        selected_parameters = selected["parameters"]
        status = "ACTIVE"
    serializable = {
        key: value for key, value in selected.items() if key != "parameters"
    }
    serializable.update(
        {
            "status": status,
            "candidateCount": len(trials),
            "eligibleCount": len(eligible),
            "parameters": {
                "halfLifeSessions": selected_parameters.half_life,
                "marketWeight": selected_parameters.market_weight,
                "symbolWeight": selected_parameters.symbol_weight,
                "volatilityClip": selected_parameters.volatility_clip,
            },
            "sealedLabelsUsed": 0,
            "bestTrials": [
                {
                    "halfLifeSessions": trial["parameters"].half_life,
                    "marketWeight": trial["parameters"].market_weight,
                    "symbolWeight": trial["parameters"].symbol_weight,
                    "meanPairedMAEImprovement": trial["meanPairedMAEImprovement"],
                    "pairedStandardError": trial["pairedStandardError"],
                    "positiveChronologicalBlocks": trial["positiveChronologicalBlocks"],
                    "maeSkill": trial["maeSkill"],
                    "directionalAccuracy": trial["directionalAccuracy"],
                    "pointToRealizedMoveRatio": trial["pointToRealizedMoveRatio"],
                }
                for trial in sorted(
                    trials,
                    key=lambda item: item["meanPairedMAEImprovement"],
                    reverse=True,
                )[:5]
            ],
        }
    )
    return selected_parameters, serializable


def audit_horizon(
    panel: pd.DataFrame,
    horizon: int,
    fast: bool,
    include_recent_training: bool = False,
    include_hierarchical: bool = False,
) -> dict[str, Any]:
    result = fit_horizon(panel, horizon, fast=fast)
    calibration, holdout = chronological_partitions(panel, horizon)
    calibration_base = base_predictions(result, calibration, horizon)
    parameters, selection = select_parameters(calibration, calibration_base, horizon)
    dynamic_parameters, dynamic_selection = select_dynamic_momentum(
        calibration, calibration_base, horizon
    )

    evaluation = pd.concat([calibration, holdout], ignore_index=True)
    evaluation_base = base_predictions(result, evaluation, horizon)
    correction, causal_audit = causal_residual_correction(
        evaluation, evaluation_base, horizon, parameters
    )
    dynamic_correction, dynamic_audit = causal_momentum_correction(
        evaluation,
        evaluation_base,
        horizon,
        half_life=int(dynamic_parameters["halfLifeSessions"]),
        shrinkage=float(dynamic_parameters["shrinkage"]),
        relative_weight=float(dynamic_parameters["relativeWeight"]),
    )
    holdout_mask = evaluation["date"] >= holdout["date"].min()
    holdout_rows = evaluation.loc[holdout_mask]
    base = evaluation_base[holdout_mask.to_numpy()]
    candidate = base + correction[holdout_mask.to_numpy()]
    dynamic_candidate = base + dynamic_correction[holdout_mask.to_numpy()]
    actual = holdout_rows[f"target{horizon}"].to_numpy(dtype=float)
    dates = holdout_rows["date"].dt.strftime("%Y-%m-%d").to_numpy()
    baseline_metrics = _metrics(actual, base, dates)
    candidate_metrics = _metrics(actual, candidate, dates)
    paired = _paired_audit(actual, base, candidate, dates)
    dynamic_metrics = _metrics(actual, dynamic_candidate, dates)
    dynamic_paired = _paired_audit(actual, base, dynamic_candidate, dates)
    momentum = momentum_challenger(
        calibration,
        holdout,
        calibration_base,
        base_predictions(result, holdout, horizon),
        horizon,
    )

    latest_date = holdout_rows["date"].max()
    latest_mask = holdout_rows["date"].eq(latest_date).to_numpy()
    fpt_mask = holdout_rows["symbol"].eq("FPT").to_numpy()
    fpt_latest = latest_mask & fpt_mask
    report = {
        "horizon": horizon,
        "selection": selection,
        "causalAudit": causal_audit,
        "baseline": baseline_metrics,
        "challenger": candidate_metrics,
        "sealedPairedComparison": paired,
        "sealedMAEDelta": candidate_metrics["maeSkill"] - baseline_metrics["maeSkill"],
        "sealedDirectionDelta": (
            (candidate_metrics["directionalAccuracy"] or 0.0)
            - (baseline_metrics["directionalAccuracy"] or 0.0)
        ),
        "momentumChallenger": momentum,
        "dynamicMomentumChallenger": {
            "selection": dynamic_selection,
            "causalAudit": dynamic_audit,
            "metrics": dynamic_metrics,
            "sealedMAEDelta": dynamic_metrics["maeSkill"] - baseline_metrics["maeSkill"],
            "sealedDirectionDelta": (dynamic_metrics["directionalAccuracy"] or 0.0)
            - (baseline_metrics["directionalAccuracy"] or 0.0),
            "sealedPairedComparison": dynamic_paired,
        },
        "latestEvaluatedOrigin": str(pd.Timestamp(latest_date).date()),
        "fptLatest": None
        if not fpt_latest.any()
        else {
            "actualReturn": float(actual[fpt_latest][0]),
            "baselineReturn": float(base[fpt_latest][0]),
            "challengerReturn": float(candidate[fpt_latest][0]),
            "correction": float(candidate[fpt_latest][0] - base[fpt_latest][0]),
        },
    }
    if include_recent_training:
        report["recentTrainingChallenger"] = recent_training_challenger(
            panel, horizon, fast=fast
        )
    if include_hierarchical:
        report["hierarchicalIssuerChallenger"] = hierarchical_issuer_challenger(
            panel, result, horizon
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizons", default="1,2,3,4,5")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--recent-training", action="store_true")
    parser.add_argument("--hierarchical", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    horizons = tuple(int(item) for item in args.horizons.split(",") if item.strip())

    histories, freshness = load_histories(())
    events, flows, _ = load_signal_sources(set(freshness["currentHOSESymbols"]))
    panel = build_panel(histories, freshness["scan"], events, flows)
    report = {
        "version": "VMEWS-FORECAST-CHALLENGER-34.0",
        "asOf": freshness["forecastAsOf"],
        "method": "sealed chronological comparison; calibration-only selection; strict label-maturity online correction",
        "horizons": {
            str(horizon): audit_horizon(
                panel,
                horizon,
                args.fast,
                include_recent_training=args.recent_training,
                include_hierarchical=args.hierarchical,
            )
            for horizon in horizons
        },
    }
    if args.output:
        Path(args.output).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
    summary = {
        key: {
            "status": item["selection"]["status"],
            "parameters": item["selection"]["parameters"],
            "sealedMAEDelta": item["sealedMAEDelta"],
            "sealedDirectionDelta": item["sealedDirectionDelta"],
            "pairedImprovement": item["sealedPairedComparison"]["meanPairedMAEImprovement"],
            "positiveBlocks": item["sealedPairedComparison"]["positiveChronologicalBlocks"],
            "baselineMoveRatio": item["baseline"]["medianForecastAbs"] / max(item["baseline"]["realizedMedianAbs"], 1e-12),
            "challengerMoveRatio": item["challenger"]["medianForecastAbs"] / max(item["challenger"]["realizedMedianAbs"], 1e-12),
            "fptLatest": item["fptLatest"],
        }
        for key, item in report["horizons"].items()
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
