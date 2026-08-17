import math

from v12_corporate_actions import reconcile_vnstock_with_yahoo

GUARD = 0.12
MAD = 0.003


def row(date, close, model_close=None):
    z = {"date": date, "open": close, "high": close, "low": close, "close": close, "volume": 1.0}
    if model_close is not None:
        z["modelClose"] = model_close
    return z


def run(vn, yh, secondary=None, known_ca_dates=None):
    return reconcile_vnstock_with_yahoo(
        vn, yh, max_return_guard=GUARD, cross_source_limit=MAD,
        raw_reference_rows=secondary, known_ca_dates=known_ca_dates,
    )


def main():
    adjusted, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 105), row("2026-01-03", 106)],
        [row("2026-01-01", 100, 50), row("2026-01-02", 105, 105), row("2026-01-03", 106, 106)],
    )
    r1 = math.log(adjusted[1]["modelClose"] / adjusted[0]["modelClose"])
    assert abs(r1 - math.log(1.05)) < 1e-12, (r1, a)
    assert a["verified"] and a["largestModelLogJump"] <= GUARD, a
    assert a["smoothEventPrimaryPreserved"] >= 1, a

    adjusted, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 50)],
        [row("2026-01-01", 100, 50), row("2026-01-02", 50, 50)],
    )
    ret = math.log(adjusted[1]["modelClose"] / adjusted[0]["modelClose"])
    assert abs(ret) < 1e-12 and a["verified"], (ret, a)
    assert a["largeMoveAdjustedSplices"] == 1 and a["largestModelLogJump"] <= GUARD, a

    adjusted, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 70)],
        [row("2026-01-01", 100, 70), row("2026-01-02", 70, 70)],
    )
    ret = math.log(adjusted[1]["modelClose"] / adjusted[0]["modelClose"])
    assert abs(ret) < 1e-12 and a["verified"], (ret, a)

    adjusted, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 104)],
        [row("2026-01-01", 100, 80), row("2026-01-02", 104, 104)],
        None, {"2026-01-02"},
    )
    ret = math.log(adjusted[1]["modelClose"] / adjusted[0]["modelClose"])
    assert abs(ret - math.log(1.04)) < 1e-12 and a["verified"], (ret, a)

    _, a = run(
        [row("2020-01-01", 100), row("2020-01-02", 130)],
        [row("2026-01-01", 200, 200)],
        [row("2020-01-01", 1000), row("2020-01-02", 1300)],
    )
    assert not a["verified"] and a["ordinaryLargeMoveViolations"] == 1, a
    assert a["secondaryRouteCorroborations"] == 1, a

    _, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 70)],
        [], [row("2026-01-01", 100), row("2026-01-02", 70)], {"2026-01-02"},
    )
    assert not a["verified"] and a["eventResidualViolations"] == 1, a

    print("V12 CORPORATE-ACTION SAFE RETURN-SPLICE TEST PASS")


if __name__ == "__main__":
    main()
