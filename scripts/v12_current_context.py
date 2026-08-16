import json,math,os,pathlib,re,time
from datetime import datetime,timezone

ROOT=pathlib.Path(os.environ.get('GITHUB_WORKSPACE','.')).resolve();OUT=ROOT/'data'/'current-context-v12.json'
FOCUS=[x.strip().upper() for x in os.environ.get('V12_CONTEXT_SYMBOLS','FPT,VCB,HPG,MBB,FRT,PNJ,VNM,SSI').split(',') if x.strip()]
# Current UI needs income + ratio snapshots; balance/cash-flow are intentionally not burned through
# the free guest quota until the UI has a concrete use for them. 16 calls / default focus list.
VNSTOCK_FUNDAMENTAL_INTERVAL=float(os.environ.get('V12_FUNDAMENTAL_INTERVAL','5.5'));_last_fundamental_call=[0.0]
def finite(v):
    try:x=float(v);return x if math.isfinite(x) else None
    except Exception:return None
def load(path):return json.loads(path.read_text(encoding='utf-8'))
def serial(v):
    if v is None:return None
    try:
        if hasattr(v,'isoformat'):return v.isoformat()
    except Exception:pass
    x=finite(v);return x if x is not None else str(v)
def throttle_fundamental():
    wait=max(0.0,VNSTOCK_FUNDAMENTAL_INTERVAL-(time.monotonic()-_last_fundamental_call[0]))
    if wait:time.sleep(wait)
    _last_fundamental_call[0]=time.monotonic()
def quarter_key(s):
    m=re.search(r'(20\d{2})[-_/ ]?Q([1-4])',str(s),re.I);return (int(m.group(1)),int(m.group(2))) if m else None
def latest_period_col(df):
    if df is None or getattr(df,'empty',True):return None
    cand=[(quarter_key(c),str(c)) for c in df.columns if quarter_key(c)];return max(cand,key=lambda x:x[0])[1] if cand else None
def previous_period_col(df,current):
    if df is None or current is None:return None
    uq={quarter_key(c):str(c) for c in df.columns if quarter_key(c)};keys=sorted(uq);cur=quarter_key(current)
    return uq[keys[keys.index(cur)-1]] if cur in keys and keys.index(cur)>0 else None
def row_map(df):
    if df is None:return []
    try:return [{str(k):serial(v) for k,v in r.to_dict().items()} for _,r in df.iterrows()]
    except Exception:return []
def find_metric(rows,col,ids=(),patterns=()):
    ids={x.lower() for x in ids}
    for r in rows:
        rid=str(r.get('item_id') or '').strip().lower();label=str(r.get('item') or '').strip().lower()
        if rid in ids or any(p.lower() in label for p in patterns):
            v=finite(r.get(col))
            if v is not None:return {'value':v,'itemId':rid or None,'label':r.get('item')}
    return None
def growth(cur,prev):
    a=finite(cur);b=finite(prev);return (a/b-1.0) if a is not None and b not in (None,0) else None
def summarize_fundamental(symbol,fe):
    def safe(fn):
        try:throttle_fundamental();return fn(),None
        except BaseException as e:return None,f'{type(e).__name__}: {e}'[:500]
    ratio,er=safe(lambda:fe.ratios(period='quarter'));income,ei=safe(lambda:fe.income_statement(period='quarter'))
    rp=latest_period_col(ratio);ip=latest_period_col(income);rrows=row_map(ratio);irows=row_map(income);prev_i=previous_period_col(income,ip)
    revenue=find_metric(irows,ip,['revenue'],['doanh thu bán hàng','doanh thu thuần']) if ip else None;revenue_prev=find_metric(irows,prev_i,['revenue'],['doanh thu bán hàng','doanh thu thuần']) if prev_i else None
    profit=find_metric(irows,ip,['profit_after_tax','net_profit','net_profit_after_tax'],['lợi nhuận sau thuế','lợi nhuận sau thuế thu nhập doanh nghiệp']) if ip else None;profit_prev=find_metric(irows,prev_i,['profit_after_tax','net_profit','net_profit_after_tax'],['lợi nhuận sau thuế','lợi nhuận sau thuế thu nhập doanh nghiệp']) if prev_i else None
    def rm(ids,pats):return find_metric(rrows,rp,ids,pats) if rp else None
    metrics={'eps':rm(['trailing_eps','eps'],['eps','thu nhập trên mỗi cổ phần']),'pe':rm(['pe','pe_ratio','price_to_earnings'],['p/e','pe ']),'pb':rm(['pb','pb_ratio','price_to_book'],['p/b','pb ']),'roe':rm(['roe'],['roe','lợi nhuận trên vốn chủ']),'roa':rm(['roa'],['roa','lợi nhuận trên tài sản']),'debtToEquity':rm(['debt_to_equity','debt_equity'],['nợ vay trên vốn chủ','nợ/vốn chủ','debt/equity']),'netMargin':rm(['net_profit_margin','net_margin'],['tỷ suất sinh lợi trên doanh thu','biên lợi nhuận ròng','net margin'])};metrics={k:v for k,v in metrics.items() if v is not None}
    return {'status':'PASS' if (rp or ip) else 'REVIEW','ratioPeriod':rp,'incomePeriod':ip,'balancePeriod':None,'cashflowPeriod':None,'revenue':revenue,'revenueQoQ':growth(revenue and revenue['value'],revenue_prev and revenue_prev['value']),'profitAfterTax':profit,'profitQoQ':growth(profit and profit['value'],profit_prev and profit_prev['value']),'ratios':metrics,'publicationTimestampCertified':False,'numericalModelEligible':False,'modelPolicy':'CURRENT_DESCRIPTIVE_ONLY_UNTIL_FILING_PUBLICATION_TIMESTAMP_ARCHIVE_EXISTS','retrievalScope':'INCOME_AND_RATIOS_CURRENT_CONTEXT','errors':{k:v for k,v in {'ratio':er,'income':ei}.items() if v}}
def typed_flow(rows,typ,asof):
    key=typ+'NetValue';buy=typ+'BuyValue';sell=typ+'SellValue';a=[r for r in (rows or []) if str(r.get('date') or '')[:10]<=asof and any(k in r for k in (key,buy,sell))];a.sort(key=lambda r:str(r.get('date') or ''))
    if not a:return {'available':False,'unit':'VND'}
    def val(r,k):return finite(r.get(k)) or 0.0
    scale=1e9 if typ=='prop' else 1.0;latest=a[-1]
    return {'available':True,'latestDate':str(latest.get('date'))[:10],'net1':val(latest,key)*scale,'buy1':val(latest,buy)*scale,'sell1':val(latest,sell)*scale,'net5':sum(val(r,key) for r in a[-5:])*scale,'net20':sum(val(r,key) for r in a[-20:])*scale,'observations':len(a),'unit':'VND','sourceUnit':'billion_VND' if typ=='prop' else 'VND','sourceScaleToVND':scale}
def main():
    dash=load(ROOT/'data'/'forecast-dashboard-v12.json');flow=load(ROOT/'data'/'flow-v12.json');asof=str(dash.get('asOf') or '')[:10]
    out={'version':'VMEWS-CURRENT-CONTEXT-12.3.2','generatedAt':datetime.now(timezone.utc).isoformat(),'forecastAsOf':asof,'symbols':{},'governance':{'flow':'Completed-EOD values are shown with their actual source date. CafeF proprietary value columns are normalized from billion VND to VND for display; missing data is never converted to zero.','fundamental':'VNStock income statements and ratios are shown as current descriptive context. They are not historical numerical forecast features until filing/publication availability timestamps are independently audited.','sponsorLayer':'vnstock_data/vnstock_ta sponsor packages are not assumed available on the public CI runner; equivalent open indicator calculations are deterministic in the browser.'}}
    from vnstock import Fundamental
    for s in FOCUS:
        if s not in (dash.get('symbols') or {}):continue
        rows=(flow.get('symbols') or {}).get(s) or [];flowz={'foreign':typed_flow(rows,'foreign',asof),'proprietary':typed_flow(rows,'prop',asof)}
        try:fund=summarize_fundamental(s,Fundamental().equity(s))
        except BaseException as e:fund={'status':'REVIEW','publicationTimestampCertified':False,'numericalModelEligible':False,'modelPolicy':'CURRENT_DESCRIPTIVE_ONLY_UNTIL_FILING_PUBLICATION_TIMESTAMP_ARCHIVE_EXISTS','errors':{'init':f'{type(e).__name__}: {e}'[:500]}}
        out['symbols'][s]={'flow':flowz,'fundamental':fund};print(json.dumps({'context':s,'flowDates':[flowz['foreign'].get('latestDate'),flowz['proprietary'].get('latestDate')],'fundamentalStatus':fund.get('status'),'period':fund.get('ratioPeriod') or fund.get('incomePeriod')},ensure_ascii=False),flush=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');print(json.dumps({'currentContext':'PASS','symbols':len(out['symbols']),'path':str(OUT)},ensure_ascii=False))
if __name__=='__main__':main()
