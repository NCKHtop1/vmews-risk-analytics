"""Bounded resilience for reference/source acquisition used during V12 source freeze.

No price, return, eligibility threshold, corporate-action rule, or gate is changed. Only
transient transport/rate-limit failures are retried. Permanent errors remain fail-safe.

Run-local reference circuits prevent a provider-wide outage from consuming the entire
GitHub Actions time budget symbol-by-symbol. A circuit opens only after two symbols each
exhaust the normal bounded transient retry policy. A clean second pass resets the
circuits and retries only symbols that have explicit transient evidence.
"""
import time

_TRANSIENT_MARKERS = (
    "timeout", "timed out", "429", "rate limit", "too many requests", "502", "503",
    "504", "connection reset", "connectionpool", "max retries exceeded",
    "temporary failure", "name resolution", "network is unreachable",
    "remote disconnected",
)
_RATE_LIMIT_MARKERS = ("429", "rate limit", "too many requests", "giới hạn api", "requests/phút")
_RATE_LIMIT_COOLDOWN_SECONDS = 61.0
_CIRCUIT_TERMINAL_FAILURES = 2


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


def _attempts_rate_limited(attempts):
    return any(
        attempt.get("ok") is False and _rate_limited(_attempt_error_text(attempt))
        for attempt in attempts or []
    )


def install(capture, max_attempts=3, backoff_seconds=(1.0, 2.0)):
    if getattr(capture, "_V12_REFERENCE_RESILIENCE_INSTALLED", False):
        return getattr(capture, "_V12_REFERENCE_RESILIENCE_AUDIT", {})

    max_attempts = max(1, int(max_attempts))
    original_yahoo = capture.base.yahoo_history
    original_vci = capture._vci_corporate_action_dates
    original_unified = getattr(capture, "_capture_unified", None)
    original_provider = getattr(capture, "_capture_provider", None)
    original_build = getattr(capture, "build_source_capture_store", None)
    original_reset = getattr(capture, "reset_provider_circuits", None)

    component_circuits = {
        "YAHOO_REFERENCE": {
            "open": False,
            "terminalTransientFailures": 0,
            "reason": None,
        },
        "UNIFIED": {
            "open": False,
            "terminalTransientFailures": 0,
            "reason": None,
        },
    }

    def reset_component_circuits():
        for state in component_circuits.values():
            state["open"] = False
            state["terminalTransientFailures"] = 0
            state["reason"] = None

    def reset_all_provider_circuits():
        if original_reset is not None:
            original_reset()
        reset_component_circuits()

    def mark_success(name):
        state = component_circuits[name]
        state["open"] = False
        state["terminalTransientFailures"] = 0
        state["reason"] = None

    def mark_terminal_transient(name, error):
        state = component_circuits[name]
        state["terminalTransientFailures"] = int(
            state.get("terminalTransientFailures") or 0
        ) + 1
        state["reason"] = str(error or "")[:700]
        if state["terminalTransientFailures"] >= _CIRCUIT_TERMINAL_FAILURES:
            state["open"] = True

    def pause(i, error=""):
        if i >= max_attempts - 1:
            return
        if _rate_limited(error):
            time.sleep(_RATE_LIMIT_COOLDOWN_SECONDS)
            return
        seq = tuple(backoff_seconds or ())
        delay = float(seq[min(i, len(seq) - 1)]) if seq else 0.0
        if delay > 0:
            time.sleep(delay)

    def yahoo(symbol):
        state = component_circuits["YAHOO_REFERENCE"]
        if state.get("open") is True:
            raise RuntimeError(
                "YAHOO reference provider_circuit_open after terminal transient "
                f"failures: {state.get('reason') or 'transient provider outage'}"
            )

        last = None
        for i in range(max_attempts):
            try:
                rows, audit = original_yahoo(symbol)
                mark_success("YAHOO_REFERENCE")
                audit = dict(audit or {})
                audit["referenceRetryPolicy"] = "TRANSIENT_ONLY_BOUNDED_WITH_RUN_CIRCUIT"
                audit["referenceAttempts"] = i + 1
                return rows, audit
            except BaseException as exc:
                last = exc
                error = f"{type(exc).__name__}: {exc}"
                if not _transient(error):
                    raise
                if i + 1 >= max_attempts:
                    mark_terminal_transient("YAHOO_REFERENCE", error)
                    raise
                pause(i, error)
        raise last

    def vci_events(symbol, attempts):
        for i in range(max_attempts):
            capture.base._throttle_vnstock()
            before = len(attempts)
            dates, audit = original_vci(symbol, attempts)
            if audit is not None:
                audit = dict(audit)
                audit["referenceRetryPolicy"] = "VNSTOCK_THROTTLED_TRANSIENT_ONLY_BOUNDED"
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

    def unified(symbol, years, attempts, stage="VNSTOCK_PRIMARY"):
        """Retry transient Unified failures, then short-circuit a provider-wide outage."""
        state = component_circuits["UNIFIED"]
        if state.get("open") is True:
            attempts.append({
                "stage": stage,
                "ok": False,
                "providerCode": "UNIFIED",
                "reason": "provider_circuit_open",
                "providerCircuitOpen": True,
                "error": state.get("reason"),
            })
            return None

        for i in range(max_attempts):
            before = len(attempts)
            result = original_unified(symbol, years, attempts, stage)
            if result is not None:
                mark_success("UNIFIED")
                if i and len(attempts) > before:
                    attempts[-1].update({
                        "sourceRetryPolicy": "TRANSIENT_ONLY_BOUNDED_WITH_RUN_CIRCUIT",
                        "sourceAttempts": i + 1,
                    })
                return result

            last_attempt = attempts[-1] if len(attempts) > before else {}
            error = last_attempt.get("error") or last_attempt.get("reason") or ""
            if last_attempt.get("reason") == "provider_circuit_open":
                return None
            if not _transient(error):
                return None
            if i + 1 >= max_attempts:
                mark_terminal_transient("UNIFIED", error)
                if component_circuits["UNIFIED"].get("open") is True and attempts:
                    attempts[-1]["providerCircuitOpen"] = True
                return None
            pause(i, error)
        return None

    def provider(symbol, source, start, end, attempts, stage):
        """Retry provider recovery only for quota-window failures, never for bad data."""
        for i in range(max_attempts):
            before = len(attempts)
            result = original_provider(symbol, source, start, end, attempts, stage)
            if result is not None:
                if i and len(attempts) > before:
                    attempts[-1].update({
                        "sourceRetryPolicy": "RATE_LIMIT_ONLY_BOUNDED",
                        "sourceAttempts": i + 1,
                    })
                return result
            last_attempt = attempts[-1] if len(attempts) > before else {}
            error = last_attempt.get("error") or last_attempt.get("reason") or ""
            if last_attempt.get("reason") == "provider_circuit_open":
                return None
            if not _rate_limited(error) or i + 1 >= max_attempts:
                return None
            pause(i, error)
        return None

    def build_source_capture_store(symbols):
        """Cleanly retry only first-pass records with explicit transient evidence.

        Two cases are eligible for one clean second pass with all run-local circuits reset:
        (1) an original-deep captured symbol whose CA certification failed during a transient
        reference/provider window; and (2) a symbol that was not captured at all because every
        available route hit an explicit transient failure. Permanent/data-quality failures are
        never retried. No price/return/gate is mutated.
        """
        store, audits, failures = original_build(symbols)
        min_rows = int(getattr(capture.base, "MIN_ROWS", 520))
        retry_symbols = []
        retry_failure_symbols = []
        rate_limited = False

        for symbol, rows in sorted(store.items()):
            audit = audits.get(symbol) or {}
            original_rows = int(audit.get("originalRows") or len(rows))
            ca_verified = (audit.get("corporateAction") or {}).get("verified") is True
            if original_rows < min_rows or ca_verified or not _audit_has_transient_failure(audit):
                continue
            retry_symbols.append(symbol)
            rate_limited = rate_limited or _attempts_rate_limited(audit.get("attempts") or [])

        for symbol, failure in sorted(failures.items()):
            if not _failure_has_transient_failure(failure):
                continue
            retry_failure_symbols.append(symbol)
            rate_limited = rate_limited or _attempts_rate_limited(
                (failure or {}).get("attempts") or []
            )

        if not retry_symbols and not retry_failure_symbols:
            return store, audits, failures

        if rate_limited:
            time.sleep(_RATE_LIMIT_COOLDOWN_SECONDS)
        reset_all_provider_circuits()

        for symbol in retry_failure_symbols:
            first_failure = dict(failures.get(symbol) or {})
            first_attempts = list(first_failure.get("attempts") or [])
            try:
                retry_rows, retry_audit = capture.capture_price_history(symbol)
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
            first_audit = audits.get(symbol) or {}
            first_attempts = list(first_audit.get("attempts") or [])
            try:
                retry_rows, retry_audit = capture.capture_price_history(symbol)
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
                    first_audit = dict(first_audit)
                    first_audit["sourceStoreRecovery"] = {
                        **recovery,
                        "retryIneligibleReasons": retry_audit.get("ineligibleReasons"),
                    }
                    audits[symbol] = first_audit
            except BaseException as exc:
                first_audit = dict(first_audit)
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

    capture.base.yahoo_history = yahoo
    capture._vci_corporate_action_dates = vci_events
    if original_unified is not None:
        capture._capture_unified = unified
    if original_provider is not None:
        capture._capture_provider = provider
    capture.reset_provider_circuits = reset_all_provider_circuits
    if original_build is not None:
        capture.build_source_capture_store = build_source_capture_store

    capture._V12_REFERENCE_COMPONENT_CIRCUITS = component_circuits
    capture._V12_REFERENCE_RESILIENCE_INSTALLED = True
    capture._V12_REFERENCE_RESILIENCE_AUDIT = {
        "version": "VMEWS-V12-REFERENCE-RESILIENCE-1.3.0",
        "maxAttempts": max_attempts,
        "retryScope": "TRANSIENT_TRANSPORT_RATE_LIMIT_ONLY",
        "rateLimitCooldownSeconds": _RATE_LIMIT_COOLDOWN_SECONDS,
        "componentCircuitTerminalFailures": _CIRCUIT_TERMINAL_FAILURES,
        "yahooReferenceTransientCircuit": True,
        "unifiedTransientCircuit": original_unified is not None,
        "vciEventUsesVNStockThrottle": True,
        "unifiedTransientRetry": original_unified is not None,
        "providerRateLimitRetry": original_provider is not None,
        "sourceStoreTransientSecondPass": original_build is not None,
        "sourceStoreTransientCaptureFailureSecondPass": original_build is not None,
        "priceOrReturnMutation": False,
        "gateMutation": False,
    }
    return dict(capture._V12_REFERENCE_RESILIENCE_AUDIT)
