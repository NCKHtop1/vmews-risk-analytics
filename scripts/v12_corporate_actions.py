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


def _asof_value(series, dates, date):
    if date in series:
        return _finite(series.get(date))
    idx = bisect.bisect_right(dates, date) - 1
    if idx < 0:
        return _finite(series.get(dates[0])) if dates else None
    return _finite(series.get(dates[idx]))


def reconcile_vnstock_with_yahoo(vn_rows, yahoo_rows, *, max_return_guard, cross_source_limit):
    """Build a VNStock-primary model series with event-boundary return splicing.

    Ordinary intervals preserve VNStock returns and large moves must be corroborated
    by Yahoo raw returns on the identical VNStock endpoints. At a Yahoo adjustment-
    factor boundary, providers may encode the raw ex-right/ex-dividend reference price
    differently. Therefore the model series does not multiply VNStock by Yahoo's
    absolute AdjClose/Close factor (which assumes identical raw-price conventions).
    Instead it splices only that interval to Yahoo's adjusted return, then carries the
    resulting VNStock-local multiplier forward. Missing reference remains fail-safe.
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

    yahoo_factors = {}
    yahoo_raw = {}
    yahoo_adjusted = {}
    for row in yahoo_rows:
        raw = _finite(row.get("close"))
        adjusted = _finite(row.get("modelClose", row.get("adjClose")))
        date = str(row.get("date", ""))[:10]
        if date and raw is not None and raw > 0:
            yahoo_raw[date] = raw
        if date and raw is not None and raw > 0 and adjusted is not None and adjusted > 0:
            yahoo_factors[date] = adjusted / raw
            yahoo_adjusted[date] = adjusted

    if not yahoo_factors:
        return reconcile_vnstock_with_yahoo(
            vn_rows, [], max_return_guard=max_return_guard, cross_source_limit=cross_source_limit
        )

    factor_dates = sorted(yahoo_factors)
    out = []
    factor_events = []
    ca_violations = []
    ordinary_large_events = []
    ordinary_violations = []

    prev = None
    splice_factor = 1.0
    for source_row in vn_rows:
        row = dict(source_row)
        raw_close = _finite(row.get("close"))
        date = str(row.get("date", ""))[:10]
        if raw_close is None or raw_close <= 0 or not date:
            continue

        if prev is None:
            model_close = raw_close * splice_factor
            row["modelClose"] = model_close
            row["adjustmentFactor"] = splice_factor
            out.append(row)
            prev = {"date": date, "rawClose": raw_close, "modelClose": model_close}
            continue

        start_date = prev["date"]
        raw_return = math.log(raw_close / prev["rawClose"])
        start_yf = _asof_value(yahoo_factors, factor_dates, start_date)
        end_yf = _asof_value(yahoo_factors, factor_dates, date)
        factor_log_change = (
            math.log(end_yf / start_yf)
            if start_yf is not None and end_yf is not None and start_yf > 0 and end_yf > 0
            else 0.0
        )

        if abs(factor_log_change) > FACTOR_EVENT_LOG_EPS:
            yahoo_return = _interval_log_return(yahoo_adjusted, start_date, date)
            reference_available = yahoo_return is not None and math.isfinite(yahoo_return)
            if reference_available:
                splice_factor *= math.exp(yahoo_return - raw_return)
            model_close = raw_close * splice_factor
            model_return = math.log(model_close / prev["modelClose"])
            residual = abs(model_return - yahoo_return) if reference_available else None
            corroborated = bool(reference_available and residual <= cross_source_limit)
            event = {
                "startDate": start_date,
                "date": date,
                "yahooFactorLogChange": factor_log_change,
                "rawLogReturn": raw_return,
                "modelLogReturn": model_return,
                "yahooAdjustedLogReturn": yahoo_return,
                "postSpliceResidual": residual,
                "yahooCorroborated": corroborated,
            }
            factor_events.append(event)
            if not corroborated and abs(raw_return) > max_return_guard:
                ca_violations.append(event)
        else:
            model_close = raw_close * splice_factor
            model_return = math.log(model_close / prev["modelClose"])
            if abs(raw_return) > max_return_guard:
                yahoo_return = _interval_log_return(yahoo_raw, start_date, date)
                corroborated = (
                    yahoo_return is not None
                    and math.isfinite(yahoo_return)
                    and abs(raw_return - yahoo_return) <= cross_source_limit
                )
                event = {
                    "startDate": start_date,
                    "date": date,
                    "rawLogReturn": raw_return,
                    "modelLogReturn": model_return,
                    "yahooRawLogReturn": yahoo_return,
                    "yahooCorroborated": corroborated,
                }
                ordinary_large_events.append(event)
                if not corroborated:
                    ordinary_violations.append(event)

        row["modelClose"] = model_close
        row["adjustmentFactor"] = splice_factor
        out.append(row)
        prev = {"date": date, "rawClose": raw_close, "modelClose": model_close}

    raw_jump, raw_jump_date = _largest_jump(vn_rows)
    model_jump, model_jump_date = _largest_jump(
        [{**row, "close": row["modelClose"]} for row in out]
    )
    largest_factor_change = max(
        factor_events, key=lambda e: abs(e["yahooFactorLogChange"])
    ) if factor_events else None
    largest_event_model_jump = max(
        factor_events, key=lambda e: abs(e["modelLogReturn"])
    ) if factor_events else None
    largest_ordinary_raw_jump = max(
        ordinary_large_events, key=lambda e: abs(e["rawLogReturn"])
    ) if ordinary_large_events else None
    verified = not ca_violations and not ordinary_violations
    return out, {
        "method": "VNSTOCK_PRIMARY_YAHOO_EVENT_RETURN_SPLICE_AND_RAW_OUTLIER_RECONCILIATION",
        "verified": verified,
        "largestRawLogJump": raw_jump,
        "largestRawJumpDate": raw_jump_date,
        "largestModelLogJump": model_jump,
        "largestModelJumpDate": model_jump_date,
        "factorDates": len(yahoo_factors),
        "factorChangeEvents": len(factor_events),
        "eventResidualViolations": len(ca_violations),
        "ordinaryLargeMoveEvents": len(ordinary_large_events),
        "ordinaryLargeMoveViolations": len(ordinary_violations),
        "largestFactorLogChange": abs(largest_factor_change["yahooFactorLogChange"]) if largest_factor_change else 0.0,
        "largestFactorChangeDate": largest_factor_change["date"] if largest_factor_change else None,
        "largestEventModelLogJump": abs(largest_event_model_jump["modelLogReturn"]) if largest_event_model_jump else 0.0,
        "largestEventModelJumpDate": largest_event_model_jump["date"] if largest_event_model_jump else None,
        "largestOrdinaryRawLogJump": abs(largest_ordinary_raw_jump["rawLogReturn"]) if largest_ordinary_raw_jump else 0.0,
        "largestOrdinaryRawJumpDate": largest_ordinary_raw_jump["date"] if largest_ordinary_raw_jump else None,
        "verificationScope": "VNSTOCK_RETURNS_PRESERVED_OUTSIDE_YAHOO_FACTOR_BOUNDARIES;EVENT_INTERVALS_SPLICE_TO_YAHOO_ADJUSTED_RETURN_ON_IDENTICAL_ENDPOINTS;NON_EVENT_LARGE_RAW_MOVES_REQUIRE_YAHOO_RAW_CORROBORATION",
        "corporateActionViolations": ca_violations[:10],
        "ordinaryMoveViolations": ordinary_violations[:10],
    }
