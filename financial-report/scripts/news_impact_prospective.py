"""Immutable first-seen event ledger for prospective news-impact research.

The ledger is NOT an impact-prediction model and has no release capability.
Use actual collector receipts only. Never backfill publication as observation.
"""
from datetime import datetime, timezone, timedelta
import re
import hybrid_news_impact as h

SCHEMA="FINQUERY_NEWS_IMPACT_PROSPECTIVE_LEDGER_V2"
WINDOW_DAYS=210
MAX_EVENTS=8000

def merge(previous, shadow, now):
    stamp=h.parse_utc(now)
    if stamp is None: raise ValueError("Prospective ledger requires aware UTC time")
    if previous and (previous.get("schema")!=SCHEMA or not isinstance(previous.get("events"),list)):
        raise ValueError("Existing prospective ledger is invalid; never replace silently")
    if shadow.get("schema")!=h.SCHEMA or shadow.get("status")!="SHADOW_ONLY":
        raise ValueError("Shadow evidence is unavailable, do not append events")
    if shadow.get("counts",{}).get("eligibleNotifications")!=0:
        raise ValueError("Research cannot approve notifications")
    if shadow.get("publicationPolicy",{}).get("killSwitch")!="LOCKED_OFF":
        raise ValueError("Impact release kill switch must remain off")
    retained={}
    cutoff=stamp-timedelta(days=WINDOW_DAYS)
    for row in (previous or {}).get("events") or []:
        if not isinstance(row,dict): raise ValueError("Malformed persisted ledger entry")
        key=str(row.get("storyId") or "")
        first=h.parse_utc(row.get("collectorFirstSeenAt"))
        if not key or not first or first>stamp or row.get("certification")!="COLLECTOR_RECEIPT":
            raise ValueError("Invalid historical ledger receipt; do not fabricate first-seen")
        if first>=cutoff: retained[key]=dict(row)
    added=0;uncertified=0;conflicts=0
    for row in shadow.get("researchCandidates") or []:
        if not isinstance(row,dict): continue
        key=str(row.get("storyId") or "")
        first=h.parse_utc(row.get("collectorFirstSeenAt"))
        if not key or len(key)>200 or not first or first>stamp or first<cutoff or row.get("sourceTimeCertified") is not True:
            uncertified+=1
            continue
        if row.get("notificationEligible") is not False:
            raise ValueError("Unreviewed event attempted to activate an alert")
        if row.get("validatedAffectedTickers") or row.get("validatedAffectedSectors"):
            raise ValueError("Unreviewed event claimed a verified affected company/sector")
        if key in retained:
            old=retained[key]
            if h.parse_utc(old["collectorFirstSeenAt"])!=first:
                conflicts+=1  # immutable initial receipt; do not change it
            if old["eventFamily"]!=row.get("family"):
                conflicts+=1
            continue
        family=str(row.get("family") or "")
        if family not in h.ALLOWED_FAMILIES:
            continue
        mentions=[s for s in (row.get("directIssuerMentions") or [])
                  if isinstance(s,str) and re.fullmatch(r"[A-Z]{3}",s)]
        retained[key]={
          "storyId":key, "eventFamily":family,
          "collectorFirstSeenAt":first.isoformat(),
          "certification":"COLLECTOR_RECEIPT",
          "directIssuerMentions":sorted(set(mentions))[:15],
          "businessExposureStatus":"UNVERIFIED_OR_RESEARCH_ONLY",
          "impactStatus":"NOT_ESTABLISHED",
          "notificationEligible":False
        }
        added+=1
    rows=sorted(retained.values(),key=lambda x:(x["collectorFirstSeenAt"],x["storyId"]),reverse=True)[:MAX_EVENTS]
    return {
      "schema":SCHEMA,"status":"PROSPECTIVE_COLLECTION_ONLY",
      "checkedAt":stamp.isoformat(),"retentionDays":WINDOW_DAYS,
      "firstSeenBasis":"COLLECTOR_RECEIPT",
      "eventCount":len(rows),"newEvents":added,
      "quarantinedWithoutReceipt":uncertified,"receiptOrFamilyConflicts":conflicts,
      "verifiedTickerAlerts":False,"verifiedSectorAlerts":False,
      "notificationsEnabled":False,"events":rows
    }
