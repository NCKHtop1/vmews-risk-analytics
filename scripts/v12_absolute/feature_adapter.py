"""
V12.1 Absolute Challenger - Feature Adapter

Purpose:
Bridge existing V12 alpha outputs with market and sector absolute layers.
No training labels are consumed here. This adapter only normalizes
pre-model features and keeps PIT boundaries explicit.
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class AbsoluteFeatureBundle:
    symbol: str
    horizon: int
    alpha_signal: float
    market_signal: float
    sector_signal: float
    volatility: float
    regime: str
    confidence: float
    liquidity: float


def build_absolute_features(
    symbol: str,
    horizon: int,
    alpha_output: Dict[str, Any],
    market_output: Dict[str, Any],
    sector_output: Dict[str, Any],
    risk_state: Dict[str, Any],
) -> AbsoluteFeatureBundle:
    """Create deterministic V12.1 feature bundle.

    All inputs must already be generated from PIT-safe upstream pipelines.
    Sealed labels are not accepted by this adapter.
    """

    return AbsoluteFeatureBundle(
        symbol=symbol,
        horizon=horizon,
        alpha_signal=float(alpha_output.get("alpha", 0.0)),
        market_signal=float(market_output.get("return", 0.0)),
        sector_signal=float(sector_output.get("return", 0.0)),
        volatility=float(risk_state.get("volatility", 0.0)),
        regime=str(risk_state.get("regime", "UNKNOWN")),
        confidence=float(risk_state.get("confidence", 0.0)),
        liquidity=float(risk_state.get("liquidity", 0.0)),
    )
