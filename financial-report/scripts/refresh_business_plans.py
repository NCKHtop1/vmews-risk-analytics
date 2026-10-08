"""Refresh public business-plan metadata for FinQuery.

24HMoney is a discovery/aggregation layer. Parse only the structured business
plan table and fail closed when the page signature exists but the table cannot
be interpreted. Never infer years or financial values from unrelated page text.
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

def clean(v):
    return re.sub(r'\s+',' ',re.sub(r'<[^>]*>',' ',html.unescape(str(v or '')))).strip()

def fetch(url,timeout=10):
    headers={
        'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/143.0.0.0 Safari/537.36',
        'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language':'vi-VN,vi;q=0.9,en;q=0.7',
        'Referer':'https://24hmoney.vn/',
        'Cache-Control':'no-cache',
    }
    req=Request(url,headers=headers)
    with urlopen(req,timeout=timeout) as r:
        return r.read().decode('utf-8',errors='ignore')

def number(v):
    if v is None:return None
    x=str(v).strip().replace('\xa0',' ').replace('%','')
    x=re.sub(r'[^0-9,.-]','',x)
    if not x:return None
    # 24HMoney table uses comma as thousands separator and dot as decimal.
    if ',' in x and '.' in x:
        x=x.replace(',','')
    elif ',' in x:
        parts=x.split(',')
        if all(len(p)==3 for p in parts[1:]):
            x=''.join(parts)
        else:
            x=x.replace(',','.')
    elif x.count('.')>1:
        x=x.replace('.','')
    try:return float(x)
    except:return None

def _table_rows(raw):
    tables=re.findall(r'<table\b[^>]*>(.*?)</table>',str(raw or ''),re.I|re.S)
    out=[]
    for table in tables:
        signature=clean(table).casefold()
        if not all(x in signature for x in ('kế hoạch năm','doanh thu','lợi nhuận trước thuế','lợi nhuận sau thuế')):
            continue
        rows=[]
        for tr in re.findall(r'<tr\b[^>]*>(.*?)</tr>',table,re.I|re.S):
            cells=[clean(x) for x in re.findall(r'<(?:td|th)\b[^>]*>(.*?)</(?:td|th)>',tr,re.I|re.S)]
            if cells: rows.append(cells)
        if rows: out.append(rows)
    return out

def _is_total_label(value):
    x=clean(value).casefold()
    return x in {'luỹ kế','lũy kế','cả năm','ca nam'} or 'luỹ kế' in x or 'lũy kế' in x or 'cả năm' in x

def _plan_metrics(plan_cells,actual_cells,actual_basis,through_quarter,symbol,year,url):
    names=('revenue','pretaxProfit','netProfit')
    rows=[]
    for idx,metric in enumerate(names):
        plan=number(plan_cells[idx]) if idx<len(plan_cells) else None
        actual=number(actual_cells[idx*2]) if idx*2<len(actual_cells) else None
        pct=number(actual_cells[idx*2+1]) if idx*2+1<len(actual_cells) else None
        if plan is None or plan<=0:
            continue
        if actual is not None and actual<0:
            # Losses can be valid for profit metrics but not revenue.
            if metric=='revenue': actual=None
        if pct is None and actual is not None and plan:
            pct=round(actual/plan*100,2)
        if pct is not None and not (-500<=pct<=500):
            pct=None
        rows.append({
            'symbol':symbol,'year':year,'metric':metric,
            'plan':plan,'actual':actual,'completionPct':pct,
            'unit':'billion_vnd','actualBasis':actual_basis,
            'throughQuarter':through_quarter,
            'sourceUrl':url,'provider':'24HMoney','checkedAt':now()
        })
    return rows

def parse_plan_html(raw,symbol,url,reference_year=None):
    text=str(raw or '')
    plain=clean(text)
    current_year=reference_year or datetime.now(timezone.utc).year
    min_year=2018;max_year=current_year+2
    signature=('kế hoạch năm' in plain.casefold() and 'doanh thu' in plain.casefold())
    tables=_table_rows(text)
    if not tables:
        status='error' if signature else 'reachable_no_plan'
        reason='plan_table_signature_unparsed' if signature else 'no_plan_table_signature'
        return [],{'status':status,'reason':reason,'parser':'24hmoney-plan-table-v2'}

    output=[];years_seen=[];blocks={}
    for rows in tables:
        active_year=None
        for cells in rows:
            year=None;year_index=None
            for i,cell in enumerate(cells[:3]):
                m=re.fullmatch(r'(20\d{2})',clean(cell))
                if m:
                    candidate=int(m.group(1))
                    if min_year<=candidate<=max_year:
                        year=candidate;year_index=i;break
            if year is not None:
                active_year=year
                years_seen.append(year)
                # Expected first row: YEAR, QUARTER, plan, actual, %, plan, actual, %, plan, actual, %
                trailing=cells[year_index+1:]
                quarter=int(number(trailing[0]) or 0) if trailing else 0
                if len(trailing)>=10:
                    blocks.setdefault(year,{})
                    blocks[year]['plan']=[trailing[1],trailing[4],trailing[7]]
                    blocks[year]['firstActual']=[trailing[2],trailing[3],trailing[5],trailing[6],trailing[8],trailing[9]]
                    blocks[year]['quarter']=quarter if 1<=quarter<=4 else None
                continue

            if active_year is None:
                continue
            label_index=next((i for i,c in enumerate(cells[:3]) if _is_total_label(c)),None)
            if label_index is None:
                # Track the highest quarter seen inside this year block.
                q=number(cells[0]) if cells else None
                if q in (1,2,3,4):
                    blocks.setdefault(active_year,{})
                    blocks[active_year]['quarter']=max(int(q),int(blocks[active_year].get('quarter') or 0)) or None
                continue

            values=cells[label_index+1:]
            if len(values)>=6:
                blocks.setdefault(active_year,{})
                blocks[active_year]['total']=[values[0],values[1],values[2],values[3],values[4],values[5]]
                label=clean(cells[label_index]).casefold()
                blocks[active_year]['basis']='full_year' if 'cả năm' in label or 'ca nam' in label else 'ytd'

    for year,block in blocks.items():
        plan=block.get('plan')
        if not plan: continue
        actual=block.get('total') or block.get('firstActual') or []
        basis=block.get('basis') or ('quarter' if block.get('firstActual') else 'plan_only')
        output.extend(_plan_metrics(plan,actual,basis,block.get('quarter'),symbol,year,url))

    # Final integrity gate: no future junk years and each row must carry a real plan.
    output=[r for r in output if min_year<=int(r['year'])<=max_year and isinstance(r.get('plan'),(int,float)) and r['plan']>0]
    unique={}
    for row in output:
        unique[(row['year'],row['metric'])]=row
    final=sorted(unique.values(),key=lambda x:(-x['year'],x['metric']))
    return final,{
        'status':'ok' if final else 'error',
        'reason':None if final else 'structured_plan_table_without_valid_rows',
        'parsed':len(final),'years':sorted(set(years_seen),reverse=True)[:8],
        'parser':'24hmoney-plan-table-v2'
    }

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
            return [],{'symbol':symbol,'url':url,'status':'error','error':str(exc)[:160],'parser':'24hmoney-plan-table-v2'}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(one,s) for s in symbols]
        for fut in as_completed(futures):
            parsed,status=fut.result();rows.extend(parsed);health.append(status)

    rows.sort(key=lambda x:(x['symbol'],-int(x['year'] or 0),x['metric']))
    errors=[x for x in health if x['status']=='error']
    current_year=datetime.now(timezone.utc).year
    symbols_with_plan={r['symbol'] for r in rows}
    current_year_symbols={r['symbol'] for r in rows if int(r.get('year') or 0)==current_year}
    status={
      'checkedAt':now(),'symbolsTotal':len(symbols),
      'symbolsWithPlan':len(symbols_with_plan),
      'currentYearSymbols':len(current_year_symbols),
      'reachable':sum(1 for x in health if x['status']!='error'),
      'errors':len(errors),
      'parser':'24hmoney-plan-table-v2',
      'invalidFutureYears':sum(1 for r in rows if int(r.get('year') or 0)>current_year+2),
      'sources':health
    }
    payload={
      'version':2,'updatedAt':now(),
      'policy':'Public structured plan metadata with source links; 24HMoney is a discovery layer, not the canonical issuer filing.',
      'unit':'billion_vnd','items':rows
    }
    (output/'business-plans.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')))
    (output/'business-plan-status.json').write_text(json.dumps(status,ensure_ascii=False,separators=(',',':')))
    print(json.dumps({k:v for k,v in status.items() if k!='sources'},ensure_ascii=False))
    if status['reachable']==0:
        raise RuntimeError('All business-plan source requests failed')
    if status['invalidFutureYears']:
        raise RuntimeError('Business-plan parser emitted invalid future years')
    minimum=max(5,min(10,len(symbols)//10))
    if status['symbolsWithPlan']<minimum:
        raise RuntimeError(f'Business-plan coverage too low: {status["symbolsWithPlan"]}/{len(symbols)} < {minimum}')
    if status['errors']>max(20,len(symbols)//3):
        raise RuntimeError(f'Business-plan parser/source errors too high: {status["errors"]}/{len(symbols)}')
    return status

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default=str(ROOT/'data'));a=p.parse_args();refresh(a.output)
