import json, pathlib, statistics
from datetime import datetime, timezone
import backfill_flow_v11 as src

SYMBOLS=['FPT','VCB','HPG','MBB','VIC','FRT','PNJ','SSI','VNM','STB']
OUT=pathlib.Path('data/v12-flow-probe.json')

def audit_rows(rows):
    dates=[x.get('date') for x in rows if x.get('date')]
    foreign=[x for x in rows if any(abs(float(x.get(k,0) or 0))>1e-9 for k in ['foreignBuyValue','foreignSellValue','foreignNetValue'])]
    prop=[x for x in rows if any(abs(float(x.get(k,0) or 0))>1e-9 for k in ['propBuyValue','propSellValue','propNetValue'])]
    return {
        'rows':len(rows),'first':min(dates) if dates else None,'last':max(dates) if dates else None,
        'uniqueDates':len(set(dates)),'duplicateDates':len(dates)-len(set(dates)),
        'foreignNonzeroRows':len(foreign),'propNonzeroRows':len(prop),
        'foreignFirst':min([x['date'] for x in foreign],default=None),'foreignLast':max([x['date'] for x in foreign],default=None),
        'propFirst':min([x['date'] for x in prop],default=None),'propLast':max([x['date'] for x in prop],default=None),
    }

def main():
    out={'version':'VMEWS-FLOW-PROBE-12.0.0','generatedAt':datetime.now(timezone.utc).isoformat(),'source':'CafeF historical trading export/JSON routes','symbols':{}}
    for s in SYMBOLS:
        try:
            sym,rows,audit=src.one(s);row_audit=audit_rows(rows);out['symbols'][s]={'ok':True,'routeAudit':audit,'rowAudit':row_audit}
        except BaseException as e:
            out['symbols'][s]={'ok':False,'error':f'{type(e).__name__}: {e}'}
        print(json.dumps({'flowProbe':s,**out['symbols'][s]},ensure_ascii=False),flush=True)
    good=[z for z in out['symbols'].values() if z.get('ok')]
    prop=[z['rowAudit']['propNonzeroRows'] for z in good];foreign=[z['rowAudit']['foreignNonzeroRows'] for z in good]
    out['summary']={
        'symbols':len(SYMBOLS),'ok':len(good),
        'symbolsForeign100plus':sum(x>=100 for x in foreign),'symbolsProp100plus':sum(x>=100 for x in prop),
        'foreignMedianNonzeroRows':statistics.median(foreign) if foreign else 0,
        'propMedianNonzeroRows':statistics.median(prop) if prop else 0,
        'status':'PASS' if len(good)>=8 and sum(x>=100 for x in foreign)>=7 and sum(x>=100 for x in prop)>=5 else 'FAIL'
    }
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'v12FlowProbe':out['summary']},ensure_ascii=False),flush=True)
    if out['summary']['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
