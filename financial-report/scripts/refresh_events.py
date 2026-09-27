"""Refresh corporate-event metadata for FinQuery.

The job prioritizes official exchange/depository/company sources. It stores only
structured event metadata plus source URLs. It does not copy full disclosure
documents. HNX issuer pages are parsed directly; HOSE/VSDC are health-checked
until a stable public listing adapter is available.
"""
import argparse, hashlib, html, json, os, re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
UA='Mozilla/5.0 (compatible; FinQueryEvents/1.0; +https://github.com/NCKHtop1/vmews-risk-analytics)'

TYPE_RULES=[
 ('cash_dividend',r'(tra|chi|tam ung).{0,35}co tuc.{0,25}(bang )?tien'),
 ('stock_dividend',r'(tra|chia).{0,35}co tuc.{0,25}(bang )?(cp|co phieu)'),
 ('bonus_share',r'(thuong|phat hanh).{0,30}co phieu.{0,20}(thuong|tang von tu nguon von chu)'),
 ('rights_issue',r'(phat hanh|quyen mua).{0,35}(co dong hien huu|quyen mua)'),
 ('agm',r'(hop|dai hoi).{0,20}(dai hoi dong co dong|dhdcd).{0,20}(thuong nien|thuong ky)'),
 ('egm',r'(hop|dai hoi).{0,20}(dai hoi dong co dong|dhdcd).{0,20}(bat thuong|bat thuong nien)'),
 ('shareholder_vote',r'(lay y kien|xin y kien).{0,25}co dong'),
 ('esop',r'\besop\b|phat hanh.{0,25}(nguoi lao dong|can bo nhan vien)'),
 ('private_placement',r'phat hanh.{0,25}rieng le'),
 ('buyback',r'(mua lai|mua).{0,25}co phieu quy'),
 ('listing',r'(niem yet bo sung|dang ky giao dich bo sung|ngay giao dich co phieu phat hanh)'),
 ('delisting',r'(huy niem yet|huy dang ky giao dich)'),
 ('earnings',r'(cong bo|bao cao).{0,20}(ket qua kinh doanh|kqkd)'),
]

def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def read(path,default):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:return default
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)
def clean(value): return re.sub(r'\s+',' ',html.unescape(str(value or ''))).strip()
def norm(value):
    import unicodedata
    s=unicodedata.normalize('NFD',clean(value).lower().replace('đ','d'))
    return ''.join(ch for ch in s if unicodedata.category(ch)!='Mn')
def fetch(url,timeout=18):
    req=Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml'})
    with urlopen(req,timeout=timeout) as r:
        return r.read(3_000_000).decode('utf-8','replace'),getattr(r,'status',200),r.headers.get('Content-Type','')

class TextParser(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True);self.parts=[]
    def handle_data(self,data):
        if data and data.strip():self.parts.append(data.strip())

def page_text(raw):
    p=TextParser();p.feed(raw);return clean(' '.join(p.parts))

class CellParser(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True);self.cells=[];self.buf=None
    def handle_starttag(self,tag,attrs):
        if tag.lower() in ('td','th'):self.buf=[]
    def handle_data(self,data):
        if self.buf is not None:self.buf.append(data)
    def handle_endtag(self,tag):
        if tag.lower() in ('td','th') and self.buf is not None:
            text=clean(' '.join(self.buf))
            if text:self.cells.append(text)
            self.buf=None

def parse_date(value):
    for p in (r'\b(\d{1,2}/\d{1,2}/20\d{2})\b',r'\b(20\d{2}-\d{2}-\d{2})\b'):
        m=re.search(p,clean(value))
        if m:
            try:
                if '/' in m.group(1):return datetime.strptime(m.group(1),'%d/%m/%Y').date().isoformat()
                return datetime.strptime(m.group(1),'%Y-%m-%d').date().isoformat()
            except ValueError:pass
    return None

def classify(title):
    s=norm(title)
    for code,pattern in TYPE_RULES:
        if re.search(pattern,s,re.I):return code
    return 'other'

def stable_id(symbol,etype,day,title):
    h=hashlib.sha1((symbol+'|'+etype+'|'+day+'|'+clean(title)).encode()).hexdigest()[:8]
    return f'{symbol}-{etype}-{day}-{h}'

def hnx_rows(raw,symbol,source_url,publisher):
    p=CellParser();p.feed(raw);cells=p.cells;rows=[]
    # HNX event table appears as: event type | ex date | record date | payment/meeting date.
    for i,text in enumerate(cells):
        etype=classify(text)
        if etype=='other':continue
        dates=[]
        for nxt in cells[i+1:i+6]:
            d=parse_date(nxt)
            if d:dates.append(d)
            elif dates:break
        if len(dates)<2:continue
        ex_date,record_date=dates[0],dates[1]
        third=dates[2] if len(dates)>2 else None
        details={'exRightDate':ex_date,'recordDate':record_date}
        if etype in ('cash_dividend','stock_dividend','bonus_share','rights_issue') and third:details['payoutDate']=third
        elif etype in ('agm','egm') and third:details['meetingDate']=third
        title=clean(text)
        rows.append({
            'id':stable_id(symbol,etype,ex_date,title),'symbol':symbol,'type':etype,'date':ex_date,
            'title':title,'summary':title,'details':details,
            'source':{'publisher':publisher,'url':source_url},'fetchedAt':now(),'dataQuality':'official'
        })
    return rows

def parse_24hmoney_events(raw,symbol,source_url):
    text=page_text(raw)
    rows=[];seen=set()
    # 24HMoney renders a timeline as: category + date + ticker + title.
    header=re.compile(
        r'(Sự kiện|Báo cáo tài chính|Lịch chia cổ tức|Kế hoạch|Phát hành)'
        r'\s+(?:\d{2}/\d{2}/20\d{2}|20\d{2}-\d{2}-\d{2})\s+'
        +re.escape(symbol)+r'\s+',
        re.I
    )
    matches=list(header.finditer(text))
    for idx,m in enumerate(matches):
        category=clean(m.group(1))
        day_match=re.search(r'(?:Sự kiện|Báo cáo tài chính|Lịch chia cổ tức|Kế hoạch|Phát hành)\s+(\d{2}/\d{2}/20\d{2}|20\d{2}-\d{2}-\d{2})\s+'+re.escape(symbol)+r'\s+',m.group(0),re.I)
        day=parse_date(day_match.group(1) if day_match else '')
        if not day:continue
        nxt=matches[idx+1].start() if idx+1<len(matches) else min(len(text),m.end()+720)
        title=clean(text[m.end():nxt])
        if not title:continue
        etype=classify(title)
        low=norm(title)
        if etype=='other' and ('quyen' in low or 'giao dich khong huong quyen' in low):
            etype='rights_issue'
        if 'bao cao tai chinh' in norm(category) or 'ket qua kinh doanh' in low:
            etype='earnings'
        if 'lich chia co tuc' in norm(category) and etype=='other':
            etype='cash_dividend'
        details={'publishedAt':day}
        ex=re.search(r'(?:GDKHQ|giao dịch không hưởng quyền)\s*:?\s*(20\d{2}-\d{2}-\d{2})',title,re.I)
        if ex:details['exRightDate']=ex.group(1)
        rec=re.search(r'(?:chốt danh sách|đăng ký cuối cùng)\s*:?\s*(20\d{2}-\d{2}-\d{2})',title,re.I)
        if rec:details['recordDate']=rec.group(1)
        pay=re.search(r'(?:ngày thực hiện|thời gian thực hiện|thanh toán)\s*:?\s*(20\d{2}-\d{2}-\d{2})',title,re.I)
        if pay:details['paymentDate']=pay.group(1)
        ratio=re.search(r'(?:tỷ lệ|tỉ lệ)(?:\s+thực hiện)?\s*:?\s*([0-9.,:]+%?)',title,re.I)
        if ratio:details['ratio']=ratio.group(1)
        rid=stable_id(symbol,etype,day,title)
        if rid in seen:continue
        seen.add(rid)
        rows.append({
            'id':rid,'symbol':symbol,'type':etype,'date':day,'title':title[:220],
            'summary':title[:340],'details':details,
            'source':{'publisher':'24HMoney','url':source_url},
            'fetchedAt':now(),'dataQuality':'aggregated'
        })
    return rows


def fingerprint(row):
    d=row.get('details') or {}
    return '|'.join([str(row.get('symbol','')),str(row.get('type','')),str(row.get('date',''))])

def merge_events(seed,published,discovered):
    out={}
    # Keep curated seed fields where present, but newer discovered source metadata may enrich.
    for row in list(seed)+list(published)+list(discovered):
        if not isinstance(row,dict) or not row.get('symbol') or not row.get('date'):continue
        key=fingerprint(row)
        if key in out:
            prior=out[key];merged={**prior,**row}
            merged['details']={**(prior.get('details') or {}),**(row.get('details') or {})}
            if prior.get('summary') and len(str(prior['summary']))>len(str(row.get('summary',''))):merged['summary']=prior['summary']
            out[key]=merged
        else:out[key]=dict(row)
    rows=sorted(out.values(),key=lambda x:(x.get('date',''),x.get('symbol',''),x.get('type','')),reverse=True)
    return rows

def refresh(output):
    output=Path(output)
    config=read(ROOT/'config/event_sources.json',{'sources':[]})
    companies=read(output/'companies.json',read(ROOT/'data/companies.json',[]))
    symbols=[str(x.get('symbol','')).upper() for x in companies if re.fullmatch(r'[A-Z]{3}',str(x.get('symbol','')).upper())]
    seed=read(ROOT/'data/corporate-events.json',{'events':[]})
    published=read(output/'corporate-events.json',{'events':[]})
    discovered=[];health=[]
    sources=[x for x in config.get('sources',[]) if x.get('enabled')]
    for source in sources:
        base={'code':source['code'],'name':source.get('name',source['code']),'checkedAt':now(),'kind':source.get('kind'),'status':'pending','parsed':0,'reachable':0}
        if source.get('kind')=='health':
            try:
                _,status,_=fetch(source['url'],timeout=8);base['httpStatus']=status;base['reachable']=1;base['status']='reachable'
            except Exception as exc:base['status']='error';base['error']=str(exc)[:180]
            health.append(base);continue
        exchange_by_symbol={str(x.get('symbol','')).upper():str(x.get('exchange','HOSE')).lower() for x in companies}
        tasks=[(symbol,str(source.get('urlTemplate','')).replace('{symbol}',symbol).replace('{exchange}',exchange_by_symbol.get(symbol,'hose'))) for symbol in symbols]
        workers=max(6,min(18,int(os.environ.get('EVENT_FETCH_WORKERS','12'))))
        def collect_one(task):
            symbol,url=task
            try:
                raw,_,_=fetch(url,timeout=8)
                if source.get('kind')=='cafef_history':rows=cafef_rows(raw,symbol,url)
                elif source.get('kind')=='24hmoney_events':rows=parse_24hmoney_events(raw,symbol,url)
                else:rows=hnx_rows(raw,symbol,url,source.get('name',source['code']))
                return rows,True
            except Exception:
                return [],False
        errors=0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(collect_one,task) for task in tasks]
            for future in as_completed(futures):
                rows,reachable=future.result()
                if reachable:base['reachable']+=1
                else:errors+=1
                discovered.extend(rows);base['parsed']+=len(rows)
        base['status']='ok' if base['parsed'] else ('reachable_no_events' if base['reachable'] else 'error')
        if errors:base['errors']=errors
        health.append(base)
    events=merge_events(seed.get('events') or [],published.get('events') or [],discovered)
    payload={'version':2,'updatedAt':now(),
      'policy':'FinQuery stores source-linked corporate-event metadata; official/depository/company sources are preferred, with 24HMoney used as a public discovery layer.',
      'events':events}
    write(output/'corporate-events.json',payload)
    status={'checkedAt':now(),'sourcesTotal':len(health),
      'sourcesReachable':sum(1 for x in health if x.get('reachable') or x.get('status')=='reachable'),
      'eventsDiscoveredThisRun':len(discovered),'storedEvents':len(events),'sources':health}
    write(output/'event-status.json',status)
    print(json.dumps(status,ensure_ascii=False))
    return status

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default=str(ROOT/'data'));a=p.parse_args();refresh(a.output)
if __name__=='__main__':main()
