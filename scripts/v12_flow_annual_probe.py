import json,pathlib
from datetime import datetime,timezone
import backfill_flow_v11 as src
OUT=pathlib.Path('data/v12-flow-annual-probe.json')
WINDOWS=[('01/01/2023','12/31/2023'),('01/01/2024','12/31/2024'),('01/01/2025','12/31/2025')]
def main():
    old=(src.START,src.END);out={'version':'VMEWS-FLOW-ANNUAL-PROBE-12.0.0','generatedAt':datetime.now(timezone.utc).isoformat(),'symbols':{}}
    try:
        for s in ['FPT','VCB','HPG']:
            arr=[]
            for a,b in WINDOWS:
                src.START=a;src.END=b
                try:r=src.json_rows(s,'foreign')
                except BaseException:r=[]
                arr.append({'start':a,'end':b,'rows':len(r),'first':r[0]['date'] if r else None,'last':r[-1]['date'] if r else None})
            out['symbols'][s]=arr;print(json.dumps({'annualFlow':s,'windows':arr},ensure_ascii=False),flush=True)
    finally:src.START,src.END=old
    good=sum(1 for arr in out['symbols'].values() for z in arr if z['rows']>=180 and z['first'] and z['first'][:4]==z['start'][-4:] and z['last'] and z['last'][:4]==z['end'][-4:]);out['status']='PASS' if good>=8 else 'FAIL';OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'v12AnnualFlowProbe':out['status'],'good':good},flush=True));raise SystemExit(0 if out['status']=='PASS' else 1)
if __name__=='__main__':main()
