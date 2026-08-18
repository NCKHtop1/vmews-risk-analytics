import gzip, json, pathlib, runpy
import v12_source_capture as capture
import v12_reference_resilience as resilience
import v12_universe as universe
from v12_reference_resilience import install as install_resilience
from v12_source_capture_methodfix import install as install_continuity
from v12_freeze_runtime_guard import install as install_runtime_guard

ROOT=pathlib.Path(__file__).resolve().parents[1];DATA=ROOT/'data';SNAP=DATA/'v12-frozen-source.json.gz';MAN=DATA/'v12-frozen-source-manifest.json';DIAG=DATA/'v12-source-freeze-diagnostic.json'


def _ca_cohort_stats(payload,min_rows):
    current=set(payload.get('currentHOSESymbols') or []);histories=payload.get('histories') or {};audits=payload.get('audits') or {}
    cohort=[];verified=[];truncated=[];truncated_short=[]
    for s in sorted(current & set(histories)):
        rows=histories.get(s) or [];a=audits.get(s) or {};orig=int(a.get('originalRows') or len(rows))
        if orig>=min_rows:
            cohort.append(s)
            if (a.get('corporateAction') or {}).get('verified') is True:verified.append(s)
        if a.get('historyContinuityPolicy')=='TRUNCATE_BEFORE_LAST_UNRESOLVED_GT_GUARD_BREAK':
            truncated.append(s)
            if len(rows)<min_rows:truncated_short.append(s)
    return {'cohort':cohort,'verified':verified,'ratio':len(verified)/max(1,len(cohort)),'truncated':truncated,'truncatedShort':truncated_short}


def _postvalidate_original_deep_ca_cohort():
    payload=json.loads(gzip.decompress(SNAP.read_bytes()).decode('utf-8'));m=json.loads(MAN.read_text(encoding='utf-8'));stats=_ca_cohort_stats(payload,capture.MIN_ROWS)
    retained_deep=int(m.get('deepHistory') or 0)
    if len(stats['cohort'])<retained_deep:raise RuntimeError(f'CA original-deep denominator shrank below retained-deep cohort: original={len(stats["cohort"])} retained={retained_deep}')
    fields={'corporateActionVerifiedRatio':stats['ratio'],'corporateActionVerifiedCount':len(stats['verified']),'corporateActionGateDenominator':len(stats['cohort']),'corporateActionGateCohort':'CURRENT_HOSE_ORIGINAL_DEEP_HISTORY_BEFORE_CONTINUITY_TRUNCATION','continuityTruncatedCount':len(stats['truncated']),'continuityTruncatedBelowMinRowsCount':len(stats['truncatedShort']),'continuityTruncatedSymbols':stats['truncated'],'continuityTruncatedBelowMinRows':stats['truncatedShort']}
    m.update(fields);MAN.write_text(json.dumps(m,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    if stats['ratio']<.98:
        d=json.loads(DIAG.read_text(encoding='utf-8')) if DIAG.exists() else {};d.update(fields);d['status']='FAIL';g=list(d.get('gateFailures') or []);g.append(f'corporate_action_verified_original_deep:{stats["ratio"]:.6f}={len(stats["verified"])}/{len(stats["cohort"])}<0.98');d['gateFailures']=g;DIAG.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');SNAP.unlink(missing_ok=True);MAN.unlink(missing_ok=True);raise RuntimeError(g[-1])
    print(json.dumps({'V12_CA_ORIGINAL_DEEP_COHORT_GATE':'PASS',**fields},ensure_ascii=False),flush=True)


def main():
    # Install continuity first so the VNStock-only wrapper audits the exact retained suffix.
    install_continuity()
    source_audit=install_resilience(capture,max_attempts=2,backoff_seconds=(2.0,))
    runtime_audit=install_runtime_guard(capture,universe,resilience,repo_root=ROOT)
    print({'v12ReferenceResilience':source_audit,'v12FreezeRuntimeGuard':runtime_audit,'v12ContinuityPolicy':'STRICT_POST_LAST_UNRESOLVED_GT_GUARD_SUFFIX_MIN_ROWS_UNCHANGED'},flush=True)
    runpy.run_path(str(pathlib.Path(__file__).with_name('freeze_v12_source_snapshot.py')),run_name='__main__')
    _postvalidate_original_deep_ca_cohort()

if __name__=='__main__':main()
