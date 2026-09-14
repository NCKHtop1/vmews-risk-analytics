"""Runtime hardening for the V41 market-wide technical-transition challenger."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss

import forecast_v41_technical_transition as v41


def _refined_transition_labels(panel: pd.DataFrame) -> pd.DataFrame:
    """Require the current technical state to be converging toward a cross."""
    frame = panel.copy().sort_values(["symbol", "date"])
    grouped = frame.groupby("symbol", observed=True, group_keys=False)
    future_hist = [grouped["macd_hist_norm"].shift(-step) for step in range(1, v41.TRANSITION_HORIZON + 1)]
    future_gap = [grouped["trend10_20_gap"].shift(-step) for step in range(1, v41.TRANSITION_HORIZON + 1)]
    hist_future_max = pd.concat(future_hist, axis=1).max(axis=1)
    hist_future_min = pd.concat(future_hist, axis=1).min(axis=1)
    gap_future_max = pd.concat(future_gap, axis=1).max(axis=1)
    gap_future_min = pd.concat(future_gap, axis=1).min(axis=1)
    bull_cross = (
        ((frame["macd_hist_norm"] <= 0) & (hist_future_max > 0))
        | ((frame["trend10_20_gap"] <= 0) & (gap_future_max > 0))
    )
    bear_cross = (
        ((frame["macd_hist_norm"] >= 0) & (hist_future_min < 0))
        | ((frame["trend10_20_gap"] >= 0) & (gap_future_min < 0))
    )
    target = frame[f"target{v41.TRANSITION_HORIZON}"]
    frame["_bull_transition"] = (bull_cross & target.gt(0)).astype(int)
    frame["_bear_transition"] = (bear_cross & target.lt(0)).astype(int)
    frame["_bull_eligible"] = (
        ((frame["macd_hist_norm"] <= 0) & (frame["macd_hist_delta1"] > 0))
        | ((frame["trend10_20_gap"] <= 0) & (frame["trend10_20_delta1"] > 0))
    ).astype(int)
    frame["_bear_eligible"] = (
        ((frame["macd_hist_norm"] >= 0) & (frame["macd_hist_delta1"] < 0))
        | ((frame["trend10_20_gap"] >= 0) & (frame["trend10_20_delta1"] < 0))
    ).astype(int)
    frame.sort_values(["date", "symbol"], inplace=True)
    frame.reset_index(drop=True, inplace=True)
    return frame


def _large_move_threshold(calibration: pd.DataFrame, target_column: str) -> float:
    """Freeze the large-move definition from calibration only, never holdout."""
    values = pd.to_numeric(calibration[target_column], errors="coerce").abs().dropna().to_numpy(dtype=float)
    if len(values) < 100:
        raise RuntimeError(f"V41 large-move calibration requires >=100 rows; got {len(values)}")
    return float(np.quantile(values, .90))


def _evaluate_side_hardened(
    enriched: pd.DataFrame,
    *,
    side: str,
):
    """Mirror the frozen V41 evaluation and expose complete transition diagnostics.

    Probability and large-move thresholds are both derived from calibration only.
    The holdout is used strictly for evaluation; it cannot change either threshold.
    """
    if side not in {"bull", "bear"}:
        raise ValueError(side)
    label = f"_{side}_transition"
    eligibility = f"_{side}_eligible"
    direction = 1.0 if side == "bull" else -1.0
    target_column = f"target{v41.TRANSITION_HORIZON}"
    maturity_column = f"maturity{v41.TRANSITION_HORIZON}"
    usable = enriched.loc[
        enriched[target_column].notna()
        & enriched[maturity_column].notna()
        & enriched[eligibility].eq(1)
    ].copy()
    train, calibration, holdout = v41._chronological_split(usable)
    model = v41._classifier(4101 if side == "bull" else 4102)
    model.fit(v41._matrix(train), train[label].to_numpy(dtype=int))

    cal_probability = model.predict_proba(v41._matrix(calibration))[:, 1]
    calibration_base_rate = float(calibration[label].mean())
    probability_threshold = float(np.quantile(cal_probability, .90))
    large_move_threshold = _large_move_threshold(calibration, target_column)

    probability = model.predict_proba(v41._matrix(holdout))[:, 1]
    labels = holdout[label].to_numpy(dtype=int)
    baseline_probability = np.full(len(labels), calibration_base_rate, dtype=float)
    brier = float(brier_score_loss(labels, probability))
    baseline_brier = float(brier_score_loss(labels, baseline_probability))
    selected = probability >= probability_threshold
    selected_n = int(selected.sum())
    precision = float(labels[selected].mean()) if selected_n else 0.0
    lift = precision / max(calibration_base_rate, 1e-12)

    positives = labels == 1
    negatives = ~positives
    true_positive_n = int(np.sum(selected & positives))
    false_positive_n = int(np.sum(selected & negatives))
    positive_n = int(np.sum(positives))
    negative_n = int(np.sum(negatives))
    transition_recall = true_positive_n / positive_n if positive_n else 0.0
    false_positive_rate = false_positive_n / negative_n if negative_n else 0.0

    signed_return = direction * holdout[target_column].to_numpy(dtype=float)
    mean_signed_return = float(signed_return[selected].mean()) if selected_n else 0.0
    positive_signed_share = float(np.mean(signed_return[selected] > 0)) if selected_n else 0.0

    large_move = signed_return >= large_move_threshold
    large_move_n = int(np.sum(large_move))
    captured_large_move_n = int(np.sum(selected & large_move))
    large_move_capture_rate = captured_large_move_n / large_move_n if large_move_n else 0.0
    selected_large_move_share = captured_large_move_n / selected_n if selected_n else 0.0

    blocks: list[dict[str, Any]] = []
    for block_dates in np.array_split(np.sort(holdout["date"].unique()), 4):
        if not len(block_dates):
            continue
        mask = selected & holdout["date"].isin(block_dates).to_numpy()
        blocks.append(
            {
                "start": str(pd.Timestamp(block_dates[0]).date()),
                "end": str(pd.Timestamp(block_dates[-1]).date()),
                "selected": int(mask.sum()),
                "meanSignedReturn": float(signed_return[mask].mean()) if mask.any() else None,
            }
        )
    positive_blocks = sum((item["meanSignedReturn"] or 0.0) > 0 for item in blocks if item["selected"])
    populated_blocks = sum(item["selected"] > 0 for item in blocks)
    brier_skill = 1.0 - brier / max(baseline_brier, 1e-12)
    status = "PASS" if (
        len(holdout) >= 1000
        and selected_n >= 40
        and brier_skill > 0
        and lift >= 1.10
        and mean_signed_return > 0
        and positive_signed_share >= .52
        and populated_blocks >= 3
        and positive_blocks >= 3
    ) else "REVIEW"

    audit = {
        "status": status,
        "side": side.upper(),
        "target": f"VALIDATED_{side.upper()}_TECHNICAL_TRANSITION_WITHIN_T_PLUS_3",
        "holdoutRows": int(len(holdout)),
        "selectedRows": selected_n,
        "calibrationBaseRate": calibration_base_rate,
        "probabilityThreshold": probability_threshold,
        "brier": brier,
        "baselineBrier": baseline_brier,
        "brierSkill": brier_skill,
        "precision": precision,
        "transitionRecall": float(transition_recall),
        "falsePositiveRate": float(false_positive_rate),
        "truePositiveRows": true_positive_n,
        "falsePositiveRows": false_positive_n,
        "positiveRows": positive_n,
        "negativeRows": negative_n,
        "liftVsCalibrationBaseRate": lift,
        "meanSignedT3Return": mean_signed_return,
        "positiveSignedReturnShare": positive_signed_share,
        "largeMoveThresholdAbsT3": large_move_threshold,
        "largeMoveThresholdQuantile": .90,
        "largeMoveThresholdSource": "CALIBRATION_ONLY_ABS_T3_Q90",
        "largeMoveRows": large_move_n,
        "capturedLargeMoveRows": captured_large_move_n,
        "largeMoveCaptureRate": float(large_move_capture_rate),
        "selectedLargeMoveShare": float(selected_large_move_share),
        "positiveChronologicalBlocks": positive_blocks,
        "populatedChronologicalBlocks": populated_blocks,
        "chronologicalBlocks": blocks,
        "selectionFrozenBeforeHoldout": True,
        "largeMoveDefinitionFrozenBeforeHoldout": True,
        "futureFeaturesUsed": 0,
        "labelMaturityPurgeSessions": v41.TRANSITION_HORIZON,
    }

    matured = usable.loc[usable[maturity_column] <= enriched["date"].max()].copy()
    refit = v41._classifier(4111 if side == "bull" else 4112)
    refit.fit(v41._matrix(matured), matured[label].to_numpy(dtype=int))
    audit["productionRefitRows"] = int(len(matured))
    audit["productionRefitUsesOnlyMaturedLabels"] = True
    return audit, refit, probability_threshold


def install_v41_refined(market_model: Any) -> None:
    """Compose V41 with V40 without symbol-specific rules or future features."""
    v41.add_transition_labels = _refined_transition_labels
    v41._evaluate_side = _evaluate_side_hardened
    v41.install_v41(market_model)
    market_model.VERSION = "VMEWS-MARKET-FORECAST-41.0.0"

    original_build = market_model.build_panel

    def build_panel_refined(*args: Any, **kwargs: Any) -> pd.DataFrame:
        panel = original_build(*args, **kwargs)
        numerical = list((market_model.FACTOR_GROUPS or {}).get("NUMERICAL") or ())
        for column in v41.TECHNICAL_FEATURE_COLUMNS:
            if column not in numerical:
                numerical.append(column)
        market_model.FACTOR_GROUPS["NUMERICAL"] = tuple(numerical)
        return panel

    market_model.build_panel = build_panel_refined
