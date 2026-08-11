import json, re, html
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from pathlib import Path

SYMBOLS={
    'FPT':'FPT Corporation','PNJ':'Phu Nhuan Jewelry','VCB':'Vietcombank','HPG':'Hoa Phat',
    'MWG':'Mobile World','VHM':'Vinhomes','SSI':'SSI Securities','DGC':'Duc Giang Chemicals'
}
DOMAINS=['','site:cafef.vn','site:vietstock.vn','site:vnexpress.net']
RECENT_DAYS=540

def clean(s):
    return re.sub(r'\s+',' ',html.unescape(s or '')).strip()

def parse_date(s):
    try:
        dt=parsedate_to_datetime(s)
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def fetch(sym,name,domain,limit=40):
    q=(f'"{sym}" cổ phiếu "{name}" {domain}').strip()
    url='https://news.google.com/rss/search?q='+quote_plus(q)+'&hl=vi&gl=VN&ceid=VN:vi'
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 VMEWS-Research-News/3.0'})
    with urlopen(req,timeout=15) as r:
        root=ET.fromstring(r.read())
    out=[]
    for it in root.findall('.//item')[:limit]:
        title=clean(it.findtext('title'));published=clean(it.findtext('pubDate'));dt=parse_date(published)
        out.append({'symbol':sym,'title':title,'link':clean(it.findtext('link')),'published':published,'publishedTs':dt.timestamp() if dt else 0,'query':q})
    return out

def noisy(title):
    low=title.lower().strip()
    return (not low or low.startswith('untitled') or low.startswith('cw.') or 'chứng quyền' in low or 'covered warrant' in low)

def main():
    now=datetime.now(timezone.utc);cutoff=(now-timedelta(days=RECENT_DAYS)).timestamp()
    payload={'generatedAt':now.isoformat(),'windowDays':RECENT_DAYS,'method':'publisher-diverse Google News RSS aggregation; recent-window filtering; deduplicated snapshot','symbols':{s:[] for s in SYMBOLS}}
    jobs=[]
    with ThreadPoolExecutor(max_workers=8) as ex:
        for sym,name in SYMBOLS.items():
            for domain in DOMAINS:jobs.append(ex.submit(fetch,sym,name,domain))
        for fut in as_completed(jobs):
            try:
                for row in fut.result():payload['symbols'][row['symbol']].append(row)
            except Exception:pass
    for sym,rows in payload['symbols'].items():
        seen=set();uniq=[]
        rows=sorted(rows,key=lambda z:z.get('publishedTs',0),reverse=True)
        for x in rows:
            if x.get('publishedTs',0) and x['publishedTs']<cutoff:continue
            if noisy(x.get('title','')):continue
            key=re.sub(r'[^a-z0-9à-ỹ]+',' ',x['title'].lower()).strip()
            if not key or key in seen:continue
            seen.add(key);x.pop('symbol',None);x.pop('publishedTs',None);uniq.append(x)
        payload['symbols'][sym]=uniq[:100]
    p=Path('data/research-news.json');p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
