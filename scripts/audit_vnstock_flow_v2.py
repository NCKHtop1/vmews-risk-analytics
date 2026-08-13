import json
from vnstock import Market
out={}
try:
 root=Market()
 out['root_methods']=[x for x in dir(root) if not x.startswith('_')]
 eq=root.equity('FPT')
 out['equity_methods']=[x for x in dir(eq) if 'flow' in x.lower() or 'trade' in x.lower() or 'summary' in x.lower()]
 for n in ['foreign_flow','proprietary_flow','summary','trade_history']:
  try:
   x=getattr(eq,n)(); out[n]={'ok':True,'rows':len(x),'columns':[str(c) for c in x.columns]}
  except Exception as e: out[n]={'ok':False,'error':str(e)}
except Exception as e:
 out['error']=str(e)
print(json.dumps(out,ensure_ascii=False,default=str))
