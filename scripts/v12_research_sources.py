import gzip
import hashlib
import json
import math
import pathlib
import statistics
from datetime import datetime, timezone

import v12_data_sources as _base

ROOT = pathlib.Path(getattr(_base, "ROOT", pathlib.Path(".").resolve()))
SNAPSHOT_PATH = ROOT / "data" / "v12-frozen-source.json.gz"
SNAPSHOT_MANIFEST_PATH = ROOT / "data" / "v12-frozen-source-manifest.json"
_SNAPSHOT_CACHE = [None, None]


def _stable_number(v):
    x = _base._finite(v)
    if x is None:
        return None
    return round(float(x), 10)


def _history_fingerprint(rows):
    payload = []
    for r in rows:
        payload.append([
            str(r.get("date", ""))[:10],
            _stable_number(r.get("open")),
            _stable_number(r.get("high")),
            _stable_number(r.get("low")),
            _stable_number(r.get("close")),
            _stable_number(r.get("modelClose", r.get("close"))),
            _stable_number(r.get("volume")),
            _stable_number(r.get("adjustmentFactor", 1.0)),
        ])
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class CanonicalIneligible(RuntimeError):
    pass


def _load_snapshot():
    if _SNAPSHOT_CACHE[0] is not None:
        return _SNAPSHOT_CACHE[0], _SNAPSHOT_CACHE[1]
    if not SNAPSHOT_PATH.exists() or not SNAPSHOT_MANIFEST_PATH.exists():
        raise RuntimeError(
            "Frozen V12 research source snapshot is missing. "
            "Run the audited v12-source-freeze workflow before model validation."
        )
    manifest = json.loads(SNAPSHOT_MANIFEST_PATH.read_text(encoding="utf-8"))
    blob = SNAPSHOT_PATH.read_bytes()
    got = hashlib.sha256(blob).hexdigest()
    expected = str(manifest.get("snapshotFileSha256") or "")
    if not expected or got != expected:
        raise RuntimeError(
            f"Frozen V12 snapshot file hash mismatch: expected={expected!r} actual={got!r}"
        )
    payload = json.loads(gzip.decompress(blob).decode("utf-8"))
    if payload.get("version") != "VMEWS-FROZEN-SOURCE-12.0.0":
        raise RuntimeError(
            f"Unexpected frozen source version: {payload.get('version')!r}"
        )
    histories = payload.get("histories") or {}
    audits = payload.get("audits") or {}
    listed = manifest.get("symbols") or {}
    for symbol, meta in listed.items():
        rows = histories.get(symbol)
        if rows is None:
            raise RuntimeError(
                f"Frozen V12 snapshot manifest symbol missing from payload: {symbol}"
            )
        fp = _history_fingerprint(rows)
        if fp != meta.get("sha256"):
            raise RuntimeError(
                f"Frozen V12 per-symbol fingerprint mismatch for {symbol}: "
                f"expected={meta.get('sha256')} actual={fp}"
            )
        if int(meta.get("rows") or 0) != len(rows):
            raise RuntimeError(f"Frozen V12 row-count mismatch for {symbol}")
        if symbol not in audits:
            raise RuntimeError(f"Frozen V12 audit missing for {symbol}")
    _SNAPSHOT_CACHE[0] = payload
    _SNAPSHOT_CACHE[1] = manifest
    return payload, manifest


def get_price_history(symbol, yahoo_reference=True):
    payload, manifest = _load_snapshot()
    rows = (payload.get("histories") or {}).get(symbol)
    audit = (payload.get("audits") or {}).get(symbol)
    if rows is None or audit is None:
        raise CanonicalIneligible(
            f"{symbol}: not present in immutable V12 source snapshot"
        )
    if len(rows) < _base.MIN_ROWS:
        raise CanonicalIneligible(
            f"{symbol}: frozen real history has only {len(rows)} rows "
            f"< MIN_ROWS={_base.MIN_ROWS}"
        )
    if audit.get("eligible") is False:
        reasons = audit.get("ineligibleReasons") or ["capture_quality_gate_failed"]
        raise CanonicalIneligible(
            f"{symbol}: frozen source is model-ineligible: "
            + " | ".join(map(str, reasons))
        )
    expected = ((manifest.get("symbols") or {}).get(symbol) or {}).get("sha256")
    got = _history_fingerprint(rows)
    if not expected or expected != got:
        raise RuntimeError(
            f"{symbol}: frozen-source fingerprint verification failed"
        )
    out_audit = dict(audit)
    out_audit.update({
        "researchFrozen": True,
        "snapshotAsOf": manifest.get("asOf"),
        "inputStartDate": rows[0]["date"] if rows else None,
        "inputEndDate": rows[-1]["date"] if rows else None,
        "inputRows": len(rows),
        "inputFingerprintSha256": got,
    })
    return rows, out_audit


def get_index_history(symbol="VNINDEX", years=8):
    if symbol.upper() != "VNINDEX":
        raise RuntimeError(
            f"Frozen V12 index source only certifies VNINDEX, got {symbol!r}"
        )
    path = ROOT / "data" / "vnindex-v12.json"
    if not path.exists():
        raise RuntimeError("Pinned data/vnindex-v12.json is missing")
    z = json.loads(path.read_text(encoding="utf-8"))
    rows = list(z.get("rows") or [])
    if len(rows) < _base.MIN_ROWS:
        raise RuntimeError(f"Frozen VNINDEX history too short: {len(rows)}")
    fp = _history_fingerprint(rows)
    src = dict(z.get("sourceAudit") or {})
    return rows, {
        "route": "VNSTOCK_INDEX_FROZEN_SNAPSHOT",
        "provider": src.get("provider") or "Vnstock Market.index OHLCV",
        "rows": len(rows),
        "researchFrozen": True,
        "sourceGeneratedAt": z.get("generatedAt"),
        "inputStartDate": rows[0]["date"],
        "inputEndDate": rows[-1]["date"],
        "inputFingerprintSha256": fp,
    }


def build_price_store(symbols):
    payload, _ = _load_snapshot()
    store = {}
    audits = {}
    failures = {}
    for i, symbol in enumerate(symbols, 1):
        try:
            rows, audit = get_price_history(symbol)
            store[symbol] = rows
            audits[symbol] = audit
        except CanonicalIneligible as exc:
            failures[symbol] = f"FROZEN_INELIGIBLE: {exc}"[:900]
        except BaseException:
            raise
        if i % 50 == 0 or i == len(symbols):
            print(json.dumps({
                "v12FrozenPriceProgress": i,
                "total": len(symbols),
                "passed": len(store),
                "failed": len(failures),
                "snapshotSymbols": len((payload.get("histories") or {})),
            }, ensure_ascii=False), flush=True)
    return store, audits, failures


def source_audit_summary(audits, failures):
    routes = {}
    mad = []
    manifest_rows = []
    for symbol, a in sorted(audits.items()):
        route = a.get("route", "UNKNOWN")
        routes[route] = routes.get(route, 0) + 1
        x = a.get("crossSourceReturnMAD")
        if isinstance(x, (int, float)) and math.isfinite(x):
            mad.append(float(x))
        manifest_rows.append({
            "symbol": symbol,
            "route": route,
            "provider": (
                (a.get("rawSource") or {}).get("providerCode")
                or (a.get("rawSource") or {}).get("provider")
                or a.get("provider")
            ),
            "start": a.get("inputStartDate"),
            "end": a.get("inputEndDate"),
            "rows": a.get("inputRows") or (a.get("rawSource") or {}).get("rows"),
            "sha256": a.get("inputFingerprintSha256"),
        })
    row_raw = json.dumps(
        manifest_rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    admitted_sha = hashlib.sha256(row_raw).hexdigest()
    try:
        _, frozen_manifest = _load_snapshot()
    except RuntimeError:
        frozen_manifest = {}
    return {
        "version": "VMEWS-DATA-AUDIT-12.3.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchInputPolicy": {
            "mode": "IMMUTABLE_FROZEN_SNAPSHOT",
            "capturePolicy": (
                "VNStock source capture is independent from model eligibility; "
                "only certified frozen histories are admitted to research"
            ),
            "runtimeProviderSwitching": False,
            "runtimeNetworkPriceFetch": False,
            "snapshotAsOf": frozen_manifest.get("asOf"),
            "snapshotFileSha256": frozen_manifest.get("snapshotFileSha256"),
            "snapshotInputManifestSha256": frozen_manifest.get("inputManifestSha256"),
            "admittedInputManifestSha256": admitted_sha,
        },
        "policy": [
            "Research OHLCV is captured once from audited VNStock routes and then consumed from an immutable frozen snapshot.",
            "Source availability is distinct from model eligibility: short or quality-ineligible real histories remain fingerprinted for provenance but are excluded from model fitting and replay.",
            "No runtime price-provider switching or runtime price-network fallback is allowed during model fitting or replay.",
            "Each frozen symbol has a row-content SHA256 fingerprint and the complete frozen input manifest is hashed.",
            "Yahoo adjusted data may be used only as an audited corporate-action/reference series during source capture; training consumes only the frozen result.",
            "No synthetic history padding is allowed.",
        ],
        "symbolsPassed": len(audits),
        "symbolsFailed": len(failures),
        "routes": routes,
        "crossSourceMedianReturnMAD": statistics.median(mad) if mad else None,
        "inputManifestSha256": (
            frozen_manifest.get("inputManifestSha256") or admitted_sha
        ),
        "admittedInputManifestSha256": admitted_sha,
        "failures": failures,
        "symbols": audits,
    }
