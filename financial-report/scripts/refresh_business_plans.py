"""Refresh public business-plan metadata for FinQuery.

24HMoney is used as a discovery/aggregation layer only. The dataset keeps source
links and structured plan-vs-actual figures; it does not copy article bodies.
"""
import argparse
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]

def now(): return datetime.now(timezone.utc).isoformat()
def clean(v): return re.sub(r'\s+',' ',re.sub(r'<[^>]*>',' ',html.unescape(str(v or '')))).strip()
def fetch(url,timeout=8):
    req=Request(url,headers={'User-Agent':'FinQuery/1.0 public financial dashboard','Accept':'text/html,*/*'})
    with urlopen(req,timeout=timeout) as r: return r.read().decode('utf-8',errors='ignore')
def number(v):
    if v is None:return None
    x=str(v).strip().replace('\xa0',' ').replace('%','')
    x=re.sub(r'[^0-9,.-]','',x)
    if not x:return None
    if x.count('.')>1 and ',' not in x:x=x.replace('.','')
    elif ',' in x and '.' not in x:x=x.replace('.','').replace(',','.')
    elif ',' in x and '.' in x:
        if x.rfind(',')>x.rfind('.'):x=x.replace('.','').replace(',','.')
        else:x=x.replace(',','')
    try:return float(x)
    except:return None

LABELS={
 'revenue':r'doanh\s*thu',
 'pretaxProfit':r'lợi\s*nhuận\s*(?:trước\s*thuế|trước\s*thuế\s*\(lntt\))|\blntt\b',
 'netProfit':r'lợi\s*nhuận\s*(?:sau\s*thuế|sau\s*thuế\s*\(lnst\))|\blnst\b',
}

def _year_near(text,pos):
    m=re.search(r'20(?:2[4-9]|3\d)',text[max(0,pos-220):pos+220])
    return int(m.group()) if m else None

def parse_plan_html(raw,symbol,url):
    text=clean(raw)
    if symbol.lower() not in text.lower() and 'kế hoạch' not in text.lower():
        return [],{'status':'template_mismatch','reason':'missing_symbol_or_plan_signature'}
    years=sorted({int(x) for x in re.findall(r'20(?:2[4-9]|3\d)',text)})
    rows=[]
    for metric,label_re in LABELS.items():
        for m in re.finditer(label_re,text,re.I):
            seg=text[m.start():m.start()+520]
            year=_year_near(text,m.start()) or (years[-1] if years else None)
            # Prefer explicit Kế hoạch / Thực hiện / % hoàn thành labels.
            plan_m=re.search(r'kế\s*hoạch[^0-9]{0,30}([0-9][0-9.,]*)',seg,re.I)
            actual_m=re.search(r'(?:thực\s*hiện|đã\s*thực\s*hiện)[^0-9]{0,30}([0-9][0-9.,]*)',seg,re.I)
            pct_m=re.search(r'(?:hoàn\s*thành|%\s*kh)[^0-9]{0,20}([0-9][0-9.,]*)\s*%',seg,re.I)
            plan=number(plan_m.group(1)) if plan_m else None
            actual=number(actual_m.group(1)) if actual_m else None
            pct=number(pct_m.group(1)) if pct_m else None
            if pct is None and plan and actual is not None and plan!=0:pct=round(actual/plan*100,2)
            if plan is None and actual is None and pct is None:continue
            rows.append({'symbol':symbol,'year':year,'metric':metric,'plan':plan,'actual':actual,'completionPct':pct,'unit':'source_display','sourceUrl':url,'provider':'24HMoney','checkedAt':now()})
            break
    # unique metric/year
    unique={}
    for r in rows: unique[(r['year'],r['metric'])]=r
    final=list(unique.values())
    return final,{'status':'ok' if final else 'reachable_no_plan','parsed':len(final),'years':years[-4:]}

def refresh(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    companies=json.loads((ROOT/'data/companies.json').read_text())
    symbols=sorted({str(x.get('symbol','')).upper() for x in companies if x.get('symbol')})
    workers=12;rows=[];health=[]

    def one(symbol):
        url=f'https://24hmoney.vn/stock/{symbol}/ke-hoach-kinh-doanh'
        try:
            raw=fetch(url)
            parsed,status=parse_plan_html(raw,symbol,url)
            return parsed,{'symbol':symbol,'url':url,**status}
        except Exception as exc:
            return [],{'symbol':symbol,'url':url,'status':'error','error':str(exc)[:160]}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(one,s) for s in symbols]
        for fut in as_completed(futures):
            parsed,status=fut.result();rows.extend(parsed);health.append(status)

    rows.sort(key=lambda x:(x['symbol'],-int(x['year'] or 0),x['metric']))
    status={
      'checkedAt':now(),'symbolsTotal':len(symbols),
      'symbolsWithPlan':len({r['symbol'] for r in rows}),
      'reachable':sum(1 for x in health if x['status']!='error'),
      'errors':sum(1 for x in health if x['status']=='error'),
      'sources':health
    }
    (output/'business-plans.json').write_text(json.dumps({'version':1,'updatedAt':now(),'policy':'Public structured plan metadata with source links; 24HMoney is a discovery layer, not the canonical issuer filing.','items':rows},ensure_ascii=False,separators=(',',':')))
    (output/'business-plan-status.json').write_text(json.dumps(status,ensure_ascii=False,separators=(',',':')))
    print(json.dumps(status,ensure_ascii=False))
    if status['reachable']==0:raise RuntimeError('All business-plan source requests failed')
    return status

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default=str(ROOT/'data'));a=p.parse_args();refresh(a.output)
