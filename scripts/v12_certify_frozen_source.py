"""Certify the already-committed V12 frozen source without any network recapture.

The snapshot bytes are immutable. This script recomputes the stronger original-deep
corporate-action cohort directly from the snapshot audits and adds certification
metadata to the manifest only when every unchanged source gate passes.
"""
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SNAP = DATA / "v12-frozen-source.json.gz"
MAN = DATA / "v12-frozen-source-manifest.json"
MIN_ROWS = 520


def main():
    manifest = json.loads(MAN.read_text(encoding="utf-8"))
    blob = SNAP.read_bytes()
    actual = hashlib.sha256(blob).hexdigest()
    assert actual == manifest.get("snapshotFileSha256"), (actual, manifest.get("snapshotFileSha256"))
    payload = json.loads(gzip.decompress(blob).decode("utf-8"))
    assert payload.get("version") == "VMEWS-FROZEN-SOURCE-12.1.0", payload.get("version")

    current = set(payload.get("currentHOSESymbols") or [])
    histories = payload.get("histories") or {}
    audits = payload.get("audits") or {}
    cohort = []
    verified = []
    truncated = []
    truncated_below = []
    for symbol in sorted(current & set(histories)):
        rows = histories.get(symbol) or []
        audit = audits.get(symbol) or {}
        original_rows = int(audit.get("originalRows") or len(rows))
        if original_rows >= MIN_ROWS:
            cohort.append(symbol)
            if (audit.get("corporateAction") or {}).get("verified") is True:
                verified.append(symbol)
        if audit.get("historyContinuityPolicy") == "TRUNCATE_BEFORE_LAST_UNRESOLVED_GT_GUARD_BREAK":
            truncated.append(symbol)
            if len(rows) < MIN_ROWS:
                truncated_below.append(symbol)

    ratio = len(verified) / max(1, len(cohort))
    current_requested = int(manifest.get("currentHOSERequested") or 0)
    primary_attempted = int(manifest.get("vnstockPrimaryAttempted") or 0)
    p95 = float(manifest.get("crossSourceMADP95") if manifest.get("crossSourceMADP95") is not None else math.inf)
    gates = {
        "currentSourceCoverage": float(manifest.get("currentSourceCoverageRatio") or 0.0) >= 0.98,
        "deepHistory": int(manifest.get("deepHistory") or 0) >= 360,
        "modelEligible": int(manifest.get("modelEligible") or 0) >= 360,
        "corporateActionOriginalDeep": ratio >= 0.98,
        "corporateActionDenominatorNotShrunk": len(cohort) >= int(manifest.get("deepHistory") or 0),
        "crossSourceMADP95": p95 <= 0.003,
        "vnstockPrimaryAttempt": primary_attempted / max(1, current_requested) >= 0.95,
    }
    assert all(gates.values()), {"gates": gates, "ratio": ratio, "cohort": len(cohort), "verified": len(verified)}

    manifest.update({
        "corporateActionVerifiedRatio": ratio,
        "corporateActionVerifiedCount": len(verified),
        "corporateActionGateDenominator": len(cohort),
        "corporateActionGateCohort": "CURRENT_HOSE_ORIGINAL_DEEP_HISTORY_BEFORE_CONTINUITY_TRUNCATION",
        "continuityTruncatedCount": len(truncated),
        "continuityTruncatedBelowMinRowsCount": len(truncated_below),
        "continuityTruncatedSymbols": truncated,
        "continuityTruncatedBelowMinRows": truncated_below,
        "sourceFreezeCertificationVersion": "VMEWS-FROZEN-SOURCE-CERTIFICATION-12.1.1",
        "sourceFreezeCertificationMode": "OFFLINE_RECOMPUTED_FROM_COMMITTED_SNAPSHOT_AUDITS_NO_NETWORK",
        "sourceFreezeCertificationGates": gates,
        "sourceFreezeCertificationSnapshotSha256": actual,
    })
    MAN.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "snapshotSha256": actual,
        "originalDeep": len(cohort),
        "verified": len(verified),
        "ratio": ratio,
        "truncated": len(truncated),
        "gates": gates,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
