"""Offline audit of the frozen V12 corporate-action gate cohort.

No network access and no source mutation. Reads the committed immutable snapshot and
reports the exact original-deep cohort, CA verification state, continuity truncations,
and current retained eligibility so source-gate debugging is evidence-based.
"""
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SNAP = DATA / "v12-frozen-source.json.gz"
MAN = DATA / "v12-frozen-source-manifest.json"
OUT = DATA / "v12-frozen-ca-cohort-audit.json"
MIN_ROWS = 520


def main():
    payload = json.loads(gzip.decompress(SNAP.read_bytes()).decode("utf-8"))
    manifest = json.loads(MAN.read_text(encoding="utf-8"))
    current = set(payload.get("currentHOSESymbols") or [])
    histories = payload.get("histories") or {}
    audits = payload.get("audits") or {}

    original_deep = []
    verified = []
    unverified = []
    truncated = []
    truncated_below = []
    retained_deep_ineligible = []
    details = {}

    for symbol in sorted(current & set(histories)):
        rows = histories.get(symbol) or []
        audit = audits.get(symbol) or {}
        orig = int(audit.get("originalRows") or len(rows))
        ca = audit.get("corporateAction") or {}
        is_verified = ca.get("verified") is True
        policy = audit.get("historyContinuityPolicy")
        eligible = audit.get("eligible") is True
        if orig >= MIN_ROWS:
            original_deep.append(symbol)
            (verified if is_verified else unverified).append(symbol)
        if policy == "TRUNCATE_BEFORE_LAST_UNRESOLVED_GT_GUARD_BREAK":
            truncated.append(symbol)
            if len(rows) < MIN_ROWS:
                truncated_below.append(symbol)
        if len(rows) >= MIN_ROWS and not eligible:
            retained_deep_ineligible.append(symbol)
        if orig >= MIN_ROWS and (not is_verified or policy == "TRUNCATE_BEFORE_LAST_UNRESOLVED_GT_GUARD_BREAK"):
            details[symbol] = {
                "rows": len(rows),
                "originalRows": orig,
                "eligible": eligible,
                "caVerified": is_verified,
                "continuityPolicy": policy,
                "safeSuffixStartDate": audit.get("safeSuffixStartDate"),
                "ineligibleReasons": audit.get("ineligibleReasons"),
                "preTruncationIneligibleReasons": audit.get("preTruncationIneligibleReasons"),
                "corporateAction": ca,
                "preTruncationCorporateAction": audit.get("preTruncationCorporateAction"),
            }

    ratio = len(verified) / max(1, len(original_deep))
    out = {
        "version": "VMEWS-V12-FROZEN-CA-COHORT-AUDIT-1.0.0",
        "snapshotFileSha256": manifest.get("snapshotFileSha256"),
        "asOf": manifest.get("asOf"),
        "minRows": MIN_ROWS,
        "currentHOSE": len(current),
        "retainedDeep": int(manifest.get("deepHistory") or 0),
        "retainedModelEligible": int(manifest.get("modelEligible") or 0),
        "retainedCorporateActionVerifiedRatio": manifest.get("corporateActionVerifiedRatio"),
        "originalDeepCount": len(original_deep),
        "originalDeepVerifiedCount": len(verified),
        "originalDeepVerifiedRatio": ratio,
        "originalDeepGatePass98": ratio >= 0.98,
        "originalDeepUnverifiedSymbols": unverified,
        "continuityTruncatedSymbols": truncated,
        "continuityTruncatedBelowMinRows": truncated_below,
        "retainedDeepIneligibleSymbols": retained_deep_ineligible,
        "details": details,
        "runtimeNetworkPriceFetch": False,
        "gateMutation": False,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: out[k] for k in [
        "asOf","originalDeepCount","originalDeepVerifiedCount","originalDeepVerifiedRatio",
        "originalDeepGatePass98","originalDeepUnverifiedSymbols","continuityTruncatedSymbols",
        "continuityTruncatedBelowMinRows","retainedDeepIneligibleSymbols"
    ]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
