"""VNStock-only bounded acquisition for the V12 source freeze.

Runtime source policy:
- all network price/reference calls go through vnstock;
- Yahoo is disabled for this workflow;
- no run-global provider circuit breaker is used;
- each external call is individually time-boxed on Linux;
- transient failures get only bounded local retries;
- one clean second pass is allowed only for records with explicit transient evidence.

No price, return, eligibility threshold, corporate-action rule, or scientific gate is relaxed.
"""
import os
import signal
import time


_TRANSIENT_MARKERS = (
    "timeout", "timed out", "network_call_timeout", "429", "rate limit",
    "too many requests", "502", "503", "504", "connection reset",
    "connectionpool", "max retries exceeded", "temporary failure",
    "name resolution", "network is unreachable", "remote disconnected",
)
_RATE_LIMIT_MARKERS = ("429", "rate limit", "too many requests", "giới hạn api", "requests/phút")
_DEFAULT_NETWORK_CALL_TIMEOUT_SECONDS = 25.0
_SECONDARY_AUDIT_MODULUS = 5


def _transient(value):
    text = str(value or "").lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _rate_limited(value):
    text = str(value or "").lower()
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)


def _attempt_error_text(attempt):
    return " ".join(str(attempt.get(k) or "") for k in ("error", "reason", "stage"))


def _audit_has_transient_failure(audit):
    return any(
        attempt.get("ok") is False and _transient(_attempt_error_text(attempt))
        for attempt in (audit or {}).get("attempts") or []
    )


def _failure_has_transient_failure(failure):
    return any(
        attempt.get("ok") is False and _transient(_attempt_error_text(attempt))
        for attempt in (failure or {}).get("attempts") or []
    )


def _network_timeout_seconds():
    try:
        value = float(os.environ.get("V12_NETWORK_CALL_TIMEOUT", _DEFAULT_NETWORK_CALL_TIMEOUT_SECONDS))
        return max(0.05, value)
    except Exception:
        return _DEFAULT_NETWORK_CALL_TIMEOUT_SECONDS


def _call_with_timeout(label, fn, *args, **kwargs):
    """Hard per-call watchdog for the Linux GitHub runner; direct call elsewhere."""
    seconds = _network_timeout_seconds()
    if not hasattr(signal, "SIGALRM") or not hasattr(signal, "setitimer"):
        return fn(*args, **kwargs)

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def _alarm(_signum, _frame):
        raise TimeoutError(f"{label}: network_call_timeout>{seconds:.1f}s")

    signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return fn(*args, **kwargs)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer and previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)


def _secondary_audit_required(symbol):
    text = str(symbol or "").upper()
    checksum = sum((i + 1) * ord(ch) for i, ch in enumerate(text))
    return checksum % _SECONDARY_AUDIT_MODULUS == 0


def install(capture, max_attempts=2, backoff_seconds=(2.0,)):
    if getattr(capture, "_V12_REFERENCE_RESILIENCE_INSTALLED", False):
        return getattr(capture, "_V12_REFERENCE_RESILIENCE_AUDIT", {})

    max_attempts = max(1, int(max_attempts))
    original_candidate = capture._candidate_audit
    original_vci = capture._vci_corporate_action_dates
    original_unified_history = capture._unified_history
    original_build = capture.build_source_capture_store
    original_capture_price_history = capture.capture_price_history

    def pause(i, error=""):
        if i >= max_attempts - 1:
            return
        seq = tuple(backoff_seconds or ())
        delay = float(seq[min(i, len(seq) - 1)]) if seq else 0.0
        if _rate_limited(error):
            delay = max(delay, 8.0)
        if delay > 0:
            time.sleep(delay)

    def yahoo_disabled(symbol):
        return [], {
            "source": "DISABLED",
            "provider": "NONE",
            "rows": 0,
            "networkCall": False,
            "policy": "VNSTOCK_ONLY_NO_YAHOO_RUNTIME_REFERENCE",
            "symbol": symbol,
        }

    def candidate(
        symbol,
        rows,
        source_audit,
        yahoo_rows,
        yahoo_audit,
        *,
        raw_reference_rows=None,
        raw_reference_audit=None,
        known_ca_dates=None,
        event_reference_audit=None,
    ):
        adjusted, audit = original_candidate(
            symbol,
            rows,
            source_audit,
            [],
            yahoo_disabled(symbol)[1],
            raw_reference_rows=raw_reference_rows or [],
            raw_reference_audit=raw_reference_audit,
            known_ca_dates=known_ca_dates or set(),
            event_reference_audit=event_reference_audit,
        )
        if raw_reference_rows:
            mad, common = capture.base._cross_source_mad(adjusted, raw_reference_rows)
            audit["crossSourceReturnMAD"] = mad
            audit["crossSourceCommonDates"] = common
            audit["crossSourceReferencePolicy"] = "VNSTOCK_RAW_SECONDARY_ROUTE_ONLY"
            if mad is not None and mad > capture.base.CROSS_SOURCE_MAD_LIMIT:
                audit["eligible"] = False
                reasons = list(audit.get("ineligibleReasons") or [])
                reason = f"cross_source_mad:{float(mad):.10f}>{capture.base.CROSS_SOURCE_MAD_LIMIT:.10f}"
                if reason not in reasons:
                    reasons.append(reason)
                audit["ineligibleReasons"] = reasons
        else:
            audit["crossSourceReferencePolicy"] = "VNSTOCK_RAW_SECONDARY_NOT_REQUIRED_FOR_THIS_SYMBOL"
        audit["adjustmentReference"] = yahoo_disabled(symbol)[1]
        return adjusted, audit

    def unified(symbol, years, attempts, stage="VNSTOCK_PRIMARY"):
        for i in range(max_attempts):
            try:
                rows, audit = _call_with_timeout(
                    f"{symbol}:{stage}:UNIFIED",
                    original_unified_history,
                    symbol,
                    years,
                )
                attempts.append({
                    "stage": stage,
                    "ok": True,
                    **audit,
                    "sourceRetryPolicy": "PER_CALL_WATCHDOG_BOUNDED_LOCAL_RETRY",
                    "sourceAttempts": i + 1,
                })
                return rows, audit
            except BaseException as exc:
                error = f"{type(exc).__name__}: {exc}"[:700]
                attempts.append({
                    "stage": stage,
                    "ok": False,
                    "providerCode": "UNIFIED",
                    "reason": "transient_provider_error" if _transient(error) else "provider_error",
                    "error": error,
                    "networkCallTimeoutSeconds": _network_timeout_seconds(),
                })
                if not _transient(error) or i + 1 >= max_attempts:
                    return None
                pause(i, error)
        return None

    def provider(symbol, source, start, end, attempts, stage):
        for i in range(max_attempts):
            try:
                rows, audit = _call_with_timeout(
                    f"{symbol}:{stage}:{source}",
                    capture.base._provider_history,
                    symbol,
                    source,
                    start,
                    end,
                )
                attempts.append({
                    "stage": stage,
                    "ok": True,
                    **audit,
                    "sourceRetryPolicy": "PER_CALL_WATCHDOG_BOUNDED_LOCAL_RETRY",
                    "sourceAttempts": i + 1,
                })
                return rows, audit
            except BaseException as exc:
                error = f"{type(exc).__name__}: {exc}"[:700]
                attempts.append({
                    "stage": stage,
                    "ok": False,
                    "providerCode": source,
                    "reason": "transient_provider_error" if _transient(error) else "provider_error",
                    "error": error,
                    "networkCallTimeoutSeconds": _network_timeout_seconds(),
                })
                if not _transient(error) or i + 1 >= max_attempts:
                    return None
                pause(i, error)
        return None

    def vci_events(symbol, attempts):
        for i in range(max_attempts):
            before = len(attempts)
            try:
                result = _call_with_timeout(
                    f"{symbol}:VNSTOCK_CA_EVENTS",
                    original_vci,
                    symbol,
                    attempts,
                )
                dates, audit = result
            except BaseException as exc:
                error = f"{type(exc).__name__}: {exc}"[:700]
                attempts.append({
                    "stage": "VCI_CORPORATE_ACTION_EVENT_REFERENCE",
                    "ok": False,
                    "reason": "transient_provider_error" if _transient(error) else "provider_error",
                    "error": error,
                    "networkCallTimeoutSeconds": _network_timeout_seconds(),
                })
                dates, audit = set(), None

            if audit is not None:
                audit = dict(audit)
                audit["referenceRetryPolicy"] = "VNSTOCK_ONLY_PER_CALL_WATCHDOG_BOUNDED_LOCAL_RETRY"
                audit["referenceAttempts"] = i + 1
                if len(attempts) > before and attempts[-1].get("ok") is True:
                    attempts[-1].update({
                        "referenceRetryPolicy": audit["referenceRetryPolicy"],
                        "referenceAttempts": i + 1,
                    })
                return dates, audit

            error = attempts[-1].get("error") if len(attempts) > before else ""
            if not _transient(error) or i + 1 >= max_attempts:
                return dates, audit
            pause(i, error)
        return set(), None

    def capture_price_history(symbol, years=8):
        started = time.monotonic()
        print({
            "v12SourceSymbolStart": symbol,
            "networkPolicy": "VNSTOCK_ONLY_NO_YAHOO_NO_GLOBAL_CIRCUIT",
        }, flush=True)
        rows, audit = original_capture_price_history(symbol, years=years)

        if (
            audit.get("eligible") is True
            and audit.get("crossSourceReturnMAD") is None
            and _secondary_audit_required(symbol)
        ):
            start, end = capture.base._history_window(years)
            attempts = list(audit.get("attempts") or [])
            ref = provider(symbol, "VCI", start, end, attempts, "VNSTOCK_VCI_SECONDARY_AUDIT")
            if ref is None:
                ref = provider(symbol, "KBS", start, end, attempts, "VNSTOCK_KBS_SECONDARY_AUDIT")
            if ref is not None:
                ref_rows, ref_audit = ref
                mad, common = capture.base._cross_source_mad(rows, ref_rows)
                audit["crossSourceReturnMAD"] = mad
                audit["crossSourceCommonDates"] = common
                audit["secondaryRawReference"] = ref_audit
                audit["crossSourceReferencePolicy"] = "DETERMINISTIC_VNSTOCK_SECONDARY_AUDIT_SAMPLE"
                if mad is not None and mad > capture.base.CROSS_SOURCE_MAD_LIMIT:
                    audit["eligible"] = False
                    reasons = list(audit.get("ineligibleReasons") or [])
                    reason = f"cross_source_mad:{float(mad):.10f}>{capture.base.CROSS_SOURCE_MAD_LIMIT:.10f}"
                    if reason not in reasons:
                        reasons.append(reason)
                    audit["ineligibleReasons"] = reasons
            audit["attempts"] = attempts

        audit["runtimeSourcePolicy"] = "VNSTOCK_ONLY_NO_YAHOO_NO_GLOBAL_CIRCUIT"
        audit["networkCallTimeoutSeconds"] = _network_timeout_seconds()
        print({
            "v12SourceSymbolDone": symbol,
            "elapsedSeconds": round(time.monotonic() - started, 3),
            "eligible": audit.get("eligible"),
            "route": audit.get("route"),
            "crossSourceMAD": audit.get("crossSourceReturnMAD"),
        }, flush=True)
        return rows, audit

    def build_source_capture_store(symbols):
        anchors = [s for s in ("FPT", "VCB", "HPG") if s in set(symbols)]
        preflight = {}
        success = 0
        start, end = capture.base._history_window(8)
        for symbol in anchors:
            attempts = []
            route = unified(symbol, 8, attempts, "VNSTOCK_PREFLIGHT_UNIFIED")
            if route is None:
                route = provider(symbol, "VCI", start, end, attempts, "VNSTOCK_PREFLIGHT_VCI")
            if route is None:
                route = provider(symbol, "KBS", start, end, attempts, "VNSTOCK_PREFLIGHT_KBS")
            ok = route is not None
            success += int(ok)
            preflight[symbol] = {"ok": ok, "attempts": attempts}
        if anchors and success < min(2, len(anchors)):
            print({
                "v12VNStockPreflight": "FAIL",
                "success": success,
                "required": min(2, len(anchors)),
                "anchors": preflight,
            }, flush=True)
            return {}, {}, {
                "__VNSTOCK_PREFLIGHT__": {
                    "error": f"VNStock preflight failed: {success}/{len(anchors)} anchor symbols reachable",
                    "attempts": [
                        x for item in preflight.values() for x in item.get("attempts", [])
                    ],
                    "anchors": preflight,
                }
            }
        print({
            "v12VNStockPreflight": "PASS",
            "success": success,
            "anchors": anchors,
        }, flush=True)

        store, audits, failures = original_build(symbols)

        retry_symbols = []
        retry_failure_symbols = []
        min_rows = int(getattr(capture.base, "MIN_ROWS", 520))
        for symbol, rows in sorted(store.items()):
            audit = audits.get(symbol) or {}
            original_rows = int(audit.get("originalRows") or len(rows))
            ca_verified = (audit.get("corporateAction") or {}).get("verified") is True
            if original_rows >= min_rows and not ca_verified and _audit_has_transient_failure(audit):
                retry_symbols.append(symbol)
        for symbol, failure in sorted(failures.items()):
            if _failure_has_transient_failure(failure):
                retry_failure_symbols.append(symbol)

        if retry_symbols or retry_failure_symbols:
            print({
                "v12SourceCleanSecondPass": True,
                "capturedRetry": retry_symbols,
                "captureFailureRetry": retry_failure_symbols,
            }, flush=True)

        for symbol in retry_failure_symbols:
            first_failure = dict(failures.get(symbol) or {})
            first_attempts = list(first_failure.get("attempts") or [])
            try:
                retry_rows, retry_audit = capture_price_history(symbol)
                retry_audit = dict(retry_audit or {})
                retry_audit["attempts"] = first_attempts + [{
                    "stage": "SOURCE_STORE_TRANSIENT_CAPTURE_RECOVERY_BOUNDARY",
                    "ok": True,
                    "policy": "TRANSIENT_CAPTURE_FAILURE_CLEAN_SECOND_PASS",
                }] + list(retry_audit.get("attempts") or [])
                retry_audit["sourceStoreRecovery"] = {
                    "policy": "TRANSIENT_CAPTURE_FAILURE_CLEAN_SECOND_PASS",
                    "attempted": True,
                    "accepted": True,
                    "priceOrReturnMutation": False,
                    "gateMutation": False,
                }
                store[symbol] = retry_rows
                audits[symbol] = retry_audit
                failures.pop(symbol, None)
            except BaseException as exc:
                first_failure["sourceStoreRecovery"] = {
                    "policy": "TRANSIENT_CAPTURE_FAILURE_CLEAN_SECOND_PASS",
                    "attempted": True,
                    "accepted": False,
                    "error": f"{type(exc).__name__}: {exc}"[:700],
                    "priceOrReturnMutation": False,
                    "gateMutation": False,
                }
                failures[symbol] = first_failure

        for symbol in retry_symbols:
            first_audit = dict(audits.get(symbol) or {})
            first_attempts = list(first_audit.get("attempts") or [])
            try:
                retry_rows, retry_audit = capture_price_history(symbol)
                retry_audit = dict(retry_audit or {})
                retry_ca = (retry_audit.get("corporateAction") or {}).get("verified") is True
                retry_eligible = retry_audit.get("eligible") is True
                recovery = {
                    "policy": "TRANSIENT_ONLY_CLEAN_SECOND_PASS",
                    "attempted": True,
                    "accepted": bool(retry_ca and retry_eligible),
                    "priceOrReturnMutation": False,
                    "gateMutation": False,
                }
                if retry_ca and retry_eligible:
                    retry_audit["attempts"] = first_attempts + [{
                        "stage": "SOURCE_STORE_TRANSIENT_RECOVERY_BOUNDARY",
                        "ok": True,
                        "policy": recovery["policy"],
                    }] + list(retry_audit.get("attempts") or [])
                    retry_audit["sourceStoreRecovery"] = recovery
                    store[symbol] = retry_rows
                    audits[symbol] = retry_audit
                    failures.pop(symbol, None)
                else:
                    first_audit["sourceStoreRecovery"] = {
                        **recovery,
                        "retryIneligibleReasons": retry_audit.get("ineligibleReasons"),
                    }
                    audits[symbol] = first_audit
            except BaseException as exc:
                first_audit["sourceStoreRecovery"] = {
                    "policy": "TRANSIENT_ONLY_CLEAN_SECOND_PASS",
                    "attempted": True,
                    "accepted": False,
                    "error": f"{type(exc).__name__}: {exc}"[:700],
                    "priceOrReturnMutation": False,
                    "gateMutation": False,
                }
                audits[symbol] = first_audit

        return store, audits, failures

    capture.base.yahoo_history = yahoo_disabled
    capture._candidate_audit = candidate
    capture._capture_unified = unified
    capture._capture_provider = provider
    capture._vci_corporate_action_dates = vci_events
    capture.capture_price_history = capture_price_history
    capture.build_source_capture_store = build_source_capture_store
    capture.reset_provider_circuits = lambda: None

    capture._V12_REFERENCE_RESILIENCE_INSTALLED = True
    capture._V12_REFERENCE_RESILIENCE_AUDIT = {
        "version": "VMEWS-V12-VNSTOCK-ONLY-RESILIENCE-2.0.0",
        "runtimeNetworkSource": "VNSTOCK_ONLY",
        "yahooRuntimeNetworkCall": False,
        "globalCircuitBreaker": False,
        "perCallWatchdog": True,
        "networkCallTimeoutSeconds": _network_timeout_seconds(),
        "maxAttemptsPerCall": max_attempts,
        "retryScope": "TRANSIENT_ONLY_BOUNDED_LOCAL",
        "preflightAnchors": ["FPT", "VCB", "HPG"],
        "deterministicSecondaryAuditModulus": _SECONDARY_AUDIT_MODULUS,
        "sourceStoreTransientSecondPass": original_build is not None,
        "priceOrReturnMutation": False,
        "gateMutation": False,
    }
    return dict(capture._V12_REFERENCE_RESILIENCE_AUDIT)
