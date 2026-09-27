"""Refresh FinQuery corporate-event and multi-broker research metadata.

The crawler stores source-linked metadata only. It never republishes report/PDF
bodies. Curated FinQuery summaries/highlights already present in
broker-research.json are preserved on refresh.

Supported public adapters are intentionally conservative. Sources that require
login/JS/API access are still health-checked so gaps remain visible instead of
being silently treated as "no reports".
"""
import argparse
import hashlib
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
UA='Mozilla/5.0 (compatible; FinQueryResearchBot/2.0; +https://github.com/NCKHtop1/vmews-risk-analytics)'
RATING_ALIASES={
    'BUY':'MUA','STRONG BUY':'MUA MẠNH','MUA':'MUA','MUA MẠNH':'MUA MẠNH',
    'OUTPERFORM':'KHẢ QUAN','OVERWEIGHT':'TĂNG TỶ TRỌNG','KHẢ QUAN':'KHẢ QUAN',
    'TĂNG TỶ TRỌNG':'TĂNG TỶ TRỌNG','MARKET PERFORM':'TRUNG LẬP',
    'NEUTRAL':'TRUNG LẬP','HOLD':'NẮM GIỮ','TRUNG LẬP':'TRUNG LẬP','NẮM GIỮ':'NẮM GIỮ',
    'UNDERPERFORM':'KÉM KHẢ QUAN','REDUCE':'GIẢM TỶ TRỌNG','SELL':'BÁN','BÁN':'BÁN'
}
REPORT_WORDS=('báo cáo','bcpt','research','update','cập nhật','khuyến nghị','x-stock','x-alpha','flash note','company research','doanh nghiệp')
MONTHS={'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}

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

def clean(value):
    return re.sub(r'\s+',' ',html.unescape(str(value or ''))).strip()

def fetch(url,timeout=22):
    req=Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml'})
    with urlopen(req,timeout=timeout) as response:
        body=response.read(3_000_000)
        ctype=response.headers.get('Content-Type','')
        return body.decode('utf-8','replace'),response.status,ctype

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
            href,text=self.current;self.rows.append((href,clean(' '.join(text))));self.current=None

class TextParser(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[]
    def handle_data(self,data):
        if data and data.strip():self.parts.append(data.strip())

def page_text(raw):
    p=TextParser();p.feed(raw);return clean(' '.join(p.parts))

def safe_url(base,href):
    try:
        url=urljoin(base,href);p=urlsplit(url)
        if p.scheme not in ('http','https'):return ''
        return p._replace(fragment='').geturl()
    except Exception:return ''

def ticker_from_text(text,universe):
    upper=' '+clean(text).upper()+' '
    direct=re.search(r'(?:^|[^A-Z0-9])([A-Z]{3})(?:[^A-Z0-9]|$)',upper)
    if direct and direct.group(1) in universe:return direct.group(1)
    for ticker in universe:
        if re.search(r'(?<![A-Z0-9])'+re.escape(ticker)+r'(?![A-Z0-9])',upper):return ticker
    return None

def parse_date(text):
    value=clean(text)
    for pattern in (r'(?:Ngày đăng|Ngày phát hành|Published(?:\s+date)?|Ngày)\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
                    r'\b(\d{1,2}/\d{1,2}/20\d{2})\b',r'\b(\d{1,2}-\d{1,2}-20\d{2})\b'):
        m=re.search(pattern,value,re.I)
        if m:
            try:return datetime.strptime(m.group(1).replace('-','/'),'%d/%m/%Y').date().isoformat()
            except ValueError:pass
    m=re.search(r'\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})\b',value,re.I)
    if m:
        try:return datetime(int(m.group(3)),MONTHS[m.group(2)[:3].lower()],int(m.group(1))).date().isoformat()
        except ValueError:pass
    return None

def parse_rating(text):
    upper=clean(text).upper()
    hits=[]
    for raw,canon in RATING_ALIASES.items():
        m=re.search(r'(?<![A-ZÀ-Ỹ])'+re.escape(raw)+r'(?![A-ZÀ-Ỹ])',upper)
        if m:hits.append((m.start(),canon))
    return min(hits)[1] if hits else None

def parse_target(text,symbol=None):
    value=clean(text)
    patterns=[
        r'(?:giá mục tiêu|target price|target|TP)\s*(?:là|:|=)?\s*(?:VND|VNĐ|đồng)?\s*([0-9][0-9.,]{2,})',
        r'(?:giá trị hợp lý)[^0-9]{0,50}([0-9][0-9.,]{2,})\s*(?:VND|VNĐ|đồng)',
    ]
    if symbol:
        patterns.append(r'\b'+re.escape(symbol)+r'\b[^0-9]{0,12}([0-9]{2,3}[.,][0-9]{3})\s*(?:\+|-)?\d+(?:[.,]\d+)?%')
    for pattern in patterns:
        m=re.search(pattern,value,re.I)
        if not m:continue
        digits=re.sub(r'[^0-9]','',m.group(1))
        if not digits:continue
        n=int(digits)
        if 1000<=n<=10_000_000:return n
    return None

def stable_id(broker,symbol,day,url,title=''):
    digest=hashlib.sha1((url or title).encode('utf-8')).hexdigest()[:8]
    return f'{broker}-{symbol}-{day}-{digest}'

def report_like(label,url):
    hay=(clean(label)+' '+url).lower()
    return any(word in hay for word in REPORT_WORDS)

def discover_generic(raw,source,universe):
    p=AnchorParser();p.feed(raw);rows=[];seen=set()
    for href,label in p.rows:
        if not label or not report_like(label,href):continue
        symbol=ticker_from_text(label,universe)
        if not symbol:continue
        url=safe_url(source['url'],href)
        if not url or url in seen:continue
        seen.add(url);rows.append({'symbol':symbol,'title':label,'sourceUrl':url})
    return rows

def discover_fpts(raw,source,universe):
    rows=discover_generic(raw,source,universe);text=page_text(raw)
    for m in re.finditer(r'(\d{1,2}/\d{1,2}/20\d{2})\s+([A-Z]{3})\s+(.{8,140}?)(?=\d{1,2}/\d{1,2}/20\d{2}|$)',text):
        day,symbol,title=m.groups()
        if symbol not in universe:continue
        try:published=datetime.strptime(day,'%d/%m/%Y').date().isoformat()
        except ValueError:continue
        rows.append({'symbol':symbol,'title':clean(title),'sourceUrl':source['url'],'publishedAt':published})
    return dedupe_seeds(rows)

def discover_vietcap(raw,source,universe):
    rows=discover_generic(raw,source,universe);text=page_text(raw)
    pattern=r'\b([A-Z]{3})\s+\[(BUY|OUTPERFORM|MARKET PERFORM|UNDERPERFORM|SELL)\s+[+\-]?[0-9.,]+%\]\s*-\s*(.{8,180}?)\s+(?:Company Research|Doanh Nghiệp)\s+(\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2})'
    for m in re.finditer(pattern,text,re.I):
        symbol,rating,title,day=m.groups()
        if symbol not in universe:continue
        published=parse_date(day)
        if not published:continue
        rows.append({'symbol':symbol,'title':clean(title),'sourceUrl':source['url'],'publishedAt':published,'recommendation':RATING_ALIASES.get(rating.upper(),rating.upper())})
    return dedupe_seeds(rows)

def discover_acbs(raw,source,universe):
    rows=discover_generic(raw,source,universe);text=page_text(raw)
    pattern=r'(\d{1,2}/\d{1,2}/20\d{2})\s+([A-Z]{3})\s+Khuyến nghị\s+(Mua|Khả quan|Trung lập|Nắm giữ|Bán).*?Giá mục tiêu\s+([0-9.]+)\s*VND'
    for m in re.finditer(pattern,text,re.I|re.S):
        day,symbol,rating,target=m.groups()
        if symbol not in universe:continue
        try:published=datetime.strptime(day,'%d/%m/%Y').date().isoformat()
        except ValueError:continue
        rows.append({'symbol':symbol,'title':'Khuyến nghị gần nhất '+symbol,'sourceUrl':source['url'],'publishedAt':published,'recommendation':parse_rating(rating),'targetPrice':int(re.sub(r'\D','',target))})
    return dedupe_seeds(rows)

def dedupe_seeds(rows):
    out=[];seen=set()
    for row in rows:
        key=(row.get('sourceUrl'),row.get('symbol'),row.get('publishedAt'),row.get('title'))
        if key in seen:continue
        seen.add(key);out.append(row)
    return out

def parse_report_page(raw,seed,source):
    text=page_text(raw);published=seed.get('publishedAt') or parse_date(text)
    if not published:return None
    symbol=seed['symbol'];rating=seed.get('recommendation') or parse_rating(text)
    target=seed.get('targetPrice') or parse_target(text,symbol)
    result={
        'id':stable_id(source['code'],symbol,published,seed.get('sourceUrl',''),seed.get('title','')),
        'symbol':symbol,'broker':source['code'],'brokerName':source.get('name',source['code']),
        'publishedAt':published,'title':clean(seed.get('title') or f'Báo cáo {symbol}'),
        'currency':'VND','sourceUrl':seed.get('sourceUrl') or source['url']
    }
    if rating:result['recommendation']=rating
    if target:result['targetPrice']=target
    bits=[]
    if rating:bits.append('khuyến nghị '+rating)
    if target:bits.append('giá mục tiêu '+f'{target:,}'.replace(',','.')+' đồng/cp')
    result['summary']=source['code']+' công bố báo cáo ngày '+datetime.fromisoformat(published).strftime('%d/%m/%Y')+((' với '+', '.join(bits))+'.' if bits else '.')+' FinQuery lưu metadata và dẫn về nguồn gốc; xem báo cáo gốc để đọc đầy đủ luận điểm.'
    return result

def seed_to_report(seed,source):
    published=seed.get('publishedAt')
    if not published:return None
    result={
        'id':stable_id(source['code'],seed['symbol'],published,seed.get('sourceUrl',''),seed.get('title','')),
        'symbol':seed['symbol'],'broker':source['code'],'brokerName':source.get('name',source['code']),
        'publishedAt':published,'title':clean(seed.get('title') or ('Báo cáo '+seed['symbol'])),
        'currency':'VND','sourceUrl':seed.get('sourceUrl') or source['url']
    }
    if seed.get('recommendation'):result['recommendation']=seed['recommendation']
    if seed.get('targetPrice'):result['targetPrice']=seed['targetPrice']
    result['summary']=source['code']+' có báo cáo '+seed['symbol']+' ngày '+datetime.fromisoformat(published).strftime('%d/%m/%Y')+'. FinQuery lưu metadata và link nguồn; mở nguồn để đọc nội dung đầy đủ.'
    return result

def merge_reports(existing,discovered):
    by_source={r.get('sourceUrl'):dict(r) for r in existing if r.get('sourceUrl')}
    by_id={r.get('id'):dict(r) for r in existing if r.get('id')}
    for row in discovered:
        prior=by_source.get(row.get('sourceUrl')) or by_id.get(row.get('id'))
        if prior:
            merged={**row,**prior}
            for key in ('publishedAt','recommendation','targetPrice','currency','sourceUrl','title','broker','brokerName','symbol'):
                if row.get(key) is not None:merged[key]=row[key]
        else:merged=row
        by_id[merged['id']]=merged
        if merged.get('sourceUrl'):by_source[merged['sourceUrl']]=merged
    unique={r['id']:r for r in by_id.values() if r.get('id')}
    return sorted(unique.values(),key=lambda r:(r.get('publishedAt',''),r.get('broker',''),r.get('symbol','')),reverse=True)

def validate_events(value):
    rows=value.get('events') if isinstance(value,dict) else None
    if not isinstance(rows,list):raise ValueError('corporate-events.json must contain events[]')
    for row in rows:
        source=row.get('source') or {}
        if not re.fullmatch(r'[A-Z]{3}',str(row.get('symbol','')).upper()):raise ValueError('invalid event symbol')
        if not re.fullmatch(r'20\d{2}-\d{2}-\d{2}',str(row.get('date',''))):raise ValueError('invalid event date')
        if not str(source.get('url','')).startswith('https://'):raise ValueError('event source must be https')
    return value

def load_sources():
    value=read(ROOT/'config/research_sources.json',{'sources':[]})
    return [x for x in value.get('sources',[]) if x.get('enabled')]

def discover_mbs_list(raw,universe):
    source={'code':'MBS','name':'MB Securities','url':'https://www.mbs.com.vn/bao-cao-phan-tich-co-phieu/','adapter':'generic_anchors'}
    return discover_generic(raw,source,universe)

def parse_mbs_report(raw,seed):
    source={'code':'MBS','name':'MB Securities','url':'https://www.mbs.com.vn/bao-cao-phan-tich-co-phieu/','adapter':'generic_anchors'}
    return parse_report_page(raw,seed,source)

def discover_source(source,raw,universe):
    adapter=source.get('adapter')
    if adapter=='fpts_listing':return discover_fpts(raw,source,universe)
    if adapter=='vietcap_listing':return discover_vietcap(raw,source,universe)
    if adapter=='acbs_listing':return discover_acbs(raw,source,universe)
    if adapter=='health_only':return []
    return discover_generic(raw,source,universe)

def refresh(output,max_detail=120):
    companies=read(output/'companies.json',read(ROOT/'data/companies.json',[]))
    universe={str(x.get('symbol','')).upper() for x in companies if re.fullmatch(r'[A-Z]{3}',str(x.get('symbol','')).upper())}
    research_path=output/'broker-research.json';events_path=output/'corporate-events.json'
    seeded_research=read(ROOT/'data/broker-research.json',{'version':1,'reports':[]})
    published_research=read(research_path,{'version':1,'reports':[]})
    current={'version':2,'reports':merge_reports(seeded_research.get('reports') or [],published_research.get('reports') or [])}
    seeded_events=read(ROOT/'data/corporate-events.json',{'version':1,'events':[]})
    published_events=read(events_path,{'version':1,'events':[]})
    event_by_id={x.get('id'):x for x in seeded_events.get('events',[]) if x.get('id')}
    event_by_id.update({x.get('id'):x for x in published_events.get('events',[]) if x.get('id')})
    events=validate_events({'version':1,'updatedAt':published_events.get('updatedAt') or seeded_events.get('updatedAt'),'events':list(event_by_id.values())})
    discovered=[];health=[];budget=max(1,max_detail)
    for source in load_sources():
        row={'code':source['code'],'name':source.get('name',source['code']),'url':source['url'],'mode':source.get('mode',''),'adapter':source.get('adapter',''),'checkedAt':now(),'status':'pending','discovered':0,'parsed':0}
        try:
            raw,status,ctype=fetch(source['url']);row['httpStatus']=status
            seeds=discover_source(source,raw,universe);row['discovered']=len(seeds)
            if source.get('adapter')=='health_only':
                row['status']='reachable';health.append(row);continue
            parsed=0
            for seed in seeds[:min(60,budget)]:
                report=None
                same_listing=(seed.get('sourceUrl')==source['url'])
                if seed.get('publishedAt') and same_listing:
                    report=seed_to_report(seed,source)
                else:
                    try:
                        detail,_,_=fetch(seed.get('sourceUrl') or source['url'])
                        report=parse_report_page(detail,seed,source)
                    except Exception:
                        report=seed_to_report(seed,source)
                if report:discovered.append(report);parsed+=1
            budget=max(1,budget-parsed);row['parsed']=parsed;row['status']='ok' if parsed else ('reachable_no_parse' if seeds else 'reachable_no_reports')
        except Exception as exc:
            row['status']='error';row['error']=str(exc)[:220]
        health.append(row)
    reports=merge_reports(current.get('reports') or [],discovered)
    value={
        'version':2,'updatedAt':now(),
        'policy':'Ratings and target prices are attributed to the publishing broker. FinQuery aggregates source-linked metadata and does not convert them into its own recommendation.',
        'reports':reports
    }
    write(research_path,value);events['updatedAt']=events.get('updatedAt') or now();write(events_path,events)
    ok=sum(1 for x in health if x['status'] in ('ok','reachable','reachable_no_reports','reachable_no_parse'))
    status={'checkedAt':now(),'sourcesTotal':len(health),'sourcesReachable':ok,'reportsDiscoveredThisRun':len(discovered),'storedReports':len(reports),'corporateEvents':len(events.get('events') or []),'sources':health}
    write(output/'insights-status.json',status)
    print(json.dumps(status,ensure_ascii=False))
    return status

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default=str(ROOT/'data'));p.add_argument('--max-detail',type=int,default=int(os.environ.get('RESEARCH_DETAIL_BUDGET','120')));args=p.parse_args()
    refresh(Path(args.output),args.max_detail)

if __name__=='__main__':main()
