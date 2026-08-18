#!/usr/bin/env python3
"""Production-stack diagnostic for the 18 current-HOSE original-deep symbols unresolved in freeze #6.

Uses the exact production stack: transient-only acquisition resilience + strict post-last-break
continuous suffix salvage. It does not change the 12% return guard, 0.003 cross-source gate,
minimum 520-row requirement, or any corporate-action verification rule.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import v12_source_capture as capture
import v12_reference_resilience
from v12_source_capture_methodfix import install as install_continuity

SYMBOLS = ["ABR","ADP","AFX","ANT","DSC","GEE","HHV","HNA","KLB","NHH","NHT","ORS","PDV","PGV","PVP","TCI","VBB","VVS"]


def main():
    capture.reset_provider_circuits()
    resilience_audit = v12_reference_resilience.install(capture, max_attempts=3, backoff_seconds=(1.0, 2.0))
    install_continuity()
    result = {
        "version": "VMEWS-V12-CA-18-PRODUCTION-STACK-PROBE-1.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "symbols": {},
        "resilience": resilience_audit,
        "continuityPolicy": "STRICT_POST_LAST_UNRESOLVED_GT_GUARD_SUFFIX_MIN_ROWS_UNCHANGED",
    }
    for i, symbol in enumerate(SYMBOLS, 1):
        try:
            rows, audit = capture.capture_price_history(symbol)
            ca = audit.get("corporateAction") or {}
            pre_ca = audit.get("preTruncationCorporateAction") or {}
            entry = {
                "captured": True,
                "rows": len(rows),
                "eligible": audit.get("eligible") is True,
                "route": audit.get("route"),
                "ineligibleReasons": audit.get("ineligibleReasons"),
                "crossSourceReturnMAD": audit.get("crossSourceReturnMAD"),
                "corporateActionVerified": ca.get("verified") is True,
                "corporateAction": ca,
                "historyContinuityPolicy": audit.get("historyContinuityPolicy"),
                "safeSuffixStartDate": audit.get("safeSuffixStartDate"),
                "unresolvedBreakDates": audit.get("unresolvedBreakDates") or [],
                "originalRows": audit.get("originalRows", len(rows)),
                "retainedRows": audit.get("retainedRows", len(rows)),
                "discardedRows": audit.get("discardedRows", 0),
                "preTruncationIneligibleReasons": audit.get("preTruncationIneligibleReasons") or [],
                "preTruncationCorporateAction": pre_ca,
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
            "policy": entry.get("historyContinuityPolicy"),
            "safeSuffixStartDate": entry.get("safeSuffixStartDate"),
            "retainedRows": entry.get("retainedRows"),
            "lastBreak": (entry.get("unresolvedBreakDates") or [None])[-1],
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
        "note": "This probe mirrors the production continuity stack; it is diagnostic only.",
    }
    out = Path("data/v12-ca-19-quota-probe.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
