#!/usr/bin/env python3
"""Independent fail-closed publication audit using frozen V12 market event study."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import news_impact_shadow_research as shadow

SCHEMA = "FINQUERY_NEWS_IMPACT_REVIEW_V1"
BLOCKERS = [
    "HISTORICAL_SECTOR_MEMBERSHIP_NOT_POINT_IN_TIME",
    "HISTORICAL_FIRST_SEEN_NOT_COLLECTOR_CERTIFIED",
    "NO_INDEPENDENT_ISSUER_SPECIFIC_IMPACT_EVIDENCE",
    "NO_FORWARD_PROSPECTIVE_IMPACT_STUDY",
    "HISTORICAL_PRE_NEWS_CONFOUNDING",
]

def verify_publication_manifest(manifest, report, sector, first_seen_count):
    """Avoid promoting priority scores, sentiment or historical association."""
    if manifest.get("schema") != SCHEMA:
        raise ValueError("Unrecognized impact review schema")
    if manifest.get("status") != "RESEARCH_ONLY":
        raise ValueError("Research cannot be promoted by editing a data manifest")
    if manifest.get("notificationsEnabled") is not False:
        raise ValueError("Verified impact notification enabled without approval")
    if manifest.get("historicalImpactCertified") is not False:
        raise ValueError("Unreviewed historical impact certification")
    if manifest.get("verifiedImpacts") != []:
        raise ValueError("Uncertified issuer/sector impact promoted")
    if sector.get("sectorAudit", {}).get("pointInTimeEligible") is not False:
        raise ValueError("Historical sector point-in-time gate changed")
    if first_seen_count != 0:
        raise ValueError("Historical collector receipt archive changed; reaudit required")
    if report["policy"]["notificationsEnabled"] is not False:
        raise ValueError("Research notification policy changed")
    if any(row.get("liveNotificationEligible") for row in report["groups"]):
        raise ValueError("Retrospective relation promoted to live alert")
    expected = {
        "inputRecords": report["inputRecords"],
        "independentEpisodes": report["filteredIndependentEvents"],
        "retrospectiveTickerCohorts": report["directTickerGroups"],
        "retrospectiveEventCohorts": report["pooledEventGroups"],
        "historicalCollectorReceipts": first_seen_count,
    }
    stats = manifest.get("research") or {}
    for key, value in expected.items():
        if stats.get(key) != value:
            raise ValueError("Stale reviewed impact statistic: " + key)
    if report["directTickerGroups"] != 0:
        raise ValueError("New ticker-specific cohort requires independent research")
    if set(manifest.get("blockers") or []) != set(BLOCKERS):
        raise ValueError("Missing research blockers")
    return {
        "status": "RESEARCH_ONLY", "notificationsEligible": 0, "verifiedRelations": 0,
        "frozenStudy": {
            **expected, "chronologicalSplits": report["splitCounts"],
            "retrospectiveAssociations": report["oosAssociationGroups"],
            "associationsFlaggedForPretrend": report["pretrendFlaggedOOSGroups"],
            "associationsWithoutLargePretrend": report["oosGroupsWithoutLargePretrend"],
        },
        "blockers": BLOCKERS,
        "reviewedCohorts": [
            {"group": row["group"], "researchEvidence": row["researchEvidence"],
             "pretrendFlagged": row["preNewsTrendFlagged"]}
            for row in report["groups"]
        ],
    }

def run(events_file, sector_file, manifest_file):
    payload = Path(events_file).read_bytes()
    events = json.loads(payload)
    sector = json.loads(Path(sector_file).read_text(encoding="utf-8"))
    manifest = json.loads(Path(manifest_file).read_text(encoding="utf-8"))
    count = sum(
        record.get("collectorFirstSeenBasis") == "COLLECTOR_RECEIPT"
        and bool(record.get("collectorFirstSeenAt"))
        for record in (events.get("records") or []) if isinstance(record, dict)
    )
    research = shadow.run(events, sector)
    result = verify_publication_manifest(manifest, research, sector, count)
    result["inputSha256"] = hashlib.sha256(payload).hexdigest()
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--events", default="data/event-intelligence-v12.json")
    p.add_argument("--sector", default="data/sector-gate-v12.json")
    p.add_argument("--manifest", default="financial-report/data/news-impact-reviewed.json")
    p.add_argument("--out", default="/tmp/finquery-news-impact-publication-audit.json")
    args = p.parse_args()
    result = run(args.events, args.sector, args.manifest)
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("NEWS_IMPACT_PUBLICATION_GATE_PASS", json.dumps({
        "status": result["status"], "verifiedRelations": result["verifiedRelations"],
        "notificationsEligible": result["notificationsEligible"],
        "frozenStudy": result["frozenStudy"],
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
