"""
V12.1 Absolute Challenger Experiment Runner

Purpose:
- Keep V12 baseline untouched.
- Execute comparable V12 vs V12.1 experiments.
- Produce evaluation payload for promotion gate.

This runner intentionally does not tune on sealed data.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any


@dataclass
class ExperimentResult:
    model: str
    horizon: int
    mae: float
    rmse: float
    rank_ic: float
    calibration_error: float
    dispersion_ratio: float


def compare_models(v12: Dict[str, Any], v121: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "mae_delta": v121["mae"] - v12["mae"],
        "rmse_delta": v121["rmse"] - v12["rmse"],
        "rank_ic_delta": v121["rank_ic"] - v12["rank_ic"],
        "calibration_delta": v121["calibration_error"] - v12["calibration_error"],
        "dispersion_delta": v121["dispersion_ratio"] - v12["dispersion_ratio"],
    }


def promotion_candidate(report: Dict[str, Any]) -> bool:
    return (
        report["mae_delta"] < 0
        and report["rmse_delta"] <= 0
        and report["rank_ic_delta"] >= 0
        and report["calibration_delta"] <= 0
    )


if __name__ == "__main__":
    print("V12.1 challenger runner ready")
