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
_original_horizon_price_gate=market_model.horizon_price_gate
_bridge_metadata={}; _historical_scan_as_of=""; _gate_counter=0

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


def _diagnostic_horizon_price_gate(audit,walk_forward):
    """Preserve the sealed gate while making every failing condition observable."""
    global _gate_counter
    _gate_counter+=1
    horizon=_gate_counter
    folds=audit.get("chronologicalFolds") or []
    wf_folds=walk_forward.get("folds") or []
    paired=audit.get("pairedNoChangeAudit") or {}
    checks={
        "maeSkill>=0.005": float(audit.get("maeSkill") or 0)>=.005,
        "rankIC>=0.05": float(audit.get("rankIC") or 0)>=.05,
        "coverage20_80[0.52,0.72]": .52<=float(audit.get("coverage20_80") or 0)<=.72,
        "executableMedianAbs>=0.0015": float(audit.get("executableMedianAbs") or 0)>=.0015,
        "executableMAESkill>=0.003": float(audit.get("executableMAESkill") or 0)>=.003,
        "chronologicalMAEPositive>=3": sum(float(fold.get("maeSkill") or 0)>0 for fold in folds)>=3,
        "chronologicalExecutableMAEPositive>=3": sum(float(fold.get("executableMAESkill") or 0)>0 for fold in folds)>=3,
        "magnitudeMAESkill>0": float(audit.get("magnitudeMAESkill") or 0)>0,
        "walkForwardExecutablePositive>=2": int(walk_forward.get("positiveExecutableMAEFolds") or 0)>=2,
        "walkForwardMagnitudePositive>=2": int(walk_forward.get("positiveMagnitudeFolds") or 0)>=2,
        "walkForwardMeanExecutableMAE>0": float(walk_forward.get("meanExecutableMAESkill") or 0)>0,
        "walkForwardMeanRankIC>=0.05": float(walk_forward.get("meanRankIC") or 0)>=.05,
    }
    if audit.get("architecture")=="MARKET_RELATIVE":
        checks.update({
            "marketRegimeStatus=ACTIVE": audit.get("marketRegimeStatus")=="ACTIVE",
            "regimeArchitectureStatus=ACTIVE": audit.get("regimeArchitectureStatus")=="ACTIVE",
            "walkForwardFoldCount=3": len(wf_folds)==3,
            "allWalkForwardArchitecture=MARKET_RELATIVE": len(wf_folds)==3 and all(fold.get("architecture")=="MARKET_RELATIVE" for fold in wf_folds),
            "walkForwardPositiveMAEFolds=3": int(walk_forward.get("positiveMAEFolds") or 0)==3,
            "walkForwardPositiveExecutableMAEFolds=3": int(walk_forward.get("positiveExecutableMAEFolds") or 0)==3,
            "walkForwardMeanExecutableMAE>=0.005": float(walk_forward.get("meanExecutableMAESkill") or 0)>=.005,
            "latestWalkForwardExecutableMAE>0": bool(wf_folds) and float(wf_folds[-1].get("executableMAESkill") or 0)>0,
            "directionalAccuracy>=0.53": float(audit.get("directionalAccuracy") or 0)>=.53,
            "pairedImprovement>DailySE": float(paired.get("meanImprovement") or 0)>float(paired.get("dailyStandardError") or float("inf")),
            "pairedPositiveChronologicalBlocks>=3": int(paired.get("positiveChronologicalBlocks") or 0)>=3,
        })
    passed=_original_horizon_price_gate(audit,walk_forward)
    payload={
        "stage":"horizon_price_gate_diagnostics",
        "horizon":horizon,
        "passed":passed,
        "architecture":audit.get("architecture"),
        "failedChecks":[name for name,ok in checks.items() if not ok],
        "metrics":{
            "maeSkill":audit.get("maeSkill"),
            "rankIC":audit.get("rankIC"),
            "coverage20_80":audit.get("coverage20_80"),
            "executableMedianAbs":audit.get("executableMedianAbs"),
            "executableMAESkill":audit.get("executableMAESkill"),
            "magnitudeMAESkill":audit.get("magnitudeMAESkill"),
            "directionalAccuracy":audit.get("directionalAccuracy"),
            "marketRegimeStatus":audit.get("marketRegimeStatus"),
            "regimeArchitectureStatus":audit.get("regimeArchitectureStatus"),
            "pairedMeanImprovement":paired.get("meanImprovement"),
            "pairedDailyStandardError":paired.get("dailyStandardError"),
            "pairedPositiveChronologicalBlocks":paired.get("positiveChronologicalBlocks"),
            "walkForwardPositiveMAEFolds":walk_forward.get("positiveMAEFolds"),
            "walkForwardPositiveExecutableMAEFolds":walk_forward.get("positiveExecutableMAEFolds"),
            "walkForwardPositiveMagnitudeFolds":walk_forward.get("positiveMagnitudeFolds"),
            "walkForwardMeanExecutableMAESkill":walk_forward.get("meanExecutableMAESkill"),
            "walkForwardMeanRankIC":walk_forward.get("meanRankIC"),
            "latestWalkForwardExecutableMAESkill":(wf_folds[-1].get("executableMAESkill") if wf_folds else None),
        },
    }
    print(json.dumps(payload,ensure_ascii=False,allow_nan=False),flush=True)
    return passed

market_model.load_histories=_load_histories_with_current_session
market_model.next_trading_dates=certified_next_trading_dates
market_model.horizon_price_gate=_diagnostic_horizon_price_gate

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
