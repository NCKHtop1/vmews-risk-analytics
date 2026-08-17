"""Bounded resilience for reference/source acquisition used during V12 source freeze.

No price, return, eligibility threshold, corporate-action rule, or gate is changed. Only
transient transport/rate-limit failures are retried. Permanent errors remain fail-safe.
"""
import time

_TRANSIENT_MARKERS=("timeout","timed out","429","rate limit","too many requests","502","503","504","connection reset","connectionpool","max retries exceeded","temporary failure","name resolution","network is unreachable","remote disconnected")
_RATE_LIMIT_MARKERS=("429","rate limit","too many requests","giới hạn api","requests/phút")
_RATE_LIMIT_COOLDOWN_SECONDS=61.0

def _transient(value):
    text=str(value or "").lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)

def _rate_limited(value):
    text=str(value or "").lower()
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)

def install(capture,max_attempts=3,backoff_seconds=(1.0,2.0)):
    if getattr(capture,"_V12_REFERENCE_RESILIENCE_INSTALLED",False):
        return getattr(capture,"_V12_REFERENCE_RESILIENCE_AUDIT",{})
    max_attempts=max(1,int(max_attempts))
    original_yahoo=capture.base.yahoo_history
    original_vci=capture._vci_corporate_action_dates
    original_unified=getattr(capture,"_capture_unified",None)
    original_provider=getattr(capture,"_capture_provider",None)
    def pause(i,error=""):
        if i>=max_attempts-1:return
        if _rate_limited(error):
            time.sleep(_RATE_LIMIT_COOLDOWN_SECONDS);return
        seq=tuple(backoff_seconds or ());delay=float(seq[min(i,len(seq)-1)]) if seq else 0.0
        if delay>0:time.sleep(delay)
    def yahoo(symbol):
        last=None
        for i in range(max_attempts):
            try:
                rows,audit=original_yahoo(symbol);audit=dict(audit or {})
                audit["referenceRetryPolicy"]="TRANSIENT_ONLY_BOUNDED";audit["referenceAttempts"]=i+1
                return rows,audit
            except BaseException as exc:
                last=exc;error=f"{type(exc).__name__}: {exc}"
                if not _transient(error) or i+1>=max_attempts:raise
                pause(i,error)
        raise last
    def vci_events(symbol,attempts):
        for i in range(max_attempts):
            capture.base._throttle_vnstock()
            before=len(attempts);dates,audit=original_vci(symbol,attempts)
            if audit is not None:
                audit=dict(audit);audit["referenceRetryPolicy"]="VNSTOCK_THROTTLED_TRANSIENT_ONLY_BOUNDED";audit["referenceAttempts"]=i+1
                if len(attempts)>before and attempts[-1].get("ok") is True:
                    attempts[-1].update({"referenceRetryPolicy":audit["referenceRetryPolicy"],"referenceAttempts":i+1})
                return dates,audit
            error=attempts[-1].get("error") if len(attempts)>before else ""
            if not _transient(error) or i+1>=max_attempts:return dates,audit
            pause(i,error)
        return set(),None
    def unified(symbol,years,attempts,stage="VNSTOCK_PRIMARY"):
        """Retry only terminal transient failures from the same immutable VNStock request.

        The retry changes acquisition availability only; the returned rows still pass the
        unchanged CA/MAD/deep-history gates downstream.
        """
        for i in range(max_attempts):
            before=len(attempts);result=original_unified(symbol,years,attempts,stage)
            if result is not None:
                if i and len(attempts)>before:
                    attempts[-1].update({"sourceRetryPolicy":"TRANSIENT_ONLY_BOUNDED","sourceAttempts":i+1})
                return result
            error=attempts[-1].get("error") if len(attempts)>before else ""
            if not _transient(error) or i+1>=max_attempts:return None
            pause(i,error)
        return None
    def provider(symbol,source,start,end,attempts,stage):
        """Retry provider recovery only for quota-window failures, never for bad data.

        Network-outage circuit semantics are intentionally preserved; only explicit rate
        limiting is retried after the provider window is allowed to reset.
        """
        for i in range(max_attempts):
            before=len(attempts);result=original_provider(symbol,source,start,end,attempts,stage)
            if result is not None:
                if i and len(attempts)>before:
                    attempts[-1].update({"sourceRetryPolicy":"RATE_LIMIT_ONLY_BOUNDED","sourceAttempts":i+1})
                return result
            error=attempts[-1].get("error") if len(attempts)>before else ""
            if not _rate_limited(error) or i+1>=max_attempts:return None
            pause(i,error)
        return None
    capture.base.yahoo_history=yahoo
    capture._vci_corporate_action_dates=vci_events
    if original_unified is not None:capture._capture_unified=unified
    if original_provider is not None:capture._capture_provider=provider
    capture._V12_REFERENCE_RESILIENCE_INSTALLED=True
    capture._V12_REFERENCE_RESILIENCE_AUDIT={"version":"VMEWS-V12-REFERENCE-RESILIENCE-1.1.0","maxAttempts":max_attempts,"retryScope":"TRANSIENT_TRANSPORT_RATE_LIMIT_ONLY","rateLimitCooldownSeconds":_RATE_LIMIT_COOLDOWN_SECONDS,"vciEventUsesVNStockThrottle":True,"unifiedTransientRetry":original_unified is not None,"providerRateLimitRetry":original_provider is not None,"priceOrReturnMutation":False,"gateMutation":False}
    return dict(capture._V12_REFERENCE_RESILIENCE_AUDIT)
