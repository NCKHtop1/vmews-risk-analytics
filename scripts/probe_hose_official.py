import requests,re,json,urllib.parse
host='https://www.hsx.vn';H={'User-Agent':'Mozilla/5.0','Accept':'text/html,*/*'};s=requests.Session();r=s.get(host+'/thong-tin-cong-bo',headers=H,timeout=20);print('HOME',r.status_code,len(r.text));scripts=re.findall(r'<script[^>]+src=["\']([^"\']+)',r.text,re.I);print('SCRIPTS',scripts)
for src in scripts:
    try:
        u=urllib.parse.urljoin(host,src);z=s.get(u,headers=H,timeout=35);txt=z.text;print('BUNDLE',u,z.status_code,len(txt));cand=set()
        for q in re.findall(r'["\']([^"\']{3,180})["\']',txt):
            low=q.lower()
            if any(k in low for k in ['news','announcement','information','disclosure','securities','secorg','article','public','tin-tuc','thong-tin']) and not any(x in low for x in ['translation','breadcrumb','tab.','homepage.','meta']):cand.add(q)
        print('CANDIDATES',len(cand))
        for x in sorted(cand)[:700]:print('STR',x)
        for needle in ['$n(un','SERVICE_NEWS','InformationPublished','DailyAnnouncements','PeriodicAnnouncements','OtherAnnouncements']:
            pos=[m.start() for m in re.finditer(re.escape(needle),txt)];print('CTX',needle,len(pos))
            for p in pos[:30]:print(txt[max(0,p-350):p+900])
    except Exception as e:print('ERR',src,repr(e))