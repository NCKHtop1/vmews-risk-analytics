import json
import math
import pathlib
from datetime import datetime, timezone

DATA=pathlib.Path('data')
audit=json.loads((DATA/'data-audit-v12.json').read_text(encoding='utf-8'))
event=json.loads((DATA/'event-intelligence-v12.json').read_text(encoding='utf-8'))
records=event.get('records') or [];summary=event.get('summary') or {};idx=audit.get('index') or {}

def finite(v):return isinstance(v,(int,float)) and math.isfinite(float(v))
def sha256_text(v):
    s=str(v or '').lower();return len(s)==64 and all(c in '0123456789abcdef' for c in s)
def valid_cache_route():
    if idx.get('route')!='LAST_GOOD_INDEX_CACHE':return False,{}
    p=DATA/'vnindex-v12.json'
    if not p.exists():return False,{'reason':'cache file missing'}
    try:z=json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:return False,{'reason':str(e)}
    s=z.get('summary') or {};ok=str(z.get('version','')).startswith('VMEWS-VNINDEX-CACHE-12') and int(s.get('rows') or 0)>=520 and int(s.get('duplicateDates') or -1)==0 and float(s.get('maxAbsLogJump') or 99)<=.12 and idx.get('cacheVersion')==z.get('version') and int(idx.get('rows') or 0)==int(s.get('rows') or 0) and str(idx.get('cacheLastDate') or '')==str(s.get('last') or '')
    return bool(ok),{'version':z.get('version'),'summary':s,'indexAudit':idx}
def valid_frozen_route():
    """Accept frozen VNINDEX only when the immutable source probe independently proves it."""
    if idx.get('route')!='VNSTOCK_INDEX_FROZEN_SNAPSHOT':return False,{}
    p=DATA/'v12-source-probe.json'
    if not p.exists():return False,{'reason':'frozen source probe missing'}
    try:z=json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:return False,{'reason':str(e)}
    zi=z.get('index') or {};snap=z.get('snapshot') or {}
    same_index=(
        zi.get('route')==idx.get('route') and
        int(zi.get('rows') or 0)==int(idx.get('rows') or 0) and
        str(zi.get('start') or '')==str(idx.get('inputStartDate') or '') and
        str(zi.get('end') or '')==str(idx.get('inputEndDate') or '') and
        str(zi.get('inputFingerprintSha256') or '')==str(idx.get('inputFingerprintSha256') or '')
    )
    ok=(
        z.get('status')=='PASS' and z.get('mode')=='IMMUTABLE_FROZEN_SNAPSHOT' and
        z.get('runtimeNetworkPriceFetch') is False and z.get('runtimeProviderSwitching') is False and
        zi.get('ok') is True and zi.get('researchFrozen') is True and zi.get('runtimeNetworkPriceFetch') is False and
        idx.get('researchFrozen') is True and idx.get('runtimeNetworkPriceFetch') is False and idx.get('prefetchedBeforeUniverse') is True and
        int(idx.get('rows') or 0)>=520 and sha256_text(idx.get('inputFingerprintSha256')) and
        sha256_text(snap.get('snapshotFileSha256')) and sha256_text(snap.get('inputManifestSha256')) and same_index
    )
    return bool(ok),{'sourceProbeVersion':z.get('version'),'sourceProbeStatus':z.get('status'),'snapshot':{k:snap.get(k) for k in ('version','asOf','snapshotFileSha256','inputManifestSha256','certificationVersion','certificationMode')},'probeIndex':zi,'indexAudit':idx,'sameIndexContract':same_index}

cache_ok,cache_detail=valid_cache_route();frozen_ok,frozen_detail=valid_frozen_route();live_route=idx.get('route') in {'VNSTOCK_INDEX_PRIMARY','YAHOO_INDEX_FALLBACK'}
matured5=[r for r in records if (r.get('priceAfter') or {}).get('5') is not None];bench5=[r for r in matured5 if (r.get('benchmarkAvailable') or {}).get('5') is True];semantic_failures=[];daily_failures=[];target_failures=[];pre_failures=[];identity_failures=[]
for r in records:
    expected=f"{str(r.get('ticker') or '').upper()}::{r.get('newsId')}"
    if r.get('eventKey')!=expected:identity_failures.append((r.get('ticker'),r.get('newsId'),r.get('eventKey'),expected))
    br=r.get('benchmarkReturn') or {};ba=r.get('benchmarkAvailable') or {};bt=r.get('benchmarkTargetDate') or {};car=r.get('cumulativeAbnormalReturn') or {};dar=r.get('abnormalReturn') or {};mature=r.get('matureDate') or {};pbr=r.get('preBenchmarkReturn') or {};pba=r.get('preBenchmarkAvailable') or {};par=r.get('preAbnormalReturn') or {}
    for h in map(str,range(1,6)):
        available=ba.get(h) is True;benchmark_value=br.get(h);abnormal=car.get(h)
        if mature.get(h) is not None and bt.get(h)!=mature.get(h):target_failures.append((r.get('eventKey'),h,bt.get(h),mature.get(h)))
        if available:
            if not finite(benchmark_value):semantic_failures.append((r.get('eventKey'),h,'available_without_benchmark_value'))
            if abnormal is not None and not finite(abnormal):semantic_failures.append((r.get('eventKey'),h,'nonfinite_abnormal_return'))
        elif benchmark_value is not None or abnormal is not None:semantic_failures.append((r.get('eventKey'),h,'raw_or_other_return_relabelled_as_abnormal'))
        cur=car.get(h);prev=0.0 if h=='1' else car.get(str(int(h)-1));daily=dar.get(h)
        if finite(cur) and finite(prev):
            if not finite(daily) or abs(float(daily)-(float(cur)-float(prev)))>1e-12:daily_failures.append((r.get('eventKey'),h,daily,cur,prev))
        elif daily is not None:daily_failures.append((r.get('eventKey'),h,'daily_AR_present_across_missing_CAR_gap'))
    for k in ('1','2','5'):
        if pba.get(k) is True:
            if not finite(pbr.get(k)) or (par.get(k) is not None and not finite(par.get(k))):pre_failures.append((r.get('eventKey'),k,'invalid_pre_benchmark_or_AR'))
        elif pbr.get(k) is not None or par.get(k) is not None:pre_failures.append((r.get('eventKey'),k,'raw_pre_return_relabelled_as_pre_AR'))
coverage=len(bench5)/max(1,len(matured5));policy=event.get('benchmarkPolicy') or {};keys=[r.get('eventKey') for r in records]
checks={
 'indexHistoryAudited':int(idx.get('rows') or 0)>=520,
 'indexRouteExplicitAndAudited':live_route or cache_ok or frozen_ok,
 'eventIdentityComposite':event.get('eventIdentity')=='TICKER_NEWS_ID' and not identity_failures,
 'eventKeysUnique':bool(keys) and len(keys)==len(set(keys)) and int(summary.get('duplicateEventKeys') or 0)==0,
 'eventBenchmarkIdentityVNINDEX':bool(records) and all(r.get('benchmark')=='VNINDEX' for r in records),
 'benchmarkFieldsMaterialized':bool(records) and all(isinstance(r.get('benchmarkReturn'),dict) and isinstance(r.get('benchmarkAvailable'),dict) and isinstance(r.get('benchmarkTargetDate'),dict) for r in records),
 'exactStockMaturityAlignment':not target_failures,
 'noRawReturnFallbackWhenBenchmarkMissing':not semantic_failures,
 'preEventBenchmarkAbstentionSafe':not pre_failures,
 'dailyARUsesAdjacentCAROnly':not daily_failures,
 'benchmarkH5CoverageAtLeast90Pct':bool(matured5) and coverage>=.90,
 'summaryMatchesComputedCoverage':int(summary.get('maturedH5Records') or 0)==len(matured5) and int(summary.get('benchmarkH5Available') or 0)==len(bench5) and abs(float(summary.get('benchmarkH5Coverage') or 0.0)-coverage)<1e-12,
 'policyExactDate':policy.get('alignment')=='ORIGIN_TO_EXACT_STOCK_MATURITY_DATE',
 'policyExplicitlyAbstainsOnMissingBenchmark':'ABSTAIN_NOT_RAW_RETURN' in str(policy.get('missingBenchmark') or '') and 'ABSTAIN_NOT_RAW_RETURN' in str(policy.get('preEventMissingBenchmark') or ''),
}
out={'version':'VMEWS-VNINDEX-BENCHMARK-GATE-12.3.0','generatedAt':datetime.now(timezone.utc).isoformat(),'status':'PASS' if all(checks.values()) else 'FAIL','benchmark':'VNINDEX','checks':checks,'indexAudit':idx,'cacheFallbackAudit':cache_detail if idx.get('route')=='LAST_GOOD_INDEX_CACHE' else None,'frozenSourceAudit':frozen_detail if idx.get('route')=='VNSTOCK_INDEX_FROZEN_SNAPSHOT' else None,'maturedH5Records':len(matured5),'benchmarkH5Available':len(bench5),'benchmarkH5Coverage':coverage,'identityFailures':identity_failures[:50],'semanticFailures':semantic_failures[:50],'targetAlignmentFailures':target_failures[:50],'preEventFailures':pre_failures[:50],'dailyARFailures':daily_failures[:50],'policy':'Event identity is ticker+newsId. Abnormal returns are VNINDEX-relative from event origin to the exact stock maturity date. Missing post/pre benchmark observations abstain; raw stock returns are never substituted or relabelled as abnormal returns. Live/cache routes remain audited; immutable research-frozen VNINDEX is accepted only when the merged index audit exactly agrees with the PASS network-free, provider-switch-free frozen-source probe and certified snapshot hashes.'}
(DATA/'benchmark-gate-v12.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False,indent=2));raise SystemExit(0 if out['status']=='PASS' else 1)
