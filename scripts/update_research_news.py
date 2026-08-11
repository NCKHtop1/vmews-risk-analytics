import json, re, html
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from pathlib import Path

SYMBOLS={
    'FPT':'FPT Corporation','PNJ':'Phu Nhuan Jewelry','VCB':'Vietcombank','HPG':'Hoa Phat',
    'MWG':'Mobile World','VHM':'Vinhomes','SSI':'SSI Securities','DGC':'Duc Giang Chemicals'
}
DOMAINS=['','site:cafef.vn','site:vietstock.vn','site:vnexpress.net']

def clean(s):
    return re.sub(r'\s+',' ',html.unescape(s or '')).strip()

def fetch(sym,name,domain,limit=35):
    q=(f'"{sym}" cổ phiếu "{name}" {domain}').strip()
    url='https://news.google.com/rss/search?q='+quote_plus(q)+'&hl=vi&gl=VN&ceid=VN:vi'
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 VMEWS-Research-News/2.0'})
    with urlopen(req,timeout=15) as r:
        root=ET.fromstring(r.read())
    out=[]
    for it in root.findall('.//item')[:limit]:
        out.append({
            'symbol':sym,
            'title':clean(it.findtext('title')),
            'link':clean(it.findtext('link')),
            'published':clean(it.findtext('pubDate')),
            'query':q
        })
    return out

def main():
    payload={
        'generatedAt':datetime.now(timezone.utc).isoformat(),
        'method':'publisher-diverse Google News RSS aggregation; deduplicated snapshot',
        'symbols':{s:[] for s in SYMBOLS}
    }
    jobs=[]
    with ThreadPoolExecutor(max_workers=8) as ex:
        for sym,name in SYMBOLS.items():
            for domain in DOMAINS:
                jobs.append(ex.submit(fetch,sym,name,domain))
        for fut in as_completed(jobs):
            try:
                for row in fut.result():payload['symbols'][row['symbol']].append(row)
            except Exception:
                pass
    for sym,rows in payload['symbols'].items():
        seen=set();uniq=[]
        for x in sorted(rows,key=lambda z:z.get('published',''),reverse=True):
            key=re.sub(r'[^a-z0-9à-ỹ]+',' ',x['title'].lower()).strip()
            if not key or key in seen:continue
            seen.add(key);x.pop('symbol',None);uniq.append(x)
        payload['symbols'][sym]=uniq[:100]
    p=Path('data/research-news.json')
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
