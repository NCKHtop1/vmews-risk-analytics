import re,requests,json
from bs4 import BeautifulSoup
u='https://cafef.vn/du-lieu/lich-su-giao-dich-fpt-3.chn'
r=requests.get(u,headers={'User-Agent':'Mozilla/5.0'},timeout=20);print(json.dumps({'status':r.status_code,'bytes':len(r.text)}))
for pat in ['ajax','Ajax','Export','export','trang-','foreign','Foreign','DataHistory','LichSu']:
    hits=[x.strip()[:500] for x in r.text.splitlines() if pat in x][:12]
    if hits:print('\nPATTERN',pat);print('\n'.join(hits))
s=BeautifulSoup(r.text,'html.parser');links=[]
for a in s.find_all('a',href=True):
    h=a['href']
    if 'lich-su-giao-dich' in h.lower() or 'ajax' in h.lower() or 'export' in h.lower():links.append(h)
print('LINKS',json.dumps(links[:80],ensure_ascii=False))
# Try old/new known endpoint patterns often used by CafeF history pages.
urls=[
 'https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/PriceHistory.ashx?Symbol=FPT&StartDate=&EndDate=&PageIndex=1&PageSize=20',
 'https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/ForeignTrading.ashx?Symbol=FPT&StartDate=&EndDate=&PageIndex=1&PageSize=20',
 'https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/GDKhoiNgoai.ashx?Symbol=FPT&StartDate=&EndDate=&PageIndex=1&PageSize=20',
 'https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/GDTuDoanh.ashx?Symbol=FPT&StartDate=&EndDate=&PageIndex=1&PageSize=20'
]
for x in urls:
 try:
  z=requests.get(x,headers={'User-Agent':'Mozilla/5.0','Referer':u},timeout=15);print('TRY',x,z.status_code,len(z.text),z.text[:250].replace('\n',' '))
 except Exception as e:print('ERR',x,str(e))
