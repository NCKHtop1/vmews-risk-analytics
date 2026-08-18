#!/usr/bin/env python3
"""Build the immutable V12 release manifest from the already validated frozen-source chain."""
from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

FILES = [
    "forecast-final.html",
    "forecast-final-v12.js",
    "forecast-polish-v12.js",
    "data/v12-frozen-source.json.gz",
    "data/v12-frozen-source-manifest.json",
    "data/v12-source-probe.json",
    "data/v12-seed-provenance.json",
    "data/vnindex-v12.json",
    "data/forecast-model-v12.json",
    "data/forecast-current-v12.json",
    "data/forecast-dashboard-v12.json",
    "data/forecast-backtest-v12.json",
    "data/data-audit-v12.json",
    "data/event-intelligence-v12.json",
    "data/flow-v12.json",
    "data/flow-audit-v12.json",
    "data/phase-gates-v12.json",
    "data/benchmark-gate-v12.json",
    "data/active-flow-audit-v12.json",
    "data/active-flow-gate-v12.json",
    "data/sector-gate-v12.json",
    "data/nested-selection-gate-v12.json",
    "data/blind-holdout-gate-v12.json",
    "data/embargo-gate-v12.json",
]

def load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def digest(path: str):
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return {"sha256": h.hexdigest(), "bytes": p.stat().st_size}

def main():
    source_commit = os.environ.get("V12_SOURCE_SHA", "").strip()
    if len(source_commit) != 40:
        raise RuntimeError("V12_SOURCE_SHA must be the exact persisted-model source commit")

    probe = load("data/v12-source-probe.json")
    frozen = load("data/v12-frozen-source-manifest.json")
    seed = load("data/v12-seed-provenance.json")
    model = load("data/forecast-model-v12.json")
    phase = load("data/phase-gates-v12.json")
    benchmark = load("data/benchmark-gate-v12.json")
    active = load("data/active-flow-gate-v12.json")
    sector = load("data/sector-gate-v12.json")
    nested = load("data/nested-selection-gate-v12.json")
    blind = load("data/blind-holdout-gate-v12.json")
    embargo = load("data/embargo-gate-v12.json")

    assert probe.get("status") == "PASS", probe
    assert probe.get("mode") == "IMMUTABLE_FROZEN_SNAPSHOT", probe
    assert probe.get("runtimeNetworkPriceFetch") is False, probe
    assert probe.get("runtimeProviderSwitching") is False, probe
    assert all((probe.get("sourceGates") or {}).values()), probe.get("sourceGates")
    snap = probe.get("snapshot") or {}
    assert snap.get("snapshotFileSha256") == frozen.get("snapshotFileSha256"), (snap, frozen)
    assert snap.get("inputManifestSha256") == frozen.get("inputManifestSha256"), (snap, frozen)
    assert float(frozen.get("currentSourceCoverageRatio") or 0) >= 0.98, frozen
    assert int(frozen.get("deepHistory") or 0) >= 360, frozen
    assert int(frozen.get("modelEligible") or 0) >= 360, frozen
    assert float(frozen.get("corporateActionVerifiedRatio") or 0) >= 0.98, frozen
    assert float(frozen.get("crossSourceMADP95") or 9) <= 0.003, frozen
    assert seed.get("status") == "PASS", seed

    promotion = model.get("promotion") or {}
    assert promotion.get("status") == "PASS", promotion
    assert set(promotion.get("directPriceHorizons") or []) == {1,2,3,4,5}, promotion
    assert phase.get("status") == "PASS", phase
    assert benchmark.get("status") == "PASS", benchmark
    assert active.get("status") == "PASS", active
    assert sector.get("status") == "PASS", sector
    assert nested.get("status") == "PASS", nested
    assert blind.get("status") == "PASS", blind
    assert embargo.get("status") == "PASS", embargo

    missing = [p for p in FILES if not Path(p).is_file()]
    if missing:
        raise RuntimeError(f"release provenance files missing: {missing}")
    files = {p: digest(p) for p in FILES}
    assert files["data/v12-frozen-source.json.gz"]["sha256"] == frozen.get("snapshotFileSha256"), files["data/v12-frozen-source.json.gz"]

    out = {
        "version": "VMEWS-FORECAST-V12-IMMUTABLE-MANIFEST-1.6.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceCommit": source_commit,
        "modelVersion": model.get("version"),
        "asOf": frozen.get("asOf"),
        "frozenSource": {
            "manifestVersion": frozen.get("version"),
            "asOf": frozen.get("asOf"),
            "currentSourceCoverageRatio": frozen.get("currentSourceCoverageRatio"),
            "deepHistory": frozen.get("deepHistory"),
            "modelEligible": frozen.get("modelEligible"),
            "corporateActionVerifiedRatio": frozen.get("corporateActionVerifiedRatio"),
            "crossSourceMADP95": frozen.get("crossSourceMADP95"),
            "snapshotFileSha256": frozen.get("snapshotFileSha256"),
            "inputManifestSha256": frozen.get("inputManifestSha256"),
            "runtimeNetworkPriceFetch": False,
            "runtimeProviderSwitching": False,
        },
        "seedProvenance": seed,
        "promotion": promotion,
        "phaseGateVersion": phase.get("version"),
        "benchmarkGate": {"version": benchmark.get("version"), "status": benchmark.get("status"), "benchmark": benchmark.get("benchmark")},
        "activeFlowGate": {"version": active.get("version"), "status": active.get("status"), "mode": active.get("mode")},
        "sectorGate": {"version": sector.get("version"), "status": sector.get("status"), "mode": sector.get("mode")},
        "nestedSelectionGate": {"version": nested.get("version"), "status": nested.get("status")},
        "blindHoldoutGate": {"version": blind.get("version"), "status": blind.get("status")},
        "embargoGate": {"version": embargo.get("version"), "status": embargo.get("status")},
        "files": files,
        "policy": "Exact frozen source -> point-in-time model -> sealed OOS gates -> UI assets are content-hashed. Runtime price/network provider switching is forbidden. Production CDN identity is the release commit SHA, never /main/.",
    }
    Path("data/forecast-release-v12.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status":"PASS","version":out["version"],"sourceCommit":source_commit,"asOf":out["asOf"],"fileCount":len(files)}, indent=2))

if __name__ == "__main__":
    main()
