import json, math, os, pathlib, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
import backfill_flow_v11 as src

ROOT=pathlib.Path(os.environ.get('GITHUB_WORKSPACE','.')).resolve();DATA=ROOT/'data';VERSION='VMEWS-FLOW-12.0.0';VN_TZ=timezone(timedelta(hours=7))
MAX_WORKERS=int(os.environ.get('V12_FLOW_WORKERS','6'))

def manifest_symbols():
    z=json.loads((DATA/'hose-fallbacks'/'manifest.json').read_text(encoding='utf-8'));return sorted(s for s,r in (z.get('routes') or {}).items() if int((r or {}).get('rows') or 0)>=520)

def nz(x,keys):return any(abs(float(x.get(k,0) or 0))>1e-9 for k in keys)
def audit_symbol(rows,route):
    rows=sorted({str(x.get('date'))[:10]:x for x in rows if x.get('date')}.values(),key=lambda x:x['date']);fk=['foreignBuyValue','foreignSellValue','foreignNetValue'];pk=['propBuyValue','propSellValue','propNetValue'];fr=[x for x in rows if nz(x,fk)];pr=[x for x in rows if nz(x,pk)];dates=[x['date'] for x in rows]
    return rows,{
        'rows':len(rows),'first':dates[0] if dates else None,'last':dates[-1] if dates else None,'duplicateDates':0,
        'foreignNonzeroRows':len(fr),'foreignFirst':fr[0]['date'] if fr else None,'foreignLast':fr[-1]['date'] if fr else None,
        'propNonzeroRows':len(pr),'propFirst':pr[0]['date'] if pr else None,'propLast':pr[-1]['date'] if pr else None,
        'route':route,
    }

def one(symbol):
    s,rows,route=src.one(symbol);clean,a=audit_symbol(rows,route);return s,clean,a

def main():
    syms=manifest_symbols();store={};aud={};fail={};today=datetime.now(VN_TZ).date().isoformat()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fs={ex.submit(one,s):s for s in syms}
        for i,f in enumerate(as_completed(fs),1):
            s=fs[f]
            try:
                symbol,rows,a=f.result();future=[x['date'] for x in rows if x['date']>today]
                if future:raise RuntimeError(f'future flow rows: {future[:3]}')
                store[symbol]=rows;aud[symbol]=a
            except BaseException as e:fail[s]=f'{type(e).__name__}: {e}'[:600]
            if i%25==0 or i==len(syms):print(json.dumps({'v12FlowProgress':i,'total':len(syms),'passed':len(store),'failed':len(fail),'foreign100':sum(x.get('foreignNonzeroRows',0)>=100 for x in aud.values()),'prop100':sum(x.get('propNonzeroRows',0)>=100 for x in aud.values())}),flush=True)
    foreign100=sum(x.get('foreignNonzeroRows',0)>=100 for x in aud.values());prop100=sum(x.get('propNonzeroRows',0)>=100 for x in aud.values());foreign_any=sum(x.get('foreignNonzeroRows',0)>0 for x in aud.values());prop_any=sum(x.get('propNonzeroRows',0)>0 for x in aud.values());prop_lens=[x.get('propNonzeroRows',0) for x in aud.values() if x.get('propNonzeroRows',0)>0];foreign_lens=[x.get('foreignNonzeroRows',0) for x in aud.values() if x.get('foreignNonzeroRows',0)>0]
    summary={
        'requested':len(syms),'passed':len(store),'failed':len(fail),'routeCoverage':len(store)/max(1,len(syms)),
        'foreignAny':foreign_any,'foreignCoverage':foreign_any/max(1,len(syms)),'foreign100plus':foreign100,'foreign100Coverage':foreign100/max(1,len(syms)),
        'propAny':prop_any,'propCoverage':prop_any/max(1,len(syms)),'prop100plus':prop100,'prop100Coverage':prop100/max(1,len(syms)),
        'foreignMedianNonzeroRows':statistics.median(foreign_lens) if foreign_lens else 0,'propMedianNonzeroRows':statistics.median(prop_lens) if prop_lens else 0,
        'todayVN':today,
    }
    # Production suitability is evidence-based. Flow can exist with partial stock coverage; missingness stays explicit in model features.
    summary['status']='PASS' if summary['routeCoverage']>=.90 and summary['foreignCoverage']>=.40 and summary['propCoverage']>=.25 and prop100>=80 else 'FAIL'
    out={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'availabilityPolicy':'Completed-EOD only. Observation dated T is eligible for a forecast produced after the close of session T; no forward filling before first genuine observation.','source':'CafeF historical foreign/proprietary trading: export XLSX primary, paged JSON fallback','sourceRole':'PIT EOD institutional-flow archive used because community VNStock Market does not expose sponsor foreign_flow/proprietary_flow methods on the production runner. VNStock remains primary OHLCV source.','symbols':store,'summary':summary,'sourceAudit':aud,'failures':fail}
    audit={'version':'VMEWS-FLOW-AUDIT-12.0.0','generatedAt':out['generatedAt'],'summary':summary,'source':out['source'],'availabilityPolicy':out['availabilityPolicy'],'symbols':aud,'failures':fail}
    DATA.mkdir(parents=True,exist_ok=True);(DATA/'flow-v12.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8');(DATA/'flow-audit-v12.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');print(json.dumps({'v12FlowComplete':summary},ensure_ascii=False),flush=True)
    if summary['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
