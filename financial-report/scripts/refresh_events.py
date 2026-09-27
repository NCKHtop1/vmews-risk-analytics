"""Refresh corporate-event metadata for FinQuery.

The job prioritizes official exchange/depository/company sources. It stores only
structured event metadata plus source URLs. It does not copy full disclosure
documents. HNX issuer pages are parsed directly; HOSE/VSDC are health-checked
until a stable public listing adapter is available.
"""
import argparse, hashlib, html, json, re
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

def cafef_rows(raw,symbol,source_url):
    text=page_text(raw)
    # Event history is rendered as date + one or more event descriptions until the next date.
    matches=list(re.finditer(r'\b(\d{2}/\d{2}/20\d{2})\s*:\s*',text))
    rows=[]
    for idx,m in enumerate(matches):
        day=parse_date(m.group(1))
        if not day:continue
        end=matches[idx+1].start() if idx+1<len(matches) else min(len(text),m.end()+420)
        chunk=clean(text[m.end():end])
        if not chunk:continue
        pieces=re.split(r'(?=(?:Cổ tức bằng|Thưởng bằng|Bán ưu đãi|Phát hành cho CBCNV|Phát hành thêm|Quyền mua))',chunk,flags=re.I)
        for piece in pieces:
            title=clean(piece)
            if len(title)<5:continue
            low=norm(title)
            if 'co tuc bang tien' in low:etype='cash_dividend'
            elif 'co tuc bang co phieu' in low:etype='stock_dividend'
            elif 'thuong bang co phieu' in low:etype='bonus_share'
            elif 'ban uu dai' in low or 'quyen mua' in low or 'phat hanh them' in low:etype='rights_issue'
            elif 'phat hanh cho cbcnv' in low:etype='esop'
            else:continue
            ratio=None
            rm=re.search(r'tỷ lệ\s*([0-9.,:]+%?)',title,re.I)
            if rm:ratio=rm.group(1)
            details={'exRightDate':day}
            if ratio:details['ratio']=ratio
            rows.append({
              'id':stable_id(symbol,etype,day,title),'symbol':symbol,'type':etype,'date':day,
              'title':title[:180],'summary':title[:260],'details':details,
              'source':{'publisher':'CafeF','url':source_url},'fetchedAt':now(),'dataQuality':'secondary'
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
    for source in [x for x in config.get('sources',[]) if x.get('enabled')]:
        base={'code':source['code'],'name':source.get('name',source['code']),'checkedAt':now(),'kind':source.get('kind'),'status':'pending','parsed':0,'reachable':0}
        if source.get('kind')=='health':
            try:
                _,status,_=fetch(source['url']);base['httpStatus']=status;base['reachable']=1;base['status']='reachable'
            except Exception as exc:base['status']='error';base['error']=str(exc)[:180]
            health.append(base);continue
        errors=0
        exchange_by_symbol={str(x.get('symbol','')).upper():str(x.get('exchange','HOSE')).lower() for x in companies}
        for symbol in symbols:
            url=str(source.get('urlTemplate','')).replace('{symbol}',symbol).replace('{exchange}',exchange_by_symbol.get(symbol,'hose'))
            try:
                raw,status,_=fetch(url);base['reachable']+=1
                if source.get('kind')=='cafef_history':
                    rows=cafef_rows(raw,symbol,url)
                else:
                    rows=hnx_rows(raw,symbol,url,source.get('name',source['code']))
                discovered.extend(rows);base['parsed']+=len(rows)
            except Exception:
                errors+=1
        base['status']='ok' if base['parsed'] else ('reachable_no_events' if base['reachable'] else 'error')
        if errors:base['errors']=errors
        health.append(base)
    events=merge_events(seed.get('events') or [],published.get('events') or [],discovered)
    payload={
      'version':2,'updatedAt':now(),
      'policy':'FinQuery stores source-linked corporate-event metadata; official exchange/depository/company sources are preferred.',
      'events':events
    }
    write(output/'corporate-events.json',payload)
    status={'checkedAt':now(),'sourcesTotal':len(health),'sourcesReachable':sum(1 for x in health if x.get('reachable') or x.get('status')=='reachable'),'eventsDiscoveredThisRun':len(discovered),'storedEvents':len(events),'sources':health}
    write(output/'event-status.json',status)
    print(json.dumps(status,ensure_ascii=False))
    return status

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default=str(ROOT/'data'));a=p.parse_args();refresh(a.output)
if __name__=='__main__':main()
