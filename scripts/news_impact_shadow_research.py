#!/usr/bin/env python3
"""FinQuery news-impact event study. RESEARCH ONLY; never emits trading alerts.

Uses frozen V12 event records already audited against exact-date VNINDEX.
PublishedAt is retrospective, NOT a certified first-seen timestamp. Current
sector mapping is NOT historical point-in-time data. Both fail closed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import statistics

PRIMARY_HORIZON = "2"
HORIZONS = ("1", "2", "5")
EVENT_TYPES = {
    "EARNINGS", "REGULATORY", "CORPORATE_ACTION", "OWNERSHIP",
    "FINANCING", "OPERATIONS_MA", "ANALYST", "MARKET_FLOW"
}
EVENT_SOURCE_TYPES = {"OFFICIAL", "NARRATIVE"}
MIN_MATERIALITY = 0.40
MIN_SOURCE_CREDIBILITY = 0.60
SEED = 20261103
VERSION = "FINQUERY-NEWS-IMPACT-SHADOW-1.0"


def finite(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError, OverflowError):
        return None


def day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_publication(value):
    try:
        v = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return v if v.tzinfo else None
    except ValueError:
        return None


def direct_key(record):
    """No current-sector features; direct issuer or pooled EVENT only."""
    return (
        ("EVENT", str(record["eventType"]), str(record["sentimentLabel"])),
        ("TICKER", str(record["ticker"]), str(record["eventType"]),
         str(record["sentimentLabel"])),
    )


def clean_records(raw):
    checked, rejected = [], Counter()
    for item in raw:
        if not isinstance(item, dict):
            rejected["malformed_record"] += 1
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        news_id = item.get("newsId")
        key = str(item.get("eventKey") or "")
        event = str(item.get("eventType") or "").upper()
        sent = str(item.get("sentimentLabel") or "").upper()
        source_type = str(item.get("sourceType") or "").upper()
        available = day(item.get("availableDate"))
        published = parse_publication(item.get("publishedAt"))
        mature = item.get("matureDate") or {}
        car = item.get("cumulativeAbnormalReturn") or {}
        benchmark = item.get("benchmarkAvailable") or {}
        m2 = day(mature.get(PRIMARY_HORIZON))
        value = finite(car.get(PRIMARY_HORIZON))
        if not ticker or not news_id or key != f"{ticker}::{news_id}":
            rejected["identity"] += 1
            continue
        if not available or not published or published.date() > available:
            rejected["publication_alignment"] += 1
            continue
        if event not in EVENT_TYPES or sent not in {"POS", "NEG"}:
            rejected["non_directional_or_general"] += 1
            continue
        if source_type not in EVENT_SOURCE_TYPES:
            rejected["rumor_or_clarification"] += 1
            continue
        if (finite(item.get("materialityScore")) or 0) < MIN_MATERIALITY:
            rejected["low_materiality"] += 1
            continue
        if (finite(item.get("sourceCredibility")) or 0) < MIN_SOURCE_CREDIBILITY:
            rejected["low_source_credibility"] += 1
            continue
        if item.get("benchmark") != "VNINDEX" or benchmark.get(PRIMARY_HORIZON) is not True:
            rejected["missing_exact_index"] += 1
            continue
        if value is None or m2 is None or m2 <= available:
            rejected["missing_mature_outcome"] += 1
            continue
        # No return-based exclusion (would select on future labels).
        checked.append({
            "eventKey": key, "ticker": ticker, "date": available.isoformat(),
            "matureDate2": m2.isoformat(),
            "matureDate5": str(mature.get("5") or m2.isoformat())[:10],
            "eventType": event, "sentimentLabel": sent,
            "sourceType": source_type,
            "sourceCredibility": float(item.get("sourceCredibility")),
            "materialityScore": float(item.get("materialityScore")),
            "publishedAt": published.isoformat(),
            "preAR2": finite((item.get("preAbnormalReturn") or {}).get("2")),
            "CAR": {h: finite(car.get(h)) if benchmark.get(h) is True else None
                    for h in HORIZONS},
        })
    # Same ticker/event/sentiment on one day is a single event, not 15 articles.
    best = {}
    for r in checked:
        k = (r["ticker"], r["date"], r["eventType"], r["sentimentLabel"])
        weight = (r["sourceCredibility"], r["materialityScore"], r["eventKey"])
        old = best.get(k)
        if old is None or weight > old[0]:
            best[k] = (weight, r)
    deduped = [x[1] for x in best.values()]
    rejected["duplicate_story_same_day"] = len(checked) - len(deduped)
    # Overlapping same-ticker future windows are highly dependent.
    # Use first chronologically available episode and purge until its T+5 maturity.
    selected = []
    lock_until = {}
    for r in sorted(deduped, key=lambda z: (z["date"], z["ticker"], z["eventKey"])):
        if r["date"] <= lock_until.get(r["ticker"], ""):
            rejected["overlapping_issuer_event_window"] += 1
            continue
        selected.append(r)
        lock_until[r["ticker"]] = r["matureDate5"]
    return selected, dict(rejected)


def split_date_boundaries(records):
    dates = sorted({r["date"] for r in records})
    if len(dates) < 60:
        raise ValueError(f"Insufficient distinct event dates for chronological study: {len(dates)}")
    return dates[int(len(dates) * 0.60)], dates[int(len(dates) * 0.80)]


def split_by_maturity(rows, validation_start, holdout_start):
    """Purge by actual outcome maturity, not ordinal row distance."""
    train = [r for r in rows if r["date"] < validation_start
             and r["matureDate2"] < validation_start]
    valid = [r for r in rows if validation_start <= r["date"] < holdout_start
             and r["matureDate2"] < holdout_start]
    hold = [r for r in rows if r["date"] >= holdout_start]
    return {"train": train, "validation": valid, "holdout": hold}


def collect_groups(rows):
    groups = defaultdict(list)
    for record in rows:
        if record["CAR"][PRIMARY_HORIZON] is None:
            continue
        for key in direct_key(record):
            groups[key].append(record)
    return groups


def daily_cluster_values(records, direction):
    daily = defaultdict(list)
    hits = []
    for row in records:
        value = row["CAR"][PRIMARY_HORIZON]
        if value is None:
            continue
        signed = direction * value
        daily[row["date"]].append(signed)
        hits.append(int(signed > 0))
    return [statistics.mean(v) for _, v in sorted(daily.items())], hits


def cluster_test(values, seed, draws=1999):
    """Day-cluster sign flip null and day-bootstrap 95% CI (predeclared T+2)."""
    if len(values) < 2:
        return {"p": 1.0, "ci95": [None, None]}
    rand = random.Random(seed)
    obs = statistics.mean(values)
    means = []
    exceed = 0
    for _ in range(draws):
        null = sum(v * (1 if rand.getrandbits(1) else -1) for v in values) / len(values)
        if abs(null) >= abs(obs):
            exceed += 1
        boot = [values[rand.randrange(len(values))] for _ in values]
        means.append(statistics.mean(boot))
    means.sort()
    return {"p": (exceed + 1) / (draws + 1),
            "ci95": [means[int(.025 * (draws - 1))], means[int(.975 * (draws - 1))]]}


def summary(rows, direction):
    if not rows:
        return {"n": 0, "days": 0, "tickers": 0, "meanCAR2": None, "hitRate": None}
    cluster, hits = daily_cluster_values(rows, direction)
    return {
        "n": len(rows), "days": len(cluster), "tickers": len({x["ticker"] for x in rows}),
        "meanCAR2": round(statistics.mean(cluster), 7) if cluster else None,
        "hitRate": round(statistics.mean(hits), 4) if hits else None,
        "preAR2": round(statistics.mean([direction * x["preAR2"] for x in rows
                     if x["preAR2"] is not None]), 7) if any(x["preAR2"] is not None for x in rows) else None,
    }


def bh_qvalues(items):
    """Adjust only hypotheses locked by TRAIN+VALIDATION, before opening HOLDOUT."""
    n = len(items)
    order = sorted(range(n), key=lambda i: items[i]["holdout"]["p"])
    previous = 1.0
    for rank in range(n - 1, -1, -1):
        idx = order[rank]
        q = min(previous, items[idx]["holdout"]["p"] * n / (rank + 1))
        items[idx]["holdout"]["qBH"] = round(q, 6)
        previous = q


def run(events, sector):
    if events.get("eventIdentity") != "TICKER_NEWS_ID" or events.get("benchmarkPolicy", {}).get("benchmark") != "VNINDEX":
        raise ValueError("Historical event identity/benchmark contract failed")
    if sector.get("status") != "PASS" or sector.get("sectorAudit", {}).get("pointInTimeEligible") is not False:
        raise ValueError("Expected explicit sector-PIT ABSTAIN gate (not current taxonomy backfill)")
    records, rejected = clean_records(events.get("records") or [])
    val_start, hold_start = split_date_boundaries(records)
    sets = split_by_maturity(records, val_start, hold_start)
    groups = {part: collect_groups(rows) for part, rows in sets.items()}
    confirmed = []
    counts = Counter()
    all_keys = sorted(set(groups["train"]), key=str)
    for key in all_keys:
        train = groups["train"][key]
        is_ticker = key[0] == "TICKER"
        min_train, min_validation, min_hold = ((18, 10, 12) if is_ticker else (35, 18, 24))
        val = groups["validation"].get(key, [])
        hold = groups["holdout"].get(key, [])
        if min(len(train) / min_train, len(val) / min_validation,
               len(hold) / min_hold) < 1:
            counts["insufficient_sample"] += 1
            continue
        if len({r["date"] for r in train}) < 12 or len({r["date"] for r in val}) < 8:
            counts["insufficient_independent_dates"] += 1
            continue
        signed_train_mean = statistics.mean(r["CAR"][PRIMARY_HORIZON] for r in train)
        direction = 1 if signed_train_mean > 0 else -1
        st, sv, sh = (summary(rows, direction) for rows in (train, val, hold))
        # Direction is locked from TRAIN; validation must independently agree.
        if (sv["meanCAR2"] is None or sv["meanCAR2"] <= 0
                or sv["hitRate"] is None or sv["hitRate"] < .52):
            counts["validation_failed"] += 1
            continue
        if sh["days"] < 10:
            counts["insufficient_holdout_days"] += 1
            continue
        random_seed = int(hashlib.sha256(str(key).encode()).hexdigest()[:8], 16) ^ SEED
        vals, _ = daily_cluster_values(hold, direction)
        test = cluster_test(vals, random_seed)
        # Do not condition further on holdout for BH family definition.
        confirmed.append({
            "group": list(key), "direction": "POSITIVE_AR" if direction == 1 else "NEGATIVE_AR",
            "train": st, "validation": sv,
            "holdout": {**sh, "p": round(test["p"], 6),
                        "ci95": [round(z, 7) for z in test["ci95"]]},
        })
    bh_qvalues(confirmed)
    for row in confirmed:
        h = row["holdout"]
        # This is a confounder audit, NOT causal adjustment. Earlier pre-news
        # price moves can create spurious publication-timestamp associations.
        pretrend = {
            stage: bool(row[stage].get("preAR2") is not None
                        and row[stage]["preAR2"] > .012)
            for stage in ("train", "validation", "holdout")
        }
        contamination = any(pretrend.values())
        observed = (
            h["meanCAR2"] is not None and h["meanCAR2"] >= .002
            and h["hitRate"] >= .55 and h["ci95"][0] > 0
            and h["qBH"] <= .10
        )
        row["preNewsTrendConfounder"] = pretrend
        row["preNewsTrendFlagged"] = contamination
        row["oosStatisticalAssociation"] = observed
        row["researchEvidence"] = (
            "OOS_ASSOCIATION_WITH_PRETREND" if observed and contamination
            else "OOS_ASSOCIATION" if observed else "UNCONFIRMED"
        )
        # Historical backfills cannot validate actual first-seen availability
        # or sector lineage; not one of these labels is a deployable alert.
        row["liveNotificationEligible"] = False
        if observed:
            counts["oos_statistical_association_only"] += 1
            if contamination:
                counts["oos_association_pretrend_flagged"] += 1
            else:
                counts["oos_association_no_large_pretrend"] += 1
        else:
            counts["holdout_gate_failed"] += 1
    confirmed.sort(key=lambda r: (
        r["researchEvidence"] != "OOS_ASSOCIATION",
        r["holdout"]["qBH"], -r["holdout"]["n"], str(r["group"])
    ))
    policy = {
        "researchOnly": True,
        "notificationsEnabled": False,
        "tickersAutomaticImpactEnabled": False,
        "sectorsAutomaticImpactEnabled": False,
        "requiresImmutableFirstSeenAt": True,
        "firstSeenAtArchiveCertified": False,
        "retrospectiveNewsBackfillBias": "UNRESOLVED",
        "historicalSectorPIT": "ABSTAIN",
        "conditionalCausalityClaim": False,
        "intradayImpactClaim": False,
        "candidateMode": "SHADOW_NOT_NOTIFICATIONS",
        "primaryHorizon": "T+2",
    }
    return {
        "version": VERSION, "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputVersion": events.get("version"), "inputGeneratedAt": events.get("generatedAt"),
        "primaryHorizon": "T+2",
        "study": "Retrospective cross-sectional event study; NOT an intraday causal study",
        "method": "Issuer/date/story dedupe; overlap purge to T+5; chronological 60/20/20; actual label-maturity embargo; VNINDEX-relative CAR T+2; publication-date clustering; signed day permutation p; day bootstrap CI; BH-FDR on train+validation locked groups",
        "boundaries": {"validationStart": val_start, "holdoutStart": hold_start},
        "inputRecords": len(events.get("records") or []),
        "filteredIndependentEvents": len(records),
        "splitCounts": {k: len(v) for k, v in sets.items()},
        "rejected": rejected, "screening": dict(counts),
        "auditedHypotheses": len(confirmed),
        "pooledEventGroups": sum(x["group"][0] == "EVENT" for x in confirmed),
        "directTickerGroups": sum(x["group"][0] == "TICKER" for x in confirmed),
        "oosAssociationGroups": sum(x["oosStatisticalAssociation"] for x in confirmed),
        "pretrendFlaggedOOSGroups": sum(
            x["oosStatisticalAssociation"] and x["preNewsTrendFlagged"]
            for x in confirmed
        ),
        "oosGroupsWithoutLargePretrend": sum(
            x["oosStatisticalAssociation"] and not x["preNewsTrendFlagged"]
            for x in confirmed
        ),
        "groups": confirmed[:100],
        "policy": policy,
        "warning": "Retrospective first-seen availability is uncertified. Current sector labels cannot be applied historically. T+2 correlation is not causal proof, intraday alpha or a recommendation. No notification may be auto-enabled by this artifact.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", default="data/event-intelligence-v12.json")
    parser.add_argument("--sector", default="data/sector-gate-v12.json")
    parser.add_argument("--output", default="/tmp/finquery-news-impact-shadow.json")
    args = parser.parse_args()
    data_path = Path(args.events)
    events = json.loads(data_path.read_text(encoding="utf-8"))
    sector = json.loads(Path(args.sector).read_text(encoding="utf-8"))
    result = run(events, sector)
    result["inputSha256"] = hashlib.sha256(data_path.read_bytes()).hexdigest()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    condensed = {k: result[k] for k in (
        "version", "inputVersion", "inputRecords", "filteredIndependentEvents",
        "splitCounts", "auditedHypotheses", "pooledEventGroups",
        "directTickerGroups", "oosAssociationGroups",
        "pretrendFlaggedOOSGroups", "oosGroupsWithoutLargePretrend", "screening"
    )}
    print("FINQUERY_NEWS_IMPACT_RESEARCH_REPORT", json.dumps(condensed, ensure_ascii=False))
    for row in result["groups"][:8]:
        print("RESEARCH_GROUP", json.dumps({
            "group": row["group"], "direction": row["direction"],
            "train": row["train"], "validation": row["validation"],
            "holdout": row["holdout"], "label": row["researchEvidence"],
            "pretrend": row["preNewsTrendConfounder"],
            "noti": row["liveNotificationEligible"]
        }, ensure_ascii=False))
    print("FINQUERY_NEWS_IMPACT_NOTIFICATIONS_DISABLED", result["policy"]["notificationsEnabled"] is False)


if __name__ == "__main__":
    main()
