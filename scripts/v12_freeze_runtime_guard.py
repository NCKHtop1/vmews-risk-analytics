"""Bounded runtime guard for the V12 frozen-source capture.

This module changes transport/runtime behavior only. It does not change prices,
returns, eligibility rules, corporate-action rules, or scientific gate thresholds.

Goals:
- every VNStock network call is bounded by a per-call timeout;
- every symbol has an end-to-end wall-clock budget shared by all recovery calls;
- VNStock universe discovery is also bounded;
- current-HOSE symbols are attempted before optional historical candidates;
- progress is persisted after every symbol so a timeout leaves exact evidence;
- no full-symbol "clean second pass" is performed after local call retries have
  already been exhausted.
"""
import json
import os
import pathlib
import signal
import time


_DEFAULT_SYMBOL_BUDGET_SECONDS = 45.0
_DEFAULT_UNIVERSE_BUDGET_SECONDS = 20.0
_DEFAULT_CAPTURE_BUDGET_SECONDS = 140.0 * 60.0

_CURRENT_DEADLINE = [None]
_PROGRESS_PATH = [None]


def _seconds(name, default, floor=0.05):
    try:
        return max(floor, float(os.environ.get(name, default)))
    except Exception:
        return float(default)


def _remaining():
    deadline = _CURRENT_DEADLINE[0]
    if deadline is None:
        return None
    return deadline - time.monotonic()


class _deadline:
    def __init__(self, seconds):
        self.seconds = float(seconds)
        self.previous = None

    def __enter__(self):
        self.previous = _CURRENT_DEADLINE[0]
        proposed = time.monotonic() + self.seconds
        if self.previous is None:
            _CURRENT_DEADLINE[0] = proposed
        else:
            _CURRENT_DEADLINE[0] = min(self.previous, proposed)
        return _CURRENT_DEADLINE[0]

    def __exit__(self, exc_type, exc, tb):
        _CURRENT_DEADLINE[0] = self.previous
        return False


def _atomic_json(path, payload):
    if path is None:
        return
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    tmp.replace(path)


def _budgeted_call(rr, label, fn, *args, **kwargs):
    """Drop-in replacement for v12_reference_resilience._call_with_timeout.

    It honors the smaller of the configured per-call timeout and the active
    symbol/universe deadline. Previous SIGALRM timers are restored with elapsed
    time deducted, avoiding deadline extension under nested watchdogs.
    """
    per_call = float(rr._network_timeout_seconds())
    remaining = _remaining()
    if remaining is not None:
        if remaining <= 0.0:
            raise TimeoutError(f"{label}: symbol_or_stage_budget_exhausted")
        seconds = min(per_call, max(0.05, remaining))
    else:
        seconds = per_call

    if not hasattr(signal, "SIGALRM") or not hasattr(signal, "setitimer"):
        return fn(*args, **kwargs)

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()

    def _alarm(_signum, _frame):
        reason = (
            "symbol_or_stage_budget_exhausted"
            if remaining is not None and seconds + 1e-6 < per_call
            else f"network_call_timeout>{seconds:.1f}s"
        )
        raise TimeoutError(f"{label}: {reason}")

    signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return fn(*args, **kwargs)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer and previous_timer[0] > 0:
            elapsed = max(0.0, time.monotonic() - started)
            restored = max(0.0, previous_timer[0] - elapsed)
            if restored > 0:
                signal.setitimer(
                    signal.ITIMER_REAL,
                    restored,
                    previous_timer[1],
                )


def install(capture, universe, rr, repo_root=None):
    if getattr(capture, "_V12_FREEZE_RUNTIME_GUARD_INSTALLED", False):
        return dict(capture._V12_FREEZE_RUNTIME_GUARD_AUDIT)

    root = pathlib.Path(repo_root or pathlib.Path(__file__).resolve().parents[1])
    progress_path = root / "data" / "v12-source-freeze-progress.json"
    _PROGRESS_PATH[0] = progress_path

    symbol_budget = _seconds(
        "V12_SYMBOL_WALL_BUDGET",
        _DEFAULT_SYMBOL_BUDGET_SECONDS,
        floor=5.0,
    )
    universe_budget = _seconds(
        "V12_UNIVERSE_WALL_BUDGET",
        _DEFAULT_UNIVERSE_BUDGET_SECONDS,
        floor=5.0,
    )
    capture_budget = _seconds(
        "V12_CAPTURE_WALL_BUDGET",
        _DEFAULT_CAPTURE_BUDGET_SECONDS,
        floor=60.0,
    )

    rr._call_with_timeout = lambda label, fn, *a, **kw: _budgeted_call(
        rr, label, fn, *a, **kw
    )

    original_discover = universe.discover_vnstock_reference

    def discover_vnstock_reference():
        attempts = []
        for i in range(2):
            try:
                with _deadline(universe_budget):
                    out, audit = rr._call_with_timeout(
                        "VNSTOCK_UNIVERSE_DISCOVERY",
                        original_discover,
                    )
                audit = dict(audit or {})
                if audit.get("error"):
                    raise RuntimeError(str(audit["error"]))
                audit["boundedRuntime"] = {
                    "status": "PASS",
                    "wallBudgetSeconds": universe_budget,
                    "attempts": i + 1,
                }
                return out, audit
            except BaseException as exc:
                error = f"{type(exc).__name__}: {exc}"[:700]
                attempts.append({
                    "attempt": i + 1,
                    "error": error,
                    "transient": bool(rr._transient(error)),
                })
                if not rr._transient(error) or i == 1:
                    return {}, {
                        "error": error,
                        "boundedRuntime": {
                            "status": "FAIL",
                            "wallBudgetSeconds": universe_budget,
                            "attempts": attempts,
                        },
                    }
                time.sleep(2.0)
        return {}, {
            "error": "VNStock universe discovery exhausted bounded attempts",
            "boundedRuntime": {
                "status": "FAIL",
                "wallBudgetSeconds": universe_budget,
                "attempts": attempts,
            },
        }

    universe.discover_vnstock_reference = discover_vnstock_reference

    def _failure(symbol, exc, attempts=None, stage="SOURCE_CAPTURE"):
        return {
            "error": f"{type(exc).__name__}: {exc}"[:900],
            "attempts": list(attempts or []) + [{
                "stage": stage,
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}"[:700],
                "symbolWallBudgetSeconds": symbol_budget,
            }],
        }

    def _snapshot_progress(
        ordered,
        index,
        store,
        audits,
        failures,
        started,
        *,
        last_symbol=None,
        phase="CAPTURE",
    ):
        eligible = sum((a or {}).get("eligible") is True for a in audits.values())
        deep = sum(len(rows) >= capture.base.MIN_ROWS for rows in store.values())
        payload = {
            "version": "VMEWS-V12-SOURCE-FREEZE-PROGRESS-1.0.0",
            "phase": phase,
            "processed": int(index),
            "total": len(ordered),
            "remaining": max(0, len(ordered) - int(index)),
            "lastSymbol": last_symbol,
            "captured": len(store),
            "failed": len(failures),
            "deep": int(deep),
            "eligible": int(eligible),
            "elapsedSeconds": round(time.monotonic() - started, 3),
            "symbolWallBudgetSeconds": symbol_budget,
            "captureWallBudgetSeconds": capture_budget,
            "recentFailures": {
                k: failures[k] for k in list(failures)[-8:]
            },
        }
        _atomic_json(progress_path, payload)
        print(json.dumps({"v12SourceFreezeProgress": payload}, ensure_ascii=False), flush=True)

    def build_source_capture_store(symbols):
        started = time.monotonic()
        current = set(universe.current_hose_symbols())
        ordered = sorted([s for s in symbols if s in current]) + sorted(
            [s for s in symbols if s not in current]
        )
        anchors = [s for s in ("FPT", "VCB", "HPG") if s in set(ordered)]
        preflight = {}
        success = 0
        start, end = capture.base._history_window(8)

        for symbol in anchors:
            attempts = []
            try:
                with _deadline(symbol_budget):
                    route = capture._capture_unified(
                        symbol, 8, attempts, "VNSTOCK_PREFLIGHT_UNIFIED"
                    )
                    if route is None:
                        route = capture._capture_provider(
                            symbol,
                            "VCI",
                            start,
                            end,
                            attempts,
                            "VNSTOCK_PREFLIGHT_VCI",
                        )
                    if route is None:
                        route = capture._capture_provider(
                            symbol,
                            "KBS",
                            start,
                            end,
                            attempts,
                            "VNSTOCK_PREFLIGHT_KBS",
                        )
                ok = route is not None
            except BaseException as exc:
                attempts.append({
                    "stage": "VNSTOCK_PREFLIGHT_SYMBOL_BUDGET",
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}"[:700],
                })
                ok = False
            success += int(ok)
            preflight[symbol] = {"ok": ok, "attempts": attempts}

        required = min(2, len(anchors))
        if anchors and success < required:
            failure = {
                "__VNSTOCK_PREFLIGHT__": {
                    "error": (
                        f"VNStock preflight failed: "
                        f"{success}/{len(anchors)} anchors reachable"
                    ),
                    "attempts": [
                        x
                        for item in preflight.values()
                        for x in item.get("attempts", [])
                    ],
                    "anchors": preflight,
                    "symbolWallBudgetSeconds": symbol_budget,
                }
            }
            _snapshot_progress(
                ordered, 0, {}, {}, failure, started,
                phase="PREFLIGHT_FAIL",
            )
            return {}, {}, failure

        store = {}
        audits = {}
        failures = {}
        _snapshot_progress(
            ordered, 0, store, audits, failures, started,
            phase="CAPTURE_START",
        )

        for i, symbol in enumerate(ordered, 1):
            elapsed = time.monotonic() - started
            if elapsed >= capture_budget:
                failures["__CAPTURE_WALL_BUDGET__"] = {
                    "error": (
                        f"capture wall budget exhausted after "
                        f"{elapsed:.1f}s at {i-1}/{len(ordered)} symbols"
                    ),
                    "attempts": [{
                        "stage": "CAPTURE_WALL_BUDGET",
                        "ok": False,
                        "elapsedSeconds": elapsed,
                        "budgetSeconds": capture_budget,
                    }],
                }
                _snapshot_progress(
                    ordered,
                    i - 1,
                    store,
                    audits,
                    failures,
                    started,
                    last_symbol=symbol,
                    phase="CAPTURE_BUDGET_EXHAUSTED",
                )
                break

            try:
                with _deadline(symbol_budget):
                    rows, audit = capture.capture_price_history(symbol)
                store[symbol] = rows
                audits[symbol] = audit
            except capture.SourceCaptureError as exc:
                failures[symbol] = _failure(
                    symbol,
                    exc,
                    exc.attempts,
                    "SOURCE_CAPTURE_ERROR",
                )
            except BaseException as exc:
                failures[symbol] = _failure(
                    symbol,
                    exc,
                    [],
                    "SOURCE_SYMBOL_WALL_BUDGET"
                    if "budget" in str(exc).lower()
                    else "SOURCE_CAPTURE_EXCEPTION",
                )

            _snapshot_progress(
                ordered,
                i,
                store,
                audits,
                failures,
                started,
                last_symbol=symbol,
                phase="CAPTURE",
            )

        return store, audits, failures

    capture.build_source_capture_store = build_source_capture_store

    audit = {
        "version": "VMEWS-V12-FREEZE-RUNTIME-GUARD-1.0.0",
        "networkWatchdogSharedDeadlineAware": True,
        "symbolWallBudgetSeconds": symbol_budget,
        "universeWallBudgetSeconds": universe_budget,
        "captureWallBudgetSeconds": capture_budget,
        "currentHOSEFirst": True,
        "progressCheckpoint": str(progress_path.relative_to(root)),
        "fullSymbolSecondPass": False,
        "localTransientRetriesRemainEnabled": True,
        "priceOrReturnMutation": False,
        "gateMutation": False,
    }
    capture._V12_FREEZE_RUNTIME_GUARD_INSTALLED = True
    capture._V12_FREEZE_RUNTIME_GUARD_AUDIT = audit
    return dict(audit)
