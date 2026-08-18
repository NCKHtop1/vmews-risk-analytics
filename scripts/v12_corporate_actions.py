import bisect
import math

FACTOR_EVENT_LOG_EPS = 1e-7

# Historical venue metadata is used only to interpret whether an observed raw close-to-close
# move was legally plausible on its exchange at that date. These seven current-HOSE names
# traded on UPCOM before their official transfer-to-HOSE effective dates. The dates are
# immutable exchange-transfer facts (VSDC/HNX notices), not model labels or future returns.
UPCOM_TO_HOSE_EFFECTIVE = {
    "ADP": "2023-07-18",
    "ANT": "2026-01-15",
    "DSC": "2024-10-17",
    "HNA": "2024-01-02",
    "ORS": "2021-11-01",
    "PDV": "2025-11-10",
    "PVP": "2023-01-11",
}

# UPCOM's daily fluctuation band is +/-15% around the reference price. Convert the up/down
# bounds separately to log-return space (they are asymmetric in logs) and add only a tiny
# tolerance for tick/reference-price rounding. The current-HOSE V12 0.12 base guard is not
# changed and no price/return is clipped or invented.
UPCOM_DAILY_PRICE_LIMIT = 0.15
UPCOM_ROUNDING_LOG_EPS = 0.002
UPCOM_MAX_UP_LOG_RETURN = math.log1p(UPCOM_DAILY_PRICE_LIMIT) + UPCOM_ROUNDING_LOG_EPS
UPCOM_MAX_DOWN_ABS_LOG_RETURN = -math.log1p(-UPCOM_DAILY_PRICE_LIMIT) + UPCOM_ROUNDING_LOG_EPS


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


def _venue_limits(symbol, end_date, base_guard):
    """Return (lower_log_return, upper_log_return, venue) for one observed interval."""
    base_guard = float(base_guard)
    symbol = str(symbol or "").upper()
    transfer_date = UPCOM_TO_HOSE_EFFECTIVE.get(symbol)
    if transfer_date and str(end_date or "")[:10] < transfer_date:
        lower = -max(base_guard, float(UPCOM_MAX_DOWN_ABS_LOG_RETURN))
        upper = max(base_guard, float(UPCOM_MAX_UP_LOG_RETURN))
        return lower, upper, "UPCOM"
    return -base_guard, base_guard, "HOSE_OR_DEFAULT"


def _within_limits(value, lower, upper):
    return value is not None and math.isfinite(value) and lower <= float(value) <= upper


def reconcile_vnstock_with_yahoo(
    vn_rows,
    yahoo_rows,
    *,
    max_return_guard,
    cross_source_limit,
    raw_reference_rows=None,
    known_ca_dates=None,
    symbol=None,
):
    """Build a VNStock-primary model series with fail-safe CA reconciliation.

    Core invariant: the reference series may *remove* a suspicious out-of-venue-band
    discontinuity, but it may never introduce one into an otherwise plausible VNStock
    primary series. The venue-aware rule is scoped only to explicitly certified former-
    UPCOM names; the current-HOSE V12 base guard remains unchanged.

    Policy per identical VNStock interval A->B:
      * If the VNStock primary return is within the legally applicable venue limits, preserve
        it verbatim, including on factor/known-event dates. Yahoo is audit evidence only.
      * If VNStock exceeds those limits and Yahoo adjusted A->B is within the same limits,
        splice only that adjusted *return* into the cumulative model index.
      * If an out-of-band VNStock interval has no safe adjusted-return reference, fail-safe.
        Raw provider agreement alone cannot legalize a move outside the venue band.

    The function never copies a Yahoo adjusted price level into VNStock, never clips a raw
    return, and never treats missing reference data as zero.
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
    normalized_symbol = str(symbol or "").upper()
    transfer_date = UPCOM_TO_HOSE_EFFECTIVE.get(normalized_symbol)

    out = []
    factor_events = []
    ca_violations = []
    ordinary_large_events = []
    ordinary_violations = []
    model_guard_violations = []
    venue_aware_intervals = []
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
        lower_guard, upper_guard, venue = _venue_limits(normalized_symbol, date, max_return_guard)
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

        raw_large = not _within_limits(raw_return, lower_guard, upper_guard)
        safe_adjusted = _within_limits(yahoo_adjusted_return, lower_guard, upper_guard)

        if (
            venue == "UPCOM"
            and abs(raw_return) > float(max_return_guard)
            and not raw_large
        ):
            venue_aware_intervals.append({
                "startDate": start_date,
                "date": date,
                "venue": venue,
                "rawLogReturn": raw_return,
                "baseGuard": float(max_return_guard),
                "venueLowerGuard": lower_guard,
                "venueUpperGuard": upper_guard,
                "knownCorporateActionDate": known_event,
            })

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
        if not _within_limits(model_return, lower_guard - 1e-12, upper_guard + 1e-12):
            model_guard_violations.append({
                "startDate": start_date,
                "date": date,
                "venue": venue,
                "modelLogReturn": model_return,
                "venueLowerGuard": lower_guard,
                "venueUpperGuard": upper_guard,
            })

        if event_boundary or adjusted_large_move:
            residual = (
                abs(model_return - yahoo_adjusted_return)
                if yahoo_adjusted_return is not None and math.isfinite(yahoo_adjusted_return)
                else None
            )
            event = {
                "startDate": start_date,
                "date": date,
                "venue": venue,
                "venueLowerGuard": lower_guard,
                "venueUpperGuard": upper_guard,
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
                "venue": venue,
                "venueLowerGuard": lower_guard,
                "venueUpperGuard": upper_guard,
                "rawLogReturn": raw_return,
                "modelLogReturn": model_return,
                "yahooAdjustedLogReturn": yahoo_adjusted_return,
                "yahooRawLogReturn": yahoo_raw_return,
                "secondaryRawLogReturn": secondary_return,
                "corroborationSource": "YAHOO_RAW" if yahoo_ok else ("SECONDARY_VNSTOCK_ROUTE" if secondary_ok else None),
                "yahooCorroborated": yahoo_ok,
                "secondaryRouteCorroborated": secondary_ok,
                "reason": "NO_SAFE_ADJUSTED_RETURN_FOR_OUT_OF_VENUE_BAND_PRIMARY_MOVE",
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
    unresolved_break_dates = sorted({
        str(item.get("date", ""))[:10]
        for item in (ca_violations + ordinary_violations + model_guard_violations)
        if str(item.get("date", ""))[:10]
    })

    model_guard_violation = bool(model_guard_violations)
    verified = not ca_violations and not ordinary_violations and not model_guard_violation

    return out, {
        "method": "VNSTOCK_PRIMARY_SAFE_ADJUSTED_RETURN_SPLICE_V3_VENUE_AWARE",
        "verified": verified,
        "largestRawLogJump": raw_jump,
        "largestRawJumpDate": raw_jump_date,
        "largestModelLogJump": model_jump,
        "largestModelJumpDate": model_jump_date,
        "modelReturnGuard": float(max_return_guard),
        "modelReturnGuardViolation": model_guard_violation,
        "modelReturnGuardViolationCount": len(model_guard_violations),
        "modelReturnGuardViolations": model_guard_violations[:10],
        "unresolvedBreakDates": unresolved_break_dates,
        "marketRegimePolicy": "CURRENT_HOSE_BASE_GUARD_WITH_OFFICIAL_PRE_TRANSFER_UPCOM_15PCT_BAND",
        "historicalVenueTransitionDate": transfer_date,
        "preTransferVenue": "UPCOM" if transfer_date else None,
        "preTransferVenueUpLogGuard": float(UPCOM_MAX_UP_LOG_RETURN) if transfer_date else None,
        "preTransferVenueDownAbsLogGuard": float(UPCOM_MAX_DOWN_ABS_LOG_RETURN) if transfer_date else None,
        "venueAwareGuardIntervalCount": len(venue_aware_intervals),
        "venueAwareGuardIntervals": venue_aware_intervals[:20],
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
            "VNSTOCK_PRIMARY_RETURNS_PRESERVED_WHEN_WITHIN_DATE_VENUE_LIMITS;"
            "CURRENT_HOSE_BASE_GUARD_UNCHANGED;"
            "OFFICIAL_PRE_TRANSFER_UPCOM_INTERVALS_USE_ASYMMETRIC_15PCT_BAND_DERIVED_LOG_LIMITS;"
            "OUT_OF_VENUE_BAND_PRIMARY_RETURNS_REQUIRE_SAFE_YAHOO_ADJUSTED_INTERVAL_RETURN;"
            "REFERENCE_SERIES_MAY_REMOVE_BUT_NEVER_INTRODUCE_OUT_OF_BAND_MODEL_JUMPS;"
            "RAW_ROUTE_CONSENSUS_IS_PROVENANCE_NOT_PERMISSION_FOR_OUT_OF_BAND_RETURNS"
        ),
        "rawPriceOrReturnMutation": False,
        "modelAdjustmentApplied": bool(large_move_adjustments),
        "gateMutation": False,
        "corporateActionViolations": ca_violations[:10],
        "ordinaryMoveViolations": ordinary_violations[:10],
    }
