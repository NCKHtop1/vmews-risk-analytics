#!/usr/bin/env python3
"""Quota-safe diagnostic for the 19 original-deep symbols unresolved in freeze #3.

This is diagnostic only. It uses the exact production capture/audit logic and transient-only
resilience wrapper. It never mutates returns, CA gates, or eligibility thresholds.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import v12_source_capture as capture
import v12_reference_resilience

SYMBOLS = ["ABR","ADP","AFX","ANT","DSC","GEE","HHV","HNA","KLB","NHH","NHT","ORS","PDV","PGV","PVP","SIP","TCI","VBB","VVS"]


def main():
    capture.reset_provider_circuits()
    resilience_audit = v12_reference_resilience.install(capture, max_attempts=3, backoff_seconds=(1.0, 2.0))
    result = {
        "version": "VMEWS-V12-CA-19-QUOTA-PROBE-1.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "symbols": {},
        "resilience": resilience_audit,
    }
    for i, symbol in enumerate(SYMBOLS, 1):
        entry = {}
        try:
            rows, audit = capture.capture_price_history(symbol)
            ca = audit.get("corporateAction") or {}
            entry = {
                "captured": True,
                "rows": len(rows),
                "eligible": audit.get("eligible") is True,
                "route": audit.get("route"),
                "ineligibleReasons": audit.get("ineligibleReasons"),
                "crossSourceReturnMAD": audit.get("crossSourceReturnMAD"),
                "corporateActionVerified": ca.get("verified") is True,
                "corporateAction": ca,
                "attempts": audit.get("attempts") or [],
            }
        except BaseException as exc:
            entry = {
                "captured": False,
                "eligible": False,
                "corporateActionVerified": False,
                "error": f"{type(exc).__name__}: {exc}"[:1600],
                "attempts": getattr(exc, "attempts", []) or [],
            }
        result["symbols"][symbol] = entry
        print(json.dumps({
            "i": i,
            "n": len(SYMBOLS),
            "symbol": symbol,
            "eligible": entry.get("eligible"),
            "caVerified": entry.get("corporateActionVerified"),
            "reasons": entry.get("ineligibleReasons"),
        }, ensure_ascii=False), flush=True)
    verified = [s for s,v in result["symbols"].items() if v.get("corporateActionVerified") is True]
    eligible = [s for s,v in result["symbols"].items() if v.get("eligible") is True]
    failed = [s for s in SYMBOLS if s not in verified]
    result["summary"] = {
        "requested": len(SYMBOLS),
        "captured": sum(v.get("captured") is True for v in result["symbols"].values()),
        "eligible": len(eligible),
        "caVerified": len(verified),
        "verifiedSymbols": verified,
        "failedSymbols": failed,
        "requiredRescueFor384Denominator": 12,
        "wouldClear98PctIfPrevious365VerifiedPlusTheseRescued": len(verified) >= 12,
    }
    out = Path("data/v12-ca-19-quota-probe.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
