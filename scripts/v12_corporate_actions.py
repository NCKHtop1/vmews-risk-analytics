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
    """Apply Yahoo adjustment factors to VNStock raw closes and verify CA boundaries.

    Corporate-action verification is deliberately scoped to dates where the Yahoo
    adjustment factor changes. A large ordinary market move is not, by itself, a
    corporate-action failure. At a factor-change boundary, an adjusted jump above
    the guard is accepted only when Yahoo adjusted returns corroborate it within
    the existing cross-source tolerance.
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
            "verificationScope": "NO_ADJUSTMENT_REFERENCE_RAW_GUARD",
        }

    factors = {}
    yahoo_adjusted_rows = []
    for row in yahoo_rows:
        raw = _finite(row.get("close"))
        adjusted = _finite(row.get("modelClose", row.get("adjClose")))
        date = str(row.get("date", ""))[:10]
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
    factor_events = []
    violations = []
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
            if abs(factor_log_change) > FACTOR_EVENT_LOG_EPS:
                model_return = math.log(model_close / prev["modelClose"])
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
                    violations.append(event)
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
    if factor_events:
        largest_factor_change = max(
            factor_events, key=lambda event: abs(event["factorLogChange"])
        )
        largest_event_model_jump = max(
            factor_events, key=lambda event: abs(event["modelLogReturn"])
        )

    return out, {
        "method": "VNSTOCK_RAW_YAHOO_CORPORATE_ACTION_FACTOR_EVENT_BOUNDARY",
        "verified": len(violations) == 0,
        "largestRawLogJump": raw_jump,
        "largestRawJumpDate": raw_jump_date,
        "largestModelLogJump": model_jump,
        "largestModelJumpDate": model_jump_date,
        "factorDates": len(factors),
        "factorChangeEvents": len(factor_events),
        "eventResidualViolations": len(violations),
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
        "verificationScope": (
            "FACTOR_CHANGE_BOUNDARIES; LARGE_EVENT_RESIDUAL_REQUIRES_"
            "YAHOO_ADJUSTED_CORROBORATION"
        ),
        "violations": violations[:10],
    }
