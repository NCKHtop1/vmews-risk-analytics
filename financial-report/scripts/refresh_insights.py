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
from concurrent.futures import ThreadPoolExecutor, as_completed
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

def fetch(url,timeout=10):
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
    iso=re.search(r'\b(20\d{2}-\d{2}-\d{2})\b',value)
    if iso:
        try:return datetime.strptime(iso.group(1),'%Y-%m-%d').date().isoformat()
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

def discover_text_listing(raw,source,universe):
    """Discover report metadata from public listing pages whose titles are plain text."""
    rows=discover_generic(raw,source,universe)
    text=page_text(raw)
    matches=list(re.finditer(r'\b(\d{1,2}[/-]\d{1,2}[/-]20\d{2})\b',text))
    for idx,m in enumerate(matches):
        published=parse_date(m.group(1))
        if not published:continue
        end=matches[idx+1].start() if idx+1<len(matches) else min(len(text),m.end()+520)
        chunk=clean(text[m.end():end])[:520]
        symbol=ticker_from_text(chunk,universe)
        if not symbol:continue
        # Keep company-research chunks; exclude obvious market-only headlines.
        low=chunk.lower()
        if any(x in low for x in ('vn-index','vnindex','thị trường giữa phiên','thị trường cuối phiên','bản tin ngày')) and not re.search(r'\b'+re.escape(symbol)+r'\b',chunk):
            continue
        title=chunk
        for noise in ('other ','Báo cáo đặc biệt ','Phân tích công ty ','Báo cáo doanh nghiệp ','XEM CHI TIẾT ','Xem báo cáo ','Tải file '):
            if title.startswith(noise):title=title[len(noise):]
        title=clean(title)[:220]
        row={'symbol':symbol,'title':title or ('Báo cáo '+symbol),'sourceUrl':source['url'],'publishedAt':published}
        rating=parse_rating(chunk);target=parse_target(chunk,symbol)
        if rating:row['recommendation']=rating
        if target:row['targetPrice']=target
        rows.append(row)
    return dedupe_seeds(rows)

BROKER_ALIASES={
    'MB SECURITIES':'MBS','MBS':'MBS','KB SECURITIES VIETNAM':'KBSV','KBSV':'KBSV',
    'BIDV SECURITIES':'BSC','BSC':'BSC','VIETCAP':'VIETCAP','VCSC':'VIETCAP',
    'FPT SECURITIES':'FPTS','FPTS':'FPTS','ACB SECURITIES':'ACBS','ACBS':'ACBS',
    'SSI':'SSI','SSI RESEARCH':'SSI','HSC':'HSC','VNDIRECT':'VNDIRECT',
    'VIETINBANK SECURITIES':'CTS','CTS':'CTS','TECHCOM SECURITIES':'TCBS','TCBS':'TCBS',
    'PHU HUNG SECURITIES':'PHS','PHS':'PHS','VIX SECURITIES':'VIX','VIX':'VIX',
    'VIET DRAGON SECURITIES':'VDSC','RONG VIET SECURITIES':'VDSC','VDSC':'VDSC',
    'MIRAE ASSET':'MIRAE','MIRAE ASSET SECURITIES VIETNAM':'MIRAE',
    'MIRAE ASSET SECURITIES':'MIRAE','MAS':'MIRAE','AGR':'AGR','AGRISOCO':'AGRISECO','AGRISECO':'AGRISECO',
    'YUANTA SECURITIES VIETNAM':'YUANTA','YUANTA':'YUANTA','KIS VIETNAM':'KIS','KIS':'KIS',
    'SAIGON-HANOI SECURITIES':'SHS','SHS':'SHS','VIETCOMBANK SECURITIES':'VCBS','VCBS':'VCBS',
    'VIETINBANKSC':'CTS','VIETINBANK SC':'CTS','VNDS':'VNDIRECT','VND':'VNDIRECT',
    'MAS':'MIRAE','YSVN':'YUANTA','DSC':'DSC','KAFI':'KAFI','NHSV':'NHSV','BETA':'BETA',
    'SSV':'SSV','VPX':'VPX','EVS':'EVS','KAFI SECURITIES':'KAFI','AGRISECO':'AGRISECO',
    'BVSC':'BVSC','BVSCC':'BVSC','BMS':'BMS','SBBS':'SBBS','VPBS':'VPBS','KAFI':'KAFI',
    'VFS':'VFS','BETA':'BETA','NHSV':'NHSV','VPBANKS':'VPX','VPS':'VPX','SSV':'SSV',
    'YSVN':'YUANTA','YUGI':'YUANTA','BVS':'BVSC','VNDIRECT':'VNDIRECT','VND':'VNDIRECT',
    'THEODOI':'THEO DÕI','TÍCH LŨY':'TÍCH LŨY','THEO DÕI':'THEO DÕI'
}

def parse_sse_or_json(body):
    body=body.decode('utf-8','replace') if isinstance(body,(bytes,bytearray)) else str(body or '')
    stripped=body.strip()
    if not stripped:return {}
    if stripped.startswith('{') or stripped.startswith('['):
        return json.loads(stripped)
    values=[]
    for line in stripped.splitlines():
        if not line.startswith('data:'):continue
        payload=line[5:].strip()
        if not payload or payload=='[DONE]':continue
        try:values.append(json.loads(payload))
        except Exception:pass
    if not values:return {}
    return next((x for x in reversed(values) if isinstance(x,dict) and ('result'in x or 'error'in x)),values[-1])

def mcp_post(url,token,payload,session_id=None,timeout=35):
    headers={'User-Agent':UA,'Accept':'application/json, text/event-stream','Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    if session_id:headers['Mcp-Session-Id']=session_id
    req=Request(url,data=json.dumps(payload).encode('utf-8'),headers=headers,method='POST')
    with urlopen(req,timeout=timeout) as response:
        body=response.read(2_000_000)
        return parse_sse_or_json(body),response.headers.get('Mcp-Session-Id') or session_id

def finlens_tool_call(token,tool_name,arguments):
    url=os.environ.get('FINLENS_MCP_URL','https://mcp.finlens.vn/mcp')
    last=None
    for protocol in ('2025-06-18','2024-11-05'):
        try:
            init={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':protocol,'capabilities':{},'clientInfo':{'name':'FinQuery','version':'7'}}}
            reply,session=mcp_post(url,token,init)
            if isinstance(reply,dict) and reply.get('error'):raise RuntimeError(str(reply['error']))
            try:mcp_post(url,token,{'jsonrpc':'2.0','method':'notifications/initialized'},session)
            except Exception:pass
            call={'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':tool_name,'arguments':arguments}}
            result,_=mcp_post(url,token,call,session)
            if isinstance(result,dict) and result.get('error'):raise RuntimeError(str(result['error']))
            return result
        except Exception as exc:last=exc
    raise RuntimeError('FinLens MCP: '+str(last))

def mcp_payload(value):
    result=value.get('result',{}) if isinstance(value,dict) else {}
    if isinstance(result.get('structuredContent'),(dict,list)):return result['structuredContent']
    for part in result.get('content') or []:
        if not isinstance(part,dict) or part.get('type')!='text':continue
        raw=part.get('text','').strip()
        try:return json.loads(raw)
        except Exception:continue
    return result

def collect_dicts(value):
    out=[]
    def walk(x):
        if isinstance(x,dict):
            out.append(x)
            for v in x.values():walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(value);return out

def first_value(row,*keys):
    for key in keys:
        value=row.get(key)
        if value not in (None,''):return value
    return None

def normalize_broker(value):
    raw=clean(value).upper()
    if raw in BROKER_ALIASES:return BROKER_ALIASES[raw]
    for name,code in BROKER_ALIASES.items():
        if name in raw:return code
    compact=re.sub(r'[^A-Z0-9]','',raw)
    return compact[:16] or 'FINLENS'

def normalize_finlens_report(row,symbol):
    title=clean(first_value(row,'title','report_title','name','report_name'))
    raw_broker=first_value(row,'broker','broker_name','securities_company','source','publisher')
    published=parse_date(first_value(row,'published_at','publishedAt','report_date','date','created_at') or '')
    row_symbol=clean(first_value(row,'ticker','symbol','stock_code') or symbol).upper()
    if row_symbol!=symbol or not title or not published:return None
    broker=normalize_broker(raw_broker or 'FINLENS')
    url=first_value(row,'source_url','sourceUrl','report_url','url','download_url','pdf_url')
    report_id=clean(first_value(row,'report_id','id','reportId') or hashlib.sha1((broker+symbol+published+title).encode()).hexdigest()[:12])
    if not (isinstance(url,str) and url.startswith(('http://','https://'))):
        url='https://finlens.vn/?ticker='+symbol+'&report='+re.sub(r'[^A-Za-z0-9_-]','',report_id)[:80]
    rating=parse_rating(first_value(row,'recommendation','rating','action') or '')
    target_raw=first_value(row,'target_price','targetPrice','target','fair_value')
    target=None
    if target_raw not in (None,''):
        try:
            n=float(str(target_raw).replace(',',''))
            if 0<n<1000:n*=1000
            if 1000<=n<=10_000_000:target=int(round(n))
        except Exception:pass
    result={
      'id':stable_id(broker,symbol,published,url,title),'symbol':symbol,'broker':broker,
      'brokerName':clean(raw_broker or broker),'publishedAt':published,'title':title[:240],
      'currency':'VND','sourceUrl':url,'dataProvider':'FINLENS'
    }
    if rating:result['recommendation']=rating
    if target:result['targetPrice']=target
    summary=clean(first_value(row,'summary','abstract','description','short_summary'))
    if summary:result['summary']=summary[:900]
    else:result['summary']='Metadata báo cáo được FinLens tổng hợp; FinQuery giữ nguyên nguồn CTCK, ngày báo cáo, khuyến nghị và giá mục tiêu khi có.'
    return result

def discover_finlens(source,universe,prior_status):
    token=os.environ.get('FINLENS_MCP_TOKEN') or os.environ.get('FINLENS_API_KEY')
    row={'code':'FINLENS','name':source.get('name','FinLens Research'),'url':source['url'],'mode':'authenticated_mcp','adapter':'finlens_mcp','checkedAt':now(),'status':'not_configured','discovered':0,'parsed':0}
    if not token:
        row['note']='Set FINLENS_API_KEY or FINLENS_MCP_TOKEN to import authenticated research metadata.'
        return [],row,int(prior_status.get('finlensCursor') or 0)
    symbols=sorted(universe)
    if not symbols:return [],row,0
    cursor=int(prior_status.get('finlensCursor') or 0)%len(symbols)
    budget=max(1,min(len(symbols),int(os.environ.get('FINLENS_SYMBOL_BUDGET','25'))))
    batch=[symbols[(cursor+i)%len(symbols)] for i in range(budget)]
    reports=[];errors=[]
    for symbol in batch:
        try:
            raw=finlens_tool_call(token,'research_list_reports',{'scope':'stock','ticker':symbol,'limit':10})
            payload=mcp_payload(raw)
            seen=set()
            for candidate in collect_dicts(payload):
                normalized=normalize_finlens_report(candidate,symbol)
                if not normalized or normalized['id'] in seen:continue
                seen.add(normalized['id']);reports.append(normalized)
        except Exception as exc:
            errors.append(symbol+': '+str(exc)[:100])
            if len(errors)>=4:break
    row['discovered']=len(reports);row['parsed']=len(reports)
    row['symbolsAttempted']=len(batch if not errors else batch[:max(1,len(batch))])
    row['status']='ok' if reports else ('error' if errors else 'reachable_no_reports')
    if errors:row['errors']=errors[:4]
    return reports,row,(cursor+budget)%len(symbols)

def aggregated_report(symbol,broker_name,published,title,page_url,provider,source_url=None):
    broker=normalize_broker(broker_name)
    title=clean(title)[:240]
    published=parse_date(published)
    if not title or not published:return None
    rating=parse_rating(title);target=parse_target(title,symbol)
    fingerprint=hashlib.sha1((broker+'|'+symbol+'|'+published+'|'+title).encode('utf-8')).hexdigest()[:12]
    source_url=source_url or (page_url+('#' if '#' not in page_url else '&')+'finquery-'+fingerprint)
    result={
      'id':stable_id(broker,symbol,published,source_url,title),'symbol':symbol,'broker':broker,
      'brokerName':clean(broker_name or broker),'publishedAt':published,'title':title,
      'currency':'VND','sourceUrl':source_url,'dataProvider':provider
    }
    if rating:result['recommendation']=rating
    if target:result['targetPrice']=target
    bits=[]
    if rating:bits.append('khuyến nghị '+rating)
    if target:bits.append('giá mục tiêu '+f'{target:,}'.replace(',','.')+' đồng/cp')
    result['summary']=(broker+' có báo cáo '+symbol+' ngày '+datetime.fromisoformat(published).strftime('%d/%m/%Y')+
      ((' với '+', '.join(bits))+'.' if bits else '.')+
      ' FinQuery lấy metadata từ chỉ mục công khai '+provider+' và giữ nguyên CTCK phát hành.')
    return result

def parse_smartchart_symbol(raw,symbol,page_url):
    text=page_text(raw);rows=[];seen=set()
    pattern=r'(?<![A-Z0-9])'+re.escape(symbol)+r'\s*:\s*(.{5,260}?)\s+([A-Za-zÀ-ỹ0-9][A-Za-zÀ-ỹ0-9 .&_-]{1,60})\s+·\s+(20\d{2}-\d{2}-\d{2})'
    for m in re.finditer(pattern,text,re.I):
        title,broker,day=m.groups()
        # Stop titles from spanning across the preceding/next item.
        title=clean(title)
        if symbol+':' in title.upper():title=title.upper().split(symbol+':')[-1].strip()
        report=aggregated_report(symbol,broker,day,symbol+': '+title,page_url,'SMARTCHART')
        if report and report['id'] not in seen:seen.add(report['id']);rows.append(report)
    return rows

def parse_24hmoney_symbol(raw,symbol,page_url):
    text=page_text(raw);rows=[];seen=set();cursor=0
    p=AnchorParser();p.feed(raw)
    for href,label in p.rows:
        label=clean(label);low=label.lower()
        if symbol not in label.upper() or '/bao-cao-phan-tich/' not in href:
            continue
        if not any(k in low for k in ('khuyến nghị','báo cáo','cập nhật','outperform','mua ','bán ','nắm giữ','tăng tỷ trọng','khả quan','theo dõi','tích lũy')):
            continue
        pos=text.find(label,cursor)
        segment=text[pos:pos+520] if pos>=0 else text[:520]
        if pos>=0:cursor=pos+len(label)
        broker_match=re.search(r'Nguồn\s*:\s*([^:]{2,80}?)(?=\s+Ngày phát hành|\s+Tải về|$)',segment,re.I)
        date_match=re.search(r'Ngày phát hành\s*:\s*(\d{1,2}/\d{1,2}/20\d{2})',segment,re.I)
        broker=clean(broker_match.group(1)) if broker_match else ''
        day=date_match.group(1) if date_match else parse_date(segment)
        source_url=safe_url(page_url,href)
        if not broker or not day:
            continue
        report=aggregated_report(symbol,broker,day,label,page_url,'24HMONEY',source_url=source_url)
        if report and report['id'] not in seen:seen.add(report['id']);rows.append(report)
    if rows:return rows
    pattern=r'(?<![A-Z0-9])'+re.escape(symbol)+r'\s*:\s*(.{5,320}?)\s+Nguồn\s*:\s*(.{2,90}?)\s+Ngày phát hành\s*:\s*(\d{1,2}/\d{1,2}/20\d{2})'
    for m in re.finditer(pattern,text,re.I):
        title,broker,day=m.groups()
        report=aggregated_report(symbol,broker,day,symbol+': '+clean(title),page_url,'24HMONEY')
        if report and report['id'] not in seen:seen.add(report['id']);rows.append(report)
    return rows

def discover_public_aggregator(source,universe,prior_status):
    symbols=sorted(universe)
    code=source['code'];adapter=source['adapter'];template=source['urlTemplate']
    cursors=dict(prior_status.get('aggregatorCursors') or {})
    cursor=int(cursors.get(code) or 0)%max(1,len(symbols))
    if adapter=='smartchart_symbol':
        default_budget=int(os.environ.get('SMARTCHART_SYMBOL_BUDGET','40'))
    else:
        default_budget=int(os.environ.get('PUBLIC_AGGREGATOR_SYMBOL_BUDGET','100'))
    budget=max(1,min(len(symbols),default_budget))
    priority=[x.strip().upper() for x in os.environ.get('RESEARCH_PRIORITY_SYMBOLS','MBB,HPG,FPT,VCB,VIC').split(',') if x.strip().upper() in universe]
    batch=[]
    for symbol in priority+[symbols[(cursor+i)%len(symbols)] for i in range(budget)]:
        if symbol not in batch:batch.append(symbol)
    def fetch_one(symbol):
        page_url=template.replace('{symbol}',symbol)
        try:
            raw,_,_=fetch(page_url,timeout=8)
            if adapter=='smartchart_symbol':rows=parse_smartchart_symbol(raw,symbol,page_url)
            else:rows=parse_24hmoney_symbol(raw,symbol,page_url)
            return symbol,rows,True,None
        except Exception as exc:
            return symbol,[],False,str(exc)[:90]
    reports=[];errors=[];reachable=0
    workers=max(4,min(18,int(os.environ.get('RESEARCH_FETCH_WORKERS','16'))))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(fetch_one,symbol) for symbol in batch]
        for future in as_completed(futures):
            symbol,rows,ok,err=future.result()
            if ok:reachable+=1;reports.extend(rows)
            elif err:errors.append(symbol+': '+err)
    next_cursor=(cursor+budget)%len(symbols) if symbols else 0
    row={'code':code,'name':source.get('name',code),'url':template,'mode':'public_aggregator','adapter':adapter,
         'checkedAt':now(),'status':'ok' if reports else ('reachable_no_reports' if reachable else 'error'),
         'discovered':len(reports),'parsed':len(reports),'symbolsAttempted':len(batch),'symbolsReachable':reachable}
    if errors:row['errors']=errors[:6]
    return reports,row,next_cursor

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

def report_logical_key(row):
    import unicodedata
    title=clean(row.get('title','')).lower()
    title=unicodedata.normalize('NFD',title)
    title=''.join(ch for ch in title if unicodedata.category(ch)!='Mn')
    title=re.sub(r'[^a-z0-9]+',' ',title).strip()
    return '|'.join([clean(row.get('broker','')).upper(),clean(row.get('symbol','')).upper(),str(row.get('publishedAt','')),title])

def report_quality(row):
    provider=str(row.get('dataProvider','')).upper()
    url=str(row.get('sourceUrl',''))
    score=0
    if provider=='24HMONEY':score+=4
    if provider=='SMARTCHART':score+=3
    if provider and provider not in ('24HMONEY','SMARTCHART'):score+=4
    if '/bao-cao-phan-tich/' in url and '24hmoney.vn' in url and '#finquery-' not in url:score+=4
    if '#finquery-' not in url:score+=1
    if row.get('recommendation'):score+=1
    if row.get('targetPrice') is not None:score+=1
    if len(str(row.get('summary','')))>=160:score+=1
    return score

def merge_reports(existing,discovered):
    buckets={}
    for row in list(existing or [])+list(discovered or []):
        if not isinstance(row,dict) or not row.get('symbol') or not row.get('broker') or not row.get('publishedAt'):
            continue
        key=report_logical_key(row)
        prior=buckets.get(key)
        if not prior:
            buckets[key]=dict(row);continue
        best=max((prior,row),key=report_quality)
        other=row if best is prior else prior
        merged={**other,**best}
        for field in ('recommendation','targetPrice','brokerName','sourceUrl','dataProvider'):
            if not merged.get(field) and other.get(field):merged[field]=other[field]
        curated_other=any(other.get(field) for field in ('highlights','catalysts','risks'))
        curated_best=any(best.get(field) for field in ('highlights','catalysts','risks'))
        for field in ('summary','highlights','catalysts','risks'):
            bv=best.get(field);ov=other.get(field)
            if isinstance(bv,list) and isinstance(ov,list):
                if len(ov)>len(bv) or (curated_other and not curated_best):merged[field]=ov
            elif isinstance(bv,str) and isinstance(ov,str):
                if len(ov)>len(bv) or (field=='summary' and curated_other and not curated_best):merged[field]=ov
            elif not bv and ov:
                merged[field]=ov
        buckets[key]=merged
    rows=list(buckets.values())
    return sorted(rows,key=lambda r:(r.get('publishedAt',''),r.get('broker',''),r.get('symbol',''),r.get('title','')),reverse=True)

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
    if adapter=='text_listing':return discover_text_listing(raw,source,universe)
    if adapter in ('health_only','finlens_mcp','smartchart_symbol','money24_symbol'):return []
    return discover_generic(raw,source,universe)

def refresh(output,max_detail=24):
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
    discovered=[];health=[];detail_jobs=[]
    prior_status=read(output/'insights-status.json',{})
    finlens_cursor=int(prior_status.get('finlensCursor') or 0)
    aggregator_cursors=dict(prior_status.get('aggregatorCursors') or {})
    detail_budget=max(0,int(max_detail))
    sources=load_sources()
    for source in sources:
        source_url=source.get('url') or source.get('urlTemplate') or ''
        row={'code':source['code'],'name':source.get('name',source['code']),'url':source_url,'mode':source.get('mode',''),'adapter':source.get('adapter',''),'checkedAt':now(),'status':'pending','discovered':0,'parsed':0}
        if source.get('adapter')=='finlens_mcp':
            rows,row,finlens_cursor=discover_finlens(source,universe,prior_status)
            discovered.extend(rows);health.append(row);continue
        if source.get('adapter') in ('smartchart_symbol','money24_symbol'):
            rows,row,next_cursor=discover_public_aggregator(source,universe,prior_status)
            aggregator_cursors[source['code']]=next_cursor
            discovered.extend(rows);health.append(row);continue
        try:
            raw,status,ctype=fetch(source_url,timeout=8);row['httpStatus']=status
            seeds=discover_source(source,raw,universe);row['discovered']=len(seeds)
            if source.get('adapter')=='health_only':
                row['status']='reachable';health.append(row);continue
            parsed=0
            # Listing metadata is enough for the full timeline. Only queue a small
            # number of detail pages when the listing did not contain a date.
            for seed in seeds:
                if seed.get('publishedAt'):
                    report=seed_to_report(seed,source)
                    if report:discovered.append(report);parsed+=1
                    continue
                if len(detail_jobs)>=detail_budget:continue
                detail_jobs.append((source,seed))
            row['parsed']=parsed
            row['status']='ok' if parsed or seeds else 'reachable_no_reports'
        except Exception as exc:
            row['status']='error';row['error']=str(exc)[:220]
        health.append(row)
    if detail_jobs:
        workers=max(4,min(16,int(os.environ.get('RESEARCH_FETCH_WORKERS','16'))))
        def enrich(task):
            source,seed=task
            try:
                detail,_,_=fetch(seed.get('sourceUrl') or source['url'],timeout=8)
                return source,parse_report_page(detail,seed,source),None
            except Exception as exc:
                return source,seed_to_report(seed,source),str(exc)[:160]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(enrich,task) for task in detail_jobs]
            for future in as_completed(futures):
                source,report,err=future.result()
                if report:discovered.append(report)
                for row in health:
                    if row['code']==source['code']:
                        row['parsed']=int(row.get('parsed') or 0)+(1 if report else 0)
                        if err:row.setdefault('detailErrors',[]).append(err)
                        break
    reports=merge_reports(current.get('reports') or [],discovered)
    value={'version':2,'updatedAt':now(),
        'policy':'Ratings and target prices are attributed to the publishing broker. FinQuery aggregates source-linked metadata and does not convert them into its own recommendation.',
        'reports':reports}
    write(research_path,value)
    events['updatedAt']=events.get('updatedAt') or now();write(events_path,events)
    ok=sum(1 for x in health if x['status'] in ('ok','reachable','reachable_no_reports','reachable_no_parse'))
    status={'checkedAt':now(),'sourcesTotal':len(health),'sourcesReachable':ok,
            'reportsDiscoveredThisRun':len(discovered),'storedReports':len(reports),
            'symbolsTotal':len(universe),'symbolsCovered':len({r.get('symbol') for r in reports if r.get('symbol')}),
            'corporateEvents':len(events.get('events') or []),'finlensCursor':finlens_cursor,
            'aggregatorCursors':aggregator_cursors,'detailEnriched':len(detail_jobs),'sources':health}
    write(output/'insights-status.json',status)
    print(json.dumps(status,ensure_ascii=False))
    return status

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default=str(ROOT/'data'));p.add_argument('--max-detail',type=int,default=int(os.environ.get('RESEARCH_DETAIL_BUDGET','120')));args=p.parse_args()
    refresh(Path(args.output),args.max_detail)

if __name__=='__main__':main()
