"""
V12.1 Market Absolute Return Layer

Purpose:
Estimate systematic market contribution separately from V12 alpha ranking.
This layer must never consume sealed labels during selection.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class MarketForecast:
    horizon: int
    expected_return: float
    confidence: float


def build_market_absolute_forecast(features: Dict[str, float], horizon: int) -> MarketForecast:
    """Baseline deterministic layer.

    The production implementation will replace this with a PIT-trained head.
    This contract intentionally separates market beta from stock alpha.
    """
    trend = features.get("market_trend", 0.0)
    breadth = features.get("market_breadth", 0.0)
    volatility = features.get("market_volatility", 1.0)

    raw = 0.45 * trend + 0.35 * breadth
    raw /= max(volatility, 0.5)
    raw = max(-0.05, min(0.05, raw))

    return MarketForecast(
        horizon=horizon,
        expected_return=float(raw),
        confidence=min(1.0, abs(raw) * 10)
    )
