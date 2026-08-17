"""Bounded resilience for reference-only acquisition used during V12 source freeze.

No price, return, eligibility threshold, or corporate-action rule is changed. Only transient
transport/rate-limit failures are retried. Permanent errors remain fail-safe.
"""
import time

_TRANSIENT_MARKERS=("timeout","timed out","429","rate limit","too many requests","502","503","504","connection reset","connectionpool","max retries exceeded","temporary failure","name resolution","network is unreachable","remote disconnected")

def _transient(value):
    text=str(value or "").lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)

def install(capture,max_attempts=3,backoff_seconds=(1.0,2.0)):
    if getattr(capture,"_V12_REFERENCE_RESILIENCE_INSTALLED",False):
        return getattr(capture,"_V12_REFERENCE_RESILIENCE_AUDIT",{})
    max_attempts=max(1,int(max_attempts))
    original_yahoo=capture.base.yahoo_history
    original_vci=capture._vci_corporate_action_dates
    def pause(i):
        if i>=max_attempts-1:return
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
                last=exc
                if not _transient(f"{type(exc).__name__}: {exc}") or i+1>=max_attempts:raise
                pause(i)
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
            pause(i)
        return set(),None
    capture.base.yahoo_history=yahoo
    capture._vci_corporate_action_dates=vci_events
    capture._V12_REFERENCE_RESILIENCE_INSTALLED=True
    capture._V12_REFERENCE_RESILIENCE_AUDIT={"version":"VMEWS-V12-REFERENCE-RESILIENCE-1.0.0","maxAttempts":max_attempts,"retryScope":"TRANSIENT_TRANSPORT_RATE_LIMIT_ONLY","vciEventUsesVNStockThrottle":True,"priceOrReturnMutation":False,"gateMutation":False}
    return dict(capture._V12_REFERENCE_RESILIENCE_AUDIT)
