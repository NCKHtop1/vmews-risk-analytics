import math

from v12_corporate_actions import reconcile_vnstock_with_yahoo

GUARD = 0.12
MAD = 0.003


def row(date, close, model_close=None):
    z = {"date": date, "open": close, "high": close, "low": close, "close": close, "volume": 1.0}
    if model_close is not None:
        z["modelClose"] = model_close
    return z


def run(vn, yh):
    return reconcile_vnstock_with_yahoo(vn, yh, max_return_guard=GUARD, cross_source_limit=MAD)


def main():
    # Legitimate >12% ordinary move: raw source consensus must preserve it.
    _, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 125)],
        [row("2026-01-01", 100, 100), row("2026-01-02", 125, 125)],
    )
    assert a["verified"] and a["ordinaryLargeMoveEvents"] == 1 and a["ordinaryLargeMoveViolations"] == 0, a

    # Sparse VNStock A->C must compare with Yahoo A->C, not Yahoo B->C.
    _, a = run(
        [row("2026-01-01", 100), row("2026-01-03", 130)],
        [row("2026-01-01", 100, 100), row("2026-01-02", 110, 110), row("2026-01-03", 130, 130)],
    )
    assert a["verified"] and a["ordinaryLargeMoveEvents"] == 1 and a["ordinaryLargeMoveViolations"] == 0, a

    # True 2:1 split: adjustment factor neutralizes the raw discontinuity.
    adjusted, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 50)],
        [row("2026-01-01", 100, 50), row("2026-01-02", 50, 50)],
    )
    ret = math.log(adjusted[1]["modelClose"] / adjusted[0]["modelClose"])
    assert abs(ret) < 1e-12 and a["verified"] and a["factorChangeEvents"] == 1 and a["eventResidualViolations"] == 0, (ret, a)

    # VNStock fails to reflect the same split: adjusted residual remains too large.
    _, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 100)],
        [row("2026-01-01", 100, 50), row("2026-01-02", 50, 50)],
    )
    assert not a["verified"] and a["eventResidualViolations"] == 1, a

    # Isolated VNStock spike is not hidden by median cross-source MAD.
    _, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 130)],
        [row("2026-01-01", 100, 100), row("2026-01-02", 100, 100)],
    )
    assert not a["verified"] and a["ordinaryLargeMoveEvents"] == 1 and a["ordinaryLargeMoveViolations"] == 1, a

    # Without an adjustment/reference source, the >12% guard remains fail-safe.
    _, a = run([row("2026-01-01", 100), row("2026-01-02", 130)], [])
    assert not a["verified"] and a["ordinaryLargeMoveViolations"] == 1, a

    print("V12 CORPORATE-ACTION RECONCILIATION TEST PASS")


if __name__ == "__main__":
    main()
