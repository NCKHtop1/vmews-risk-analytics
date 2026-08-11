import json, pathlib, importlib.util
from datetime import datetime, timezone

ROOT=pathlib.Path(__file__).resolve().parents[1]
core_path=ROOT/'api'/'stocks.py'
spec=importlib.util.spec_from_file_location('vmews_market_core',core_path)
core=importlib.util.module_from_spec(spec); spec.loader.exec_module(core)

CANDIDATES=['^VNINDEX.VN','0P0000HY8X.VN','VNINDEX.VN']

def main():
    errors=[]; market=None
    for ticker in CANDIDATES:
        try:
            rows,meta,host=core.yahoo_chart(ticker,'10y',15)
            cur,hz,_=core.technical_state(rows)
            a=hz['20']
            score=.65*cur['technical']+.35*(a['score'] if a.get('available') else 50)
            market={
                'score':score,'available':True,'technical':cur['technical'],'analog20':a,
                'date':cur['date'],'ticker':ticker,'rows':len(rows),
                'source':'Yahoo Finance','provider':host,
                'audit':[{'source':'Yahoo Finance','provider':host,'symbol':ticker,'rows':len(rows),'ok':True}]
            }
            break
        except Exception as e:
            errors.append({'ticker':ticker,'error':str(e)[:300]})
    payload={
        'generatedAt':datetime.now(timezone.utc).isoformat(),
        'market':market,
        'candidates':CANDIDATES,
        'errors':errors,
        'method':'Independent VNINDEX EOD context snapshot; Yahoo primary with alternate Yahoo benchmark fallback; same technical/analog methodology as VMEWS core.'
    }
    p=ROOT/'data'/'market-context.json'; p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    if not market: raise SystemExit('No VNINDEX market candidate returned usable history')

if __name__=='__main__': main()
