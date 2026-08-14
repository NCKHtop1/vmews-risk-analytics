import requests,json
H={'User-Agent':'Mozilla/5.0','Accept':'application/json,text/plain,*/*','Origin':'https://www.hsx.vn','Referer':'https://www.hsx.vn/'}
base='https://api.hsx.vn/n/api/v1'
urls=[
 base+'/news/cate?pageIndex=1&pageSize=30&startDate=2026-01-01&endDate=2026-08-14&aliasCate=thong-tin-cong-bo',
 base+'/news/securitiesType/1?pageIndex=1&pageSize=30&startDate=2026-01-01&endDate=2026-08-14',
 base+'/news/newstype/-1/1?pageIndex=1&pageSize=30&startDate=2026-01-01&endDate=2026-08-14',
 base+'/news/homepage?pageIndex=1&pageSize=30&startDate=2026-08-01&endDate=2026-08-14']
for u in urls:
 try:
  r=requests.get(u,headers=H,timeout=25);print('\nURL',u,'STATUS',r.status_code,'CT',r.headers.get('content-type'),'BYTES',len(r.content));print(r.text[:8000])
 except Exception as e:print('ERR',u,repr(e))