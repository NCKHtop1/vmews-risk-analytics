import json,math,os,pathlib,re,time
from datetime import datetime,timezone

ROOT=pathlib.Path(os.environ.get('GITHUB_WORKSPACE','.')).resolve()
OUT=ROOT/'data'/'current-context-v12.json'
FOCUS=[x.strip().upper() for x in os.environ.get('V12_CONTEXT_SYMBOLS','FPT,VCB,HPG,MBB,FRT,PNJ,VNM,SSI').split(',') if x.strip()]

def finite(v):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None

def load(path):return json.loads(path.read_text(encoding='utf-8'))
def serial(v):
    if v is None:return None
    try:
        if hasattr(v,'isoformat'):return v.isoformat()
    except Exception:pass
    x=finite(v)
    return x if x is not None else str(v)

def quarter_key(s):
    m=re.search(r'(20\d{2})[-_/ ]?Q([1-4])',str(s),re.I)
    return (int(m.group(1)),int(m.group(2))) if m else None

def latest_period_col(df):
    if df is None or getattr(df,'empty',True):return None
    cand=[]
    for c in df.columns:
        q=quarter_key(c)
        if q:cand.append((q,str(c)))
    if cand:return max(cand,key=lambda x:x[0])[1]
    return None

def previous_period_col(df,current):
    if df is None or current is None:return None
    uq={}
    for c in df.columns:
        q=quarter_key(c)
        if q and q not in uq:uq[q]=str(c)
    keys=sorted(uq)
    cur=quarter_key(current)
    if cur in keys:
        i=keys.index(cur)
        if i>0:return uq[keys[i-1]]
    return None

def row_map(df):
    out=[]
    if df is None:return out
    try:
        for _,r in df.iterrows():
            d={str(k):serial(v) for k,v in r.to_dict().items()};out.append(d)
    except Exception:pass
    return out

def find_metric(rows,col,ids=(),patterns=()):
    ids={x.lower() for x in ids}
    for r in rows:
        rid=str(r.get('item_id') or '').strip().lower();label=str(r.get('item') or '').strip().lower()
        if rid in ids or any(p.lower() in label for p in patterns):
            v=finite(r.get(col))
            if v is not None:return {'value':v,'itemId':rid or None,'label':r.get('item')}
    return None

def growth(cur,prev):
    a=finite(cur);b=finite(prev)
    return (a/b-1.0) if a is not None and b not in (None,0) else None

def summarize_fundamental(symbol,fe):
    def safe(name,fn):
        try:
            time.sleep(1.3);return fn(),None
        except BaseException as e:return None,f'{type(e).__name__}: {e}'[:400]
    ratio,er=safe('ratio',lambda:fe.ratios(period='quarter'))
    income,ei=safe('income',lambda:fe.income_statement(period='quarter'))
    balance,eb=safe('balance',lambda:fe.balance_sheet(period='quarter'))
    cash,ec=safe('cash',lambda:fe.cash_flow(period='quarter'))
    rp=latest_period_col(ratio);ip=latest_period_col(income);bp=latest_period_col(balance);cp=latest_period_col(cash)
    rrows=row_map(ratio);irows=row_map(income);brows=row_map(balance);crows=row_map(cash)
    prev_i=previous_period_col(income,ip);prev_r=previous_period_col(ratio,rp)
    revenue=find_metric(irows,ip,['revenue'],['doanh thu bán hàng','doanh thu thuần']) if ip else None
    revenue_prev=find_metric(irows,prev_i,['revenue'],['doanh thu bán hàng','doanh thu thuần']) if prev_i else None
    profit=find_metric(irows,ip,['profit_after_tax','net_profit','net_profit_after_tax'],['lợi nhuận sau thuế','lợi nhuận sau thuế thu nhập doanh nghiệp']) if ip else None
    profit_prev=find_metric(irows,prev_i,['profit_after_tax','net_profit','net_profit_after_tax'],['lợi nhuận sau thuế','lợi nhuận sau thuế thu nhập doanh nghiệp']) if prev_i else None
    def rm(ids,pats):return find_metric(rrows,rp,ids,pats) if rp else None
    metrics={
      'eps':rm(['trailing_eps','eps'],['eps','thu nhập trên mỗi cổ phần']),
      'pe':rm(['pe','price_to_earnings'],['p/e','pe ']),
      'pb':rm(['pb','price_to_book'],['p/b','pb ']),
      'roe':rm(['roe'],['roe','lợi nhuận trên vốn chủ']),
      'roa':rm(['roa'],['roa','lợi nhuận trên tài sản']),
      'debtToEquity':rm(['debt_to_equity','debt_equity'],['nợ/vốn chủ','debt/equity']),
      'netMargin':rm(['net_profit_margin','net_margin'],['biên lợi nhuận ròng','net margin']),
    }
    metrics={k:v for k,v in metrics.items() if v is not None}
    return {
      'status':'PASS' if (rp or ip) else 'REVIEW',
      'ratioPeriod':rp,'incomePeriod':ip,'balancePeriod':bp,'cashflowPeriod':cp,
      'revenue':revenue,'revenueQoQ':growth(revenue and revenue['value'],revenue_prev and revenue_prev['value']),
      'profitAfterTax':profit,'profitQoQ':growth(profit and profit['value'],profit_prev and profit_prev['value']),
      'ratios':metrics,
      'publicationTimestampCertified':False,
      'numericalModelEligible':False,
      'modelPolicy':'CURRENT_DESCRIPTIVE_ONLY_UNTIL_FILING_PUBLICATION_TIMESTAMP_ARCHIVE_EXISTS',
      'errors':{k:v for k,v in {'ratio':er,'income':ei,'balance':eb,'cashflow':ec}.items() if v},
    }

def typed_flow(rows,typ,asof):
    key=typ+'NetValue';buy=typ+'BuyValue';sell=typ+'SellValue'
    a=[r for r in (rows or []) if str(r.get('date') or '')[:10]<=asof and any(k in r for k in (key,buy,sell))]
    a.sort(key=lambda r:str(r.get('date') or ''))
    if not a:return {'available':False}
    def val(r,k):return finite(r.get(k)) or 0.0
    latest=a[-1]
    return {'available':True,'latestDate':str(latest.get('date'))[:10],'net1':val(latest,key),'buy1':val(latest,buy),'sell1':val(latest,sell),'net5':sum(val(r,key) for r in a[-5:]),'net20':sum(val(r,key) for r in a[-20:]),'observations':len(a),'staleSessionsApprox':max(0,len({str(r.get('date'))[:10] for r in a if str(r.get('date'))[:10]>str(latest.get('date'))[:10]}))}

def main():
    dash=load(ROOT/'data'/'forecast-dashboard-v12.json');flow=load(ROOT/'data'/'flow-v12.json');asof=str(dash.get('asOf') or '')[:10]
    out={'version':'VMEWS-CURRENT-CONTEXT-12.3.0','generatedAt':datetime.now(timezone.utc).isoformat(),'forecastAsOf':asof,'symbols':{},'governance':{'flow':'Raw completed-EOD values are shown with their own latest source date; missing/stale proprietary data is never converted to zero.','fundamental':'VNStock period statements and ratios are shown as current descriptive context. They are not historical numerical forecast features until filing/publication availability timestamps are independently audited.','sponsorLayer':'vnstock_data sponsor-only market endpoints are not assumed available on the public CI runner.'}}
    from vnstock import Fundamental
    for s in FOCUS:
        if s not in (dash.get('symbols') or {}):continue
        rows=(flow.get('symbols') or {}).get(s) or []
        flowz={'foreign':typed_flow(rows,'foreign',asof),'proprietary':typed_flow(rows,'prop',asof)}
        try:fund=summarize_fundamental(s,Fundamental().equity(s))
        except BaseException as e:fund={'status':'REVIEW','publicationTimestampCertified':False,'numericalModelEligible':False,'modelPolicy':'CURRENT_DESCRIPTIVE_ONLY_UNTIL_FILING_PUBLICATION_TIMESTAMP_ARCHIVE_EXISTS','errors':{'init':f'{type(e).__name__}: {e}'[:400]}}
        out['symbols'][s]={'flow':flowz,'fundamental':fund}
        print(json.dumps({'context':s,'flow':flowz,'fundamentalStatus':fund.get('status'),'period':fund.get('ratioPeriod') or fund.get('incomePeriod')},ensure_ascii=False),flush=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'currentContext':'PASS','symbols':len(out['symbols']),'path':str(OUT)},ensure_ascii=False))
if __name__=='__main__':main()
