import math

from v12_corporate_actions import (
    UPCOM_MAX_DOWN_ABS_LOG_RETURN,
    UPCOM_MAX_UP_LOG_RETURN,
    reconcile_vnstock_with_yahoo,
)

GUARD = 0.12
MAD = 0.003


def row(date, close, model_close=None):
    z = {"date": date, "open": close, "high": close, "low": close, "close": close, "volume": 1.0}
    if model_close is not None:
        z["modelClose"] = model_close
    return z


def run(vn, yh, secondary=None, known_ca_dates=None, symbol=None):
    return reconcile_vnstock_with_yahoo(
        vn, yh, max_return_guard=GUARD, cross_source_limit=MAD,
        raw_reference_rows=secondary, known_ca_dates=known_ca_dates,
        symbol=symbol,
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

    # +14% is above the unchanged 0.12 V12 base guard but inside UPCOM's +15% band.
    adjusted, a = run(
        [row("2023-06-01", 100), row("2023-06-02", 114)],
        [], symbol="ADP",
    )
    ret = math.log(adjusted[1]["modelClose"] / adjusted[0]["modelClose"])
    assert abs(ret - math.log(1.14)) < 1e-12, (ret, a)
    assert a["verified"] is True, a
    assert a["historicalVenueTransitionDate"] == "2023-07-18", a
    assert a["venueAwareGuardIntervalCount"] == 1, a
    assert a["preTransferVenueUpLogGuard"] >= UPCOM_MAX_UP_LOG_RETURN - 1e-12, a
    assert a["preTransferVenueDownAbsLogGuard"] >= UPCOM_MAX_DOWN_ABS_LOG_RETURN - 1e-12, a

    # -15% is also legal pre-transfer; the negative log bound is wider than the positive one.
    adjusted, a = run(
        [row("2023-06-01", 100), row("2023-06-02", 85)],
        [], symbol="ADP",
    )
    ret = math.log(adjusted[1]["modelClose"] / adjusted[0]["modelClose"])
    assert abs(ret - math.log(.85)) < 1e-12 and a["verified"] is True, (ret, a)

    # +16% is beyond UPCOM's +15% band even though a symmetric absolute guard could hide it.
    _, a = run(
        [row("2023-06-01", 100), row("2023-06-02", 116)],
        [], symbol="ADP",
    )
    assert a["verified"] is False and a["ordinaryLargeMoveViolations"] == 1, a

    # The exact same +14% move after ADP is on HOSE remains above the unchanged base guard.
    _, a = run(
        [row("2023-07-18", 100), row("2023-07-19", 114)],
        [], symbol="ADP",
    )
    assert a["verified"] is False and a["ordinaryLargeMoveViolations"] == 1, a
    assert a["venueAwareGuardIntervalCount"] == 0, a

    # Unknown/current-HOSE names never inherit the UPCOM rule.
    _, a = run(
        [row("2023-06-01", 100), row("2023-06-02", 114)],
        [], symbol="FPT",
    )
    assert a["verified"] is False and a["ordinaryLargeMoveViolations"] == 1, a

    # A move far beyond the UPCOM band remains fail-safe and exposes its complete break date.
    _, a = run(
        [row("2023-06-01", 100), row("2023-06-02", 75)],
        [], symbol="ADP",
    )
    assert a["verified"] is False and a["ordinaryLargeMoveViolations"] == 1, a
    assert a["unresolvedBreakDates"] == ["2023-06-02"], a

    # Current policy preserves known-event returns when inside the active venue limits.
    adjusted, a = run(
        [row("2023-03-01", 100), row("2023-03-02", 87)],
        [], known_ca_dates={"2023-03-02"}, symbol="ADP",
    )
    ret = math.log(adjusted[1]["modelClose"] / adjusted[0]["modelClose"])
    assert abs(ret - math.log(.87)) < 1e-12 and a["verified"] is True, (ret, a)
    assert a["smoothEventPrimaryPreserved"] == 1, a
    assert a["eventResidualViolations"] == 0, a

    print("V12 CORPORATE-ACTION VENUE-AWARE SAFE RETURN-SPLICE TEST PASS")


if __name__ == "__main__":
    main()
