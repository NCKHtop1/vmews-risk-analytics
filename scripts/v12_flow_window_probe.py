import json,pathlib
from datetime import datetime,timezone
import backfill_flow_v11 as src
OUT=pathlib.Path('data/v12-flow-window-probe.json')
WINDOWS=[('01/01/2023','03/31/2023'),('01/01/2024','03/31/2024'),('01/01/2025','03/31/2025'),('01/01/2026','03/31/2026'),('04/01/2026','06/30/2026')]
def main():
    old=(src.START,src.END);out={'version':'VMEWS-FLOW-WINDOW-PROBE-12.2.0','generatedAt':datetime.now(timezone.utc).isoformat(),'symbol':'FPT','dateContract':'CafeF GDKhoiNgoai StartDate/EndDate use MM/DD/YYYY','windows':[]};allrows=[]
    try:
        for a,b in WINDOWS:
            src.START=a;src.END=b
            try:r=src.json_rows('FPT','foreign');route='JSON_MMDDYYYY'
            except BaseException as e:r=[];route=f'JSON_ERROR:{type(e).__name__}:{e}'
            out['windows'].append({'start':a,'end':b,'rows':len(r),'first':r[0]['date'] if r else None,'last':r[-1]['date'] if r else None,'route':route});allrows.extend(r);print(json.dumps({'window':out['windows'][-1]},ensure_ascii=False),flush=True)
    finally:src.START,src.END=old
    ded={x['date']:x for x in allrows};out['merged']={'rows':len(ded),'first':min(ded) if ded else None,'last':max(ded) if ded else None};out['status']='PASS' if len(ded)>=200 and sum(x['rows']>=20 for x in out['windows'])>=4 else 'FAIL';OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'v12FlowWindowProbe':out},ensure_ascii=False),flush=True);raise SystemExit(0 if out['status']=='PASS' else 1)
if __name__=='__main__':main()
