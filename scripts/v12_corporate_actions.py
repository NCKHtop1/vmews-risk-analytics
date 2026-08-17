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


def _price_series(rows, field="close"):
    out = {}
    for row in rows or []:
        date = str(row.get("date", ""))[:10]
        value = _finite(row.get(field))
        if date and value is not None and value > 0:
            out[date] = value
    return out


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


def reconcile_vnstock_with_yahoo(
    vn_rows,
    yahoo_rows,
    *,
    max_return_guard,
    cross_source_limit,
    raw_reference_rows=None,
    known_ca_dates=None,
):
    """Build a VNStock-primary model series with fail-safe CA reconciliation.

    Core invariant: the reference series may *remove* a suspicious >guard discontinuity,
    but it may never introduce a >guard discontinuity into an otherwise smooth VNStock
    primary series.  This matters because VNStock and Yahoo can be expressed on different
    historical adjustment bases; blindly splicing every Yahoo factor event can double-adjust
    an already-adjusted VNStock history.

    Policy per identical VNStock interval A->B:
      * If the VNStock primary return is within the guard, preserve it verbatim, including
        on factor/known-event dates. Yahoo is audit evidence only on that interval.
      * If VNStock exceeds the guard and Yahoo adjusted A->B exists within the guard, splice
        that *return* into the cumulative model index. This handles splits/ex-right events
        even when Yahoo's factor-change date does not exactly match the VNStock convention.
      * If a >guard VNStock interval has no safe adjusted-return reference, fail-safe. Raw
        provider agreement cannot make a >guard HOSE model return admissible because the
        same corporate-action convention can be shared by multiple raw routes.

    The function never copies a Yahoo adjusted *price level* into VNStock. Only interval
    returns are used, preserving continuity of the cumulative VNStock-primary model index.
    """
    yahoo_factors = {}
    yahoo_raw = {}
    yahoo_adjusted = {}
    for row in yahoo_rows or []:
        raw = _finite(row.get("close"))
        adjusted = _finite(row.get("modelClose", row.get("adjClose")))
        date = str(row.get("date", ""))[:10]
        if date and raw is not None and raw > 0:
            yahoo_raw[date] = raw
        if date and raw is not None and raw > 0 and adjusted is not None and adjusted > 0:
            yahoo_factors[date] = adjusted / raw
            yahoo_adjusted[date] = adjusted

    factor_dates = sorted(yahoo_factors)
    secondary_raw = _price_series(raw_reference_rows or [], "close")
    ca_dates = {str(x)[:10] for x in (known_ca_dates or []) if str(x)[:10]}

    out = []
    factor_events = []
    ca_violations = []
    ordinary_large_events = []
    ordinary_violations = []
    secondary_corroborations = 0
    yahoo_raw_corroborations = 0
    known_event_splices = 0
    large_move_adjustments = 0
    smooth_event_primary_preserved = 0

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
        yahoo_adjusted_return = _interval_log_return(yahoo_adjusted, start_date, date)
        yahoo_raw_return = _interval_log_return(yahoo_raw, start_date, date)
        secondary_return = _interval_log_return(secondary_raw, start_date, date) if secondary_raw else None

        start_yf = _asof_value(yahoo_factors, factor_dates, start_date) if factor_dates else None
        end_yf = _asof_value(yahoo_factors, factor_dates, date) if factor_dates else None
        factor_log_change = (
            math.log(end_yf / start_yf)
            if start_yf is not None and end_yf is not None and start_yf > 0 and end_yf > 0
            else 0.0
        )
        known_event = date in ca_dates
        factor_event = abs(factor_log_change) > FACTOR_EVENT_LOG_EPS
        event_boundary = factor_event or known_event

        raw_large = abs(raw_return) > max_return_guard
        safe_adjusted = (
            yahoo_adjusted_return is not None
            and math.isfinite(yahoo_adjusted_return)
            and abs(yahoo_adjusted_return) <= max_return_guard
        )

        target_return = raw_return
        adjusted_large_move = False
        if raw_large and safe_adjusted:
            target_return = float(yahoo_adjusted_return)
            splice_factor *= math.exp(target_return - raw_return)
            adjusted_large_move = True
            large_move_adjustments += 1
            if known_event:
                known_event_splices += 1
        elif event_boundary and not raw_large:
            smooth_event_primary_preserved += 1

        model_close = raw_close * splice_factor
        model_return = math.log(model_close / prev["modelClose"])

        if event_boundary or adjusted_large_move:
            residual = (
                abs(model_return - yahoo_adjusted_return)
                if yahoo_adjusted_return is not None and math.isfinite(yahoo_adjusted_return)
                else None
            )
            event = {
                "startDate": start_date,
                "date": date,
                "knownCorporateActionDate": known_event,
                "factorEvent": factor_event,
                "yahooFactorLogChange": factor_log_change,
                "rawLogReturn": raw_return,
                "modelLogReturn": model_return,
                "yahooAdjustedLogReturn": yahoo_adjusted_return,
                "postSpliceResidual": residual,
                "adjustedLargeMove": adjusted_large_move,
                "smoothPrimaryPreserved": bool(event_boundary and not raw_large),
                "yahooCorroborated": bool(adjusted_large_move and residual is not None and residual <= cross_source_limit),
            }
            factor_events.append(event)
            if raw_large and not adjusted_large_move:
                ca_violations.append(event)

        if raw_large and not adjusted_large_move and not event_boundary:
            yahoo_ok = (
                yahoo_raw_return is not None
                and math.isfinite(yahoo_raw_return)
                and abs(raw_return - yahoo_raw_return) <= cross_source_limit
            )
            secondary_ok = (
                secondary_return is not None
                and math.isfinite(secondary_return)
                and abs(raw_return - secondary_return) <= cross_source_limit
            )
            if yahoo_ok:
                yahoo_raw_corroborations += 1
            elif secondary_ok:
                secondary_corroborations += 1
            event = {
                "startDate": start_date,
                "date": date,
                "rawLogReturn": raw_return,
                "modelLogReturn": model_return,
                "yahooAdjustedLogReturn": yahoo_adjusted_return,
                "yahooRawLogReturn": yahoo_raw_return,
                "secondaryRawLogReturn": secondary_return,
                "corroborationSource": "YAHOO_RAW" if yahoo_ok else ("SECONDARY_VNSTOCK_ROUTE" if secondary_ok else None),
                "yahooCorroborated": yahoo_ok,
                "secondaryRouteCorroborated": secondary_ok,
                "reason": "NO_SAFE_ADJUSTED_RETURN_FOR_GT_GUARD_PRIMARY_MOVE",
            }
            ordinary_large_events.append(event)
            ordinary_violations.append(event)

        row["modelClose"] = model_close
        row["adjustmentFactor"] = splice_factor
        out.append(row)
        prev = {"date": date, "rawClose": raw_close, "modelClose": model_close}

    raw_jump, raw_jump_date = _largest_jump(vn_rows)
    model_jump, model_jump_date = _largest_jump([{**row, "close": row["modelClose"]} for row in out])
    largest_factor_change = max(factor_events, key=lambda e: abs(e["yahooFactorLogChange"])) if factor_events else None
    largest_event_model_jump = max(factor_events, key=lambda e: abs(e["modelLogReturn"])) if factor_events else None
    largest_ordinary_raw_jump = max(ordinary_large_events, key=lambda e: abs(e["rawLogReturn"])) if ordinary_large_events else None

    model_guard_violation = bool(model_jump > max_return_guard + 1e-12)
    verified = not ca_violations and not ordinary_violations and not model_guard_violation

    return out, {
        "method": "VNSTOCK_PRIMARY_SAFE_ADJUSTED_RETURN_SPLICE_V2",
        "verified": verified,
        "largestRawLogJump": raw_jump,
        "largestRawJumpDate": raw_jump_date,
        "largestModelLogJump": model_jump,
        "largestModelJumpDate": model_jump_date,
        "modelReturnGuard": float(max_return_guard),
        "modelReturnGuardViolation": model_guard_violation,
        "factorDates": len(yahoo_factors),
        "factorChangeEvents": len(factor_events),
        "knownCorporateActionDates": len(ca_dates),
        "knownEventSplices": known_event_splices,
        "largeMoveAdjustedSplices": large_move_adjustments,
        "smoothEventPrimaryPreserved": smooth_event_primary_preserved,
        "eventResidualViolations": len(ca_violations),
        "ordinaryLargeMoveEvents": len(ordinary_large_events),
        "ordinaryLargeMoveViolations": len(ordinary_violations),
        "yahooRawCorroborations": yahoo_raw_corroborations,
        "secondaryRouteCorroborations": secondary_corroborations,
        "secondaryRawReferenceAvailable": bool(secondary_raw),
        "largestFactorLogChange": abs(largest_factor_change["yahooFactorLogChange"]) if largest_factor_change else 0.0,
        "largestFactorChangeDate": largest_factor_change["date"] if largest_factor_change else None,
        "largestEventModelLogJump": abs(largest_event_model_jump["modelLogReturn"]) if largest_event_model_jump else 0.0,
        "largestEventModelJumpDate": largest_event_model_jump["date"] if largest_event_model_jump else None,
        "largestOrdinaryRawLogJump": abs(largest_ordinary_raw_jump["rawLogReturn"]) if largest_ordinary_raw_jump else 0.0,
        "largestOrdinaryRawJumpDate": largest_ordinary_raw_jump["date"] if largest_ordinary_raw_jump else None,
        "verificationScope": (
            "VNSTOCK_PRIMARY_RETURNS_PRESERVED_WHEN_WITHIN_GUARD;"
            "GT_GUARD_PRIMARY_RETURNS_REQUIRE_SAFE_YAHOO_ADJUSTED_INTERVAL_RETURN;"
            "REFERENCE_SERIES_MAY_REMOVE_BUT_NEVER_INTRODUCE_GT_GUARD_MODEL_JUMPS;"
            "RAW_ROUTE_CONSENSUS_IS_PROVENANCE_NOT_PERMISSION_FOR_GT_GUARD_HOSE_MODEL_RETURNS"
        ),
        "corporateActionViolations": ca_violations[:10],
        "ordinaryMoveViolations": ordinary_violations[:10],
    }
