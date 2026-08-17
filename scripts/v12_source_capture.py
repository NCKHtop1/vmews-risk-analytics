import json
import math
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
        super().__init__(
            f"{symbol}: VNStock source capture failed" + (f": {detail}" if detail else "")
        )


def _candidate_audit(symbol, rows, source_audit, yahoo_rows, yahoo_audit):
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
        "symbol": symbol,
        "route": "VNSTOCK_SOURCE_CAPTURE",
        "rawSource": source_audit,
        "adjustmentReference": yahoo_audit,
        "crossSourceReturnMAD": mad,
        "crossSourceCommonDates": common,
        "corporateAction": ca,
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


def _capture_provider(symbol, source, start, end, attempts, stage):
    try:
        rows, audit = base._provider_history(symbol, source, start, end)
        attempts.append({"stage": stage, "ok": True, **audit})
        return rows, audit
    except BaseException as exc:
        attempts.append({
            "stage": stage,
            "ok": False,
            "providerCode": source,
            "error": f"{type(exc).__name__}: {exc}"[:700],
        })
        return None


def _quality_rank(item):
    rows, audit, priority = item
    mad = audit.get("crossSourceReturnMAD")
    mad_rank = (
        float(mad)
        if isinstance(mad, (int, float)) and math.isfinite(mad)
        else float("inf")
    )
    ca_ok = (audit.get("corporateAction") or {}).get("verified") is True
    return (
        0 if audit.get("deepHistory") is True else 1,
        0 if ca_ok else 1,
        mad_rank,
        -len(rows),
        priority,
    )


def _evaluate_candidate(
    symbol,
    rows,
    source_audit,
    yahoo_rows,
    yahoo_audit,
    attempts,
    priority,
):
    adjusted, audit = _candidate_audit(
        symbol, rows, source_audit, yahoo_rows, yahoo_audit
    )
    provider = str(source_audit.get("providerCode") or "UNKNOWN")
    attempts.append({
        "stage": f"VNSTOCK_{provider}_QUALITY",
        "ok": audit.get("eligible") is True,
        "providerCode": provider,
        "rows": len(adjusted),
        "deepHistory": audit.get("deepHistory"),
        "eligible": audit.get("eligible"),
        "ineligibleReasons": audit.get("ineligibleReasons"),
        "crossSourceReturnMAD": audit.get("crossSourceReturnMAD"),
        "crossSourceCommonDates": audit.get("crossSourceCommonDates"),
        "corporateAction": audit.get("corporateAction"),
    })
    return adjusted, audit, priority


def _capture_unified(symbol, years, attempts):
    try:
        rows, audit = _unified_history(symbol, years=years)
        attempts.append({
            "stage": "VNSTOCK_UNIFIED_RECOVERY",
            "ok": True,
            **audit,
        })
        return rows, audit
    except BaseException as exc:
        attempts.append({
            "stage": "VNSTOCK_UNIFIED_RECOVERY",
            "ok": False,
            "providerCode": "UNIFIED",
            "error": f"{type(exc).__name__}: {exc}"[:700],
        })
        return None


def capture_price_history(symbol, years=8):
    """Capture real VNStock OHLCV separately from downstream model eligibility.

    Provider policy is deterministic and non-shopping: VCI is audited first; KBS is
    queried only when VCI is unavailable or fails the same depth/CA/MAD certification;
    Unified Market is the final VNStock recovery route. If no provider is model-eligible,
    the best real VNStock history is still frozen for provenance and explicitly marked
    ineligible so research abstains rather than fabricating or padding history.
    """
    attempts = []
    start, end = base._history_window(years)
    candidates = []

    vci = _capture_provider(
        symbol, "VCI", start, end, attempts, "VNSTOCK_PRIMARY"
    )

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

    if vci is not None:
        rows, source_audit = vci
        candidates.append(
            _evaluate_candidate(
                symbol,
                rows,
                source_audit,
                yahoo_rows,
                yahoo_audit,
                attempts,
                0,
            )
        )

    selected = next(
        (item for item in candidates if item[1].get("eligible") is True),
        None,
    )

    if selected is None:
        kbs = _capture_provider(
            symbol, "KBS", start, end, attempts, "VNSTOCK_KBS_RECOVERY"
        )
        if kbs is not None:
            rows, source_audit = kbs
            item = _evaluate_candidate(
                symbol,
                rows,
                source_audit,
                yahoo_rows,
                yahoo_audit,
                attempts,
                1,
            )
            candidates.append(item)
            if item[1].get("eligible") is True:
                selected = item

    if selected is None:
        unified = _capture_unified(symbol, years, attempts)
        if unified is not None:
            rows, source_audit = unified
            item = _evaluate_candidate(
                symbol,
                rows,
                source_audit,
                yahoo_rows,
                yahoo_audit,
                attempts,
                2,
            )
            candidates.append(item)
            if item[1].get("eligible") is True:
                selected = item

    if not candidates:
        raise SourceCaptureError(symbol, attempts)

    if selected is None:
        candidates.sort(key=_quality_rank)
        selected = candidates[0]

    adjusted, audit, _ = selected
    provider = str(
        (audit.get("rawSource") or {}).get("providerCode") or "UNKNOWN"
    )
    audit["route"] = "VNSTOCK_SOURCE_CAPTURE_" + provider
    audit["attempts"] = attempts
    audit["candidateCount"] = len(candidates)
    audit["selectionPolicy"] = (
        "FIRST_CERTIFIED_VCI_THEN_KBS_THEN_UNIFIED;"
        "BEST_DEEP_CA_MAD_PROVENANCE_IF_NONE_CERTIFIED"
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
                "deep": sum(
                    len(r) >= base.MIN_ROWS for r in store.values()
                ),
                "eligible": sum(
                    a.get("eligible") is True for a in audits.values()
                ),
            }, ensure_ascii=False), flush=True)

    return store, audits, failures


def source_capture_summary(audits, failures):
    return {
        "version": "VMEWS-SOURCE-CAPTURE-AUDIT-12.3.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "captured": len(audits),
        "failed": len(failures),
        "deep": sum(
            a.get("deepHistory") is True for a in audits.values()
        ),
        "eligible": sum(
            a.get("eligible") is True for a in audits.values()
        ),
        "failures": failures,
        "symbols": audits,
    }
