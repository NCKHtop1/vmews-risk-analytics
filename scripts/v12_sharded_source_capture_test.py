import copy
import v12_sharded_source_capture as s


def _rows(symbol, end="2026-08-18"):
    return [
        {"date": "2026-08-17", "open": 10, "high": 11, "low": 9, "close": 10, "modelClose": 10, "volume": 100, "adjustmentFactor": 1},
        {"date": end, "open": 10, "high": 12, "low": 9, "close": 11, "modelClose": 11, "volume": 120, "adjustmentFactor": 1},
    ]


def _audit(symbol):
    return {
        "symbol": symbol,
        "runtimeSourcePolicy": "VNSTOCK_ONLY_NO_YAHOO_NO_GLOBAL_CIRCUIT",
        "adjustmentReference": {"networkCall": False, "source": "DISABLED"},
        "eligible": True,
        "corporateAction": {"verified": True},
        "attempts": [{"stage": "VNSTOCK_PRIMARY", "ok": True}],
    }


def _plan():
    p = {
        "policyVersion": s.POLICY_VERSION,
        "sourceTriggerSha": "a" * 40,
        "runtimeScriptsTreeSha": "b" * 40,
        "workflowSha256": "c" * 64,
        "targetAsOfHint": "2026-08-18",
        "shardCount": 2,
        "currentHOSESymbols": ["AAA", "BBB", "CCC"],
        "historicalCandidates": {"DDD": {"formerExchange": "HOSE"}},
        "requestedSymbols": ["AAA", "BBB", "CCC", "DDD"],
        "assignments": {"0": ["AAA", "CCC"], "1": ["BBB", "DDD"]},
    }
    p["planFingerprint"] = s._sha({
        "policyVersion": p["policyVersion"],
        "runtimeScriptsTreeSha": p["runtimeScriptsTreeSha"],
        "workflowSha256": p["workflowSha256"],
        "targetAsOfHint": p["targetAsOfHint"],
        "shardCount": p["shardCount"],
        "currentHOSESymbols": p["currentHOSESymbols"],
        "historicalCandidates": p["historicalCandidates"],
        "assignments": p["assignments"],
    })
    return p


def _checkpoint(plan, shard, symbols):
    cp = s._new_checkpoint(plan, shard)
    for sym in symbols:
        rows = _rows(sym)
        cp["entries"][sym] = {
            "rows": rows,
            "audit": _audit(sym),
            "sha256": s.row_fingerprint(rows),
            "capturedAt": "2026-08-18T13:00:00+00:00",
        }
    return cp


def test_assignment_deterministic_unique():
    a = s._assignment(["CCC", "AAA", "BBB"], ["EEE", "DDD"], 3)
    b = s._assignment(["AAA", "BBB", "CCC"], ["DDD", "EEE"], 3)
    assert a == b
    flat = [x for values in a.values() for x in values]
    assert len(flat) == len(set(flat)) == 5


def test_resume_and_stale_checkpoint_rejection():
    plan = _plan()
    cp = _checkpoint(plan, 0, ["AAA"])
    ok, reason = s.validate_checkpoint(cp, plan, 0)
    assert ok, reason
    pending = [x for x in plan["assignments"]["0"] if x not in cp["entries"]]
    assert pending == ["CCC"]
    stale = copy.deepcopy(cp)
    stale["runtimeScriptsTreeSha"] = "z" * 40
    ok, reason = s.validate_checkpoint(stale, plan, 0)
    assert not ok and reason == "runtimeScriptsTreeSha_mismatch"
    stale = copy.deepcopy(cp)
    stale["targetAsOfHint"] = "2026-08-17"
    ok, reason = s.validate_checkpoint(stale, plan, 0)
    assert not ok and reason == "targetAsOfHint_mismatch"


def test_tamper_and_yahoo_network_rejected():
    plan = _plan()
    cp = _checkpoint(plan, 0, ["AAA"])
    cp["entries"]["AAA"]["rows"][0]["close"] = 999
    ok, reason = s.validate_checkpoint(cp, plan, 0)
    assert not ok and "row_fingerprint_mismatch" in reason
    cp = _checkpoint(plan, 0, ["AAA"])
    cp["entries"]["AAA"]["audit"]["adjustmentReference"]["networkCall"] = True
    ok, reason = s.validate_checkpoint(cp, plan, 0)
    assert not ok and "yahoo_network_reference_forbidden" in reason


def test_merge_failure_isolation_and_idempotence():
    plan = _plan()
    cp0 = _checkpoint(plan, 0, ["AAA", "CCC"])
    cp1 = _checkpoint(plan, 1, ["BBB"])
    cp1["failures"]["DDD"] = {
        "error": "timeout",
        "attempts": [{"stage": "VNSTOCK_PRIMARY", "ok": False}],
    }
    checkpoints = {
        0: (cp0, "PASS", "1" * 64),
        1: (cp1, "PASS", "2" * 64),
    }
    store, audits, failures, provenance = s.merge_checkpoints(plan, checkpoints)
    assert sorted(store) == ["AAA", "BBB", "CCC"]
    assert list(failures) == ["DDD"]
    assert audits["AAA"]["eligible"] is True
    first = s._sha({k: s.row_fingerprint(v) for k, v in sorted(store.items())})
    store2, _, failures2, _ = s.merge_checkpoints(
        plan, dict(reversed(list(checkpoints.items())))
    )
    second = s._sha({k: s.row_fingerprint(v) for k, v in sorted(store2.items())})
    assert first == second and failures2 == failures
    assert provenance["0"]["captured"] == 2


def test_exact_asof_normalization():
    store = {
        "AAA": _rows("AAA", "2026-08-18") + [{"date": "2026-08-19", "close": 12}],
        "BBB": _rows("BBB", "2026-08-18"),
        "CCC": _rows("CCC", "2026-08-18"),
    }
    assert s._modal_end(store, ["AAA", "BBB", "CCC"]) == "2026-08-18"
    normalized = s.normalize_store_to_asof(store, "2026-08-18")
    assert normalized["AAA"][-1]["date"] == "2026-08-18"
    assert normalized["BBB"][-1]["date"] == "2026-08-18"
    assert normalized["CCC"][-1]["date"] == "2026-08-18"


def main():
    test_assignment_deterministic_unique()
    test_resume_and_stale_checkpoint_rejection()
    test_tamper_and_yahoo_network_rejected()
    test_merge_failure_isolation_and_idempotence()
    test_exact_asof_normalization()
    print("V12 SHARDED RESUMABLE SOURCE CAPTURE TEST PASS")


if __name__ == "__main__":
    main()
