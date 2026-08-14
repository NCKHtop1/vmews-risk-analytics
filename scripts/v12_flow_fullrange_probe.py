import json,pathlib
from datetime import datetime,timezone
import backfill_flow_v11 as src
OUT=pathlib.Path('data/v12-flow-fullrange-probe.json')
def stats(rows,kind):
    keys=['foreignBuyValue','foreignSellValue','foreignNetValue'] if kind=='foreign' else ['propBuyValue','propSellValue','propNetValue'];nz=[x for x in rows if any(abs(float(x.get(k,0) or 0))>1e-9 for k in keys)];return {'rows':len(rows),'first':rows[0]['date'] if rows else None,'last':rows[-1]['date'] if rows else None,'nonzero':len(nz)}
def main():
    old=(src.START,src.END);src.START='01/01/2018';src.END='08/14/2026';out={'version':'VMEWS-FLOW-FULLRANGE-PROBE-12.0.0','generatedAt':datetime.now(timezone.utc).isoformat(),'dateContract':'MM/DD/YYYY','symbols':{}}
    try:
        for s in ['FPT','VCB','HPG']:
            z={}
            for kind in ['foreign','prop']:
                try:r=src.export_rows(s,kind);z[kind+'Export']=stats(r,kind)
                except BaseException as e:z[kind+'Export']={'error':f'{type(e).__name__}: {e}'}
                if z[kind+'Export'].get('rows',0)<500:
                    try:j=src.json_rows(s,kind);z[kind+'Json']=stats(j,kind)
                    except BaseException as e:z[kind+'Json']={'error':f'{type(e).__name__}: {e}'}
            out['symbols'][s]=z;print(json.dumps({'fullFlow':s,**z},ensure_ascii=False),flush=True)
    finally:src.START,src.END=old
    foreign=[max(z.get('foreignExport',{}).get('rows',0),z.get('foreignJson',{}).get('rows',0)) for z in out['symbols'].values()];prop=[max(z.get('propExport',{}).get('rows',0),z.get('propJson',{}).get('rows',0)) for z in out['symbols'].values()];out['status']='PASS' if min(foreign)>=1000 and min(prop)>=500 else 'FAIL';OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'v12FullRangeFlowProbe':out['status'],'foreign':foreign,'prop':prop},flush=True));raise SystemExit(0 if out['status']=='PASS' else 1)
if __name__=='__main__':main()
