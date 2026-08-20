"""
V12.1 Absolute Challenger Backtest Runner

Purpose:
Compare existing V12 baseline against V12.1 Absolute Forecast Layer
on identical chronological splits.

No sealed labels may be used for training, blending, or promotion.
Sealed data is evaluation only.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any


@dataclass
class ChallengerResult:
    horizon: int
    baseline_mae: float
    challenger_mae: float
    baseline_rank_ic: float
    challenger_rank_ic: float
    baseline_dispersion: float
    challenger_dispersion: float

    @property
    def mae_delta(self):
        return self.baseline_mae - self.challenger_mae

    @property
    def ic_delta(self):
        return self.challenger_rank_ic - self.baseline_rank_ic


def evaluate_horizon(baseline: Dict[str, Any], challenger: Dict[str, Any], horizon: int):
    return ChallengerResult(
        horizon=horizon,
        baseline_mae=float(baseline["mae"]),
        challenger_mae=float(challenger["mae"]),
        baseline_rank_ic=float(baseline["rank_ic"]),
        challenger_rank_ic=float(challenger["rank_ic"]),
        baseline_dispersion=float(baseline["dispersion"]),
        challenger_dispersion=float(challenger["dispersion"]),
    )


def promotion_candidate(results):
    return all(
        r.mae_delta > 0 and r.ic_delta >= 0
        for r in results
    )


if __name__ == "__main__":
    print("V12.1 challenger backtest runner ready")
