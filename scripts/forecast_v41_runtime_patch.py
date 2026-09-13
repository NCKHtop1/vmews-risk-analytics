"""Runtime hardening for the V41 market-wide technical-transition challenger."""
from __future__ import annotations

from typing import Any
import pandas as pd

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


def install_v41_refined(market_model: Any) -> None:
    """Compose V41 with V40 without symbol-specific rules or future features."""
    v41.add_transition_labels = _refined_transition_labels
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
