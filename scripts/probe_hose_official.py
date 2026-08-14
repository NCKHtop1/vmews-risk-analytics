import requests,re,json
from urllib.parse import urlencode
H={'User-Agent':'Mozilla/5.0','Accept':'application/json, text/javascript, */*; q=0.01','X-Requested-With':'XMLHttpRequest','Referer':'https://www.hsx.vn/vi/quan-ly-niem-yet/co-phieu'}
s=requests.Session()
params={'pageFieldName1':'Code','pageFieldValue1':'FPT','pageFieldOperator1':'eq','pageFieldName2':'Sectors','pageFieldValue2':'','pageFieldOperator2':'','pageFieldName3':'Sector','pageFieldValue3':'00000000-0000-0000-0000-000000000000','pageFieldOperator3':'','pageFieldName4':'StartWith','pageFieldValue4':'','pageFieldOperator4':'','pageCriteriaLength':'4','_search':'false','rows':30,'page':'1','sidx':'id','sord':'desc'}
for host in ['https://www.hsx.vn','https://www1.hsx.vn']:
 try:
  u=host+'/Modules/Listed/Web/SymbolList?'+urlencode(params);r=s.get(u,headers=H,timeout=20);print('SYMBOL',host,r.status_code,len(r.text),r.text[:1500]);p=r.json();rows=p.get('rows') or [];f=[x for x in rows if len(x.get('cell',[]))>1 and x['cell'][1]=='FPT'];print('FPTROW',json.dumps(f[:2],ensure_ascii=False));
  if not f:continue
  id=f[0]['id'];v=host+f'/Modules/Listed/Web/SymbolView/{id}';rr=s.get(v,headers={'User-Agent':H['User-Agent']},timeout=20);print('VIEW',v,rr.status_code,len(rr.text));
  pats=sorted(set(re.findall(r'[/A-Za-z0-9._-]*(?:Ajax|ajax|Announcement|News|Disclosure|Information|SymbolView)[/A-Za-z0-9?&=._-]*',rr.text)))
  for x in pats[:200]:print('PATH',x)
  for line in rr.text.splitlines():
   if any(k.lower() in line.lower() for k in ['congbo','disclosure','information','ajax','announcement','news']):print('LINE',line.strip()[:1200])
 except Exception as e:print('ERR',host,repr(e))
