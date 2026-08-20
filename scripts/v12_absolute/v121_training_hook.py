"""
V12.1 Absolute Challenger Training Hook

This module defines the integration contract between existing V12 alpha
forecasting and the new absolute-return challenger layers.

The production V12 model remains unchanged. This hook is only for challenger
experiments and promotion comparison.
"""

from dataclasses import dataclass


@dataclass
class AbsoluteForecastComponents:
    market_return: float
    sector_return: float
    alpha_return: float
    magnitude: float


def compose_absolute_return(
    market_return: float,
    sector_return: float,
    alpha_return: float,
    market_weight: float,
    sector_weight: float,
    alpha_weight: float,
    magnitude: float,
) -> float:
    """Combine PIT-trained components into final challenger return."""
    raw = (
        market_return * market_weight
        + sector_return * sector_weight
        + alpha_return * alpha_weight
    )
    return raw * magnitude


# Promotion remains external and must compare against frozen V12 baseline.
# No sealed labels are allowed for fitting weights or magnitude calibration.
