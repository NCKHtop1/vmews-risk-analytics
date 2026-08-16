import hashlib
import json
import math
import os
import statistics
from datetime import datetime, timedelta, timezone

import v12_data_sources as _base

CANONICAL_PROVIDER = str(os.environ.get("V12_RESEARCH_PROVIDER", "VCI")).upper().strip()
ALLOWED_PROVIDERS = ("VCI", "KBS")
if CANONICAL_PROVIDER not in ALLOWED_PROVIDERS:
    raise RuntimeError(f"Unsupported V12_RESEARCH_PROVIDER={CANONICAL_PROVIDER!r}; allowed={ALLOWED_PROVIDERS}")


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
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class CanonicalIneligible(RuntimeError):
    pass


def _strict_canonical_equity(symbol, years=8):
    start, end = _base._history_window(years)
    attempts = []
    try:
        rows, raw_audit = _base._provider_history(symbol, CANONICAL_PROVIDER, start, end)
    except BaseException as exc:
        raise RuntimeError(
            f"{symbol}: canonical VNStock provider {CANONICAL_PROVIDER} unavailable; "
            f"research run refuses provider switching: {type(exc).__name__}: {exc}"
        ) from exc

    if len(rows) < _base.MIN_ROWS:
        raise CanonicalIneligible(
            f"{symbol}: canonical VNStock provider {CANONICAL_PROVIDER} has only "
            f"{len(rows)} rows < MIN_ROWS={_base.MIN_ROWS}; excluded deterministically without fallback"
        )

    attempts.append({"stage": f"CANONICAL_{CANONICAL_PROVIDER}", "ok": True, **raw_audit})

    try:
        yahoo_rows, yahoo_audit = _base.yahoo_history(symbol)
    except BaseException as exc:
        raise RuntimeError(
            f"{symbol}: Yahoo corporate-action reference unavailable; "
            f"research run refuses an unverified adjustment path: {type(exc).__name__}: {exc}"
        ) from exc

    if len(yahoo_rows) < 60:
        raise RuntimeError(f"{symbol}: Yahoo corporate-action reference has insufficient rows={len(yahoo_rows)}")

    mad, common = _base._cross_source_mad(rows, yahoo_rows)
    adjusted, ca = _base.reconcile_vnstock_with_yahoo(rows, yahoo_rows)
    severe = mad is not None and mad > _base.CROSS_SOURCE_MAD_LIMIT
    verified = bool(ca.get("verified")) and not severe
    attempts.append(
        {
            "stage": "CANONICAL_QUALITY_GATE",
            "ok": verified,
            "crossSourceReturnMAD": mad,
            "crossSourceCommonDates": common,
            "corporateAction": ca,
        }
    )
    if not verified:
        reason = "corporate_action_unverified" if not ca.get("verified") else "cross_source_disagreement"
        raise RuntimeError(
            f"{symbol}: canonical provider failed quality gate ({reason}); "
            f"provider switching is disabled in research mode; "
            f"crossSourceReturnMAD={mad} limit={_base.CROSS_SOURCE_MAD_LIMIT}"
        )

    audit = {
        "symbol": symbol,
        "route": f"VNSTOCK_CANONICAL_{CANONICAL_PROVIDER}",
        "researchCanonical": True,
        "canonicalProvider": CANONICAL_PROVIDER,
        "rawSource": raw_audit,
        "adjustmentReference": yahoo_audit,
        "crossSourceReturnMAD": mad,
        "crossSourceCommonDates": common,
        "corporateAction": ca,
        "attempts": attempts,
        "eligible": True,
        "inputStartDate": adjusted[0]["date"] if adjusted else None,
        "inputEndDate": adjusted[-1]["date"] if adjusted else None,
        "inputRows": len(adjusted),
        "inputFingerprintSha256": _history_fingerprint(adjusted),
    }
    return adjusted, audit


def get_price_history(symbol, yahoo_reference=True):
    # `yahoo_reference` is intentionally ignored: the canonical research path always
    # requires a corporate-action reference so identical source policy is applied on every run.
    return _strict_canonical_equity(symbol)


def get_index_history(symbol="VNINDEX", years=8):
    today = datetime.now(_base.VN_TZ).date()
    start = (today - timedelta(days=366 * years + 30)).isoformat()
    end = (today + timedelta(days=1)).isoformat()
    _base._throttle_vnstock()
    try:
        from vnstock.ui import Market
        df = Market().index(symbol).ohlcv(start=start, end=end, interval="1D", count=3200)
        rows, scale = _base._normalize_df(df, symbol, "Vnstock Index")
    except BaseException as exc:
        raise RuntimeError(
            f"{symbol}: canonical VNStock index route unavailable; "
            f"research run refuses Yahoo/provider fallback: {type(exc).__name__}: {exc}"
        ) from exc
    if len(rows) < _base.MIN_ROWS:
        raise RuntimeError(
            f"{symbol}: canonical VNStock index route has only {len(rows)} rows "
            f"< MIN_ROWS={_base.MIN_ROWS}"
        )
    for r in rows:
        r["modelClose"] = r["close"]
        r["adjustmentFactor"] = 1.0
    return rows, {
        "route": "VNSTOCK_INDEX_CANONICAL",
        "provider": "Vnstock Market.index OHLCV",
        "rows": len(rows),
        "unitNormalization": "x1000" if scale == 1000.0 else "native",
        "researchCanonical": True,
        "inputStartDate": rows[0]["date"] if rows else None,
        "inputEndDate": rows[-1]["date"] if rows else None,
        "inputFingerprintSha256": _history_fingerprint(rows),
    }


def build_price_store(symbols):
    store = {}
    audits = {}
    failures = {}
    operational_failures = {}
    for i, symbol in enumerate(symbols, 1):
        try:
            rows, audit = get_price_history(symbol)
            store[symbol] = rows
            audits[symbol] = audit
        except CanonicalIneligible as exc:
            failures[symbol] = f"CANONICAL_INELIGIBLE: {exc}"[:900]
        except BaseException as exc:
            msg = f"{type(exc).__name__}: {exc}"[:900]
            failures[symbol] = msg
            operational_failures[symbol] = msg
        if i % 25 == 0 or i == len(symbols):
            print(
                json.dumps(
                    {
                        "v12CanonicalPriceProgress": i,
                        "total": len(symbols),
                        "passed": len(store),
                        "failed": len(failures),
                        "provider": CANONICAL_PROVIDER,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    # Short-history listings are deterministically excluded. Operational/quality
    # failures are different: hard-stop so the research universe cannot drift because
    # a live source was temporarily unavailable.
    if operational_failures:
        sample = dict(list(sorted(operational_failures.items()))[:12])
        raise RuntimeError(
            f"V12 canonical-source reproducibility gate hit {len(operational_failures)} operational/quality "
            f"failures; no live provider fallback is permitted. sample={sample}"
        )
    return store, audits, failures


def source_audit_summary(audits, failures):
    routes = {}
    mad = []
    manifest = []
    for symbol, a in sorted(audits.items()):
        route = a.get("route", "UNKNOWN")
        routes[route] = routes.get(route, 0) + 1
        x = a.get("crossSourceReturnMAD")
        if isinstance(x, (int, float)) and math.isfinite(x):
            mad.append(float(x))
        manifest.append(
            {
                "symbol": symbol,
                "route": route,
                "provider": ((a.get("rawSource") or {}).get("providerCode") or (a.get("rawSource") or {}).get("provider")),
                "start": a.get("inputStartDate"),
                "end": a.get("inputEndDate"),
                "rows": a.get("inputRows") or ((a.get("rawSource") or {}).get("rows")),
                "sha256": a.get("inputFingerprintSha256"),
            }
        )
    manifest_raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    return {
        "version": "VMEWS-DATA-AUDIT-12.1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchInputPolicy": {
            "mode": "STRICT_CANONICAL",
            "canonicalEquityProvider": CANONICAL_PROVIDER,
            "equityProviderSwitching": False,
            "indexProviderSwitching": False,
            "corporateActionReferenceRequired": True,
            "fallbackOnCanonicalFailure": "FAIL_SAFE",
        },
        "policy": [
            f"Research equity OHLCV is pinned to explicit VNStock {CANONICAL_PROVIDER}; no runtime provider switching is allowed.",
            "Yahoo adjusted data is used only as a required corporate-action reference, never as a research-price fallback.",
            "VNINDEX is pinned to the VNStock index route; no runtime index fallback is allowed.",
            "Every admitted symbol has a row-content SHA256 fingerprint and the complete input manifest is hashed.",
            "No synthetic history padding is allowed.",
        ],
        "symbolsPassed": len(audits),
        "symbolsFailed": len(failures),
        "routes": routes,
        "crossSourceMedianReturnMAD": statistics.median(mad) if mad else None,
        "inputManifestSha256": manifest_sha,
        "inputManifest": manifest,
        "failures": failures,
        "symbols": audits,
    }
