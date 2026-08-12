"""VMEWS live model monitor.

This job does NOT retrain or promote any model. It archives aligned completed-EOD
states, evaluates only outcomes that have actually matured through 20 later
completed-EOD snapshots, and monitors ranking/calibration stability over time.

Core rules:
- never overwrite an already archived PIT snapshot silently;
- never label a signal until 20 later archived EOD dates exist;
- if any required forward close is missing, mark the outcome unresolved rather
  than filling or extending the horizon;
- absolute pooled probabilities remain governed by the existing manual model
  promotion process. Live monitoring may recommend review, never auto-promote.
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import statistics
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE = ROOT / 'data' / 'live-track'
SNAPS = LIVE / 'snapshots'
TRACK = LIVE / 'track-record.json'
CURRENT_INTEGRITY = LIVE / 'integrity.json'
MARKET = ROOT / 'data' / 'market-scan.json'
POOLED = ROOT / 'data' / 'pooled-hose' / 'current-scores.json'
ROBUST = ROOT / 'data' / 'pooled-hose' / 'robustness.json'
POLICY = ROOT / 'data' / 'alert-policy.json'
VERSION = 'VMEWS-LIVE-MONITOR-1.0.0'
SNAP_VERSION = 'VMEWS-PIT-SNAPSHOT-1.0.0'
HORIZON = 20
EVENT_DD = -0.12


def load(path: pathlib.Path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {} if default is None else default


def dump(path: pathlib.Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def finite(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except Exception:
        return None


def canonical_hash(obj) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def compact_market_state(x):
    return {
        'symbol': str(x.get('symbol') or '').upper(),
        'exchange': x.get('exchange'),
        'close': finite(x.get('close')),
        'status': x.get('status'),
        'score': finite(x.get('score')),
        'technicalScore': finite(x.get('technicalScore')),
        'independentStressSignals': int(x.get('independentStressSignals') or 0),
    }


def compact_signal(x, pooled_scores, aligned):
    sym = str(x.get('symbol') or '').upper()
    p = pooled_scores.get(sym) if aligned else None
    return {
        **compact_market_state(x),
        'drivers': list(x.get('drivers') or [])[:4],
        'pooledRiskPercentile': finite((p or {}).get('riskPercentile')),
        'pooledRiskBucket': int((p or {}).get('riskBucket') or 0) or None,
        'pooledAuditCalibratedProbability': finite((p or {}).get('auditCalibratedProbability')),
        'pooledAuditUse': (p or {}).get('auditCalibrationUse'),
    }


def compact_pooled(sym, p, close_by_symbol):
    c = close_by_symbol.get(sym) or {}
    return {
        'symbol': sym,
        'exchange': c.get('exchange') or 'HOSE',
        'close': finite(c.get('close')),
        'riskPercentile': finite(p.get('riskPercentile')),
        'riskBucket': int(p.get('riskBucket') or 0) or None,
        'empiricalBucketEventRate': finite(p.get('empiricalBucketEventRate')),
        'auditCalibratedProbability': finite(p.get('auditCalibratedProbability')),
        'probabilityUsable': bool(p.get('probabilityUsable')),
    }


def current_integrity(market, pooled, policy):
    md = str(market.get('modelDate') or '')
    pd = str(pooled.get('modelAsOf') or '')
    mc = market.get('marketContext') or {}
    dq = market.get('dataQuality') or {}
    policy_ok = market.get('policyVersion') == policy.get('version')
    aligned = bool(md and pd and md == pd)
    point_ready = bool(dq.get('pointInTimeReady', market.get('ranking')))
    if mc.get('available'):
        market_context_status = 'ALIGNED' if mc.get('vnindexModelDate') == md else 'STALE_CONTEXT'
    else:
        market_context_status = 'EXCLUDED_UNAVAILABLE'
    reasons = []
    if not md:
        reasons.append('market modelDate missing')
    if not pd:
        reasons.append('pooled modelAsOf missing')
    if not aligned:
        reasons.append(f'market/pooled EOD mismatch ({md or "N/A"} vs {pd or "N/A"})')
    if not policy_ok:
        reasons.append('canonical policy version mismatch')
    if not point_ready:
        reasons.append('market PIT outcome tape unavailable')
    return {
        'status': 'PASS' if not reasons else 'WAITING_OR_REVIEW',
        'reasons': reasons,
        'marketModelDate': md or None,
        'pooledModelDate': pd or None,
        'sameCompletedEod': aligned,
        'policyVersion': policy.get('version'),
        'policyAligned': policy_ok,
        'marketVersion': market.get('version'),
        'pooledVersion': pooled.get('version'),
        'marketContextDate': mc.get('vnindexModelDate'),
        'marketContextStatus': market_context_status,
        'marketContextImputed': False,
        'pointInTimeReady': point_ready,
        'timeBasis': 'LATEST_COMPLETED_EOD_ONLY',
        'watchlistBasis': dq.get('watchlistTimeBasis') or 'CANONICAL_MARKET_EOD',
        'rule': 'Archive only aligned market + pooled completed-EOD states. Missing/stale auxiliary context is excluded, never neutral-imputed.',
    }


def build_snapshot(market, pooled, integrity):
    model_date = integrity['marketModelDate']
    ranking = market.get('monitorUniverse') or market.get('ranking') or []
    market_states = [compact_market_state(x) for x in ranking if x.get('symbol') and finite(x.get('close')) is not None]
    market_states = [x for x in market_states if x['symbol']]
    close_tape_src = market.get('outcomeTape') or ranking
    close_tape = {}
    for x in close_tape_src:
        sym = str(x.get('symbol') or '').upper()
        c = finite(x.get('close'))
        d = str(x.get('date') or model_date)
        if sym and c is not None and d == model_date:
            close_tape[sym] = {'symbol': sym, 'exchange': x.get('exchange'), 'close': c}
    pooled_scores = pooled.get('scores') or {}
    alerts = list(market.get('redList') or []) + list(market.get('yellowList') or [])
    signals = [compact_signal(x, pooled_scores, True) for x in alerts]
    pooled_rows = []
    for sym, p in sorted(pooled_scores.items()):
        row = compact_pooled(str(sym).upper(), p or {}, close_tape)
        if row['close'] is not None and row['riskPercentile'] is not None:
            pooled_rows.append(row)
    core = {
        'version': SNAP_VERSION,
        'modelDate': model_date,
        'policyVersion': integrity.get('policyVersion'),
        'marketVersion': integrity.get('marketVersion'),
        'pooledVersion': integrity.get('pooledVersion'),
        'marketGeneratedAt': market.get('generatedAt'),
        'pooledGeneratedAt': pooled.get('generatedAt'),
        'integrityAtArchive': integrity,
        'signals': signals,
        'marketStates': market_states,
        'pooledScores': pooled_rows,
        'closeTape': list(close_tape.values()),
    }
    core['snapshotHash'] = canonical_hash({k: v for k, v in core.items() if k not in {'marketGeneratedAt', 'pooledGeneratedAt'}})
    return core


def archive_snapshot(snapshot):
    SNAPS.mkdir(parents=True, exist_ok=True)
    path = SNAPS / f"{snapshot['modelDate']}.json"
    if not path.exists():
        dump(path, snapshot)
        return 'CREATED', None
    old = load(path)
    if old.get('snapshotHash') == snapshot.get('snapshotHash'):
        return 'EXISTING_IDENTICAL', None
    return 'REVISION_DETECTED_PRESERVED_FIRST_ARCHIVE', {
        'existingHash': old.get('snapshotHash'),
        'newHash': snapshot.get('snapshotHash'),
        'modelDate': snapshot.get('modelDate'),
    }


def load_snapshots():
    out = []
    for path in sorted(SNAPS.glob('????-??-??.json')):
        p = load(path)
        if p.get('modelDate') and p.get('snapshotHash'):
            p['_path'] = path.name
            p['_close'] = {x.get('symbol'): x for x in p.get('closeTape') or [] if x.get('symbol')}
            out.append(p)
    out.sort(key=lambda x: x['modelDate'])
    return out


def outcome(snaps, idx, symbol, entry_close):
    future = snaps[idx + 1: idx + 1 + HORIZON]
    if len(future) < HORIZON:
        return {'status': 'PENDING', 'futureDatesAvailable': len(future), 'required': HORIZON}
    closes = []
    missing = []
    for s in future:
        row = s.get('_close', {}).get(symbol)
        c = finite((row or {}).get('close'))
        if c is None:
            missing.append(s['modelDate'])
        else:
            closes.append((s['modelDate'], c))
    if missing:
        return {'status': 'UNRESOLVED_DATA_GAP', 'missingDates': missing, 'required': HORIZON}
    dd = min(c / entry_close - 1 for _, c in closes)
    ret20 = closes[-1][1] / entry_close - 1
    return {
        'status': 'MATURED',
        'maturedOn': future[-1]['modelDate'],
        'maxDrawdown20': dd,
        'forwardReturn20': ret20,
        'event': dd <= EVENT_DD,
        'observations': HORIZON,
    }


def collect_records(snaps, field):
    records = []
    pending = unresolved = 0
    for i, s in enumerate(snaps):
        for row in s.get(field) or []:
            sym = row.get('symbol')
            close = finite(row.get('close'))
            if not sym or close is None or close <= 0:
                continue
            o = outcome(snaps, i, sym, close)
            rec = {'signalDate': s['modelDate'], **row, 'outcome': o}
            if o['status'] == 'MATURED':
                records.append(rec)
            elif o['status'] == 'PENDING':
                pending += 1
            else:
                unresolved += 1
    return records, pending, unresolved


def mean(a):
    return statistics.fmean(a) if a else None


def average_precision(y, score):
    pairs = sorted([(float(s), 1 if yy else 0) for yy, s in zip(y, score) if finite(s) is not None], reverse=True)
    positives = sum(v for _, v in pairs)
    if not pairs or positives == 0:
        return None
    tp = 0
    acc = 0.0
    for rank, (_, label) in enumerate(pairs, 1):
        if label:
            tp += 1
            acc += tp / rank
    return acc / positives


def binary_summary(records):
    n = len(records)
    events = sum(1 for r in records if r['outcome'].get('event'))
    dds = [finite(r['outcome'].get('maxDrawdown20')) for r in records]
    dds = [x for x in dds if x is not None]
    return {
        'matured': n,
        'events': events,
        'eventRate': events / n if n else None,
        'medianMaxDrawdown20': statistics.median(dds) if dds else None,
    }


def brier(y, p):
    vals = [(float(pp) - (1.0 if yy else 0.0)) ** 2 for yy, pp in zip(y, p) if finite(pp) is not None]
    return mean(vals)


def ece(y, p, bins=10):
    pairs = [(1 if yy else 0, float(pp)) for yy, pp in zip(y, p) if finite(pp) is not None]
    if not pairs:
        return None
    total = len(pairs)
    err = 0.0
    for k in range(bins):
        lo, hi = k / bins, (k + 1) / bins
        z = [(yy, pp) for yy, pp in pairs if (lo <= pp < hi) or (k == bins - 1 and pp == 1)]
        if not z:
            continue
        obs = mean([yy for yy, _ in z])
        pred = mean([pp for _, pp in z])
        err += len(z) / total * abs(obs - pred)
    return err


def calibration_summary(records):
    usable = [r for r in records if finite(r.get('auditCalibratedProbability')) is not None]
    n = len(usable)
    y = [bool(r['outcome'].get('event')) for r in usable]
    p = [float(r['auditCalibratedProbability']) for r in usable]
    events = sum(y)
    br = brier(y, p)
    base = events / n if n else None
    base_br = brier(y, [base] * n) if n and base is not None else None
    skill = 1 - br / base_br if br is not None and base_br and base_br > 0 else None
    halves = []
    if n >= 2:
        ordered = sorted(usable, key=lambda r: (r['signalDate'], r.get('symbol') or ''))
        cut = len(ordered) // 2
        for label, part in [('first', ordered[:cut]), ('second', ordered[cut:])]:
            yy = [bool(r['outcome'].get('event')) for r in part]
            pp = [float(r['auditCalibratedProbability']) for r in part]
            ev = sum(yy)
            bb = ev / len(part) if part else None
            b = brier(yy, pp)
            b0 = brier(yy, [bb] * len(part)) if part and bb is not None else None
            halves.append({'period': label, 'n': len(part), 'events': ev, 'brierSkill': 1 - b / b0 if b is not None and b0 and b0 > 0 else None})
    sufficient = n >= 1000 and events >= 100 and all(h['n'] >= 400 and h['events'] >= 30 for h in halves)
    stable = bool(
        sufficient and skill is not None and skill > 0 and (ece(y, p) or 1) <= .05
        and all(h.get('brierSkill') is not None and h['brierSkill'] > 0 for h in halves)
    )
    return {
        'maturedAuditStates': n,
        'events': events,
        'baseRate': base,
        'brier': br,
        'baseRateBrier': base_br,
        'brierSkill': skill,
        'ece10': ece(y, p),
        'halves': halves,
        'minimumLiveEvidenceMet': sufficient,
        'stable': stable,
        'status': 'STABLE_REVIEW_ELIGIBLE' if stable else ('UNSTABLE_KEEP_WITHHELD' if sufficient else 'INSUFFICIENT_MATURED_LIVE_DATA'),
        'effect': 'Monitoring only. Even a future PASS requires manual independent review before any probability promotion.',
    }


def build_track(snaps, integrity, archive_status, revision):
    signals, signal_pending, signal_unresolved = collect_records(snaps, 'signals')
    baseline, baseline_pending, baseline_unresolved = collect_records(snaps, 'marketStates')
    pooled, pooled_pending, pooled_unresolved = collect_records(snaps, 'pooledScores')

    by_status = {}
    all_signal_rows = []
    for st in ('RED', 'YELLOW'):
        rr = [r for r in signals if r.get('status') == st]
        s = binary_summary(rr)
        s['pending'] = sum(len(x.get('signals') or []) for x in snaps[-HORIZON:]) if not snaps[:-HORIZON] else None
        by_status[st] = s
        all_signal_rows.extend(rr)
    combined = binary_summary(signals)
    base_sum = binary_summary(baseline)
    if combined['eventRate'] is not None and base_sum['eventRate'] not in (None, 0):
        combined['liftVsEligibleMarketStates'] = combined['eventRate'] / base_sum['eventRate']
    else:
        combined['liftVsEligibleMarketStates'] = None

    pooled_y = [bool(r['outcome'].get('event')) for r in pooled]
    pooled_score = [finite(r.get('riskPercentile')) for r in pooled]
    pr = average_precision(pooled_y, pooled_score)
    pooled_base = sum(pooled_y) / len(pooled_y) if pooled_y else None
    top = [r for r in pooled if finite(r.get('riskPercentile')) is not None and r['riskPercentile'] >= .90]
    top_sum = binary_summary(top)
    if top_sum['eventRate'] is not None and pooled_base not in (None, 0):
        top_sum['liftVsLiveBase'] = top_sum['eventRate'] / pooled_base
    else:
        top_sum['liftVsLiveBase'] = None
    rank_sufficient = len(pooled) >= 1000 and sum(pooled_y) >= 100
    rank_pass = bool(rank_sufficient and pr is not None and pooled_base is not None and pr > pooled_base + .02 and (top_sum.get('liftVsLiveBase') or 0) > 1.2)
    calibration = calibration_summary(pooled)

    first = snaps[0]['modelDate'] if snaps else None
    last = snaps[-1]['modelDate'] if snaps else None
    return {
        'version': VERSION,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'trackingStarted': first,
        'latestArchivedEod': last,
        'archivedSnapshots': len(snaps),
        'horizonSessions': HORIZON,
        'eventDefinition': f'20-session forward maximum drawdown <= {EVENT_DD:.0%}',
        'currentIntegrity': {**integrity, 'archiveStatus': archive_status, 'revision': revision},
        'tDayLiveTrack': {
            'status': 'LIVE_EVIDENCE_AVAILABLE' if combined['matured'] >= 100 else 'BUILDING_LIVE_TRACK_RECORD',
            'bySignalBand': by_status,
            'combinedAlerts': combined,
            'eligibleMarketBaseline': base_sum,
            'maturedSignals': len(signals),
            'pendingSignals': signal_pending,
            'unresolvedSignals': signal_unresolved,
            'baselinePending': baseline_pending,
            'baselineUnresolved': baseline_unresolved,
            'minimumRecommendedMaturedSignals': 100,
        },
        'pooledLiveTrack': {
            'status': 'RANKING_LIVE_PASS' if rank_pass else ('RANKING_LIVE_REVIEW' if rank_sufficient else 'BUILDING_LIVE_TRACK_RECORD'),
            'maturedStates': len(pooled),
            'events': sum(pooled_y),
            'baseRate': pooled_base,
            'prAuc': pr,
            'topDecile': top_sum,
            'pendingStates': pooled_pending,
            'unresolvedStates': pooled_unresolved,
            'minimumLiveEvidenceMet': rank_sufficient,
            'rankMonitorPass': rank_pass,
            'effect': 'Live rank monitoring can trigger review or downgrade. It never auto-promotes a model.',
        },
        'calibrationLiveMonitor': calibration,
        'governance': [
            'Daily inference remains frozen; this monitor never retrains or promotes a champion.',
            'A live signal is labelled only after exactly 20 later archived completed-EOD dates exist.',
            'Any missing close inside the fixed 20-date horizon produces UNRESOLVED_DATA_GAP rather than an imputed label.',
            'The first archived snapshot for a model date is immutable; later revisions are flagged rather than silently replacing history.',
            'Absolute pooled probability remains WITHHELD until the existing historical stability limitation and future live calibration evidence are both reviewed manually.',
        ],
    }


def main():
    LIVE.mkdir(parents=True, exist_ok=True)
    SNAPS.mkdir(parents=True, exist_ok=True)
    market = load(MARKET)
    pooled = load(POOLED)
    policy = load(POLICY)
    integrity = current_integrity(market, pooled, policy)
    archive_status = 'NOT_ARCHIVED_WAITING_FOR_ALIGNMENT'
    revision = None
    if integrity['status'] == 'PASS':
        snap = build_snapshot(market, pooled, integrity)
        archive_status, revision = archive_snapshot(snap)
    integrity_payload = {
        'version': VERSION,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        **integrity,
        'archiveStatus': archive_status,
        'revision': revision,
    }
    dump(CURRENT_INTEGRITY, integrity_payload)
    snaps = load_snapshots()
    track = build_track(snaps, integrity, archive_status, revision)
    dump(TRACK, track)
    print(json.dumps({
        'version': VERSION,
        'integrity': integrity['status'],
        'marketModelDate': integrity.get('marketModelDate'),
        'pooledModelDate': integrity.get('pooledModelDate'),
        'archiveStatus': archive_status,
        'snapshots': len(snaps),
        'maturedSignals': track['tDayLiveTrack']['maturedSignals'],
        'maturedPooledStates': track['pooledLiveTrack']['maturedStates'],
        'calibrationStatus': track['calibrationLiveMonitor']['status'],
    }, indent=2))


if __name__ == '__main__':
    main()
