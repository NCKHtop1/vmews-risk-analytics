"""Bounded resilience for reference/source acquisition used during V12 source freeze.

No price, return, eligibility threshold, corporate-action rule, or gate is changed. Only
transient transport/rate-limit failures are retried. Permanent errors remain fail-safe.
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


def install(capture, max_attempts=3, backoff_seconds=(1.0, 2.0)):
    if getattr(capture, "_V12_REFERENCE_RESILIENCE_INSTALLED", False):
        return getattr(capture, "_V12_REFERENCE_RESILIENCE_AUDIT", {})

    max_attempts = max(1, int(max_attempts))
    original_yahoo = capture.base.yahoo_history
    original_vci = capture._vci_corporate_action_dates
    original_unified = getattr(capture, "_capture_unified", None)
    original_provider = getattr(capture, "_capture_provider", None)
    original_build = getattr(capture, "build_source_capture_store", None)

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
        last = None
        for i in range(max_attempts):
            try:
                rows, audit = original_yahoo(symbol)
                audit = dict(audit or {})
                audit["referenceRetryPolicy"] = "TRANSIENT_ONLY_BOUNDED"
                audit["referenceAttempts"] = i + 1
                return rows, audit
            except BaseException as exc:
                last = exc
                error = f"{type(exc).__name__}: {exc}"
                if not _transient(error) or i + 1 >= max_attempts:
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
        """Retry only terminal transient failures from the same immutable VNStock request."""
        for i in range(max_attempts):
            before = len(attempts)
            result = original_unified(symbol, years, attempts, stage)
            if result is not None:
                if i and len(attempts) > before:
                    attempts[-1].update({
                        "sourceRetryPolicy": "TRANSIENT_ONLY_BOUNDED",
                        "sourceAttempts": i + 1,
                    })
                return result
            error = attempts[-1].get("error") if len(attempts) > before else ""
            if not _transient(error) or i + 1 >= max_attempts:
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
            error = attempts[-1].get("error") if len(attempts) > before else ""
            if not _rate_limited(error) or i + 1 >= max_attempts:
                return None
            pause(i, error)
        return None

    def build_source_capture_store(symbols):
        """Give original-deep CA failures one clean second pass only after transient faults.

        A long universe capture can leave a symbol fail-safe because its independent CA/raw
        corroboration request hit a transient quota/network window even though the price
        history itself was captured. Re-acquire only those original-deep symbols whose first
        audit contains an explicit transient failure. The second pass uses the exact same PIT
        capture function and unchanged gates. It replaces the first pass only if the normal
        capture returns eligible with CA verified; permanent/data failures remain untouched.
        """
        store, audits, failures = original_build(symbols)
        min_rows = int(getattr(capture.base, "MIN_ROWS", 520))
        retry_symbols = []
        rate_limited = False
        for symbol, rows in sorted(store.items()):
            audit = audits.get(symbol) or {}
            original_rows = int(audit.get("originalRows") or len(rows))
            ca_verified = (audit.get("corporateAction") or {}).get("verified") is True
            if original_rows < min_rows or ca_verified or not _audit_has_transient_failure(audit):
                continue
            retry_symbols.append(symbol)
            rate_limited = rate_limited or any(
                attempt.get("ok") is False and _rate_limited(_attempt_error_text(attempt))
                for attempt in audit.get("attempts") or []
            )

        if not retry_symbols:
            return store, audits, failures

        if rate_limited:
            time.sleep(_RATE_LIMIT_COOLDOWN_SECONDS)
        reset = getattr(capture, "reset_provider_circuits", None)
        if reset is not None:
            reset()

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
    if original_build is not None:
        capture.build_source_capture_store = build_source_capture_store

    capture._V12_REFERENCE_RESILIENCE_INSTALLED = True
    capture._V12_REFERENCE_RESILIENCE_AUDIT = {
        "version": "VMEWS-V12-REFERENCE-RESILIENCE-1.2.0",
        "maxAttempts": max_attempts,
        "retryScope": "TRANSIENT_TRANSPORT_RATE_LIMIT_ONLY",
        "rateLimitCooldownSeconds": _RATE_LIMIT_COOLDOWN_SECONDS,
        "vciEventUsesVNStockThrottle": True,
        "unifiedTransientRetry": original_unified is not None,
        "providerRateLimitRetry": original_provider is not None,
        "sourceStoreTransientSecondPass": original_build is not None,
        "priceOrReturnMutation": False,
        "gateMutation": False,
    }
    return dict(capture._V12_REFERENCE_RESILIENCE_AUDIT)
