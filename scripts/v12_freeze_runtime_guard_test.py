import json
import os
import pathlib
import tempfile
import time
from types import SimpleNamespace

import v12_freeze_runtime_guard as guard


class FakeRR:
    def _network_timeout_seconds(self):
        return 1.0

    @staticmethod
    def _transient(value):
        return "timeout" in str(value).lower()


def test_shared_deadline_watchdog():
    rr = FakeRR()
    started = time.monotonic()
    try:
        with guard._deadline(0.08):
            guard._budgeted_call(rr, "TEST", time.sleep, 0.5)
        raise AssertionError("expected timeout")
    except TimeoutError as exc:
        assert "TEST" in str(exc)
    elapsed = time.monotonic() - started
    assert elapsed < 0.30, elapsed


def test_current_first_single_pass_and_progress():
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / "data").mkdir()
        order = []

        class SourceCaptureError(RuntimeError):
            def __init__(self, symbol, attempts):
                self.symbol = symbol
                self.attempts = attempts
                super().__init__(symbol)

        class Base:
            MIN_ROWS = 2

            @staticmethod
            def _history_window(years):
                return "2020-01-01", "2026-01-01"

        def preflight(symbol, years, attempts, stage):
            attempts.append({"stage": stage, "ok": True})
            return ([{"date": "2026-01-01", "close": 1}], {"providerCode": "UNIFIED"})

        def provider(symbol, source, start, end, attempts, stage):
            raise AssertionError("provider fallback not expected")

        def capture_price_history(symbol):
            order.append(symbol)
            rows = [
                {"date": "2026-01-01", "close": 1},
                {"date": "2026-01-02", "close": 1},
            ]
            return rows, {
                "eligible": True,
                "route": "TEST",
                "corporateAction": {"verified": True},
                "attempts": [{"stage": "VNSTOCK_PRIMARY", "ok": True}],
            }

        capture = SimpleNamespace(
            base=Base(),
            SourceCaptureError=SourceCaptureError,
            _capture_unified=preflight,
            _capture_provider=provider,
            capture_price_history=capture_price_history,
        )

        universe = SimpleNamespace()
        universe.current_hose_symbols = lambda: {"A", "B", "FPT", "VCB"}
        universe.discover_vnstock_reference = lambda: ({}, {"rows": 0})

        rr = FakeRR()
        rr._call_with_timeout = lambda label, fn, *a, **kw: fn(*a, **kw)

        old = {
            "V12_SYMBOL_WALL_BUDGET": os.environ.get("V12_SYMBOL_WALL_BUDGET"),
            "V12_UNIVERSE_WALL_BUDGET": os.environ.get("V12_UNIVERSE_WALL_BUDGET"),
            "V12_CAPTURE_WALL_BUDGET": os.environ.get("V12_CAPTURE_WALL_BUDGET"),
        }
        os.environ["V12_SYMBOL_WALL_BUDGET"] = "5"
        os.environ["V12_UNIVERSE_WALL_BUDGET"] = "5"
        os.environ["V12_CAPTURE_WALL_BUDGET"] = "60"
        try:
            audit = guard.install(capture, universe, rr, repo_root=root)
            store, audits, failures = capture.build_source_capture_store(
                ["HIST", "B", "A", "VCB", "FPT"]
            )
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        assert not failures, failures
        assert order == ["A", "B", "FPT", "VCB", "HIST"], order
        assert set(store) == set(order)
        assert audit["fullSymbolSecondPass"] is False
        progress = json.loads(
            (root / "data" / "v12-source-freeze-progress.json").read_text(
                encoding="utf-8"
            )
        )
        assert progress["processed"] == 5
        assert progress["captured"] == 5
        assert progress["eligible"] == 5


if __name__ == "__main__":
    test_shared_deadline_watchdog()
    test_current_first_single_pass_and_progress()
    print("V12 FREEZE RUNTIME GUARD TEST PASS")
