import json
import math
import pathlib
from datetime import datetime, timezone

DATA=pathlib.Path('data')
audit=json.loads((DATA/'data-audit-v12.json').read_text(encoding='utf-8'))
event=json.loads((DATA/'event-intelligence-v12.json').read_text(encoding='utf-8'))
records=event.get('records') or [];summary=event.get('summary') or {};idx=audit.get('index') or {}

def finite(v):return isinstance(v,(int,float)) and math.isfinite(float(v))
def valid_cache_route():
    if idx.get('route')!='LAST_GOOD_INDEX_CACHE':return False,{}
    p=DATA/'vnindex-v12.json'
    if not p.exists():return False,{'reason':'cache file missing'}
    try:z=json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:return False,{'reason':str(e)}
    s=z.get('summary') or {};ok=str(z.get('version','')).startswith('VMEWS-VNINDEX-CACHE-12') and int(s.get('rows') or 0)>=520 and int(s.get('duplicateDates') or -1)==0 and float(s.get('maxAbsLogJump') or 99)<=.12 and idx.get('cacheVersion')==z.get('version') and int(idx.get('rows') or 0)==int(s.get('rows') or 0) and str(idx.get('cacheLastDate') or '')==str(s.get('last') or '')
    return bool(ok),{'version':z.get('version'),'summary':s,'indexAudit':idx}

cache_ok,cache_detail=valid_cache_route();live_route=idx.get('route') in {'VNSTOCK_INDEX_PRIMARY','YAHOO_INDEX_FALLBACK'}
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
 'indexRouteExplicitAndAudited':live_route or cache_ok,
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
out={'version':'VMEWS-VNINDEX-BENCHMARK-GATE-12.2.0','generatedAt':datetime.now(timezone.utc).isoformat(),'status':'PASS' if all(checks.values()) else 'FAIL','benchmark':'VNINDEX','checks':checks,'indexAudit':idx,'cacheFallbackAudit':cache_detail if idx.get('route')=='LAST_GOOD_INDEX_CACHE' else None,'maturedH5Records':len(matured5),'benchmarkH5Available':len(bench5),'benchmarkH5Coverage':coverage,'identityFailures':identity_failures[:50],'semanticFailures':semantic_failures[:50],'targetAlignmentFailures':target_failures[:50],'preEventFailures':pre_failures[:50],'dailyARFailures':daily_failures[:50],'policy':'Event identity is ticker+newsId. Abnormal returns are VNINDEX-relative from event origin to the exact stock maturity date. Missing post/pre benchmark observations abstain; raw stock returns are never substituted or relabelled as abnormal returns. Audited VNINDEX cache is accepted only when its integrity contract matches the training index audit.'}
(DATA/'benchmark-gate-v12.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False,indent=2));raise SystemExit(0 if out['status']=='PASS' else 1)
