import argparse
import gzip
import hashlib
import json
import math
import pathlib
from datetime import datetime, timezone

from v12_research_sources import get_index_history, get_price_history

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SNAPSHOT = DATA / "v12-frozen-source.json.gz"
MANIFEST = DATA / "v12-frozen-source-manifest.json"
OUTPUT = DATA / "v12-source-probe.json"

MIN_CURRENT_SOURCE_COVERAGE = 0.98
MIN_DEEP_HISTORY = 360
MIN_MODEL_ELIGIBLE = 360
MIN_CA_VERIFIED_RATIO = 0.98
MAX_CROSS_SOURCE_MAD_P95 = 0.003
MIN_VNSTOCK_PRIMARY_ATTEMPT_RATIO = 0.95
CERTIFICATION_VERSION = "VMEWS-FROZEN-SOURCE-CERTIFICATION-12.1.1"
CERTIFICATION_MODE = "OFFLINE_RECOMPUTED_FROM_COMMITTED_SNAPSHOT_AUDITS_NO_NETWORK"
CA_GATE_COHORT = "CURRENT_HOSE_ORIGINAL_DEEP_HISTORY_BEFORE_CONTINUITY_TRUNCATION"


def _load_and_verify_snapshot():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    blob = SNAPSHOT.read_bytes()
    actual_sha = hashlib.sha256(blob).hexdigest()
    expected_sha = str(manifest.get("snapshotFileSha256") or "")
    if manifest.get("version") != "VMEWS-FROZEN-SOURCE-MANIFEST-12.1.0":
        raise RuntimeError(f"unexpected frozen manifest version: {manifest.get('version')!r}")
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"frozen snapshot SHA256 mismatch: expected={expected_sha} actual={actual_sha}"
        )
    payload = json.loads(gzip.decompress(blob).decode("utf-8"))
    if payload.get("version") != "VMEWS-FROZEN-SOURCE-12.1.0":
        raise RuntimeError(f"unexpected frozen snapshot version: {payload.get('version')!r}")
    if len(payload.get("histories") or {}) != int(manifest.get("available") or 0):
        raise RuntimeError("frozen snapshot available/history count mismatch")
    if len(str(manifest.get("inputManifestSha256") or "")) != 64:
        raise RuntimeError("frozen input manifest SHA256 is missing or malformed")
    return payload, manifest, actual_sha


def _source_gates(manifest):
    current_requested = int(manifest.get("currentHOSERequested") or 0)
    primary_attempted = int(manifest.get("vnstockPrimaryAttempted") or 0)
    primary_ratio = primary_attempted / max(1, current_requested)
    deep_history = int(manifest.get("deepHistory") or 0)
    ca_ratio = float(manifest.get("corporateActionVerifiedRatio") or 0.0)
    ca_verified_count = int(manifest.get("corporateActionVerifiedCount") or 0)
    ca_denominator = int(manifest.get("corporateActionGateDenominator") or 0)
    certified_ratio = ca_verified_count / max(1, ca_denominator)
    certification_gates = manifest.get("sourceFreezeCertificationGates") or {}
    values = {
        "currentSourceCoverageRatio": float(manifest.get("currentSourceCoverageRatio") or 0.0),
        "deepHistory": deep_history,
        "modelEligible": int(manifest.get("modelEligible") or 0),
        "corporateActionVerifiedRatio": ca_ratio,
        "corporateActionVerifiedCount": ca_verified_count,
        "corporateActionGateDenominator": ca_denominator,
        "corporateActionCertifiedRatio": certified_ratio,
        "corporateActionGateCohort": manifest.get("corporateActionGateCohort"),
        "crossSourceMADP95": float(manifest.get("crossSourceMADP95") or math.inf),
        "vnstockPrimaryAttemptRatio": primary_ratio,
        "sourceFreezeCertificationVersion": manifest.get("sourceFreezeCertificationVersion"),
        "sourceFreezeCertificationMode": manifest.get("sourceFreezeCertificationMode"),
    }
    checks = {
        "currentSourceCoverage": values["currentSourceCoverageRatio"] >= MIN_CURRENT_SOURCE_COVERAGE,
        "deepHistory": values["deepHistory"] >= MIN_DEEP_HISTORY,
        "modelEligible": values["modelEligible"] >= MIN_MODEL_ELIGIBLE,
        "corporateActionVerified": ca_ratio >= MIN_CA_VERIFIED_RATIO,
        "corporateActionOriginalDeepCohort": manifest.get("corporateActionGateCohort") == CA_GATE_COHORT,
        "corporateActionOriginalDeepDenominator": ca_denominator >= deep_history and ca_denominator > 0,
        "corporateActionOriginalDeepCount": (
            0 <= ca_verified_count <= ca_denominator
            and certified_ratio >= MIN_CA_VERIFIED_RATIO
            and abs(certified_ratio - ca_ratio) <= 1e-12
        ),
        "crossSourceMADP95": values["crossSourceMADP95"] <= MAX_CROSS_SOURCE_MAD_P95,
        "vnstockPrimaryAttempt": values["vnstockPrimaryAttemptRatio"] >= MIN_VNSTOCK_PRIMARY_ATTEMPT_RATIO,
        "sourceFreezeCertification": (
            manifest.get("sourceFreezeCertificationVersion") == CERTIFICATION_VERSION
            and manifest.get("sourceFreezeCertificationMode") == CERTIFICATION_MODE
            and manifest.get("sourceFreezeCertificationSnapshotSha256") == manifest.get("snapshotFileSha256")
            and bool(certification_gates)
            and all(v is True for v in certification_gates.values())
        ),
    }
    return values, checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", default=["FPT", "VCB", "HPG", "FRT", "PNJ", "VIC", "MBB"])
    args = ap.parse_args()

    payload, manifest, snapshot_sha = _load_and_verify_snapshot()
    gate_values, gate_checks = _source_gates(manifest)
    report = {
        "version": "VMEWS-V12-FROZEN-SOURCE-PROBE-1.1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "IMMUTABLE_FROZEN_SNAPSHOT",
        "runtimeNetworkPriceFetch": False,
        "runtimeProviderSwitching": False,
        "snapshot": {
            "version": payload.get("version"),
            "manifestVersion": manifest.get("version"),
            "asOf": manifest.get("asOf"),
            "snapshotFileSha256": snapshot_sha,
            "inputManifestSha256": manifest.get("inputManifestSha256"),
            "available": manifest.get("available"),
            "certificationVersion": manifest.get("sourceFreezeCertificationVersion"),
            "certificationMode": manifest.get("sourceFreezeCertificationMode"),
            "corporateActionGateCohort": manifest.get("corporateActionGateCohort"),
            "corporateActionGateDenominator": manifest.get("corporateActionGateDenominator"),
            "corporateActionVerifiedCount": manifest.get("corporateActionVerifiedCount"),
        },
        "sourceGateValues": gate_values,
        "sourceGates": gate_checks,
        "symbols": {},
    }

    passed = 0
    for symbol in args.symbols:
        try:
            rows, audit = get_price_history(symbol)
            model = [float(x.get("modelClose", x["close"])) for x in rows]
            bad = sum(
                a > 0 and b > 0 and abs(math.log(b / a)) > 0.24
                for a, b in zip(model[:-1], model[1:])
            )
            item = {
                "ok": len(rows) >= 520 and bad == 0,
                "rows": len(rows),
                "start": rows[0]["date"],
                "end": rows[-1]["date"],
                "route": audit.get("route"),
                "corporateAction": audit.get("corporateAction"),
                "crossSourceReturnMAD": audit.get("crossSourceReturnMAD"),
                "unexplainedModelJumps": bad,
                "researchFrozen": audit.get("researchFrozen") is True,
                "runtimeNetworkPriceFetch": audit.get("runtimeNetworkPriceFetch") is True,
                "inputFingerprintSha256": audit.get("inputFingerprintSha256"),
            }
            if item["runtimeNetworkPriceFetch"]:
                item["ok"] = False
            report["symbols"][symbol] = item
            passed += int(item["ok"])
        except BaseException as exc:
            report["symbols"][symbol] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    try:
        rows, audit = get_index_history("VNINDEX")
        report["index"] = {
            "ok": len(rows) >= 520 and audit.get("runtimeNetworkPriceFetch") is False,
            "rows": len(rows),
            "start": rows[0]["date"],
            "end": rows[-1]["date"],
            "route": audit.get("route"),
            "researchFrozen": audit.get("researchFrozen") is True,
            "runtimeNetworkPriceFetch": audit.get("runtimeNetworkPriceFetch"),
            "inputFingerprintSha256": audit.get("inputFingerprintSha256"),
        }
    except BaseException as exc:
        report["index"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    report["passed"] = passed
    report["total"] = len(args.symbols)
    report["status"] = "PASS" if (
        all(gate_checks.values())
        and passed >= max(5, len(args.symbols) - 1)
        and report["index"].get("ok") is True
    ) else "FAIL"
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
