import json
import vnstock
out={'version':getattr(vnstock,'__version__',None),'available':[],'errors':[]}
try:
 from vnstock import Market
 out['available'].append('Market')
 m=Market(source='VCI').equity('FPT')
 out['methods']=[x for x in dir(m) if 'flow' in x.lower() or 'trade' in x.lower() or 'summary' in x.lower()]
 for name in ['foreign_flow','proprietary_flow','summary']:
  try:
   z=getattr(m,name)(); out[name]={'ok':True,'rows':len(z),'columns':[str(c) for c in z.columns]}
  except Exception as e: out[name]={'ok':False,'error':str(e)}
except Exception as e:
 out['errors'].append(str(e))
print(json.dumps(out,ensure_ascii=False,default=str))
