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
        vn,
        yh,
        max_return_guard=GUARD,
        cross_source_limit=MAD,
        raw_reference_rows=secondary,
        known_ca_dates=known_ca_dates,
    )


def main():
    # Legitimate >12% ordinary move: Yahoo raw source consensus must preserve it.
    _, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 125)],
        [row("2026-01-01", 100, 100), row("2026-01-02", 125, 125)],
    )
    assert a["verified"] and a["ordinaryLargeMoveEvents"] == 1 and a["ordinaryLargeMoveViolations"] == 0, a
    assert a["yahooRawCorroborations"] == 1, a

    # Sparse VNStock A->C must compare with Yahoo A->C, not Yahoo B->C.
    _, a = run(
        [row("2026-01-01", 100), row("2026-01-03", 130)],
        [row("2026-01-01", 100, 100), row("2026-01-02", 110, 110), row("2026-01-03", 130, 130)],
    )
    assert a["verified"] and a["ordinaryLargeMoveEvents"] == 1 and a["ordinaryLargeMoveViolations"] == 0, a

    # True 2:1 split with matching raw conventions: event splice neutralizes the discontinuity.
    adjusted, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 50)],
        [row("2026-01-01", 100, 50), row("2026-01-02", 50, 50)],
    )
    ret = math.log(adjusted[1]["modelClose"] / adjusted[0]["modelClose"])
    assert abs(ret) < 1e-12 and a["verified"] and a["factorChangeEvents"] == 1 and a["eventResidualViolations"] == 0, (ret, a)

    # VNStock and Yahoo can encode the raw ex-right reference price differently.
    adjusted, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 70)],
        [row("2026-01-01", 100, 70), row("2026-01-02", 80, 70)],
    )
    ret = math.log(adjusted[1]["modelClose"] / adjusted[0]["modelClose"])
    assert abs(ret) < 1e-12 and a["verified"] and a["factorChangeEvents"] == 1 and a["eventResidualViolations"] == 0, (ret, a)

    # Isolated VNStock spike outside a CA boundary is not hidden by median cross-source MAD.
    _, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 130)],
        [row("2026-01-01", 100, 100), row("2026-01-02", 100, 100)],
    )
    assert not a["verified"] and a["ordinaryLargeMoveEvents"] == 1 and a["ordinaryLargeMoveViolations"] == 1, a

    # Without any quantitative raw reference, the >12% guard remains fail-safe.
    _, a = run([row("2026-01-01", 100), row("2026-01-02", 130)], [])
    assert not a["verified"] and a["ordinaryLargeMoveViolations"] == 1, a

    # If Yahoo lacks an old interval, a second captured VNStock route may corroborate
    # the identical raw endpoints. This validates the observed move; it does not adjust it.
    _, a = run(
        [row("2020-01-01", 100), row("2020-01-02", 130)],
        [row("2026-01-01", 200, 200)],
        [row("2020-01-01", 1000), row("2020-01-02", 1300)],
    )
    assert a["verified"] and a["secondaryRouteCorroborations"] == 1, a

    # Secondary route disagreement remains fail-safe.
    _, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 130)],
        [],
        [row("2026-01-01", 100), row("2026-01-02", 105)],
    )
    assert not a["verified"] and a["ordinaryLargeMoveViolations"] == 1, a

    # Raw-route consensus can never hide a known DIV/ISS event when no adjusted
    # return reference exists.
    _, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 70)],
        [],
        [row("2026-01-01", 100), row("2026-01-02", 70)],
        {"2026-01-02"},
    )
    assert not a["verified"] and a["eventResidualViolations"] == 1, a

    # A VCI-known event boundary can use Yahoo adjusted return even when Yahoo's
    # factor itself does not change. Event classification and quantitative adjustment
    # remain separate pieces of evidence.
    adjusted, a = run(
        [row("2026-01-01", 100), row("2026-01-02", 70)],
        [row("2026-01-01", 100, 100), row("2026-01-02", 70, 70)],
        None,
        {"2026-01-02"},
    )
    ret = math.log(adjusted[1]["modelClose"] / adjusted[0]["modelClose"])
    assert abs(ret - math.log(0.7)) < 1e-12 and a["verified"] and a["knownCorporateActionDates"] == 1, (ret, a)

    print("V12 CORPORATE-ACTION RETURN-SPLICE + SECONDARY-ROUTE TEST PASS")


if __name__ == "__main__":
    main()
