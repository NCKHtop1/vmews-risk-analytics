"""Exchange-calendar and current-session aware release-audit wrapper."""
from __future__ import annotations
import json
from datetime import datetime
import forecast_v20_release_audit as legacy
from vn_exchange_calendar import VN_TZ, latest_completed_session, trading_session_age

legacy._business_age=lambda observed,as_of: trading_session_age(observed,as_of)
legacy.completed_session=lambda: latest_completed_session()
_original=legacy.run_audit

V41_MARKET_VERSION="VMEWS-MARKET-FORECAST-41.0.0"
_LEGACY_VERSION_BLOCKERS={
    "market artifact is not V39",
    "dashboard model version differs from market",
    "current model version differs from market",
}

def run_audit():
    report=_original()
    market=json.loads((legacy.DATA/"forecast-market-v13.json").read_text(encoding="utf-8"))
    dashboard=json.loads((legacy.DATA/"forecast-dashboard-v12.json").read_text(encoding="utf-8"))
    current=json.loads((legacy.DATA/"forecast-current-v12.json").read_text(encoding="utf-8"))

    # The legacy V20 audit intentionally pins V39. V41 changes the fitted feature
    # space and must publish a new exact version across all three public artifacts.
    # Remove only the obsolete V39-string blockers when the V41 version contract
    # is itself exact and internally consistent; every statistical/data/leakage
    # blocker from the legacy audit remains untouched.
    versions=(
        market.get("version"),
        dashboard.get("modelVersion"),
        current.get("modelVersion"),
    )
    if versions==(V41_MARKET_VERSION,V41_MARKET_VERSION,V41_MARKET_VERSION):
        report["blockers"]=[
            blocker for blocker in report.get("blockers",[])
            if blocker not in _LEGACY_VERSION_BLOCKERS
        ]
    else:
        message=(
            "V41 artifact version contract mismatch: "
            f"market={versions[0]!r} dashboard={versions[1]!r} current={versions[2]!r}"
        )
        if message not in report["blockers"]:
            report["blockers"].append(message)

    sources=market.get("sources") or {}; bridge=sources.get("postCloseBridge") or {}
    expected=latest_completed_session(); today=datetime.now(VN_TZ).date()
    if expected==today and str(report.get("asOf") or "")[:10]==today.isoformat():
        checks=[
            (bridge.get("status")=="PASS","current session post-close bridge is not PASS"),
            (bridge.get("completedSessionVerified") is True,"current session completion is not verified"),
            (bridge.get("independentCloseConfirmed") is True,"current close lacks independent confirmation"),
            (float(bridge.get("coverage") or 0)>=float(bridge.get("minimumCoverage") or 1),"primary same-day OHLC coverage is insufficient"),
            (float(bridge.get("secondaryCoverage") or 0)>=float(bridge.get("minimumSecondaryCoverage") or 1),"secondary same-day close coverage is insufficient"),
            (int(bridge.get("mismatchCount") or 0)==0,"current-session sources disagree beyond tolerance"),
            (bridge.get("realOHLCRequired") is True,"synthetic current-session OHLC is allowed"),
        ]
        for ok,message in checks:
            if not ok and message not in report["blockers"]: report["blockers"].append(message)
    report["status"]="PASS" if not report["blockers"] else "FAIL"
    report.setdefault("price",{})["currentSessionBridge"]=bridge
    report.setdefault("limitations",[]).append("A current-session forecast is withheld unless same-day real OHLC coverage and independent close confirmation pass; provider failure therefore causes abstention rather than a stale-date relabel.")
    return report

legacy.run_audit=run_audit
if __name__=="__main__": legacy.main()
