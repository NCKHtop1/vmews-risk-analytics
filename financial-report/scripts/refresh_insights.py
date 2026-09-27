"""Refresh public broker-research metadata while preserving curated FinQuery summaries.

No report body/PDF is republished. New discoveries store source URL, date,
broker rating and target price when those fields are explicitly present.
Corporate-event records remain source-linked curated metadata in the same data
branch and are schema-validated here.
"""
import argparse
import html
import json
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
MBS_INDEX='https://www.mbs.com.vn/bao-cao-phan-tich-co-phieu/'
RATINGS=('KHẢ QUAN','MUA','TRUNG LẬP','NẮM GIỮ','BÁN')
UA='Mozilla/5.0 (compatible; FinQueryResearchBot/1.0; +https://github.com/NCKHtop1/vmews-risk-analytics)'

def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def read(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(path)

def fetch(url,timeout=20):
    req=Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml'})
    with urlopen(req,timeout=timeout) as response:
        content_type=response.headers.get('Content-Type','')
        if 'text' not in content_type and 'html' not in content_type:raise ValueError('non-text response')
        return response.read(2_500_000).decode('utf-8','replace')

class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.current=None;self.rows=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=='a':
            href=dict(attrs).get('href')
            if href:self.current=[href,[]]
    def handle_data(self,data):
        if self.current is not None:self.current[1].append(data)
    def handle_endtag(self,tag):
        if tag.lower()=='a' and self.current is not None:
            href,text=self.current;self.rows.append((href,' '.join(text)));self.current=None

class TextParser(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[]
    def handle_data(self,data):
        if data and data.strip():self.parts.append(data.strip())

def clean(value):
    return re.sub(r'\s+',' ',html.unescape(str(value or ''))).strip()

def page_text(raw):
    p=TextParser();p.feed(raw);return clean(' '.join(p.parts))

def normalize_url(url):
    try:
        p=urlsplit(url)
        if p.scheme!='https' or p.hostname not in ('www.mbs.com.vn','mbs.com.vn'):return ''
        return p._replace(query='',fragment='').geturl()
    except Exception:return ''

def symbol_from_title(title,universe):
    text=clean(title).upper()
    match=re.match(r'^([A-Z]{3})\s*[-–—:]',text)
    if match and match.group(1) in universe:return match.group(1)
    return None

def discover_mbs_list(raw,universe):
    parser=AnchorParser();parser.feed(raw);rows=[];seen=set()
    for href,label in parser.rows:
        title=clean(label);symbol=symbol_from_title(title,universe)
        if not symbol:continue
        url=normalize_url(urljoin(MBS_INDEX,href))
        if not url or url.rstrip('/')==MBS_INDEX.rstrip('/') or url in seen:continue
        path=urlsplit(url).path.lower()
        if '/bao-cao-phan-tich-co-phieu' in path or '/page/' in path:continue
        if symbol.lower() not in path and 'bcpt' not in path and 'update' not in path:continue
        seen.add(url);rows.append({'symbol':symbol,'title':title,'sourceUrl':url})
    return rows

def parse_date(text):
    patterns=[
      r'(?:Ngày đăng|Published(?:\s+date)?)\s*:?[ ]*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
      r'\b(\d{1,2}/\d{1,2}/20\d{2})\b'
    ]
    for pattern in patterns:
        m=re.search(pattern,text,re.I)
        if not m:continue
        raw=m.group(1).replace('-','/')
        try:return datetime.strptime(raw,'%d/%m/%Y').date().isoformat()
        except ValueError:pass
    return None

def parse_rating(text):
    upper=text.upper()
    positions=[]
    for rating in RATINGS:
        for m in re.finditer(r'\b'+re.escape(rating)+r'\b',upper):positions.append((m.start(),rating))
    return min(positions)[1] if positions else None

def parse_target(text):
    patterns=[
      r'(?:giá mục tiêu|target price)\s*(?:là|:)?\s*(?:VND|VNĐ|đồng)?\s*([0-9][0-9.,]{2,})',
      r'(?:giá mục tiêu|target price)[^0-9]{0,70}([0-9][0-9.,]{2,})\s*(?:VND|VNĐ|đồng)'
    ]
    for pattern in patterns:
        m=re.search(pattern,text,re.I)
        if not m:continue
        raw=m.group(1).strip()
        # Vietnamese research targets are whole VND/share values.
        digits=re.sub(r'[^0-9]','',raw)
        if not digits:continue
        value=int(digits)
        if 1000<=value<=10_000_000:return value
    return None

def parse_mbs_report(raw,seed):
    text=page_text(raw)
    published=parse_date(text)
    rating=parse_rating(text)
    target=parse_target(text)
    if not published:return None
    symbol=seed['symbol']
    title=clean(seed['title'])
    result={
      'id':f'MBS-{symbol}-{published}',
      'symbol':symbol,'broker':'MBS','publishedAt':published,'title':title,
      'currency':'VND','sourceUrl':seed['sourceUrl']
    }
    if rating:result['recommendation']=rating
    if target:result['targetPrice']=target
    bits=[]
    if rating:bits.append('khuyến nghị '+rating)
    if target:bits.append('giá mục tiêu '+f'{target:,}'.replace(',','.')+' đồng/cp')
    result['summary']='MBS công bố báo cáo ngày '+datetime.fromisoformat(published).strftime('%d/%m/%Y')+((' với '+', '.join(bits))+'.' if bits else '.')+' FinQuery lưu metadata và dẫn về nguồn gốc; xem báo cáo MBS để đọc đầy đủ luận điểm.'
    return result

def merge_reports(existing,discovered):
    by_source={r.get('sourceUrl'):dict(r) for r in existing if r.get('sourceUrl')}
    by_id={r.get('id'):dict(r) for r in existing if r.get('id')}
    for row in discovered:
        prior=by_source.get(row.get('sourceUrl')) or by_id.get(row.get('id'))
        if prior:
            merged={**row,**prior}
            # Fresh explicit metadata may correct parser-stable fields.
            for key in ('publishedAt','recommendation','targetPrice','currency','sourceUrl','title'):
                if row.get(key) is not None:merged[key]=row[key]
            by_id[merged['id']]=merged
            if merged.get('sourceUrl'):by_source[merged['sourceUrl']]=merged
        else:
            by_id[row['id']]=row
            if row.get('sourceUrl'):by_source[row['sourceUrl']]=row
    unique={r['id']:r for r in by_id.values() if r.get('id')}
    return sorted(unique.values(),key=lambda r:(r.get('publishedAt',''),r.get('broker',''),r.get('symbol','')),reverse=True)

def validate_events(value):
    rows=value.get('events') if isinstance(value,dict) else None
    if not isinstance(rows,list):raise ValueError('corporate-events.json must contain events[]')
    valid=[]
    for row in rows:
        if not isinstance(row,dict):continue
        symbol=str(row.get('symbol','')).upper()
        day=str(row.get('date',''))
        source=row.get('source') or {}
        if not re.fullmatch(r'[A-Z]{3}',symbol):continue
        if not re.fullmatch(r'20\d{2}-\d{2}-\d{2}',day):continue
        if not str(row.get('title','')).strip():continue
        if not str(source.get('url','')).startswith('https://'):continue
        valid.append(row)
    if len(valid)!=len(rows):raise ValueError('invalid corporate event record')
    return value

def refresh(output,pages=4):
    companies=read(output/'companies.json',[])
    universe={str(x.get('symbol','')).upper() for x in companies if re.fullmatch(r'[A-Z]{3}',str(x.get('symbol','')).upper())}
    research_path=output/'broker-research.json'
    events_path=output/'corporate-events.json'
    current=read(research_path,{'version':1,'reports':[]})
    events=validate_events(read(events_path,{'version':1,'events':[]}))
    errors=[];seeds=[];seen=set()
    for page in range(1,max(1,pages)+1):
        url=MBS_INDEX if page==1 else urljoin(MBS_INDEX,f'page/{page}/')
        try:
            for row in discover_mbs_list(fetch(url),universe):
                if row['sourceUrl'] not in seen:seen.add(row['sourceUrl']);seeds.append(row)
        except Exception as e:errors.append('MBS list '+str(page)+': '+str(e)[:180])
    found=[]
    for seed in seeds[:80]:
        try:
            row=parse_mbs_report(fetch(seed['sourceUrl']),seed)
            if row:found.append(row)
        except Exception as e:errors.append(seed['symbol']+': '+str(e)[:140])
    reports=merge_reports(current.get('reports') or [],found)
    value={
      'version':1,'updatedAt':now(),
      'policy':'Ratings and target prices are attributed to the publishing broker. FinQuery does not convert them into its own recommendation.',
      'reports':reports
    }
    write(research_path,value)
    events['updatedAt']=events.get('updatedAt') or now();write(events_path,events)
    status={'checkedAt':now(),'mbsListPages':pages,'discoveredLinks':len(seeds),'parsedReports':len(found),'storedReports':len(reports),'corporateEvents':len(events.get('events') or []),'errors':errors[:20]}
    write(output/'insights-status.json',status)
    print(json.dumps(status,ensure_ascii=False))
    return status

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(ROOT/'data'));parser.add_argument('--mbs-pages',type=int,default=int(os.environ.get('MBS_REPORT_PAGES','4')));args=parser.parse_args()
    refresh(Path(args.output),args.mbs_pages)

if __name__=='__main__':main()
