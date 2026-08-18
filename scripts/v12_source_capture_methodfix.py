"""Strict source-capture method fix: salvage only a post-break continuous suffix.

This module does not relax any V12 source gate. If an otherwise deep symbol contains
an unresolved out-of-venue-band discontinuity with no safe adjusted-return evidence,
history before the LAST unresolved break is discarded. The break date itself becomes
the first observation, so no model return crosses the unverified corporate-action/data
break. The suffix is admitted only if the unchanged candidate audit still passes and
retains >= V12_MIN_ROWS observations.
"""
from copy import deepcopy

import v12_source_capture as basecap

_ORIGINAL = basecap._candidate_audit
_INSTALLED = False


def _date(x):
    return str(x or "")[:10]


def _violation_dates(ca):
    dates = []
    # Newer CA audits expose the complete date-only break set even when detailed violation
    # objects are capped for artifact size. Consume it first so suffix salvage always starts
    # after the true LAST unresolved break, not merely the last displayed diagnostic item.
    for value in (ca or {}).get("unresolvedBreakDates") or []:
        d = _date(value)
        if d:
            dates.append(d)
    # Backward-compatible fallback for older committed audits.
    for key in ("corporateActionViolations", "ordinaryMoveViolations", "modelReturnGuardViolations"):
        for item in (ca or {}).get(key) or []:
            d = _date((item or {}).get("date"))
            if d:
                dates.append(d)
    # Defensive: if the aggregate model guard caught a break not present in the
    # diagnostic lists, preserve fail-safe behavior by including it.
    if (ca or {}).get("modelReturnGuardViolation") is True:
        d = _date((ca or {}).get("largestModelJumpDate"))
        if d:
            dates.append(d)
    return sorted(set(dates))


def _slice_from(rows, start):
    return [dict(r) for r in (rows or []) if _date(r.get("date")) >= start]


def _strict_suffix_candidate_audit(
    symbol,
    rows,
    source_audit,
    yahoo_rows,
    yahoo_audit,
    *,
    raw_reference_rows=None,
    raw_reference_audit=None,
    known_ca_dates=None,
    event_reference_audit=None,
):
    adjusted, audit = _ORIGINAL(
        symbol,
        rows,
        source_audit,
        yahoo_rows,
        yahoo_audit,
        raw_reference_rows=raw_reference_rows,
        raw_reference_audit=raw_reference_audit,
        known_ca_dates=known_ca_dates,
        event_reference_audit=event_reference_audit,
    )
    if audit.get("eligible") is True:
        audit["historyContinuityPolicy"] = "FULL_HISTORY_CERTIFIED"
        return adjusted, audit

    ca = audit.get("corporateAction") or {}
    breaks = _violation_dates(ca)
    # Only structural CA/return-guard failures are eligible for suffix salvage.
    # Short histories or pure cross-source-disagreement failures remain rejected.
    if not breaks or not audit.get("deepHistory"):
        audit["historyContinuityPolicy"] = "FULL_HISTORY_REJECTED_NO_SAFE_SUFFIX_RULE"
        audit["unresolvedBreakDates"] = breaks
        return adjusted, audit

    last_break = breaks[-1]
    suffix_rows = _slice_from(rows, last_break)
    suffix_yahoo = _slice_from(yahoo_rows, last_break)
    suffix_secondary = _slice_from(raw_reference_rows, last_break)
    suffix_ca_dates = {d for d in (known_ca_dates or set()) if _date(d) >= last_break}

    suffix_adjusted, suffix_audit = _ORIGINAL(
        symbol,
        suffix_rows,
        source_audit,
        suffix_yahoo,
        yahoo_audit,
        raw_reference_rows=suffix_secondary,
        raw_reference_audit=raw_reference_audit,
        known_ca_dates=suffix_ca_dates,
        event_reference_audit=event_reference_audit,
    )
    suffix_audit["historyContinuityPolicy"] = "TRUNCATE_BEFORE_LAST_UNRESOLVED_GT_GUARD_BREAK"
    suffix_audit["safeSuffixStartDate"] = last_break
    suffix_audit["unresolvedBreakDates"] = breaks
    suffix_audit["originalRows"] = len(rows or [])
    suffix_audit["retainedRows"] = len(suffix_adjusted)
    suffix_audit["discardedRows"] = max(0, len(rows or []) - len(suffix_adjusted))
    suffix_audit["preTruncationCorporateAction"] = deepcopy(ca)
    suffix_audit["preTruncationIneligibleReasons"] = list(audit.get("ineligibleReasons") or [])
    suffix_audit["continuityRationale"] = (
        "NO_RETURN_CROSSES_THE_LAST_UNVERIFIED_OUT_OF_VENUE_BAND_BREAK;"
        "POST_BREAK_SUFFIX_MUST_REPASS_UNCHANGED_MIN_ROWS_CA_AND_CROSS_SOURCE_GATES"
    )
    return suffix_adjusted, suffix_audit


def install():
    global _INSTALLED
    if not _INSTALLED:
        basecap._candidate_audit = _strict_suffix_candidate_audit
        _INSTALLED = True
    return basecap
