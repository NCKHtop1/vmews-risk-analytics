import argparse,json,math,pathlib
from datetime import datetime,timezone
from v12_data_sources import get_price_history,get_index_history
def main():
    ap=argparse.ArgumentParser();ap.add_argument('symbols',nargs='*',default=['FPT','VCB','HPG','FRT','PNJ','VIC','MBB']);args=ap.parse_args();report={'version':'VMEWS-V12-SOURCE-PROBE-1.0.0','generatedAt':datetime.now(timezone.utc).isoformat(),'symbols':{}};passed=0
    for s in args.symbols:
        try:
            rows,audit=get_price_history(s);model=[float(x.get('modelClose',x['close'])) for x in rows];bad=sum(a>0 and b>0 and abs(math.log(b/a))>.24 for a,b in zip(model[:-1],model[1:]));z={'ok':len(rows)>=520 and bad==0,'rows':len(rows),'start':rows[0]['date'],'end':rows[-1]['date'],'route':audit.get('route'),'corporateAction':audit.get('corporateAction'),'crossSourceReturnMAD':audit.get('crossSourceReturnMAD'),'unexplainedModelJumps':bad};report['symbols'][s]=z;passed+=z['ok']
        except BaseException as exc:report['symbols'][s]={'ok':False,'error':f'{type(exc).__name__}: {exc}'}
    try:
        rows,audit=get_index_history('VNINDEX');report['index']={'ok':len(rows)>=520,'rows':len(rows),'start':rows[0]['date'],'end':rows[-1]['date'],'route':audit.get('route')}
    except BaseException as exc:report['index']={'ok':False,'error':f'{type(exc).__name__}: {exc}'}
    report['passed']=passed;report['total']=len(args.symbols);pathlib.Path('data/v12-source-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(1 if passed<max(5,len(args.symbols)-1) or not report['index'].get('ok') else 0)
if __name__=='__main__':main()
