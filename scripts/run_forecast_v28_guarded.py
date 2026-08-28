"""Run the market forecast with conservative fund and freshness governance."""

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
from forecast_v28_postclose_bridge import bridge_completed_session  # noqa: E402


_original_load_histories = market_model.load_histories


def _load_histories_with_current_session(*args, **kwargs):
    histories, freshness = _original_load_histories(*args, **kwargs)
    return bridge_completed_session(histories, freshness)


market_model.load_histories = _load_histories_with_current_session


if __name__ == "__main__":
    sys.argv[0] = "forecast_v13_market_model.py"
    market_model.main()
