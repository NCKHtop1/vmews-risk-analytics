import json,pathlib
from datetime import datetime,timezone
import backfill_flow_v11 as src
SYMBOLS=['FPT','VCB','HPG']
OUT=pathlib.Path('data/v12-flow-deep-probe.json')

def stats(rows,kind):
    keys=['foreignBuyValue','foreignSellValue','foreignNetValue'] if kind=='foreign' else ['propBuyValue','propSellValue','propNetValue'];nz=[x for x in rows if any(abs(float(x.get(k,0) or 0))>1e-9 for k in keys)];return {'rows':len(rows),'first':rows[0]['date'] if rows else None,'last':rows[-1]['date'] if rows else None,'nonzero':len(nz)}
def main():
    out={'version':'VMEWS-FLOW-DEEP-PROBE-12.0.0','generatedAt':datetime.now(timezone.utc).isoformat(),'symbols':{}}
    for s in SYMBOLS:
        z={}
        for kind in ['foreign','prop']:
            try:x=src.export_rows(s,kind);z[kind+'Export']=stats(x,kind)
            except BaseException as e:z[kind+'Export']={'error':f'{type(e).__name__}: {e}'}
            try:j=src.json_rows(s,kind);z[kind+'Json']=stats(j,kind)
            except BaseException as e:z[kind+'Json']={'error':f'{type(e).__name__}: {e}'}
        out['symbols'][s]=z;print(json.dumps({'deepFlow':s,**z},ensure_ascii=False),flush=True)
    j=[z.get('foreignJson',{}).get('rows',0) for z in out['symbols'].values()];out['status']='PASS' if sum(x>=500 for x in j)>=2 else 'FAIL';OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'v12FlowDeepProbe':out['status']},flush=True));raise SystemExit(0 if out['status']=='PASS' else 1)
if __name__=='__main__':main()
