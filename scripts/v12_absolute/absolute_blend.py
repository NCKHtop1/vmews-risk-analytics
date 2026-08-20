"""
V12.1 Absolute Forecast Layer

Blend:
    market component
    sector component
    V12 alpha residual

This module intentionally does not alter V12 production outputs.
It produces challenger forecasts only.
"""

from dataclasses import dataclass


@dataclass
class AbsoluteComponents:
    market_return: float
    sector_return: float
    alpha_return: float


@dataclass
class CalibrationContext:
    volatility_scale: float
    regime_scale: float
    confidence_scale: float


DEFAULT_WEIGHTS = {
    "market": 0.40,
    "sector": 0.25,
    "alpha": 0.35,
}


def blend_return(
    components: AbsoluteComponents,
    calibration: CalibrationContext,
    weights=None,
):
    weights = weights or DEFAULT_WEIGHTS

    raw = (
        weights["market"] * components.market_return
        + weights["sector"] * components.sector_return
        + weights["alpha"] * components.alpha_return
    )

    magnitude = (
        calibration.volatility_scale
        * calibration.regime_scale
        * calibration.confidence_scale
    )

    # Prevent unstable amplification.
    magnitude = min(max(magnitude, 0.5), 1.5)

    return raw * magnitude
