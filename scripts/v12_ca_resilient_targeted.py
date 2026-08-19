"""Targeted CA audit for the historically unresolved current-HOSE cohort.

This diagnostic does not change prices, returns, eligibility thresholds, CA rules, or
freeze gates. It re-runs the exact resilient + strict-continuity capture path only for
the 41 symbols that were unresolved in the earlier full-universe diagnostic, so later
source-freeze work can distinguish transient acquisition failures from permanent data
quality failures without repeatedly recapturing the whole universe.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import v12_source_capture as capture
from v12_reference_resilience import install as install_resilience
from v12_source_capture_methodfix import install as install_continuity

SYMBOLS = [
    "ABR","ADG","ADP","AFX","ANT","BCM","BSR","BVB","CTR","DSC","EVF","GEE","GHC","GVR","HHV","HNA","HTG","KLB","KOS","LPB","MCH","MCM","NAB","NHH","NHT","NTC","ORS","PDV","PGV","PVP","SIP","TAL","TCI","TDP","TSA","VAB","VBB","VCA","VIB","VTP","VVS"
]

OUT = Path("data/v12-ca-resilient-targeted.json")


def _jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    try:
        if value != value:
            return None
    except Exception:
        pass
    return str(value)


def main():
    resilience = install_resilience(capture, max_attempts=3, backoff_seconds=(1.0, 2.0))
    install_continuity()
    capture.reset_provider_circuits()

    result = {
        "version": "VMEWS-V12-CA-RESILIENT-TARGETED-1.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "scientificGateMutation": False,
        "priceOrReturnMutation": False,
        "resilience": resilience,
        "symbols": {},
    }

    for i, symbol in enumerate(SYMBOLS, 1):
        entry = {}
        try:
            rows, audit = capture.capture_price_history(symbol)
            audit = dict(audit or {})
            ca = audit.get("corporateAction") or {}
            entry.update({
                "captured": True,
                "rows": len(rows),
                "originalRows": int(audit.get("originalRows") or len(rows)),
                "eligible": audit.get("eligible") is True,
                "caVerified": ca.get("verified") is True,
                "route": audit.get("route"),
                "historyContinuityPolicy": audit.get("historyContinuityPolicy"),
                "safeSuffixStartDate": audit.get("safeSuffixStartDate"),
                "ineligibleReasons": audit.get("ineligibleReasons"),
                "crossSourceReturnMAD": audit.get("crossSourceReturnMAD"),
                "corporateAction": ca,
                "attempts": audit.get("attempts") or [],
            })
        except BaseException as exc:
            entry.update({
                "captured": False,
                "eligible": False,
                "caVerified": False,
                "error": f"{type(exc).__name__}: {exc}"[:1200],
                "attempts": getattr(exc, "attempts", []) or [],
            })
        result["symbols"][symbol] = _jsonable(entry)
        print(json.dumps({
            "targetedResilientCA": i,
            "total": len(SYMBOLS),
            "symbol": symbol,
            "captured": entry.get("captured"),
            "eligible": entry.get("eligible"),
            "caVerified": entry.get("caVerified"),
            "rows": entry.get("rows"),
            "originalRows": entry.get("originalRows"),
            "continuity": entry.get("historyContinuityPolicy"),
        }, ensure_ascii=False), flush=True)

    symbols = result["symbols"]
    result["summary"] = {
        "requested": len(SYMBOLS),
        "captured": sum(v.get("captured") is True for v in symbols.values()),
        "eligible": sum(v.get("eligible") is True for v in symbols.values()),
        "caVerified": sum(v.get("caVerified") is True for v in symbols.values()),
        "deepOriginal": sum(int(v.get("originalRows") or 0) >= capture.base.MIN_ROWS for v in symbols.values()),
        "deepOriginalCaVerified": sum(
            int(v.get("originalRows") or 0) >= capture.base.MIN_ROWS and v.get("caVerified") is True
            for v in symbols.values()
        ),
        "unverifiedSymbols": sorted(s for s, v in symbols.items() if v.get("caVerified") is not True),
        "ineligibleSymbols": sorted(s for s, v in symbols.items() if v.get("eligible") is not True),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"V12_TARGETED_RESILIENT_CA_SUMMARY": result["summary"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
