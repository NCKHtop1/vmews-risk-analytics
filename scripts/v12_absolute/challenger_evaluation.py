"""
V12.1 Challenger evaluation.

V12 remains baseline. This module exists to prevent replacing a stable
model with a visually attractive but worse forecaster.
"""


def compare_models(v12_metrics, challenger_metrics):
    return {
        "mae_improvement": v12_metrics["mae"] - challenger_metrics["mae"],
        "rank_ic_change": challenger_metrics.get("rank_ic", 0)
        - v12_metrics.get("rank_ic", 0),
        "accepted": (
            challenger_metrics["mae"] < v12_metrics["mae"]
            and challenger_metrics.get("blind_pass", False)
            and challenger_metrics.get("calibration_pass", False)
        ),
    }
