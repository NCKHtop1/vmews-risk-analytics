"""V41 market-wide technical regime-transition challenger and radar.

The module has two deliberately separated responsibilities:
1. add point-in-time technical transition geometry to the existing T+1...T+5
   forecasting feature panel; and
2. train a separate, leakage-safe classifier that ranks HOSE names whose
   technical state is likely to transition within the next three sessions.

Nothing here is symbol-specific. A single-stock miss was only a motivating failure case.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss

VERSION = "VMEWS-TECHNICAL-TRANSITION-41.0.0"
TRANSITION_HORIZON = 3

# Small, fixed feature family chosen before holdout evaluation. These are
# geometric transition descriptors rather than a large indicator sweep.
TECHNICAL_FEATURE_COLUMNS = [
    "macd_signal_norm",
    "macd_hist_norm",
    "macd_hist_delta1",
    "macd_hist_slope3",
    "macd_cross_distance_vol",
    "macd_cross_velocity",
    "trend10_20_gap",
    "trend10_20_delta1",
    "trend10_20_slope3",
    "rsi_delta3",
    "drawup20",
]

RADAR_FEATURE_COLUMNS = [
    "macd_hist_norm",
    "macd_hist_delta1",
    "macd_hist_slope3",
    "macd_cross_distance_vol",
    "macd_cross_velocity",
    "trend10_20_gap",
    "trend10_20_delta1",
    "trend10_20_slope3",
    "rsi14",
    "rsi_delta3",
    "volume_ratio20",
    "volume_z20",
    "ret5",
    "ret20",
    "vol20",
    "atr14",
    "relative_ret5",
    "relative_ret20",
    "sector_relative5",
    "breadth5",
    "market_ret5",
]


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else fallback
    except (TypeError, ValueError):
        return fallback


def add_transition_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Add causal technical-transition geometry using only T0-or-earlier rows."""
    frame = panel.copy()
    frame.sort_values(["symbol", "date"], inplace=True)
    grouped = frame.groupby("symbol", observed=True, group_keys=False)

    frame["macd_signal_norm"] = grouped["macd_norm"].transform(
        lambda values: values.ewm(span=9, adjust=False).mean()
    )
    frame["macd_hist_norm"] = frame["macd_norm"] - frame["macd_signal_norm"]
    frame["macd_hist_delta1"] = grouped["macd_hist_norm"].diff(1)
    frame["macd_hist_slope3"] = grouped["macd_hist_norm"].diff(3) / 3.0
    vol = frame["vol20"].clip(lower=.002)
    frame["macd_cross_distance_vol"] = frame["macd_hist_norm"].abs() / vol
    frame["macd_cross_velocity"] = -np.sign(frame["macd_hist_norm"]) * frame["macd_hist_delta1"] / vol

    frame["trend10_20_gap"] = frame["trend10"] - frame["trend20"]
    frame["trend10_20_delta1"] = grouped["trend10_20_gap"].diff(1)
    frame["trend10_20_slope3"] = grouped["trend10_20_gap"].diff(3) / 3.0
    frame["rsi_delta3"] = grouped["rsi14"].diff(3) / 3.0

    rolling_min20 = grouped["close"].transform(
        lambda values: values.rolling(20, min_periods=10).min()
    )
    frame["drawup20"] = frame["close"] / rolling_min20.clip(lower=1.0) - 1.0

    frame.replace([np.inf, -np.inf], np.nan, inplace=True)
    frame.sort_values(["date", "symbol"], inplace=True)
    frame.reset_index(drop=True, inplace=True)
    return frame


def add_transition_labels(panel: pd.DataFrame) -> pd.DataFrame:
    """Create future transition outcomes strictly for training/evaluation.

    A positive event requires a MACD-histogram or 10/20 trend-gap cross within
    the next three sessions *and* a same-sign T+3 realized return. These fields
    are never included in ``RADAR_FEATURE_COLUMNS``.
    """
    frame = panel.copy().sort_values(["symbol", "date"])
    grouped = frame.groupby("symbol", observed=True, group_keys=False)
    future_hist = [grouped["macd_hist_norm"].shift(-step) for step in range(1, TRANSITION_HORIZON + 1)]
    future_gap = [grouped["trend10_20_gap"].shift(-step) for step in range(1, TRANSITION_HORIZON + 1)]
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
    target = frame[f"target{TRANSITION_HORIZON}"]
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


def _matrix(rows: pd.DataFrame) -> np.ndarray:
    return rows[RADAR_FEATURE_COLUMNS].to_numpy(dtype=np.float32)


def _classifier(seed: int) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        learning_rate=.05,
        max_iter=90,
        max_leaf_nodes=15,
        min_samples_leaf=120,
        l2_regularization=10.0,
        max_bins=128,
        early_stopping=False,
        random_state=seed,
    )


def _chronological_split(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = np.sort(rows["date"].dropna().unique())
    if len(dates) < 360:
        raise RuntimeError(f"V41 transition radar requires >=360 sessions; got {len(dates)}")
    holdout_days = min(120, max(70, len(dates) // 6))
    calibration_days = min(90, max(60, len(dates) // 8))
    holdout_start = dates[-holdout_days]
    calibration_start = dates[-(holdout_days + calibration_days)]
    maturity = f"maturity{TRANSITION_HORIZON}"
    train = rows.loc[(rows["date"] < calibration_start) & (rows[maturity] < calibration_start)].copy()
    calibration = rows.loc[
        (rows["date"] >= calibration_start)
        & (rows["date"] < holdout_start)
        & (rows[maturity] < holdout_start)
    ].copy()
    holdout = rows.loc[rows["date"] >= holdout_start].copy()
    if min(len(train), len(calibration), len(holdout)) < 1000:
        raise RuntimeError(
            "V41 transition split too small: "
            f"train={len(train)} calibration={len(calibration)} holdout={len(holdout)}"
        )
    return train, calibration, holdout


def _evaluate_side(
    enriched: pd.DataFrame,
    *,
    side: str,
) -> tuple[dict[str, Any], HistGradientBoostingClassifier, float]:
    if side not in {"bull", "bear"}:
        raise ValueError(side)
    label = f"_{side}_transition"
    eligibility = f"_{side}_eligible"
    direction = 1.0 if side == "bull" else -1.0
    usable = enriched.loc[
        enriched[f"target{TRANSITION_HORIZON}"].notna()
        & enriched[f"maturity{TRANSITION_HORIZON}"].notna()
        & enriched[eligibility].eq(1)
    ].copy()
    train, calibration, holdout = _chronological_split(usable)
    model = _classifier(4101 if side == "bull" else 4102)
    model.fit(_matrix(train), train[label].to_numpy(dtype=int))

    cal_probability = model.predict_proba(_matrix(calibration))[:, 1]
    calibration_base_rate = float(calibration[label].mean())
    threshold = float(np.quantile(cal_probability, .90))

    probability = model.predict_proba(_matrix(holdout))[:, 1]
    labels = holdout[label].to_numpy(dtype=int)
    baseline_probability = np.full(len(labels), calibration_base_rate, dtype=float)
    brier = float(brier_score_loss(labels, probability))
    baseline_brier = float(brier_score_loss(labels, baseline_probability))
    selected = probability >= threshold
    selected_n = int(selected.sum())
    precision = float(labels[selected].mean()) if selected_n else 0.0
    lift = precision / max(calibration_base_rate, 1e-12)
    signed_return = direction * holdout[f"target{TRANSITION_HORIZON}"].to_numpy(dtype=float)
    mean_signed_return = float(signed_return[selected].mean()) if selected_n else 0.0
    positive_signed_share = float(np.mean(signed_return[selected] > 0)) if selected_n else 0.0

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
        "probabilityThreshold": threshold,
        "brier": brier,
        "baselineBrier": baseline_brier,
        "brierSkill": brier_skill,
        "precision": precision,
        "liftVsCalibrationBaseRate": lift,
        "meanSignedT3Return": mean_signed_return,
        "positiveSignedReturnShare": positive_signed_share,
        "positiveChronologicalBlocks": positive_blocks,
        "populatedChronologicalBlocks": populated_blocks,
        "chronologicalBlocks": blocks,
        "selectionFrozenBeforeHoldout": True,
        "futureFeaturesUsed": 0,
        "labelMaturityPurgeSessions": TRANSITION_HORIZON,
    }

    # Production refit uses all labels that have matured. Architecture and the
    # calibration threshold remain frozen by the evaluation above.
    matured = usable.loc[usable[f"maturity{TRANSITION_HORIZON}"] <= enriched["date"].max()].copy()
    refit = _classifier(4111 if side == "bull" else 4112)
    refit.fit(_matrix(matured), matured[label].to_numpy(dtype=int))
    audit["productionRefitRows"] = int(len(matured))
    audit["productionRefitUsesOnlyMaturedLabels"] = True
    return audit, refit, threshold


def _forecast_context(snapshot: dict[str, Any], side: str) -> dict[str, Any]:
    horizon = (snapshot.get("horizons") or {}).get(str(TRANSITION_HORIZON)) or {}
    expected = _safe_float(horizon.get("expectedReturn"))
    probability = _safe_float(horizon.get("probUp"), .5)
    validated = bool(horizon.get("priceValidated")) and horizon.get("economicPointStatus") == "PASS"
    agreement = (
        expected > 0 and probability >= .5 if side == "bull"
        else expected < 0 and probability <= .5
    )
    return {
        "expectedReturnT3": expected,
        "probUpT3": probability,
        "forecastValidated": validated,
        "forecastAgreement": bool(agreement),
        "expectedPriceT3": horizon.get("expectedPrice"),
    }


def _candidate_record(
    row: pd.Series,
    probability: float,
    threshold: float,
    audit: dict[str, Any],
    snapshot: dict[str, Any],
    side: str,
) -> dict[str, Any]:
    context = _forecast_context(snapshot, side)
    qualified = bool(
        audit.get("status") == "PASS"
        and probability >= threshold
        and context["forecastValidated"]
        and context["forecastAgreement"]
    )
    return {
        "symbol": str(row["symbol"]),
        "date": str(pd.Timestamp(row["date"]).date()),
        "transitionScore": float(probability),
        "threshold": float(threshold),
        "state": "QUALIFIED_TRANSITION" if qualified else "WATCH",
        "side": "BULLISH_TRANSITION" if side == "bull" else "BEARISH_TRANSITION_RISK",
        "macdHistogram": _safe_float(row.get("macd_hist_norm")),
        "macdVelocity": _safe_float(row.get("macd_cross_velocity")),
        "macdDistanceVol": _safe_float(row.get("macd_cross_distance_vol")),
        "trend10_20Gap": _safe_float(row.get("trend10_20_gap")),
        "trend10_20Slope3": _safe_float(row.get("trend10_20_slope3")),
        "rsi14": _safe_float(row.get("rsi14"), .5),
        "rsiSlope3": _safe_float(row.get("rsi_delta3")),
        "relativeVolume20": _safe_float(row.get("volume_ratio20")),
        "relativeReturn5": _safe_float(row.get("relative_ret5")),
        "sectorRelative5": _safe_float(row.get("sector_relative5")),
        **context,
    }


def build_transition_radar(
    panel: pd.DataFrame,
    snapshots: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    enriched = add_transition_labels(panel)
    bull_audit, bull_model, bull_threshold = _evaluate_side(enriched, side="bull")
    bear_audit, bear_model, bear_threshold = _evaluate_side(enriched, side="bear")
    latest = enriched.sort_values(["date", "symbol"]).groupby("symbol", observed=True).tail(1).copy()

    bull_rows = latest.loc[latest["_bull_eligible"].eq(1)].copy()
    bear_rows = latest.loc[latest["_bear_eligible"].eq(1)].copy()
    bull_prob = bull_model.predict_proba(_matrix(bull_rows))[:, 1] if len(bull_rows) else np.asarray([])
    bear_prob = bear_model.predict_proba(_matrix(bear_rows))[:, 1] if len(bear_rows) else np.asarray([])

    bullish = [
        _candidate_record(row, float(prob), bull_threshold, bull_audit, snapshots.get(str(row["symbol"]), {}), "bull")
        for (_, row), prob in zip(bull_rows.iterrows(), bull_prob)
    ]
    bearish = [
        _candidate_record(row, float(prob), bear_threshold, bear_audit, snapshots.get(str(row["symbol"]), {}), "bear")
        for (_, row), prob in zip(bear_rows.iterrows(), bear_prob)
    ]
    bullish.sort(key=lambda item: (item["state"] == "QUALIFIED_TRANSITION", item["transitionScore"], item["expectedReturnT3"]), reverse=True)
    bearish.sort(key=lambda item: (item["state"] == "QUALIFIED_TRANSITION", item["transitionScore"], -item["expectedReturnT3"]), reverse=True)

    per_symbol: dict[str, dict[str, Any]] = {}
    for item in bullish:
        per_symbol.setdefault(item["symbol"], {})["bullish"] = item
    for item in bearish:
        per_symbol.setdefault(item["symbol"], {})["bearish"] = item

    return {
        "version": VERSION,
        "horizon": TRANSITION_HORIZON,
        "name": "TECHNICAL_REGIME_TRANSITION_RADAR",
        "displayName": "Radar chuyển pha kỹ thuật",
        "method": "POINT_IN_TIME_MACD_AND_TREND_CROSS_GEOMETRY_PLUS_MULTIVARIATE_CLASSIFIER",
        "candidateSemantics": "QUALIFIED only when transition audit passes and validated T+3 forecast agrees; otherwise WATCH",
        "featureColumns": RADAR_FEATURE_COLUMNS,
        "coreForecastAddedFeatures": TECHNICAL_FEATURE_COLUMNS,
        "audit": {"bullish": bull_audit, "bearish": bear_audit},
        "bullish": bullish[:20],
        "bearish": bearish[:20],
        "perSymbol": per_symbol,
        "researchGovernance": {
            "symbolSpecificHardCode": False,
            "futureFeaturesUsed": 0,
            "selectionUsesCalibrationOnly": True,
            "holdoutChronological": True,
            "recommendationRequiresForecastAgreement": True,
            "singleIndicatorRecommendation": False,
        },
    }


def publish_transition_radar(data_dir: Path, panel: pd.DataFrame) -> dict[str, Any]:
    dashboard_path = data_dir / "forecast-dashboard-v12.json"
    current_path = data_dir / "forecast-current-v12.json"
    market_path = data_dir / "forecast-market-v13.json"
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    current = json.loads(current_path.read_text(encoding="utf-8"))
    market = json.loads(market_path.read_text(encoding="utf-8"))
    snapshots = dashboard.get("symbols") or {}
    radar = build_transition_radar(panel, snapshots)

    dashboard["technicalTransitionRadar"] = radar
    current["technicalTransitionRadar"] = {
        key: radar[key] for key in ("version", "horizon", "name", "displayName", "audit", "bullish", "bearish")
    }
    market["technicalTransitionRadar"] = {
        key: radar[key] for key in ("version", "horizon", "name", "method", "audit", "researchGovernance")
    }
    for symbol, technical in radar["perSymbol"].items():
        if symbol in snapshots:
            snapshots[symbol]["technicalTransition"] = technical
    dashboard["symbols"] = snapshots

    for path, payload in ((dashboard_path, dashboard), (current_path, current), (market_path, market)):
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    return radar


def install_v41(market_model: Any) -> None:
    """Install V41 at the guarded publication boundary without editing V39 core."""
    if getattr(market_model, "_v41_installed", False):
        return
    original_build_panel = market_model.build_panel
    original_write_artifacts = market_model.write_artifacts
    # V41 changes the fitted feature space, so published metadata must not keep
    # advertising the older V39 model version. V40 remains the amplitude selector
    # at the guarded boundary and composes with these V41 causal features.
    market_model.VERSION = "VMEWS-MARKET-FORECAST-41.0.0"

    def build_panel_v41(*args: Any, **kwargs: Any) -> pd.DataFrame:
        panel = add_transition_features(original_build_panel(*args, **kwargs))
        for column in TECHNICAL_FEATURE_COLUMNS:
            if column not in market_model.PRICE_FEATURE_COLUMNS:
                market_model.PRICE_FEATURE_COLUMNS.append(column)
            if column not in market_model.FEATURE_COLUMNS:
                market_model.FEATURE_COLUMNS.append(column)
        numerical = getattr(market_model, "FACTOR_GROUPS", {}).get("NUMERICAL")
        if isinstance(numerical, (list, tuple)):
            values = list(numerical)
            for column in TECHNICAL_FEATURE_COLUMNS:
                if column not in values:
                    values.append(column)
            market_model.FACTOR_GROUPS["NUMERICAL"] = tuple(values)
        panel.attrs["v41TechnicalTransitionFeatures"] = list(TECHNICAL_FEATURE_COLUMNS)
        return panel

    def write_artifacts_v41(*args: Any, **kwargs: Any) -> dict[str, Any]:
        diagnostic = original_write_artifacts(*args, **kwargs)
        panel = args[0] if args else kwargs["panel"]
        radar = publish_transition_radar(Path(market_model.DATA), panel)
        diagnostic = dict(diagnostic or {})
        diagnostic["technicalTransitionRadar"] = {
            "version": radar["version"],
            "bullishStatus": radar["audit"]["bullish"]["status"],
            "bearishStatus": radar["audit"]["bearish"]["status"],
            "bullishCandidates": len(radar["bullish"]),
            "bearishCandidates": len(radar["bearish"]),
        }
        return diagnostic

    market_model.build_panel = build_panel_v41
    market_model.write_artifacts = write_artifacts_v41
    market_model._v41_installed = True
