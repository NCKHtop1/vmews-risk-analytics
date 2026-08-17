import json
from datetime import datetime, timezone

import v12_data_sources as base


class SourceCaptureError(RuntimeError):
    def __init__(self, symbol, attempts):
        self.symbol = symbol
        self.attempts = list(attempts or [])
        detail = " | ".join(
            f"{a.get('stage')}: {a.get('error') or a.get('reason') or 'failed'}"
            for a in self.attempts
            if a.get("ok") is False
        )
        super().__init__(f"{symbol}: VNStock source capture failed" + (f": {detail}" if detail else ""))


def _candidate_audit(rows, source_audit, yahoo_rows, yahoo_audit, attempts):
    mad, common = base._cross_source_mad(rows, yahoo_rows or [])
    adjusted, ca = base.reconcile_vnstock_with_yahoo(rows, yahoo_rows or [])
    severe = mad is not None and mad > base.CROSS_SOURCE_MAD_LIMIT
    deep = len(adjusted) >= base.MIN_ROWS
    eligible = bool(deep and ca.get("verified") and not severe)
    reasons = []
    if not deep:
        reasons.append(f"insufficient_rows:{len(adjusted)}<{base.MIN_ROWS}")
    if not ca.get("verified"):
        reasons.append("corporate_action_unverified")
    if severe:
        reasons.append(
            f"cross_source_mad:{float(mad):.10f}>{base.CROSS_SOURCE_MAD_LIMIT:.10f}"
        )
    return adjusted, {
        "symbol": None,
        "route": "VNSTOCK_SOURCE_CAPTURE",
        "rawSource": source_audit,
        "adjustmentReference": yahoo_audit,
        "crossSourceReturnMAD": mad,
        "crossSourceCommonDates": common,
        "corporateAction": ca,
        "attempts": attempts,
        "sourceCaptured": True,
        "deepHistory": deep,
        "eligible": eligible,
        "ineligibleReasons": reasons,
    }


def _unified_history(symbol, years=8):
    start, end = base._history_window(years)
    base._throttle_vnstock()
    from vnstock.ui import Market

    df = Market().equity(symbol).ohlcv(
        start=start, end=end, interval="1D", count=3200
    )
    rows, scale = base._normalize_df(df, symbol, "Vnstock Unified Market")
    return rows, {
        "source": "VNSTOCK",
        "provider": "Unified Market equity OHLCV",
        "rows": len(rows),
        "unitNormalization": "x1000_to_VND" if scale == 1000.0 else "VND",
        "providerCode": "UNIFIED",
        "api": "vnstock.ui.Market.equity.ohlcv",
    }


def capture_price_history(symbol, years=8):
    """Capture real VNStock OHLCV independently from model-depth eligibility.

    VCI is the deterministic primary capture route. KBS and Unified are recovery
    routes. A valid normalized VNStock history is preserved even when it is too
    short or fails a later modelling-quality gate; the audit marks that history
    ineligible instead of pretending the source is unavailable.
    """
    attempts = []
    start, end = base._history_window(years)
    candidates = []

    try:
        rows, audit = base._provider_history(symbol, "VCI", start, end)
        attempts.append({"stage": "VNSTOCK_PRIMARY", "ok": True, **audit})
        candidates.append((rows, audit, 0))
    except BaseException as exc:
        attempts.append({
            "stage": "VNSTOCK_PRIMARY",
            "ok": False,
            "providerCode": "VCI",
            "error": f"{type(exc).__name__}: {exc}"[:700],
        })

    if not candidates or len(candidates[0][0]) < base.MIN_ROWS:
        try:
            rows, audit = base._provider_history(symbol, "KBS", start, end)
            attempts.append({"stage": "VNSTOCK_KBS_RECOVERY", "ok": True, **audit})
            candidates.append((rows, audit, 1))
        except BaseException as exc:
            attempts.append({
                "stage": "VNSTOCK_KBS_RECOVERY",
                "ok": False,
                "providerCode": "KBS",
                "error": f"{type(exc).__name__}: {exc}"[:700],
            })

    if not candidates:
        try:
            rows, audit = _unified_history(symbol, years=years)
            attempts.append({"stage": "VNSTOCK_UNIFIED_RECOVERY", "ok": True, **audit})
            candidates.append((rows, audit, 2))
        except BaseException as exc:
            attempts.append({
                "stage": "VNSTOCK_UNIFIED_RECOVERY",
                "ok": False,
                "providerCode": "UNIFIED",
                "error": f"{type(exc).__name__}: {exc}"[:700],
            })

    if not candidates:
        raise SourceCaptureError(symbol, attempts)

    candidates.sort(key=lambda x: (-len(x[0]), x[2]))
    rows, source_audit, _ = candidates[0]

    yahoo_rows = []
    yahoo_audit = None
    try:
        yahoo_rows, yahoo_audit = base.yahoo_history(symbol)
        attempts.append({
            "stage": "YAHOO_ADJUSTMENT_REFERENCE",
            "ok": True,
            **yahoo_audit,
        })
    except BaseException as exc:
        attempts.append({
            "stage": "YAHOO_ADJUSTMENT_REFERENCE",
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}"[:700],
        })

    adjusted, audit = _candidate_audit(
        rows, source_audit, yahoo_rows, yahoo_audit, attempts
    )
    audit["symbol"] = symbol
    audit["route"] = "VNSTOCK_SOURCE_CAPTURE_" + str(
        source_audit.get("providerCode") or "UNKNOWN"
    )
    return adjusted, audit


def build_source_capture_store(symbols):
    store = {}
    audits = {}
    failures = {}
    for i, symbol in enumerate(symbols, 1):
        try:
            rows, audit = capture_price_history(symbol)
            store[symbol] = rows
            audits[symbol] = audit
        except SourceCaptureError as exc:
            failures[symbol] = {
                "error": str(exc)[:900],
                "attempts": exc.attempts,
            }
        except BaseException as exc:
            failures[symbol] = {
                "error": f"{type(exc).__name__}: {exc}"[:900],
                "attempts": [],
            }

        if i % 25 == 0 or i == len(symbols):
            print(json.dumps({
                "v12SourceCaptureProgress": i,
                "total": len(symbols),
                "captured": len(store),
                "failed": len(failures),
                "deep": sum(len(r) >= base.MIN_ROWS for r in store.values()),
                "eligible": sum(a.get("eligible") is True for a in audits.values()),
            }, ensure_ascii=False), flush=True)

    return store, audits, failures


def source_capture_summary(audits, failures):
    return {
        "version": "VMEWS-SOURCE-CAPTURE-AUDIT-12.3.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "captured": len(audits),
        "failed": len(failures),
        "deep": sum(a.get("deepHistory") is True for a in audits.values()),
        "eligible": sum(a.get("eligible") is True for a in audits.values()),
        "failures": failures,
        "symbols": audits,
    }
