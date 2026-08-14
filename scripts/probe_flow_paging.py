import requests,json
base='https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/'
H={'User-Agent':'Mozilla/5.0','Referer':'https://cafef.vn/du-lieu/lich-su-giao-dich-fpt-3.chn'}
def longest(x):
 b=[]
 if isinstance(x,list) and (not x or isinstance(x[0],dict)):b=x
 if isinstance(x,dict):
  for v in x.values():
   z=longest(v)
   if len(z)>len(b):b=z
 return b
for ep in ['GDKhoiNgoai.ashx','GDTuDoanh.ashx']:
 for size in [20,100,500,2000]:
  u=base+ep;params={'Symbol':'FPT','Exchange':'HOSE','StartDate':'01/01/2018','EndDate':'13/08/2026','PageIndex':1,'PageSize':size};r=requests.get(u,params=params,headers=H,timeout=20);p=r.json();rows=longest(p);print(ep,'size',size,'status',r.status_code,'rows',len(rows),'topkeys',list(p)[:20] if isinstance(p,dict) else type(p).__name__);print('META',json.dumps({k:v for k,v in p.items() if not isinstance(v,(list,dict))},ensure_ascii=False)[:2000] if isinstance(p,dict) else '');print('DATES',[(x.get('Ngay') or x.get('Date')) for x in rows[:2]],[(x.get('Ngay') or x.get('Date')) for x in rows[-2:]])
 try:
  rr=requests.get(u,params={**params,'Type':'EXPORT','PageSize':20},headers=H,timeout=30);print('EXPORT',ep,rr.status_code,rr.headers.get('content-type'),len(rr.content),rr.text[:120].replace('\n',' '))
 except Exception as e:print('EXPORTERR',e)
