import requests,re,json,urllib.parse
host='https://www.hsx.vn';H={'User-Agent':'Mozilla/5.0','Accept':'text/html,*/*'};s=requests.Session();r=s.get(host+'/vi/quan-ly-niem-yet/co-phieu',headers=H,timeout=20);print('HOME',r.status_code,len(r.text));scripts=re.findall(r'<script[^>]+src=["\']([^"\']+)',r.text,re.I);print('SCRIPTS',scripts)
for src in scripts:
 try:
  u=urllib.parse.urljoin(host,src);z=s.get(u,headers=H,timeout=25);print('BUNDLE',u,z.status_code,len(z.text));
  if len(z.text)<5000:continue
  needles=['api/','/api','cong-bo','congbo','disclosure','announcement','listed','symbol','news','information']
  for nd in needles:
   hits=[]
   for m in re.finditer(re.escape(nd),z.text,re.I):hits.append(z.text[max(0,m.start()-180):m.start()+520])
   if hits:
    print('\nNEEDLE',nd,'COUNT',len(hits));print('\n---\n'.join(hits[:8]))
 except Exception as e:print('ERR',src,repr(e))