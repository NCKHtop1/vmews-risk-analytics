import gzip
import hashlib
import json
import math
import pathlib
from collections import Counter
from datetime import datetime, timezone

from v12_universe import current_hose_symbols, discover_candidates
import v12_data_sources as ds
import v12_source_capture as capture

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
    raw = json.dumps(
        arr,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _attempt_stage_counts(audits, failures):
    counts = Counter()
    failed = Counter()
    attempt_lists = [a.get("attempts") or [] for a in audits.values()]
    attempt_lists.extend(
        (f.get("attempts") or [])
        for f in failures.values()
        if isinstance(f, dict)
    )
    for attempts in attempt_lists:
        for attempt in attempts:
            stage = str(attempt.get("stage") or "UNKNOWN")
            counts[stage] += 1
            if attempt.get("ok") is False:
                failed[stage] += 1
    return dict(sorted(counts.items())), dict(sorted(failed.items()))


def _write_diag(diag):
    DATA.mkdir(parents=True, exist_ok=True)
    DIAG.write_text(
        json.dumps(diag, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps(
        {"v12SourceFreezeDiagnostic": diag},
        ensure_ascii=False,
        allow_nan=False,
    ), flush=True)


def _percentile95(values):
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return ordered[idx]


def _modal_end(store, current_symbols):
    ends = [
        str(store[s][-1].get("date", ""))[:10]
        for s in current_symbols
        if s in store and store[s]
    ]
    if not ends:
        return None
    counts = Counter(ends)
    return max(counts, key=lambda d: (counts[d], d))


def main():
    current_symbols = sorted(current_hose_symbols())
    historical_candidates, universe_discovery = discover_candidates()
    historical_candidates = {
        s: meta
        for s, meta in sorted(historical_candidates.items())
        if s not in set(current_symbols)
    }
    historical_symbols = sorted(historical_candidates)
    symbols = sorted(set(current_symbols) | set(historical_symbols))

    discovery_error = (
        (universe_discovery.get("vnstockReference") or {}).get("error")
        if isinstance(universe_discovery, dict)
        else "invalid universe discovery payload"
    )

    store, audits, failures = capture.build_source_capture_store(symbols)
    if not store:
        diag = {
            "status": "FAIL",
            "gateFailures": ["captured_no_symbols"],
            "requested": len(symbols),
            "currentHOSERequested": len(current_symbols),
            "historicalCandidateRequested": len(historical_symbols),
            "available": 0,
            "sourceCoverageRatio": 0.0,
            "captureFailures": failures,
            "universeDiscovery": universe_discovery,
        }
        _write_diag(diag)
        raise RuntimeError("V12 source freeze captured no symbols")

    as_of = _modal_end(store, current_symbols)
    if not as_of:
        diag = {
            "status": "FAIL",
            "gateFailures": ["no_current_hose_modal_cutoff"],
            "requested": len(symbols),
            "available": len(store),
            "captureFailures": failures,
            "universeDiscovery": universe_discovery,
        }
        _write_diag(diag)
        raise RuntimeError("V12 source freeze has no current-HOSE cutoff")

    store = {
        s: [r for r in rows if str(r.get("date", ""))[:10] <= as_of]
        for s, rows in store.items()
    }
    store = {s: rows for s, rows in store.items() if rows}
    audits = {s: audits[s] for s in store if s in audits}

    requested_total = len(symbols)
    available_total = len(store)
    total_coverage = available_total / max(1, requested_total)

    current_set = set(current_symbols)
    historical_set = set(historical_symbols)
    current_captured = current_set & set(store)
    historical_captured = historical_set & set(store)
    current_coverage = len(current_captured) / max(1, len(current_set))
    historical_coverage = len(historical_captured) / max(1, len(historical_set)) if historical_set else 1.0

    total_deep_symbols = {
        s for s, rows in store.items()
        if len(rows) >= ds.MIN_ROWS
    }
    current_deep_symbols = total_deep_symbols & current_set
    historical_deep_symbols = total_deep_symbols & historical_set

    current_eligible_symbols = {
        s for s in current_deep_symbols
        if (audits.get(s) or {}).get("eligible") is True
    }
    historical_eligible_symbols = {
        s for s in historical_deep_symbols
        if (audits.get(s) or {}).get("eligible") is True
    }

    current_deep = len(current_deep_symbols)
    current_deep_ratio = current_deep / max(1, len(current_set))
    model_eligible = len(current_eligible_symbols)
    eligible_ratio = model_eligible / max(1, len(current_set))

    short_current = sorted(current_captured - current_deep_symbols)
    deep_but_ineligible = sorted(current_deep_symbols - current_eligible_symbols)

    deep_current_audits = [
        audits[s] for s in sorted(current_deep_symbols) if s in audits
    ]
    cas = [
        (a.get("corporateAction") or {}).get("verified") is True
        for a in deep_current_audits
    ]
    ca_ratio = sum(cas) / max(1, len(cas))

    mads = [
        float(a.get("crossSourceReturnMAD"))
        for a in deep_current_audits
        if isinstance(a.get("crossSourceReturnMAD"), (int, float))
        and finite(a.get("crossSourceReturnMAD"))
    ]
    p95 = _percentile95(mads)

    current_audits = {s: audits[s] for s in current_set if s in audits}
    current_failures = {s: failures[s] for s in current_set if s in failures}
    attempt_stage_counts, attempt_stage_failures = _attempt_stage_counts(
        current_audits, current_failures
    )
    attempted = int(attempt_stage_counts.get("VNSTOCK_PRIMARY", 0))
    attempt_ratio = attempted / max(1, len(current_set))

    route_counts = Counter(
        str(a.get("route") or "UNKNOWN")
        for a in audits.values()
    )
    provider_counts = Counter(
        str(
            (a.get("rawSource") or {}).get("providerCode")
            or (a.get("rawSource") or {}).get("provider")
            or "UNKNOWN"
        )
        for a in audits.values()
    )

    gate_failures = []
    if discovery_error:
        gate_failures.append(
            "historical_universe_discovery:" + str(discovery_error)[:300]
        )
    if current_coverage < 0.98:
        gate_failures.append(
            f"current_source_coverage:{len(current_captured)}/{len(current_set)}={current_coverage:.6f}<0.98"
        )
    if current_deep < 360:
        gate_failures.append(f"current_deep_history:{current_deep}<360")
    if model_eligible < 360:
        gate_failures.append(f"current_model_eligible:{model_eligible}<360")
    if ca_ratio < 0.98:
        gate_failures.append(
            f"corporate_action_verified_current_deep:{ca_ratio:.6f}<0.98"
        )
    if p95 is not None and p95 > 0.003:
        gate_failures.append(
            f"cross_source_mad_p95_current_deep:{p95:.10f}>0.003"
        )
    if attempt_ratio < 0.95:
        gate_failures.append(
            f"vnstock_primary_attempted_current:{attempted}/{len(current_set)}={attempt_ratio:.6f}<0.95"
        )

    diag = {
        "status": "FAIL" if gate_failures else "GATES_PASS",
        "asOf": as_of,
        "requested": requested_total,
        "available": available_total,
        "coverageRatio": total_coverage,
        "sourceCoverageRatio": total_coverage,
        "currentHOSERequested": len(current_set),
        "currentHOSECaptured": len(current_captured),
        "currentSourceCoverageRatio": current_coverage,
        "historicalCandidateRequested": len(historical_set),
        "historicalCandidateCaptured": len(historical_captured),
        "historicalCandidateCoverageRatio": historical_coverage,
        "historicalCandidates": historical_symbols,
        "historicalCandidateMetadata": historical_candidates,
        "universeDiscovery": universe_discovery,
        "deepHistory": current_deep,
        "deepHistoryCoverageRatio": current_deep_ratio,
        "totalDeepHistory": len(total_deep_symbols),
        "historicalDeepHistory": len(historical_deep_symbols),
        "modelEligible": model_eligible,
        "modelEligibleCoverageRatio": eligible_ratio,
        "historicalModelEligible": len(historical_eligible_symbols),
        "shortHistoryCapturedCount": len(short_current),
        "shortHistoryCaptured": short_current,
        "deepButIneligibleCount": len(deep_but_ineligible),
        "deepButIneligible": deep_but_ineligible,
        "corporateActionVerifiedRatio": ca_ratio,
        "corporateActionGateCohort": "CURRENT_HOSE_DEEP_HISTORY_ONLY",
        "crossSourceMADP95": p95,
        "crossSourceMADCount": len(mads),
        "crossSourceMADGateCohort": "CURRENT_HOSE_DEEP_HISTORY_ONLY",
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
        raise RuntimeError(
            "Frozen-source gates failed: " + " | ".join(gate_failures)
        )

    symbol_manifest = {}
    for s, rows in sorted(store.items()):
        a = audits.get(s) or {}
        role = "CURRENT_HOSE" if s in current_set else "HISTORICAL_CANDIDATE"
        symbol_manifest[s] = {
            "universeRole": role,
            "route": a.get("route"),
            "provider": (
                (a.get("rawSource") or {}).get("providerCode")
                or (a.get("rawSource") or {}).get("provider")
            ),
            "rows": len(rows),
            "start": rows[0]["date"],
            "end": rows[-1]["date"],
            "deepHistory": s in total_deep_symbols,
            "eligible": (
                s in current_eligible_symbols or s in historical_eligible_symbols
            ),
            "sha256": fingerprint(rows),
        }

    manifest_material = {
        "currentHOSESymbols": current_symbols,
        "historicalCandidates": historical_candidates,
        "symbols": [
            {"symbol": s, **m}
            for s, m in sorted(symbol_manifest.items())
        ],
    }
    manifest_raw = json.dumps(
        manifest_material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    input_manifest_sha = hashlib.sha256(manifest_raw).hexdigest()

    payload = {
        "version": "VMEWS-FROZEN-SOURCE-12.1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "asOf": as_of,
        "sourcePolicy": "ONE_TIME_AUDITED_VNSTOCK_CAPTURE_SEPARATE_FROM_MODEL_ELIGIBILITY",
        "currentHOSESymbols": current_symbols,
        "historicalCandidates": historical_candidates,
        "universeDiscovery": universe_discovery,
        "requestedSymbols": symbols,
        "histories": store,
        "audits": audits,
        "captureFailures": failures,
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    blob = gzip.compress(raw, compresslevel=9, mtime=0)
    OUT.write_bytes(blob)
    file_sha = hashlib.sha256(blob).hexdigest()

    manifest = {
        "version": "VMEWS-FROZEN-SOURCE-MANIFEST-12.1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "asOf": as_of,
        "requested": requested_total,
        "available": available_total,
        "coverageRatio": total_coverage,
        "sourceCoverageRatio": total_coverage,
        "currentHOSERequested": len(current_set),
        "currentHOSECaptured": len(current_captured),
        "currentSourceCoverageRatio": current_coverage,
        "historicalCandidateRequested": len(historical_set),
        "historicalCandidateCaptured": len(historical_captured),
        "historicalCandidateCoverageRatio": historical_coverage,
        "historicalCandidates": historical_candidates,
        "universeDiscovery": universe_discovery,
        "deepHistory": current_deep,
        "deepHistoryCoverageRatio": current_deep_ratio,
        "totalDeepHistory": len(total_deep_symbols),
        "historicalDeepHistory": len(historical_deep_symbols),
        "modelEligible": model_eligible,
        "modelEligibleCoverageRatio": eligible_ratio,
        "historicalModelEligible": len(historical_eligible_symbols),
        "shortHistoryCapturedCount": len(short_current),
        "deepButIneligibleCount": len(deep_but_ineligible),
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
        "requested": requested_total,
        "available": available_total,
        "currentHOSERequested": len(current_set),
        "currentHOSECaptured": len(current_captured),
        "currentSourceCoverageRatio": current_coverage,
        "historicalCandidateRequested": len(historical_set),
        "historicalCandidateCaptured": len(historical_captured),
        "deepHistory": current_deep,
        "modelEligible": model_eligible,
        "snapshotBytes": len(blob),
        "snapshotFileSha256": file_sha,
        "inputManifestSha256": input_manifest_sha,
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
