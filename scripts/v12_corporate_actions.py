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


def _interval_log_return(series, start_date, end_date):
    start = _finite(series.get(start_date))
    end = _finite(series.get(end_date))
    if start is None or end is None or start <= 0 or end <= 0:
        return None
    return math.log(end / start)


def reconcile_vnstock_with_yahoo(vn_rows, yahoo_rows, *, max_return_guard, cross_source_limit):
    """Reconcile VNStock with Yahoo using identical VNStock interval endpoints.

    For sparse names, a VNStock A->C return is compared with Yahoo A->C, never
    Yahoo B->C. Factor-change boundaries use adjusted-return corroboration;
    ordinary large moves use raw-return corroboration. Missing reference stays
    fail-safe and all scientific thresholds are preserved.
    """
    if not yahoo_rows:
        out = [{**row, "modelClose": row["close"], "adjustmentFactor": 1.0} for row in vn_rows]
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
    yahoo_raw = {}
    yahoo_adjusted = {}
    for row in yahoo_rows:
        raw = _finite(row.get("close"))
        adjusted = _finite(row.get("modelClose", row.get("adjClose")))
        date = str(row.get("date", ""))[:10]
        if date and raw is not None and raw > 0:
            yahoo_raw[date] = raw
        if date and raw is not None and raw > 0 and adjusted is not None and adjusted > 0:
            factors[date] = adjusted / raw
            yahoo_adjusted[date] = adjusted

    if not factors:
        return reconcile_vnstock_with_yahoo(
            vn_rows, [], max_return_guard=max_return_guard, cross_source_limit=cross_source_limit
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
        out.append({**row, "modelClose": row["close"] * factor, "adjustmentFactor": factor})

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
            prev is not None and raw_close is not None and raw_close > 0
            and model_close is not None and model_close > 0 and factor is not None and factor > 0
            and prev["rawClose"] > 0 and prev["modelClose"] > 0 and prev["factor"] > 0
        ):
            factor_log_change = math.log(factor / prev["factor"])
            raw_return = math.log(raw_close / prev["rawClose"])
            model_return = math.log(model_close / prev["modelClose"])
            start_date = prev["date"]
            if abs(factor_log_change) > FACTOR_EVENT_LOG_EPS:
                yahoo_return = _interval_log_return(yahoo_adjusted, start_date, date)
                corroborated = (
                    yahoo_return is not None and math.isfinite(yahoo_return)
                    and abs(model_return - yahoo_return) <= cross_source_limit
                )
                event = {
                    "startDate": start_date, "date": date,
                    "factorLogChange": factor_log_change,
                    "modelLogReturn": model_return,
                    "yahooAdjustedLogReturn": yahoo_return,
                    "yahooCorroborated": corroborated,
                }
                factor_events.append(event)
                if abs(model_return) > max_return_guard and not corroborated:
                    ca_violations.append(event)
            elif abs(raw_return) > max_return_guard:
                yahoo_return = _interval_log_return(yahoo_raw, start_date, date)
                corroborated = (
                    yahoo_return is not None and math.isfinite(yahoo_return)
                    and abs(raw_return - yahoo_return) <= cross_source_limit
                )
                event = {
                    "startDate": start_date, "date": date,
                    "rawLogReturn": raw_return,
                    "yahooRawLogReturn": yahoo_return,
                    "yahooCorroborated": corroborated,
                }
                ordinary_large_events.append(event)
                if not corroborated:
                    ordinary_violations.append(event)
        prev = {
            "date": date,
            "rawClose": raw_close or 0.0,
            "modelClose": model_close or 0.0,
            "factor": factor or 0.0,
        }

    raw_jump, raw_jump_date = _largest_jump(vn_rows)
    model_jump, model_jump_date = _largest_jump([{**row, "close": row["modelClose"]} for row in out])
    largest_factor_change = max(factor_events, key=lambda e: abs(e["factorLogChange"])) if factor_events else None
    largest_event_model_jump = max(factor_events, key=lambda e: abs(e["modelLogReturn"])) if factor_events else None
    largest_ordinary_raw_jump = max(ordinary_large_events, key=lambda e: abs(e["rawLogReturn"])) if ordinary_large_events else None
    verified = not ca_violations and not ordinary_violations
    return out, {
        "method": "VNSTOCK_RAW_YAHOO_ALIGNED_INTERVAL_CA_AND_OUTLIER_RECONCILIATION",
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
        "largestFactorLogChange": abs(largest_factor_change["factorLogChange"]) if largest_factor_change else 0.0,
        "largestFactorChangeDate": largest_factor_change["date"] if largest_factor_change else None,
        "largestEventModelLogJump": abs(largest_event_model_jump["modelLogReturn"]) if largest_event_model_jump else 0.0,
        "largestEventModelJumpDate": largest_event_model_jump["date"] if largest_event_model_jump else None,
        "largestOrdinaryRawLogJump": abs(largest_ordinary_raw_jump["rawLogReturn"]) if largest_ordinary_raw_jump else 0.0,
        "largestOrdinaryRawJumpDate": largest_ordinary_raw_jump["date"] if largest_ordinary_raw_jump else None,
        "verificationScope": "ALIGNED_VNSTOCK_INTERVAL_ENDPOINTS;FACTOR_CHANGE_BOUNDARIES_USE_YAHOO_ADJUSTED_RETURN;NON_FACTOR_LARGE_RAW_MOVES_USE_YAHOO_RAW_RETURN",
        "corporateActionViolations": ca_violations[:10],
        "ordinaryMoveViolations": ordinary_violations[:10],
    }
