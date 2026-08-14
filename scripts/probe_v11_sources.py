import re,requests,json
from bs4 import BeautifulSoup
u='https://cafef.vn/du-lieu/lich-su-giao-dich-fpt-3.chn'
r=requests.get(u,headers={'User-Agent':'Mozilla/5.0'},timeout=20);print(json.dumps({'status':r.status_code,'bytes':len(r.text)}))
for pat in ['Ajax/PageNew/DataHistory/GDKhoiNgoai','GDTuDoanh']:
    hits=[x.strip()[:900] for x in r.text.splitlines() if pat in x][:8]
    if hits:print('\nPATTERN',pat);print('\n'.join(hits))

def longest_list(x):
    best=[]
    if isinstance(x,list) and (not x or isinstance(x[0],dict)):best=x
    if isinstance(x,dict):
        for v in x.values():
            z=longest_list(v)
            if len(z)>len(best):best=z
    return best
urls={
 'price':'https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/PriceHistory.ashx?Symbol=FPT&Exchange=HOSE&StartDate=01/01/2024&EndDate=13/08/2026&PageIndex=1&PageSize=20',
 'foreign':'https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/GDKhoiNgoai.ashx?Symbol=FPT&Exchange=HOSE&StartDate=01/01/2024&EndDate=13/08/2026&PageIndex=1&PageSize=20',
 'prop':'https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/GDTuDoanh.ashx?Symbol=FPT&Exchange=HOSE&StartDate=01/01/2024&EndDate=13/08/2026&PageIndex=1&PageSize=20'}
for name,x in urls.items():
    try:
        z=requests.get(x,headers={'User-Agent':'Mozilla/5.0','Referer':u},timeout=15);p=z.json();rows=longest_list(p);print('\nSCHEMA',name,'status',z.status_code,'rows',len(rows));print(json.dumps(rows[0] if rows else p,ensure_ascii=False,default=str)[:4000])
    except Exception as e:print('ERR',name,str(e))