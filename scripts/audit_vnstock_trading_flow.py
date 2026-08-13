import json
from vnstock import Trading
out={}
for kwargs in [dict(symbol='FPT',source='VCI'),dict(source='VCI')]:
 try:
  x=Trading(**kwargs); out['init']=kwargs; out['methods']=[m for m in dir(x) if 'foreign' in m.lower() or 'trade' in m.lower() or 'price' in m.lower()]
  for n in ['foreign_trade','price_board']:
   try:
    f=getattr(x,n); z=f() if n=='foreign_trade' else f(['FPT']); out[n]={'ok':True,'rows':len(z),'columns':[str(c) for c in z.columns]}
   except Exception as e:out[n]={'ok':False,'error':str(e)}
  break
 except Exception as e:out.setdefault('errors',[]).append(str(e))
print(json.dumps(out,ensure_ascii=False,default=str))
