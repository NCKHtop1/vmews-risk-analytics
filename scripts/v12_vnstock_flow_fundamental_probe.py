import importlib.metadata
import json
import math
import pathlib
import traceback
from datetime import datetime, timezone

from v12_data_sources import _cross_source_mad, _normalize_df, _provider_history, _throttle_vnstock

OUT=pathlib.Path('data/v12-vnstock-flow-fundamental-probe.json')
SYMBOLS=['FPT','VCB','HPG']
SCHEMA_SYMBOL='FPT'
START='2025-01-01'
END='2026-08-16'
MAD_LIMIT=0.003
STABLE_VERSION='4.0.4'

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
    date_cols=[c for c in cols if any(k in c.lower() for k in ['date','time','period','report','publish','filing','announce','release','year','quarter'])]
    publication_cols=[c for c in cols if any(k in c.lower() for k in ['publish','filing','announce','release','disclosure'])]
    ranges={}
    for c in date_cols:
        try:
            vals=[serial(x) for x in df[c].dropna().tolist()]
            if vals:ranges[c]={'first':vals[0],'last':vals[-1],'unique':len(set(map(str,vals)))}
        except Exception:pass
    return {'rows':int(len(df)),'columns':cols,'dateLikeColumns':date_cols,'publicationTimestampColumns':publication_cols,'publicationTimestampPresent':bool(publication_cols),'ranges':ranges,'sample':sample}

def call(label,fn):
    try:
        _throttle_vnstock()
        return {'ok':True,**frame_summary(fn())}
    except BaseException as e:return {'ok':False,'error':f'{type(e).__name__}: {e}','traceback':traceback.format_exc()[-2500:]}

def normalized(label,fn,symbol):
    try:
        _throttle_vnstock();df=fn();rows,scale=_normalize_df(df,symbol,label)
        return {'ok':True,'rows':len(rows),'start':rows[0]['date'],'end':rows[-1]['date'],'scale':scale,'history':rows}
    except BaseException as e:return {'ok':False,'error':f'{type(e).__name__}: {e}','traceback':traceback.format_exc()[-2500:]}

def strip_history(z):return {k:v for k,v in z.items() if k!='history'}

def main():
    version=importlib.metadata.version('vnstock')
    out={'version':'VMEWS-VNSTOCK-PIT-PROBE-12.2.0','generatedAt':datetime.now(timezone.utc).isoformat(),'vnstockVersion':version,'stableVersionExpected':STABLE_VERSION,'marketWindow':{'start':START,'end':END},'symbols':{}}
    from vnstock.ui import Market
    from vnstock import Fundamental
    market=Market();consensus_pass=0
    for s in SYMBOLS:
        unified=normalized('Unified Market',lambda s=s:market.equity(s).ohlcv(start=START,end=END,interval='1D',count=500),s)
        explicit={}
        for provider in ('VCI','KBS'):
            try:
                rows,audit=_provider_history(s,provider,START,END);explicit[provider]={'ok':True,'rows':len(rows),'start':rows[0]['date'],'end':rows[-1]['date'],'history':rows,'provider':audit.get('provider'),'api':audit.get('api')}
            except BaseException as e:explicit[provider]={'ok':False,'error':f'{type(e).__name__}: {e}'}
        pairs={}
        if unified.get('ok'):
            for provider,z in explicit.items():
                if z.get('ok'):
                    mad,n=_cross_source_mad(unified['history'],z['history']);pairs[f'UNIFIED_vs_{provider}']={'mad':mad,'common':n,'pass':mad is not None and n>=60 and mad<=MAD_LIMIT}
        if explicit.get('VCI',{}).get('ok') and explicit.get('KBS',{}).get('ok'):
            mad,n=_cross_source_mad(explicit['VCI']['history'],explicit['KBS']['history']);pairs['VCI_vs_KBS']={'mad':mad,'common':n,'pass':mad is not None and n>=60 and mad<=MAD_LIMIT}
        source_consensus=bool(unified.get('ok')) and any(x.get('pass') for x in pairs.values());consensus_pass+=int(source_consensus)
        out['symbols'][s]={'sourceConsensus':{'status':'PASS' if source_consensus else 'REVIEW','unified':strip_history(unified),'providers':{k:strip_history(v) for k,v in explicit.items()},'pairs':pairs}}
        print(json.dumps({'symbol':s,'sourceConsensus':out['symbols'][s]['sourceConsensus']},ensure_ascii=False),flush=True)
    eq=market.equity(SCHEMA_SYMBOL);fe=Fundamental().equity(SCHEMA_SYMBOL)
    schema={
        'foreignFlow':call('foreign',lambda:eq.foreign_flow()),
        'proprietaryFlow':call('prop',lambda:eq.proprietary_flow()),
        'sessionStats':call('session',lambda:eq.session_stats()),
        'tradeHistory':call('trade',lambda:eq.trade_history(start='2024-01-01',end='2026-08-14')),
        'incomeQuarter':call('income',lambda:fe.income_statement(period='quarter')),
        'balanceQuarter':call('balance',lambda:fe.balance_sheet(period='quarter')),
        'cashflowQuarter':call('cashflow',lambda:fe.cash_flow(period='quarter')),
        'ratiosQuarter':call('ratios',lambda:fe.ratios(period='quarter')),
    }
    financial=[schema[k] for k in ['incomeQuarter','balanceQuarter','cashflowQuarter','ratiosQuarter']]
    publication_evidence=any(z.get('publicationTimestampPresent') for z in financial if z.get('ok'))
    out['schemaProbe']={'symbol':SCHEMA_SYMBOL,**schema,'financialPublicationTimestampEvidence':publication_evidence,'numericalAccountingPITRecommendation':'ELIGIBLE_FOR_FURTHER_VALIDATION' if publication_evidence else 'KEEP_BLOCKED'}
    out['summary']={'status':'PASS' if version==STABLE_VERSION and consensus_pass>=2 else 'FAIL','stableVersionPinned':version==STABLE_VERSION,'sourceConsensusPassed':consensus_pass,'sourceConsensusTotal':len(SYMBOLS),'madLimit':MAD_LIMIT,'explicitProviderApi':'vnstock.api.quote.Quote','financialPublicationTimestampEvidence':publication_evidence}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'v12VNStockPITProbe':out['summary'],'path':str(OUT)},ensure_ascii=False),flush=True)
    raise SystemExit(0 if out['summary']['status']=='PASS' else 1)
if __name__=='__main__':main()
