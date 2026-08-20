"""
V12.1 Absolute Challenger Horizon Runner

Purpose:
- keep V12 baseline untouched
- attach absolute market/sector/alpha blend
- generate comparable H1-H5 evaluation outputs

This module does not promote any model. Promotion remains gated by blind OOS tests.
"""

from dataclasses import dataclass


@dataclass
class HorizonResult:
    horizon: int
    baseline_mae: float
    challenger_mae: float
    baseline_rank_ic: float
    challenger_rank_ic: float

    @property
    def mae_improvement(self):
        return self.baseline_mae - self.challenger_mae


def evaluate_horizon(baseline, challenger, horizon):
    return HorizonResult(
        horizon=horizon,
        baseline_mae=baseline['mae'],
        challenger_mae=challenger['mae'],
        baseline_rank_ic=baseline['rankIC'],
        challenger_rank_ic=challenger['rankIC'],
    )


def run_all_horizons(results):
    return [evaluate_horizon(x['baseline'], x['challenger'], x['horizon']) for x in results]
