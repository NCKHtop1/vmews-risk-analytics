import json,pathlib,requests
from datetime import datetime,timezone
from vnstock.explorer.vci.const import _GRAPHQL_URL
from vnstock.core.utils.user_agent import get_headers
OUT=pathlib.Path('data/v12-active-flow-probe.json')
SYMBOLS=['FPT','VCB','HPG','MBB','SSI']
QUERY='''query Query($ticker: String!, $offset: Int!, $limit: Int!, $fromDate: String!, $toDate: String!) { TickerPriceHistory(ticker: $ticker, offset: $offset, limit: $limit, fromDate: $fromDate, toDate: $toDate) { history { tradingDate totalBuyTrade totalBuyTradeVolume totalSellTrade totalSellTradeVolume unMatchedBuyTradeVolume unMatchedSellTradeVolume difVolumeBuySell totalMatchVolume totalMatchValue } totalRecords __typename } }'''
def fetch(symbol):
    payload={'query':QUERY,'variables':{'ticker':symbol,'offset':0,'limit':5000,'fromDate':'2018-01-01','toDate':'2026-08-14'}}
    headers=get_headers(data_source='VCI');headers={**headers,'Content-Type':'application/json'}
    r=requests.post(_GRAPHQL_URL,data=json.dumps(payload),headers=headers,timeout=30);text=r.text;r.raise_for_status()
    try:z=r.json()
    except BaseException as e:raise RuntimeError(f'non-JSON response status={r.status_code} body={text[:800]}') from e
    if z.get('errors'):raise RuntimeError(f"GraphQL errors={z.get('errors')} body={text[:1200]}")
    if 'data' not in z:raise RuntimeError(f"VCI response missing data status={r.status_code} keys={list(z)[:20]} body={text[:1200]}")
    box=(z.get('data') or {}).get('TickerPriceHistory') or {};rows=box.get('history') or []
    dates=[];nonzero=0;buy_sell=0
    for x in rows:
        t=x.get('tradingDate')
        if isinstance(t,(int,float)):dates.append(datetime.fromtimestamp(t/1000,timezone.utc).date().isoformat())
        vals=[x.get('totalBuyTrade'),x.get('totalBuyTradeVolume'),x.get('totalSellTrade'),x.get('totalSellTradeVolume'),x.get('difVolumeBuySell')]
        if any(isinstance(v,(int,float)) and abs(v)>0 for v in vals):nonzero+=1
        if isinstance(x.get('totalBuyTradeVolume'),(int,float)) and isinstance(x.get('totalSellTradeVolume'),(int,float)):buy_sell+=1
    return {'httpStatus':r.status_code,'rows':len(rows),'totalRecords':box.get('totalRecords'),'first':min(dates) if dates else None,'last':max(dates) if dates else None,'nonzeroRows':nonzero,'buySellRows':buy_sell,'sample':rows[:2]}
def main():
    out={'version':'VMEWS-ACTIVE-FLOW-PROBE-12.1.0','generatedAt':datetime.now(timezone.utc).isoformat(),'source':'VCI TickerPriceHistory','requestContract':'POST raw JSON body + VCI headers','symbols':{}}
    for s in SYMBOLS:
        try:out['symbols'][s]={'ok':True,**fetch(s)}
        except BaseException as e:out['symbols'][s]={'ok':False,'error':f'{type(e).__name__}: {e}'}
        print(json.dumps({'activeFlowProbe':s,**out['symbols'][s]},ensure_ascii=False),flush=True)
    good=[x for x in out['symbols'].values() if x.get('ok') and x.get('rows',0)>=1000 and x.get('buySellRows',0)>=500]
    out['status']='PASS' if len(good)>=4 else 'FAIL';OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');print(json.dumps({'v12ActiveFlowProbe':out['status'],'good':len(good)},flush=True));raise SystemExit(0 if out['status']=='PASS' else 1)
if __name__=='__main__':main()
