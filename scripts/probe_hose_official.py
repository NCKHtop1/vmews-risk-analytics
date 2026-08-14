import requests,re,urllib.parse
host='https://www.hsx.vn';H={'User-Agent':'Mozilla/5.0'};s=requests.Session();r=s.get(host+'/',headers=H,timeout=20);src=re.findall(r'<script[^>]+src=["\']([^"\']+)',r.text,re.I)[-1];txt=s.get(urllib.parse.urljoin(host,src),headers=H,timeout=35).text
for needle in ['function $n','$n=function','var $n','getUrlApi','SERVICE_NEWS','configData','serviceUrl','SERVICE_DEFAULT']:
 pos=[m.start() for m in re.finditer(re.escape(needle),txt)];print('\nNEEDLE',needle,'N',len(pos))
 for p in pos[:40]:print(txt[max(0,p-1200):p+2200])
# Collect all URLs and API-ish host fragments embedded in bundle.
urls=sorted(set(re.findall(r'https?://[^"\'\\\s]{5,220}',txt)))
for u in urls:
 if any(k in u.lower() for k in ['api','hsx','hose']):print('URL',u[:500])
