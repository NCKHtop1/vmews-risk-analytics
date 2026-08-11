import json, re, time, html
from datetime import datetime, timezone
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from pathlib import Path

SYMBOLS={
    'FPT':'FPT Corporation','PNJ':'Phu Nhuan Jewelry','VCB':'Vietcombank','HPG':'Hoa Phat',
    'MWG':'Mobile World','VHM':'Vinhomes','SSI':'SSI Securities','DGC':'Duc Giang Chemicals'
}
PUBLISHER_QUERIES=['','site:cafef.vn','site:vietstock.vn','site:vnexpress.net','site:tuoitre.vn','site:dantri.com.vn']

def clean(s):
    return re.sub(r'\s+',' ',html.unescape(s or '')).strip()

def fetch(q,limit=40):
    url='https://news.google.com/rss/search?q='+quote_plus(q)+'&hl=vi&gl=VN&ceid=VN:vi'
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 VMEWS-Research-News/1.0'})
    with urlopen(req,timeout=20) as r:
        root=ET.fromstring(r.read())
    out=[]
    for it in root.findall('.//item')[:limit]:
        out.append({
            'title':clean(it.findtext('title')),
            'link':clean(it.findtext('link')),
            'published':clean(it.findtext('pubDate')),
            'query':q
        })
    return out

def main():
    payload={
        'generatedAt':datetime.now(timezone.utc).isoformat(),
        'method':'publisher-diverse Google News RSS aggregation',
        'symbols':{}
    }
    for sym,name in SYMBOLS.items():
        rows=[]
        bases=[
            f'"{sym}" cổ phiếu "{name}"',
            f'"{sym}" "{name}" công bố thông tin',
            f'"{sym}" "{name}" kết quả kinh doanh'
        ]
        for base in bases:
            for domain in PUBLISHER_QUERIES:
                q=(base+' '+domain).strip()
                try:
                    rows.extend(fetch(q,25))
                except Exception:
                    pass
                time.sleep(.15)
        seen=set(); uniq=[]
        for x in rows:
            key=re.sub(r'[^a-z0-9à-ỹ]+',' ',x['title'].lower()).strip()
            if not key or key in seen:
                continue
            seen.add(key); uniq.append(x)
        payload['symbols'][sym]=uniq[:100]
    p=Path('data/research-news.json')
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    main()
