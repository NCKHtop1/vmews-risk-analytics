"""
V12.1 Absolute Challenger Integration Pipeline

Purpose:
- Keep V12 alpha engine unchanged.
- Add market + sector absolute components.
- Blend components before magnitude calibration.
- Produce challenger forecast only; production promotion requires gates.

No sealed labels are used for selection.
"""

from dataclasses import dataclass


@dataclass
class AbsoluteComponents:
    market_return: float
    sector_return: float
    alpha_return: float


def blend_absolute_return(
    components: AbsoluteComponents,
    market_weight: float,
    sector_weight: float,
    alpha_weight: float,
):
    total = market_weight + sector_weight + alpha_weight
    if abs(total - 1.0) > 1e-9:
        raise ValueError("weights must sum to one")

    return (
        components.market_return * market_weight
        + components.sector_return * sector_weight
        + components.alpha_return * alpha_weight
    )


def apply_conditional_magnitude(raw_return, volatility_scale, regime_scale, confidence_scale):
    multiplier = volatility_scale * regime_scale * confidence_scale
    multiplier = max(0.5, min(1.5, multiplier))
    return raw_return * multiplier


def build_v121_forecast(components, weights, calibration):
    raw = blend_absolute_return(
        components,
        weights["market"],
        weights["sector"],
        weights["alpha"],
    )
    return apply_conditional_magnitude(raw, **calibration)
