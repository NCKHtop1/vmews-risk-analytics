"""
V12.1 challenger metrics.

Comparison rules:
- Compare against frozen V12 baseline.
- Evaluate on identical origins.
- No sealed tuning.
"""


def compare_models(v12_metrics, v121_metrics):
    return {
        "mae_improvement": v12_metrics["mae"] - v121_metrics["mae"],
        "rmse_improvement": v12_metrics["rmse"] - v121_metrics["rmse"],
        "rank_ic_delta": v121_metrics["rank_ic"] - v12_metrics["rank_ic"],
        "promotable": (
            v121_metrics["mae"] < v12_metrics["mae"]
            and v121_metrics["calibration_pass"] is True
            and v121_metrics["blind_holdout_pass"] is True
        ),
    }
