import json, math, os, pathlib, statistics, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone, timedelta
from urllib.parse import urlencode
import backfill_flow_v11 as src

ROOT=pathlib.Path(os.environ.get('GITHUB_WORKSPACE','.')).resolve();DATA=ROOT/'data';VERSION='VMEWS-FLOW-12.1.0';VN_TZ=timezone(timedelta(hours=7))
MAX_WORKERS=int(os.environ.get('V12_FLOW_WORKERS','8'));START_YEAR=int(os.environ.get('V12_FLOW_START_YEAR','2018'))
BASE=src.BASE

def manifest_symbols():
    z=json.loads((DATA/'hose-fallbacks'/'manifest.json').read_text(encoding='utf-8'));return sorted(s for s,r in (z.get('routes') or {}).items() if int((r or {}).get('rows') or 0)>=520)

def mmdd(d):return d.strftime('%m/%d/%Y')
def qwindows(today):
    out=[]
    for y in range(START_YEAR,today.year+1):
        bounds=[(1,1,3,31),(4,1,6,30),(7,1,9,30),(10,1,12,31)]
        for sm,sd,em,ed in bounds:
            a=date(y,sm,sd)
            if a>today:continue
            b=min(date(y,em,ed),today);out.append((a,b))
    return out

def nval(kk,*alts):
    for alt in alts:
        for k,v in kk.items():
            if all(t in k for t in alt):return src.asnum(v)
    return 0.0

def parse_payload(p,kind):
    a=p.get('Data') or p.get('data') or p.get('DataRows') or []
    meta=p
    if isinstance(a,dict):
        meta={**p,**a};a=a.get('Data') or a.get('Rows') or a.get('rows') or []
    if not isinstance(a,list):return [],meta
    out=[]
    for r in a:
        if not isinstance(r,dict):continue
        kk={src.nkey(k):v for k,v in r.items()};d=src.date_iso(next((v for k,v in kk.items() if 'ngay' in k or 'date' in k),None))
        if not d:continue
        if kind=='foreign':z={'date':d,'foreignBuyValue':nval(kk,('mua','giatri'),('mua','gt'),('buy','value')),'foreignSellValue':nval(kk,('ban','giatri'),('ban','gt'),('sell','value')),'foreignNetValue':nval(kk,('rong','giatri'),('rong','gt'),('net','value'))}
        else:z={'date':d,'propBuyValue':nval(kk,('mua','giatri'),('mua','gt'),('buy','value')),'propSellValue':nval(kk,('ban','giatri'),('ban','gt'),('sell','value')),'propNetValue':nval(kk,('rong','giatri'),('rong','gt'),('net','value'))}
        out.append(z)
    return out,meta

def json_window(symbol,kind,a,b):
    ep='GDKhoiNgoai.ashx' if kind=='foreign' else 'GDTuDoanh.ashx';out=[];page=1
    while page<=10:
        q=urlencode({'Symbol':symbol,'StartDate':mmdd(a),'EndDate':mmdd(b),'PageIndex':page,'PageSize':100});err=None;p=None
        for attempt in range(3):
            try:
                raw,_=src.get(BASE+ep+'?'+q,20);p=json.loads(raw.decode('utf-8','ignore'));break
            except BaseException as e:
                err=e;time.sleep(.35*(attempt+1))
        if p is None:raise RuntimeError(f'{kind} {symbol} {a}..{b} page={page}: {type(err).__name__}: {err}')
        rows,meta=parse_payload(p,kind)
        if not rows:break
        out.extend(rows)
        pages=int(meta.get('TotalPage') or meta.get('totalPage') or meta.get('TotalPages') or p.get('TotalPage') or p.get('totalPage') or p.get('TotalPages') or 0)
        total=int(meta.get('TotalCount') or meta.get('totalCount') or meta.get('Total') or p.get('TotalCount') or p.get('totalCount') or p.get('Total') or 0)
        if (pages and page>=pages) or (total and len(out)>=total) or (not pages and len(rows)<20):break
        page+=1
    lo=a.isoformat();hi=b.isoformat();return sorted({x['date']:x for x in out if lo<=x['date']<=hi}.values(),key=lambda x:x['date'])

def foreign_rows(symbol,today):
    out=[];ok=0;empty=0
    for a,b in qwindows(today):
        r=json_window(symbol,'foreign',a,b);out.extend(r);ok+=1;empty+=not bool(r)
    return sorted({x['date']:x for x in out}.values(),key=lambda x:x['date']),{'method':'QUARTERLY_JSON_MMDDYYYY','windows':ok,'emptyWindows':empty}

def prop_rows(symbol,today):
    # CafeF proprietary export was verified to return ~900 sessions in one request. Use one immutable date contract for all workers.
    r=src.export_rows(symbol,'prop');return [{k:v for k,v in x.items() if k in {'date','propBuyValue','propSellValue','propNetValue'}} for x in r],{'method':'FULL_RANGE_EXPORT_MMDDYYYY'}

def nz(x,keys):return any(abs(float(x.get(k,0) or 0))>1e-9 for k in keys)
def audit_symbol(rows,route):
    rows=sorted({str(x.get('date'))[:10]:x for x in rows if x.get('date')}.values(),key=lambda x:x['date']);fk=['foreignBuyValue','foreignSellValue','foreignNetValue'];pk=['propBuyValue','propSellValue','propNetValue'];fr=[x for x in rows if nz(x,fk)];pr=[x for x in rows if nz(x,pk)];dates=[x['date'] for x in rows]
    return rows,{'rows':len(rows),'first':dates[0] if dates else None,'last':dates[-1] if dates else None,'duplicateDates':0,'foreignNonzeroRows':len(fr),'foreignFirst':fr[0]['date'] if fr else None,'foreignLast':fr[-1]['date'] if fr else None,'propNonzeroRows':len(pr),'propFirst':pr[0]['date'] if pr else None,'propLast':pr[-1]['date'] if pr else None,'route':route}

def one(symbol,today):
    fr,fa=foreign_rows(symbol,today);pr,pa=prop_rows(symbol,today);d={}
    for x in fr+pr:d.setdefault(x['date'],{'date':x['date']}).update(x)
    rows=[d[k] for k in sorted(d)];clean,a=audit_symbol(rows,{'foreign':fa,'prop':pa});return symbol,clean,a

def main():
    today=datetime.now(VN_TZ).date();today_iso=today.isoformat();src.START='01/01/2018';src.END=mmdd(today)
    syms=manifest_symbols();store={};aud={};fail={}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fs={ex.submit(one,s,today):s for s in syms}
        for i,fut in enumerate(as_completed(fs),1):
            s=fs[fut]
            try:
                symbol,rows,a=fut.result();future=[x['date'] for x in rows if x['date']>today_iso]
                if future:raise RuntimeError(f'future flow rows: {future[:3]}')
                store[symbol]=rows;aud[symbol]=a
            except BaseException as e:fail[s]=f'{type(e).__name__}: {e}'[:800]
            if i%20==0 or i==len(syms):print(json.dumps({'v12FlowProgress':i,'total':len(syms),'passed':len(store),'failed':len(fail),'foreign100':sum(x.get('foreignNonzeroRows',0)>=100 for x in aud.values()),'foreign500':sum(x.get('foreignNonzeroRows',0)>=500 for x in aud.values()),'prop100':sum(x.get('propNonzeroRows',0)>=100 for x in aud.values())}),flush=True)
    foreign100=sum(x.get('foreignNonzeroRows',0)>=100 for x in aud.values());prop100=sum(x.get('propNonzeroRows',0)>=100 for x in aud.values());foreign_any=sum(x.get('foreignNonzeroRows',0)>0 for x in aud.values());prop_any=sum(x.get('propNonzeroRows',0)>0 for x in aud.values());prop_lens=[x.get('propNonzeroRows',0) for x in aud.values() if x.get('propNonzeroRows',0)>0];foreign_lens=[x.get('foreignNonzeroRows',0) for x in aud.values() if x.get('foreignNonzeroRows',0)>0]
    summary={'requested':len(syms),'passed':len(store),'failed':len(fail),'routeCoverage':len(store)/max(1,len(syms)),'foreignAny':foreign_any,'foreignCoverage':foreign_any/max(1,len(syms)),'foreign100plus':foreign100,'foreign100Coverage':foreign100/max(1,len(syms)),'foreign500plus':sum(x.get('foreignNonzeroRows',0)>=500 for x in aud.values()),'propAny':prop_any,'propCoverage':prop_any/max(1,len(syms)),'prop100plus':prop100,'prop100Coverage':prop100/max(1,len(syms)),'foreignMedianNonzeroRows':statistics.median(foreign_lens) if foreign_lens else 0,'propMedianNonzeroRows':statistics.median(prop_lens) if prop_lens else 0,'todayVN':today_iso,'foreignWindowContract':'quarterly MM/DD/YYYY','propContract':'full-range export MM/DD/YYYY'}
    summary['status']='PASS' if summary['routeCoverage']>=.90 and summary['foreignCoverage']>=.60 and foreign100>=150 and summary['propCoverage']>=.25 and prop100>=80 else 'FAIL'
    out={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'range':{'start':f'{START_YEAR}-01-01','end':today_iso},'availabilityPolicy':'Completed-EOD only. Observation dated T is eligible for a forecast produced after the close of session T; no forward filling before first genuine observation.','source':'CafeF historical foreign quarterly JSON + proprietary full-range XLSX','sourceRole':'PIT EOD institutional-flow archive. VNStock remains primary OHLCV; community VNStock flow methods were unavailable on the production runner, so flow source is separately audited and missingness is explicit.','symbols':store,'summary':summary,'sourceAudit':aud,'failures':fail}
    audit={'version':'VMEWS-FLOW-AUDIT-12.1.0','generatedAt':out['generatedAt'],'summary':summary,'source':out['source'],'availabilityPolicy':out['availabilityPolicy'],'symbols':aud,'failures':fail}
    DATA.mkdir(parents=True,exist_ok=True);(DATA/'flow-v12.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8');(DATA/'flow-audit-v12.json').write_text(json.dumps(audit,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8');print(json.dumps({'v12FlowComplete':summary},ensure_ascii=False),flush=True)
    if summary['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
