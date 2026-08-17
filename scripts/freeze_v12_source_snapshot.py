import gzip
import hashlib
import json
import math
import pathlib
from collections import Counter
from datetime import datetime, timezone

from v12_universe import current_hose_symbols
import v12_data_sources as ds

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "v12-frozen-source.json.gz"
MAN = DATA / "v12-frozen-source-manifest.json"
DIAG = DATA / "v12-source-freeze-diagnostic.json"


def finite(v):
    try:
        return math.isfinite(float(v))
    except Exception:
        return False


def stable(v):
    try:
        x = float(v)
        return round(x, 10) if math.isfinite(x) else None
    except Exception:
        return None


def fingerprint(rows):
    arr = [[
        str(r.get("date", ""))[:10],
        stable(r.get("open")),
        stable(r.get("high")),
        stable(r.get("low")),
        stable(r.get("close")),
        stable(r.get("modelClose", r.get("close"))),
        stable(r.get("volume")),
        stable(r.get("adjustmentFactor", 1.0)),
    ] for r in rows]
    raw = json.dumps(arr, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _attempt_stage_counts(audits):
    counts = Counter()
    failures = Counter()
    for audit in audits.values():
        for attempt in audit.get("attempts") or []:
            stage = str(attempt.get("stage") or "UNKNOWN")
            counts[stage] += 1
            if attempt.get("ok") is False:
                failures[stage] += 1
    return dict(sorted(counts.items())), dict(sorted(failures.items()))


def _write_diag(diag):
    DATA.mkdir(parents=True, exist_ok=True)
    DIAG.write_text(
        json.dumps(diag, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps({"v12SourceFreezeDiagnostic": diag}, ensure_ascii=False, allow_nan=False), flush=True)


def main():
    symbols = sorted(current_hose_symbols())
    store, audits, failures = ds.build_price_store(symbols)
    if not store:
        diag = {
            "status": "FAIL",
            "gateFailures": ["captured_no_symbols"],
            "requested": len(symbols),
            "available": 0,
            "captureFailures": failures,
        }
        _write_diag(diag)
        raise RuntimeError("V12 source freeze captured no symbols")

    ends = [str(rows[-1].get("date", ""))[:10] for rows in store.values() if rows]
    as_of = max(set(ends), key=ends.count)
    store = {
        s: [r for r in rows if str(r.get("date", ""))[:10] <= as_of]
        for s, rows in store.items()
    }
    store = {s: rows for s, rows in store.items() if rows}
    audits = {s: audits[s] for s in store if s in audits}

    available = len(store)
    deep = sum(len(rows) >= ds.MIN_ROWS for rows in store.values())
    coverage = available / max(1, len(symbols))

    cas = [
        (a.get("corporateAction") or {}).get("verified") is True
        for a in audits.values()
    ]
    ca_ratio = sum(cas) / max(1, len(cas))

    mads = [
        float(a.get("crossSourceReturnMAD"))
        for a in audits.values()
        if isinstance(a.get("crossSourceReturnMAD"), (int, float))
        and finite(a.get("crossSourceReturnMAD"))
    ]
    p95 = (
        sorted(mads)[min(len(mads) - 1, int(round((len(mads) - 1) * 0.95)))]
        if mads else None
    )

    attempted = sum(
        any(x.get("stage") == "VNSTOCK_PRIMARY" for x in (a.get("attempts") or []))
        for a in audits.values()
    )
    attempt_ratio = attempted / max(1, available)

    route_counts = Counter(str(a.get("route") or "UNKNOWN") for a in audits.values())
    provider_counts = Counter(
        str(((a.get("rawSource") or {}).get("providerCode") or
             (a.get("rawSource") or {}).get("provider") or "UNKNOWN"))
        for a in audits.values()
    )
    attempt_stage_counts, attempt_stage_failures = _attempt_stage_counts(audits)

    gate_failures = []
    if coverage < 0.98:
        gate_failures.append(f"coverage:{available}/{len(symbols)}={coverage:.6f}<0.98")
    if deep < 360:
        gate_failures.append(f"deep_history:{deep}<360")
    if ca_ratio < 0.98:
        gate_failures.append(f"corporate_action_verified:{ca_ratio:.6f}<0.98")
    if p95 is not None and p95 > 0.003:
        gate_failures.append(f"cross_source_mad_p95:{p95:.10f}>0.003")
    if attempted < max(1, available) * 0.95:
        gate_failures.append(f"vnstock_primary_attempted:{attempted}/{available}={attempt_ratio:.6f}<0.95")

    diag = {
        "status": "FAIL" if gate_failures else "GATES_PASS",
        "asOf": as_of,
        "requested": len(symbols),
        "available": available,
        "deepHistory": deep,
        "coverageRatio": coverage,
        "corporateActionVerifiedRatio": ca_ratio,
        "crossSourceMADP95": p95,
        "crossSourceMADCount": len(mads),
        "vnstockPrimaryAttempted": attempted,
        "vnstockPrimaryAttemptRatio": attempt_ratio,
        "routeCounts": dict(sorted(route_counts.items())),
        "providerCounts": dict(sorted(provider_counts.items())),
        "attemptStageCounts": attempt_stage_counts,
        "attemptStageFailures": attempt_stage_failures,
        "gateFailures": gate_failures,
        "captureFailureCount": len(failures),
        "captureFailures": failures,
    }
    _write_diag(diag)

    if gate_failures:
        raise RuntimeError("Frozen-source gates failed: " + " | ".join(gate_failures))

    symbol_manifest = {}
    for s, rows in sorted(store.items()):
        a = audits.get(s) or {}
        symbol_manifest[s] = {
            "route": a.get("route"),
            "provider": ((a.get("rawSource") or {}).get("providerCode") or
                         (a.get("rawSource") or {}).get("provider")),
            "rows": len(rows),
            "start": rows[0]["date"],
            "end": rows[-1]["date"],
            "sha256": fingerprint(rows),
        }

    manifest_raw = json.dumps(
        [{"symbol": s, **m} for s, m in sorted(symbol_manifest.items())],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    input_manifest_sha = hashlib.sha256(manifest_raw).hexdigest()

    payload = {
        "version": "VMEWS-FROZEN-SOURCE-12.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "asOf": as_of,
        "sourcePolicy": "ONE_TIME_AUDITED_VNSTOCK_FIRST_CAPTURE_THEN_IMMUTABLE",
        "requestedSymbols": symbols,
        "histories": store,
        "audits": audits,
        "captureFailures": failures,
    }
    raw = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    blob = gzip.compress(raw, compresslevel=9, mtime=0)
    OUT.write_bytes(blob)
    file_sha = hashlib.sha256(blob).hexdigest()

    manifest = {
        "version": "VMEWS-FROZEN-SOURCE-MANIFEST-12.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "asOf": as_of,
        "requested": len(symbols),
        "available": available,
        "deepHistory": deep,
        "coverageRatio": coverage,
        "corporateActionVerifiedRatio": ca_ratio,
        "crossSourceMADP95": p95,
        "vnstockPrimaryAttempted": attempted,
        "inputManifestSha256": input_manifest_sha,
        "snapshotFileSha256": file_sha,
        "snapshotBytes": len(blob),
        "symbols": symbol_manifest,
        "captureFailures": failures,
    }
    MAN.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps({
        "v12SourceFreeze": "PASS",
        "asOf": as_of,
        "requested": len(symbols),
        "available": available,
        "deepHistory": deep,
        "coverageRatio": coverage,
        "snapshotBytes": len(blob),
        "snapshotFileSha256": file_sha,
        "inputManifestSha256": input_manifest_sha,
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
