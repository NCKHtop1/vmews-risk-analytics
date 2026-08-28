"""Run the market forecast with conservative fund and freshness governance."""
from __future__ import annotations
import json, sys
from pathlib import Path
import forecast_v16_external_data as external

_original_fund_feature_panel=external.fund_feature_panel

def _guarded_fund_feature_panel(*args,**kwargs):
    features,audit=_original_fund_feature_panel(*args,**kwargs); audit=dict(audit or {})
    audit["rawHistoryGateEligible"]=bool(audit.get("modelEligible")); audit["modelEligible"]=False
    audit["status"]="CONTEXT_ONLY" if audit.get("snapshotCount",0) else audit.get("status","UNAVAILABLE")
    audit["trainingFeaturesMasked"]=True; audit["promotionRequired"]="SEPARATE_LONGITUDINAL_BACKTEST_AND_STABILITY_AUDIT"
    audit["rule"]="Fund holdings remain scenario-only until an independently validated longitudinal history/backtest promotes them; snapshot count alone never activates fitted central-price features."
    return features,audit
external.fund_feature_panel=_guarded_fund_feature_panel

import forecast_v13_market_model as market_model  # noqa:E402
from forecast_v28_postclose_bridge import bridge_completed_session  # noqa:E402
from vn_exchange_calendar import next_trading_dates as certified_next_trading_dates  # noqa:E402

_original_load_histories=market_model.load_histories
_bridge_metadata={}; _historical_scan_as_of=""

def _load_histories_with_current_session(*args,**kwargs):
    global _bridge_metadata,_historical_scan_as_of
    histories,freshness=_original_load_histories(*args,**kwargs)
    _historical_scan_as_of=str(freshness.get("marketScanAsOf") or "")[:10]
    secondary=market_model._vn_direct_hose_rows()
    histories,freshness=bridge_completed_session(histories,freshness,secondary_rows=secondary)
    bridge=freshness.get("postCloseBridge") or {}; _bridge_metadata=dict(bridge)
    if bridge.get("status")=="PASS":
        freshness["historicalMarketScanAsOf"]=_historical_scan_as_of
        freshness["marketScanAsOf"]=str(freshness.get("forecastAsOf") or "")[:10]
        freshness["freshSymbols"]=sum(str((rows or [{}])[-1].get("date") or "")[:10]==freshness["forecastAsOf"] for rows in histories.values() if rows)
        freshness["staleSymbols"]=len(histories)-freshness["freshSymbols"]
    return histories,freshness

market_model.load_histories=_load_histories_with_current_session
market_model.next_trading_dates=certified_next_trading_dates

def _persist_source_semantics():
    data=Path(__file__).resolve().parents[1]/"data"; market_path=data/"forecast-market-v13.json"; dash_path=data/"forecast-dashboard-v12.json"
    if not market_path.exists() or not dash_path.exists(): return
    market=json.loads(market_path.read_text(encoding="utf-8")); dash=json.loads(dash_path.read_text(encoding="utf-8"))
    sources=market.setdefault("sources",{}); sources["priceSessionAsOf"]=market.get("asOf"); sources["historicalRiskScanAsOf"]=_historical_scan_as_of or None
    if _bridge_metadata:
        sources["postCloseBridge"]=_bridge_metadata; sources["marketScanAsOfSemantics"]="CURRENT_PRICE_SESSION_COMPATIBILITY_ALIAS"
        mf=dash.setdefault("marketForecast",{}); mf["priceSessionAsOf"]=dash.get("asOf"); mf["historicalRiskScanAsOf"]=_historical_scan_as_of or None; mf["postCloseBridge"]=_bridge_metadata
    market_path.write_text(json.dumps(market,ensure_ascii=False,separators=(",",":"),allow_nan=False),encoding="utf-8")
    dash_path.write_text(json.dumps(dash,ensure_ascii=False,separators=(",",":"),allow_nan=False),encoding="utf-8")

if __name__=="__main__":
    sys.argv[0]="forecast_v13_market_model.py"; market_model.main(); _persist_source_semantics()
