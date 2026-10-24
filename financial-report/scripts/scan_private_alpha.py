#!/usr/bin/env python3
"""Private FinQuery Alpha rules -> public, formula-free market event feed.

Proprietary rules are supplied ONLY in FINQUERY_ALPHA_RULES_JSON (CI secret);
never store, render, print or embed rule formulas in public datasets or JS.
When secrets, live observations or source timestamps are missing the runner
fails closed without writing an Alpha feed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")
UTC = timezone.utc
FIELDS = {
    "price", "changePct", "sma20", "sma50", "sma200", "ema9", "ema20",
    "ema50", "vwma20", "supertrend", "supertrendDir", "adx14",
    "rsi14", "macd", "macdSignal", "macdHistogram", "stochK",
    "stochD", "cci20", "roc10", "willr14", "mfi14", "bbPctB",
    "atr14", "volume", "volumeRatio20", "obv", "obvSlope5", "cmf20"
}
OPS = {"gt", "gte", "lt", "lte", "cross_up", "cross_down", "rising", "falling"}
ID_RE = re.compile(r"^ALPHA[_-][0-9]{2,3}$")
SYMBOL_RE = re.compile(r"^[A-Z]{3}$")


def date_time(raw):
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.astimezone(UTC) if dt.tzinfo else None
    except (TypeError, ValueError):
        return None


def numeric(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def validate_rules(config):
    if not isinstance(config, dict) or config.get("schemaVersion") != 1:
        raise ValueError("Unsupported private Alpha specification")
    rows = config.get("rules")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 40:
        raise ValueError("Private Alpha count invalid")
    seen = set()
    for rule in rows:
        if not isinstance(rule, dict) or not ID_RE.fullmatch(str(rule.get("id", ""))):
            raise ValueError("Invalid Alpha ID")
        if rule["id"] in seen:
            raise ValueError("Duplicate Alpha ID")
        seen.add(rule["id"])
        conditions = rule.get("conditions")
        if not isinstance(conditions, list) or not 1 <= len(conditions) <= 9:
            raise ValueError("Invalid Alpha condition count")
        if rule.get("join", "AND") != "AND":
            raise ValueError("Unknown Alpha condition combination")
        for c in conditions:
            if not isinstance(c, dict) or c.get("field") not in FIELDS or c.get("op") not in OPS:
                raise ValueError("Invalid Alpha field or operator")
            if c.get("otherField") is not None:
                if c["otherField"] not in FIELDS or c["otherField"] == c["field"]:
                    raise ValueError("Invalid comparison field")
            elif c.get("op") not in ("rising", "falling") and numeric(c.get("value")) is None:
                raise ValueError("Missing numeric comparison value")
            near = numeric(c.get("nearPct", 0.005))
            if near is None or not 0 <= near <= .05:
                raise ValueError("Invalid crossover proximity")
    return rows


def side(row, c, previous=False):
    field = c["field"]
    values = row.get("previous" if previous else "current") or {}
    left = numeric(values.get(field))
    if c.get("otherField"):
        right = numeric(values.get(c["otherField"]))
    else:
        right = numeric(c.get("value"))
    return left, right


def evaluate_condition(row, c):
    current, right = side(row, c)
    prior, prior_right = side(row, c, True)
    op = c["op"]
    if current is None or prior is None:
        return False, False
    if op in ("rising", "falling"):
        return (current > prior if op == "rising" else current < prior), False
    if right is None or prior_right is None:
        return False, False
    if op == "gt": return current > right, False
    if op == "gte": return current >= right, False
    if op == "lt": return current < right, False
    if op == "lte": return current <= right, False
    if op == "cross_up":
        confirmed = prior <= prior_right and current > right
        close = prior <= prior_right and current <= right and (right - current) <= max(abs(right), abs(current), 1) * c.get("nearPct", .005)
        return bool(confirmed), bool(close and not confirmed)
    if op == "cross_down":
        confirmed = prior >= prior_right and current < right
        close = prior >= prior_right and current >= right and (current - right) <= max(abs(right), abs(current), 1) * c.get("nearPct", .005)
        return bool(confirmed), bool(close and not confirmed)
    return False, False


def stage(row, rule):
    checks = [evaluate_condition(row, c) for c in rule["conditions"]]
    if all(met for met, _ in checks):
        return "confirmed"
    if any(near for met, near in checks if not met) and all(met or near for met, near in checks):
        return "preparing"
    return None


def trading_day(now):
    local = now.astimezone(VN)
    minute = local.hour * 60 + local.minute
    return local.weekday() < 5 and 525 <= minute <= 895


def compute(snapshot, config, previous=None, now=None):
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Clock must be timezone aware")
    rules = validate_rules(config)
    source = date_time(snapshot.get("sourceTime"))
    if not source or source > now + timedelta(minutes=5):
        raise ValueError("Unverified strategy source timestamp")
    if snapshot.get("status") != "ok" or not isinstance(snapshot.get("symbols"), dict):
        raise ValueError("Invalid strategy source snapshot")
    # Do not declare new in-session signals if the market-derived source is
    # old, incomplete, or from a previous session.
    if not trading_day(now) or now - source > timedelta(minutes=20):
        raise ValueError("No fresh in-session market observation")
    local_day = source.astimezone(VN).date().isoformat()
    prior_source = str((previous or {}).get("sourceTime") or "")
    if prior_source and date_time(prior_source) and source <= date_time(prior_source):
        return None
    states = {}
    prev_states = (previous or {}).get("states") or {}
    alerts = []
    for symbol, row in snapshot["symbols"].items():
        if not SYMBOL_RE.fullmatch(symbol) or row.get("tier") not in ("CORE", "LIQUID"):
            continue
        if row.get("barDate") != local_day or str(row.get("cadence", "")).upper() == "EOD":
            continue
        row_source = date_time(row.get("sourceTime"))
        if not row_source or abs((source - row_source).total_seconds()) > 1800:
            continue
        for rule in rules:
            current = stage(row, rule)
            key = rule["id"] + "|" + symbol
            prior = prev_states.get(key)
            if current:
                states[key] = current
                if prior != current:
                    event_id = hashlib.sha256((key+"|"+current+"|"+source.isoformat()).encode()).hexdigest()[:24]
                    alerts.append({
                        "id": event_id, "alphaId": rule["id"], "symbol": symbol,
                        "stage": current, "sourceTime": source.isoformat(),
                        "market": "HOSE", "tier": row["tier"]
                    })
    alerts.sort(key=lambda x: (x["stage"] != "confirmed", x["alphaId"], x["symbol"]))
    return {
        "schemaVersion": 1, "status": "verified", "sourceTime": source.isoformat(),
        "generatedAt": now.isoformat(), "scope": "HOSE_CORE_LIQUID",
        "alerts": alerts[:100], "states": states,
        "rulesCount": len(rules), "privateRulesIncluded": False,
        "dataDisclaimer": "Confirmed indicator-state events only, not executed trades."
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    secret = os.environ.get("FINQUERY_ALPHA_RULES_JSON", "")
    if not secret:
        print("ALPHA_SOURCE_DISABLED: protected strategy configuration not available")
        return 0
    config = json.loads(secret)  # never log this object
    source = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    out = Path(args.output)
    try:
        prior = json.loads(out.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        prior = None
    result = compute(source, config, prior)
    if result is None:
        print("ALPHA_NO_NEW_SOURCE: unchanged market snapshot")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    tmp.replace(out)
    print("ALPHA_SCANNER_VERIFIED: events=", len(result["alerts"]), "sourceTime=", result["sourceTime"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
