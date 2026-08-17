import bisect
import math

FACTOR_EVENT_LOG_EPS = 1e-7


def _finite(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _raw_log_returns(rows):
    out = {}
    prev = None
    for row in rows:
        close = _finite(row.get("close"))
        if close is None or close <= 0:
            continue
        date = str(row.get("date", ""))[:10]
        if prev is not None and prev[1] > 0 and date:
            out[date] = math.log(close / prev[1])
        prev = (date, close)
    return out


def _largest_jump(rows):
    returns = _raw_log_returns(rows)
    if not returns:
        return 0.0, None
    date, value = max(returns.items(), key=lambda kv: abs(kv[1]))
    return abs(float(value)), date


def reconcile_vnstock_with_yahoo(
    vn_rows,
    yahoo_rows,
    *,
    max_return_guard,
    cross_source_limit,
):
    """Reconcile VNStock raw closes with an audited Yahoo adjustment reference.

    The >guard check has two distinct meanings and neither lowers the existing gate:
    1) at Yahoo adjustment-factor boundaries, a large adjusted residual must be
       corroborated by Yahoo adjusted returns;
    2) away from a factor boundary, a large VNStock raw move must be corroborated
       by Yahoo raw returns.

    This prevents ordinary legitimate moves from being mislabeled as corporate-action
    failures while still rejecting isolated source spikes that a median MAD statistic
    could otherwise hide.
    """
    if not yahoo_rows:
        out = [
            {**row, "modelClose": row["close"], "adjustmentFactor": 1.0}
            for row in vn_rows
        ]
        jump, jump_date = _largest_jump(out)
        return out, {
            "method": "VNSTOCK_RAW_NO_ADJUSTMENT_REFERENCE",
            "verified": jump <= max_return_guard,
            "largestRawLogJump": jump,
            "largestRawJumpDate": jump_date,
            "factorDates": 0,
            "factorChangeEvents": 0,
            "eventResidualViolations": 0,
            "ordinaryLargeMoveEvents": int(jump > max_return_guard),
            "ordinaryLargeMoveViolations": int(jump > max_return_guard),
            "verificationScope": "NO_ADJUSTMENT_REFERENCE_RAW_GUARD",
        }

    factors = {}
    yahoo_adjusted_rows = []
    yahoo_raw_rows = []
    for row in yahoo_rows:
        raw = _finite(row.get("close"))
        adjusted = _finite(row.get("modelClose", row.get("adjClose")))
        date = str(row.get("date", ""))[:10]
        if date and raw is not None and raw > 0:
            yahoo_raw_rows.append({"date": date, "close": raw})
        if date and raw is not None and raw > 0 and adjusted is not None and adjusted > 0:
            factors[date] = adjusted / raw
            yahoo_adjusted_rows.append({"date": date, "close": adjusted})

    if not factors:
        return reconcile_vnstock_with_yahoo(
            vn_rows,
            [],
            max_return_guard=max_return_guard,
            cross_source_limit=cross_source_limit,
        )

    factor_dates = sorted(factors)
    out = []
    for row in vn_rows:
        date = str(row.get("date", ""))[:10]
        if date in factors:
            factor = factors[date]
        else:
            idx = bisect.bisect_right(factor_dates, date) - 1
            factor = factors[factor_dates[0]] if idx < 0 else factors[factor_dates[idx]]
        factor = factor if math.isfinite(factor) and factor > 0 else 1.0
        out.append(
            {
                **row,
                "modelClose": row["close"] * factor,
                "adjustmentFactor": factor,
            }
        )

    yahoo_adjusted_returns = _raw_log_returns(yahoo_adjusted_rows)
    yahoo_raw_returns = _raw_log_returns(yahoo_raw_rows)
    factor_events = []
    ca_violations = []
    ordinary_large_events = []
    ordinary_violations = []
    prev = None

    for row in out:
        raw_close = _finite(row.get("close"))
        model_close = _finite(row.get("modelClose"))
        factor = _finite(row.get("adjustmentFactor"))
        date = str(row.get("date", ""))[:10]
        if (
            prev is not None
            and raw_close is not None
            and raw_close > 0
            and model_close is not None
            and model_close > 0
            and factor is not None
            and factor > 0
            and prev["rawClose"] > 0
            and prev["modelClose"] > 0
            and prev["factor"] > 0
        ):
            factor_log_change = math.log(factor / prev["factor"])
            raw_return = math.log(raw_close / prev["rawClose"])
            model_return = math.log(model_close / prev["modelClose"])

            if abs(factor_log_change) > FACTOR_EVENT_LOG_EPS:
                yahoo_return = yahoo_adjusted_returns.get(date)
                corroborated = (
                    yahoo_return is not None
                    and math.isfinite(yahoo_return)
                    and abs(model_return - yahoo_return) <= cross_source_limit
                )
                event = {
                    "date": date,
                    "factorLogChange": factor_log_change,
                    "modelLogReturn": model_return,
                    "yahooAdjustedLogReturn": yahoo_return,
                    "yahooCorroborated": corroborated,
                }
                factor_events.append(event)
                if abs(model_return) > max_return_guard and not corroborated:
                    ca_violations.append(event)
            elif abs(raw_return) > max_return_guard:
                yahoo_return = yahoo_raw_returns.get(date)
                corroborated = (
                    yahoo_return is not None
                    and math.isfinite(yahoo_return)
                    and abs(raw_return - yahoo_return) <= cross_source_limit
                )
                event = {
                    "date": date,
                    "rawLogReturn": raw_return,
                    "yahooRawLogReturn": yahoo_return,
                    "yahooCorroborated": corroborated,
                }
                ordinary_large_events.append(event)
                if not corroborated:
                    ordinary_violations.append(event)

        prev = {
            "rawClose": raw_close or 0.0,
            "modelClose": model_close or 0.0,
            "factor": factor or 0.0,
        }

    raw_jump, raw_jump_date = _largest_jump(vn_rows)
    model_jump, model_jump_date = _largest_jump(
        [{**row, "close": row["modelClose"]} for row in out]
    )

    largest_factor_change = None
    largest_event_model_jump = None
    largest_ordinary_raw_jump = None
    if factor_events:
        largest_factor_change = max(
            factor_events, key=lambda event: abs(event["factorLogChange"])
        )
        largest_event_model_jump = max(
            factor_events, key=lambda event: abs(event["modelLogReturn"])
        )
    if ordinary_large_events:
        largest_ordinary_raw_jump = max(
            ordinary_large_events, key=lambda event: abs(event["rawLogReturn"])
        )

    verified = not ca_violations and not ordinary_violations
    return out, {
        "method": "VNSTOCK_RAW_YAHOO_EVENT_BOUNDARY_AND_RAW_OUTLIER_RECONCILIATION",
        "verified": verified,
        "largestRawLogJump": raw_jump,
        "largestRawJumpDate": raw_jump_date,
        "largestModelLogJump": model_jump,
        "largestModelJumpDate": model_jump_date,
        "factorDates": len(factors),
        "factorChangeEvents": len(factor_events),
        "eventResidualViolations": len(ca_violations),
        "ordinaryLargeMoveEvents": len(ordinary_large_events),
        "ordinaryLargeMoveViolations": len(ordinary_violations),
        "largestFactorLogChange": (
            abs(largest_factor_change["factorLogChange"])
            if largest_factor_change
            else 0.0
        ),
        "largestFactorChangeDate": (
            largest_factor_change["date"] if largest_factor_change else None
        ),
        "largestEventModelLogJump": (
            abs(largest_event_model_jump["modelLogReturn"])
            if largest_event_model_jump
            else 0.0
        ),
        "largestEventModelJumpDate": (
            largest_event_model_jump["date"] if largest_event_model_jump else None
        ),
        "largestOrdinaryRawLogJump": (
            abs(largest_ordinary_raw_jump["rawLogReturn"])
            if largest_ordinary_raw_jump
            else 0.0
        ),
        "largestOrdinaryRawJumpDate": (
            largest_ordinary_raw_jump["date"] if largest_ordinary_raw_jump else None
        ),
        "verificationScope": (
            "FACTOR_CHANGE_BOUNDARIES_USE_YAHOO_ADJUSTED_RETURN;"
            "NON_FACTOR_LARGE_RAW_MOVES_USE_YAHOO_RAW_RETURN"
        ),
        "corporateActionViolations": ca_violations[:10],
        "ordinaryMoveViolations": ordinary_violations[:10],
    }
