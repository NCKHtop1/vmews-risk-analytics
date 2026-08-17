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
    mad_rank = float(mad) if isinstance(mad, (int, float)) and math.isfinite(mad) else float("inf")
    ca_ok = (audit.get("corporateAction") or {}).get("verified") is True
    return (
        0 if audit.get("eligible") is True else 1,
        0 if audit.get("deepHistory") is True else 1,
        0 if ca_ok else 1,
        mad_rank,
        -len(rows),
        priority,
    )


def _evaluate_candidate(symbol, rows, source_audit, yahoo_rows, yahoo_audit, attempts, priority):
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


def capture_price_history(symbol, years=8):
    """Capture normalized real VNStock OHLCV independently from model eligibility.

    Explicit VCI and KBS histories are both evaluated under the same corporate-action,
    cross-source and depth audit. Unified Market is a recovery candidate when neither
    explicit provider is model-eligible. A real VNStock history is still frozen when
    it is short or quality-ineligible; downstream research must abstain from that
    symbol rather than treating the source as unavailable or padding history.
    """
    attempts = []
    start, end = base._history_window(years)
    raw_candidates = []

    for priority, source in enumerate(("VCI", "KBS")):
        result = _capture_provider(
            symbol,
            source,
            start,
            end,
            attempts,
            "VNSTOCK_PRIMARY" if source == "VCI" else "VNSTOCK_KBS_RECOVERY",
        )
        if result is not None:
            rows, source_audit = result
            raw_candidates.append((rows, source_audit, priority))

    if not raw_candidates:
        try:
            rows, source_audit = _unified_history(symbol, years=years)
            attempts.append({
                "stage": "VNSTOCK_UNIFIED_RECOVERY",
                "ok": True,
                **source_audit,
            })
            raw_candidates.append((rows, source_audit, 2))
        except BaseException as exc:
            attempts.append({
                "stage": "VNSTOCK_UNIFIED_RECOVERY",
                "ok": False,
                "providerCode": "UNIFIED",
                "error": f"{type(exc).__name__}: {exc}"[:700],
            })

    if not raw_candidates:
        raise SourceCaptureError(symbol, attempts)

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

    candidates = [
        _evaluate_candidate(
            symbol,
            rows,
            source_audit,
            yahoo_rows,
            yahoo_audit,
            attempts,
            priority,
        )
        for rows, source_audit, priority in raw_candidates
    ]

    if not any(audit.get("eligible") is True for _, audit, _ in candidates):
        try:
            rows, source_audit = _unified_history(symbol, years=years)
            attempts.append({
                "stage": "VNSTOCK_UNIFIED_RECOVERY",
                "ok": True,
                **source_audit,
            })
            candidates.append(
                _evaluate_candidate(
                    symbol,
                    rows,
                    source_audit,
                    yahoo_rows,
                    yahoo_audit,
                    attempts,
                    2,
                )
            )
        except BaseException as exc:
            attempts.append({
                "stage": "VNSTOCK_UNIFIED_RECOVERY",
                "ok": False,
                "providerCode": "UNIFIED",
                "error": f"{type(exc).__name__}: {exc}"[:700],
            })

    candidates.sort(key=_quality_rank)
    adjusted, audit, _ = candidates[0]
    provider = str((audit.get("rawSource") or {}).get("providerCode") or "UNKNOWN")
    audit["route"] = "VNSTOCK_SOURCE_CAPTURE_" + provider
    audit["attempts"] = attempts
    audit["candidateCount"] = len(candidates)
    audit["selectionPolicy"] = (
        "ELIGIBLE_THEN_DEEP_THEN_CA_THEN_LOWEST_MAD_THEN_ROWS_THEN_PROVIDER_PRIORITY"
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
