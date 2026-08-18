import os
import time
from types import SimpleNamespace

import v12_reference_resilience as r


sleeps = []
real_sleep = time.sleep
r.time.sleep = lambda seconds: sleeps.append(float(seconds))
os.environ["V12_NETWORK_CALL_TIMEOUT"] = "0.05"


class Base:
    MIN_ROWS = 520
    CROSS_SOURCE_MAD_LIMIT = 0.003

    def __init__(self):
        self.provider_calls = 0

    def yahoo_history(self, symbol):
        raise AssertionError("Yahoo network path must be disabled by VNStock-only install")

    def _provider_history(self, symbol, source, start, end):
        self.provider_calls += 1
        if self.provider_calls == 1:
            raise RuntimeError("ReadTimeout: transient")
        return ([{"date": "2026-01-01", "close": 100.0}], {
            "source": "VNSTOCK",
            "providerCode": source,
            "rows": 1,
        })

    def _history_window(self, years=8):
        return "2020-01-01", "2026-01-02"

    def _cross_source_mad(self, a, b):
        return (0.0001, 100) if a and b else (None, 0)


base = Base()
unified_calls = {"n": 0}
vci_calls = {"n": 0}


def candidate(symbol, rows, source_audit, yahoo_rows, yahoo_audit, **kwargs):
    return list(rows), {
        "symbol": symbol,
        "eligible": True,
        "deepHistory": True,
        "corporateAction": {"verified": True},
        "ineligibleReasons": [],
        "crossSourceReturnMAD": None,
        "crossSourceCommonDates": 0,
        "attempts": [],
    }


def unified_history(symbol, years=8):
    unified_calls["n"] += 1
    if unified_calls["n"] == 1:
        raise RuntimeError("ReadTimeout: transient")
    return ([{"date": "2026-01-01", "close": 100.0}], {
        "source": "VNSTOCK",
        "providerCode": "UNIFIED",
        "rows": 1,
    })


def vci_events(symbol, attempts):
    vci_calls["n"] += 1
    if vci_calls["n"] == 1:
        attempts.append({
            "stage": "VCI_CORPORATE_ACTION_EVENT_REFERENCE",
            "ok": False,
            "error": "HTTP 429 Too Many Requests",
        })
        return set(), None
    audit = {"source": "VNSTOCK_VCI_EVENT_REFERENCE", "eventCount": 1}
    attempts.append({
        "stage": "VCI_CORPORATE_ACTION_EVENT_REFERENCE",
        "ok": True,
        **audit,
    })
    return {"2025-12-01"}, audit


def capture_price_history(symbol, years=8):
    attempts = []
    route = c._capture_unified(symbol, years, attempts)
    if route is None:
        start, end = base._history_window(years)
        route = c._capture_provider(symbol, "VCI", start, end, attempts, "VNSTOCK_VCI_RECOVERY")
    if route is None:
        raise RuntimeError("no VNStock route")
    rows, source_audit = route
    adjusted, audit = c._candidate_audit(
        symbol, rows, source_audit, [], None,
        raw_reference_rows=[], raw_reference_audit=None,
        known_ca_dates=set(), event_reference_audit=None,
    )
    audit["route"] = "VNSTOCK_SOURCE_CAPTURE_" + source_audit.get("providerCode", "UNKNOWN")
    audit["attempts"] = attempts
    return adjusted, audit


def build_store(symbols):
    store = {}
    audits = {}
    failures = {}
    for symbol in symbols:
        try:
            rows, audit = c.capture_price_history(symbol)
            store[symbol] = rows
            audits[symbol] = audit
        except Exception as exc:
            failures[symbol] = {"error": str(exc), "attempts": []}
    return store, audits, failures


c = SimpleNamespace(
    base=base,
    _candidate_audit=candidate,
    _vci_corporate_action_dates=vci_events,
    _unified_history=unified_history,
    build_source_capture_store=build_store,
    capture_price_history=capture_price_history,
)

audit = r.install(c, max_attempts=2, backoff_seconds=(0,))

rows, y = c.base.yahoo_history("AAA")
assert rows == [] and y["networkCall"] is False and y["policy"] == "VNSTOCK_ONLY_NO_YAHOO_RUNTIME_REFERENCE"

attempts = []
u = c._capture_unified("AAA", 8, attempts)
assert u is not None and unified_calls["n"] == 2, (u, unified_calls, attempts)
attempts2 = []
u2 = c._capture_unified("BBB", 8, attempts2)
assert u2 is not None and unified_calls["n"] == 3, (u2, unified_calls, attempts2)

pa = []
p = c._capture_provider("AAA", "VCI", "2020-01-01", "2026-01-01", pa, "VNSTOCK_VCI_RECOVERY")
assert p is not None and base.provider_calls == 2, (p, base.provider_calls, pa)
pa2 = []
p2 = c._capture_provider("BBB", "VCI", "2020-01-01", "2026-01-01", pa2, "VNSTOCK_VCI_RECOVERY")
assert p2 is not None and base.provider_calls == 3, (p2, base.provider_calls, pa2)

va = []
dates, event_audit = c._vci_corporate_action_dates("AAA", va)
assert dates == {"2025-12-01"} and event_audit is not None and vci_calls["n"] == 2, (dates, event_audit, va)

r.time.sleep = real_sleep
started = time.monotonic()
try:
    r._call_with_timeout("TEST_HANG", time.sleep, 2.0)
    raise AssertionError("watchdog did not interrupt hanging call")
except TimeoutError as exc:
    assert "network_call_timeout" in str(exc)
assert time.monotonic() - started < 0.5
r.time.sleep = lambda seconds: sleeps.append(float(seconds))

adjusted, ca = c._candidate_audit(
    "AAA",
    [{"date": "2026-01-01", "close": 100.0}],
    {"providerCode": "UNIFIED"},
    [],
    None,
    raw_reference_rows=[{"date": "2026-01-01", "close": 100.0}],
    raw_reference_audit={"providerCode": "VCI"},
    known_ca_dates=set(),
    event_reference_audit=None,
)
assert ca["crossSourceReturnMAD"] == 0.0001
assert ca["crossSourceReferencePolicy"] == "VNSTOCK_RAW_SECONDARY_ROUTE_ONLY"

assert audit["runtimeNetworkSource"] == "VNSTOCK_ONLY"
assert audit["yahooRuntimeNetworkCall"] is False
assert audit["globalCircuitBreaker"] is False
assert audit["perCallWatchdog"] is True
assert audit["gateMutation"] is False
assert audit["priceOrReturnMutation"] is False
assert audit["version"] == "VMEWS-V12-VNSTOCK-ONLY-RESILIENCE-2.0.0"

print("V12 VNSTOCK-ONLY NO-GLOBAL-CIRCUIT + PER-CALL WATCHDOG TEST PASS")
