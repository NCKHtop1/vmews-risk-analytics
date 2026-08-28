"""Run the market forecast with conservative fund-feature governance.

Fund holdings remain available as decision-time scenario context, but they are
not allowed into fitted central-price features until a separate longitudinal
validation explicitly promotes them.  This prevents a handful of recently
collected snapshots from becoming a training feature merely because a small
snapshot-count threshold was crossed.
"""

from __future__ import annotations

import sys

import forecast_v16_external_data as external


_original_fund_feature_panel = external.fund_feature_panel


def _guarded_fund_feature_panel(*args, **kwargs):
    features, audit = _original_fund_feature_panel(*args, **kwargs)
    audit = dict(audit or {})
    audit["rawHistoryGateEligible"] = bool(audit.get("modelEligible"))
    audit["modelEligible"] = False
    audit["status"] = "CONTEXT_ONLY" if audit.get("snapshotCount", 0) else audit.get("status", "UNAVAILABLE")
    audit["trainingFeaturesMasked"] = True
    audit["promotionRequired"] = "SEPARATE_LONGITUDINAL_BACKTEST_AND_STABILITY_AUDIT"
    audit["rule"] = (
        "Fund holdings remain scenario-only until an independently validated longitudinal "
        "history/backtest promotes them; snapshot count alone never activates fitted central-price features."
    )
    return features, audit


external.fund_feature_panel = _guarded_fund_feature_panel

import forecast_v13_market_model as market_model  # noqa: E402


if __name__ == "__main__":
    sys.argv[0] = "forecast_v13_market_model.py"
    market_model.main()
