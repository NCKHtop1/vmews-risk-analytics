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
from forecast_v40_tail_blend import select_tail_guarded_directional_blend  # noqa:E402
from forecast_v41_runtime_patch import install_v41_refined  # noqa:E402
from forecast_v28_postclose_bridge import bridge_completed_session, fetch_tradingview_quotes, tradingview_close_confirmation  # noqa:E402
from vn_exchange_calendar import next_trading_dates as certified_next_trading_dates  # noqa:E402

# V40 protects amplitude/tail calibration. V41 adds market-wide causal technical
# transition geometry and a separately audited transition radar. Neither layer
# contains symbol-specific rules and both keep holdout labels sealed.
market_model.select_directional_magnitude_blend=select_tail_guarded_directional_blend
install_v41_refined(market_model)

_original_load_histories=market_model.load_histories
_bridge_metadata={}; _historical_scan_as_of=""

def _legacy_snapshot_rows(session_date: str) -> dict[str, list[dict]]:
    """Independent same-session fallback from the archived live snapshot.

    This source is used only to CONFIRM VNDIRECT close prices when TradingView
    coverage collapses. It never supplies synthetic OHLC or replaces the primary
    EOD history used by the model.
    """
    path=Path(__file__).resolve().parents[1]/"data"/"forecast-live-v10"/"snapshots"/f"{session_date}.json"
    if not path.exists():
        return {}
    payload=json.loads(path.read_text(encoding="utf-8"))
    if str(payload.get("asOf") or "")[:10] != session_date:
        return {}
    rows={}
    for item in payload.get("predictions") or []:
        symbol=str(item.get("symbol") or "").upper().strip()
        close=item.get("close")
        try:
            close=float(close)
        except (TypeError,ValueError):
            continue
        if symbol and close>0:
            rows[symbol]=[{"date":session_date,"close":close}]
    return rows

def _frame_from_vndirect(rows_by_symbol: dict[str, list[dict]], session_date: str):
    """Build a verified primary OHLC frame from VNDIRECT same-session bars."""
    import pandas as pd
    rows=[]
    for symbol,items in rows_by_symbol.items():
        matches=[x for x in (items or []) if str(x.get("date") or "")[:10]==session_date]
        if not matches:
            continue
        row=matches[-1]
        rows.append({
            "name":symbol,"exchange":"HOSE","date":session_date,
            "open":row.get("open"),"high":row.get("high"),"low":row.get("low"),
            "close":row.get("close"),"volume":row.get("volume"),"update_time":None,
        })
    return pd.DataFrame(rows)

def _tradingview_confirmation_rows(session_date: str) -> dict[str, list[dict]]:
    """Use TradingView only as an independent completed-session close confirmer.

    If TradingView has already rolled to today's session, recover the immediately
    previous close from current close + percentage change. This confirms VNDIRECT
    EOD without pretending that today's live row is yesterday's OHLC.
    """
    rows={}
    try:
        frame=fetch_tradingview_quotes()
    except Exception:
        return rows
    for _,item in frame.iterrows():
        symbol=str(item.get("name") or item.get("ticker") or "").upper().split(":")[-1].strip()
        exchange=str(item.get("exchange") or "").upper().strip()
        if exchange in {"HSX","HOCHIMINH"}:
            exchange="HOSE"
        if not symbol or exchange!="HOSE":
            continue
        close,mode=tradingview_close_confirmation(item,session_date)
        if close is not None and close>0:
            rows[symbol]=[{"date":session_date,"close":close,"confirmationMode":mode}]
    return rows

def _load_histories_with_current_session(*args,**kwargs):
    global _bridge_metadata,_historical_scan_as_of
    histories,freshness=_original_load_histories(*args,**kwargs)
    _historical_scan_as_of=str(freshness.get("marketScanAsOf") or "")[:10]
    secondary=market_model._vn_direct_hose_rows()
    try:
        histories,freshness=bridge_completed_session(histories,freshness,secondary_rows=secondary)
    except RuntimeError as primary_error:
        from datetime import datetime
        from vn_exchange_calendar import VN_TZ, latest_completed_session
        session_date=latest_completed_session(datetime.now(VN_TZ)).isoformat()
        yahoo_secondary=_legacy_snapshot_rows(session_date)
        tv_secondary=_tradingview_confirmation_rows(session_date)
        original_symbols=sorted(set(freshness.get("currentHOSESymbols") or histories))
        composite_secondary=dict(tv_secondary)
        for symbol,rows in yahoo_secondary.items():
            if symbol not in composite_secondary:
                composite_secondary[symbol]=rows
        verified_symbols=sorted(
            set(composite_secondary)
            & set(secondary)
            & set(original_symbols)
        )
        if len(verified_symbols) < max(1,int(len(original_symbols)*.90)):
            raise primary_error
        fallback_frame=_frame_from_vndirect(
            {symbol:secondary[symbol] for symbol in original_symbols if symbol in secondary},
            session_date,
        )
        histories,freshness=bridge_completed_session(
            histories,freshness,
            frame=fallback_frame,
            secondary_rows={symbol:composite_secondary[symbol] for symbol in verified_symbols},
            primary_name="VNDIRECT_PUBLIC_EOD",
            secondary_name="TRADINGVIEW_PREVIOUS_CLOSE_PLUS_YAHOO_CONFIRMATION",
            provider_label="VNDIRECT completed-session OHLC, independently confirmed close",
            provider_code="VNDIRECT_POST_CLOSE_COMPOSITE_CONFIRMED",
        )
        bridge=freshness.setdefault("postCloseBridge",{})
        bridge["fallbackFrom"]=str(primary_error)
        bridge["originalUniverseSymbols"]=len(original_symbols)
        bridge["tradingViewConfirmedSymbols"]=len(set(tv_secondary)&set(original_symbols))
        bridge["tradingViewPreviousCloseSymbols"]=sum(
            1 for symbol in set(tv_secondary)&set(original_symbols)
            if (tv_secondary[symbol] or [{}])[-1].get("confirmationMode")=="CURRENT_SESSION_CHANGE_IMPLIED_PREVIOUS_CLOSE"
        )
        bridge["yahooFillSymbols"]=len((set(yahoo_secondary)-set(tv_secondary))&set(original_symbols))
        bridge["fallbackVerifiedSymbols"]=len(verified_symbols)
        bridge["fallbackPolicy"]="VNDIRECT_OHLC_WITH_TRADINGVIEW_SAME_OR_IMPLIED_PREVIOUS_CLOSE_CONFIRMATION_AND_YAHOO_GAP_FILL"
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
    data=Path(__file__).resolve().parents[1]/"data"
    market_path=data/"forecast-market-v13.json"; dash_path=data/"forecast-dashboard-v12.json"; current_path=data/"forecast-current-v12.json"
    if not market_path.exists() or not dash_path.exists() or not current_path.exists(): return
    market=json.loads(market_path.read_text(encoding="utf-8")); dash=json.loads(dash_path.read_text(encoding="utf-8")); current=json.loads(current_path.read_text(encoding="utf-8"))
    sources=market.setdefault("sources",{}); sources["priceSessionAsOf"]=market.get("asOf"); sources["historicalRiskScanAsOf"]=_historical_scan_as_of or None
    if _bridge_metadata:
        sources["postCloseBridge"]=_bridge_metadata; sources["marketScanAsOfSemantics"]="CURRENT_PRICE_SESSION_COMPATIBILITY_ALIAS"
        mf=dash.setdefault("marketForecast",{}); mf["priceSessionAsOf"]=dash.get("asOf"); mf["historicalRiskScanAsOf"]=_historical_scan_as_of or None; mf["postCloseBridge"]=_bridge_metadata

    # V41 appends per-symbol transition diagnostics after the core writer has
    # produced both dashboard/current snapshots. Keep those two public symbol
    # contracts byte-semantically aligned instead of letting the radar exist in
    # only one artifact. This preserves the longstanding publication invariant
    # used by the regression suite and by downstream clients.
    dash_symbols=dash.get("symbols") or {}; current_symbols=current.get("symbols") or {}
    for symbol,snapshot in dash_symbols.items():
        if symbol in current_symbols and "technicalTransition" in snapshot:
            current_symbols[symbol]["technicalTransition"]=snapshot["technicalTransition"]
    current["symbols"]=current_symbols

    market_path.write_text(json.dumps(market,ensure_ascii=False,separators=(",",":"),allow_nan=False),encoding="utf-8")
    dash_path.write_text(json.dumps(dash,ensure_ascii=False,separators=(",",":"),allow_nan=False),encoding="utf-8")
    current_path.write_text(json.dumps(current,ensure_ascii=False,separators=(",",":"),allow_nan=False),encoding="utf-8")

if __name__=="__main__":
    sys.argv[0]="forecast_v13_market_model.py"; market_model.main(); _persist_source_semantics()
