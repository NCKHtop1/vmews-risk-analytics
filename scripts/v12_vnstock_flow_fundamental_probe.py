import json, math, pathlib, traceback
from datetime import datetime, timezone

OUT=pathlib.Path('data/v12-vnstock-flow-fundamental-probe.json')
SYMBOLS=['FPT','VCB','HPG']

def serial(v):
    if v is None:return None
    try:
        if hasattr(v,'isoformat'):return v.isoformat()
    except Exception:pass
    try:
        x=float(v)
        if math.isfinite(x):return x
    except Exception:pass
    return str(v)

def frame_summary(df):
    if df is None:return {'rows':0,'columns':[]}
    cols=[str(c) for c in df.columns]
    sample=[]
    try:
        for _,r in df.head(3).iterrows():sample.append({str(k):serial(v) for k,v in r.to_dict().items()})
    except Exception:pass
    date_cols=[c for c in cols if any(k in c.lower() for k in ['date','time','period','report','publish','filing','year','quarter'])]
    ranges={}
    for c in date_cols:
        try:
            vals=[serial(x) for x in df[c].dropna().tolist()]
            if vals:ranges[c]={'first':vals[0],'last':vals[-1],'unique':len(set(map(str,vals)))}
        except Exception:pass
    return {'rows':int(len(df)),'columns':cols,'dateLikeColumns':date_cols,'ranges':ranges,'sample':sample}

def call(label,fn):
    try:return {'ok':True,**frame_summary(fn())}
    except BaseException as e:return {'ok':False,'error':f'{type(e).__name__}: {e}','traceback':traceback.format_exc()[-3000:]}

def main():
    out={'version':'VMEWS-VNSTOCK-PIT-PROBE-12.0.0','generatedAt':datetime.now(timezone.utc).isoformat(),'symbols':{}}
    from vnstock import Market, Fundamental
    market=Market();fund=Fundamental()
    for s in SYMBOLS:
        eq=market.equity(s);fe=fund.equity(s)
        out['symbols'][s]={
            'foreignFlow':call('foreign',lambda:eq.foreign_flow()),
            'proprietaryFlow':call('prop',lambda:eq.proprietary_flow()),
            'sessionStats':call('session',lambda:eq.session_stats()),
            'tradeHistory':call('trade',lambda:eq.trade_history(start='2024-01-01',end='2026-08-14')),
            'incomeQuarter':call('income',lambda:fe.income_statement(period='quarter')),
            'balanceQuarter':call('balance',lambda:fe.balance_sheet(period='quarter')),
            'cashflowQuarter':call('cashflow',lambda:fe.cash_flow(period='quarter')),
            'ratiosQuarter':call('ratios',lambda:fe.ratios(period='quarter')),
        }
        print(json.dumps({'symbol':s,'probe':{k:{'ok':v.get('ok'),'rows':v.get('rows'),'columns':v.get('columns')} for k,v in out['symbols'][s].items()}},ensure_ascii=False),flush=True)
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'v12VNStockPITProbe':'DONE','path':str(OUT)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
