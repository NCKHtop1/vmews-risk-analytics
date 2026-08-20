"""
V12.1 Absolute Blend Optimizer

Combines:
- market absolute return
- sector absolute return
- V12 alpha residual

The optimizer is intentionally constrained. It must improve OOS error,
not create larger-looking forecasts.
"""

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class BlendWeights:
    market: float
    sector: float
    alpha: float


DEFAULT_GRID = [
    BlendWeights(0.20, 0.20, 0.60),
    BlendWeights(0.30, 0.25, 0.45),
    BlendWeights(0.40, 0.25, 0.35),
    BlendWeights(0.35, 0.35, 0.30),
]


def blend_return(
    market_return: float,
    sector_return: float,
    alpha_return: float,
    weights: BlendWeights,
) -> float:
    return (
        weights.market * market_return
        + weights.sector * sector_return
        + weights.alpha * alpha_return
    )


def select_weights(metrics: Dict[Tuple[float, float, float], Dict[str, float]]) -> BlendWeights:
    """
    Select only using pre-blind metrics.

    Objective:
    MAE first, stability second.
    No sealed labels allowed.
    """
    best = None
    best_key = None

    for key, value in metrics.items():
        score = (
            value.get("mae", 999999)
            + 0.05 * value.get("instability", 0)
        )
        if best is None or score < best:
            best = score
            best_key = key

    if best_key is None:
        return DEFAULT_GRID[0]

    return BlendWeights(*best_key)
