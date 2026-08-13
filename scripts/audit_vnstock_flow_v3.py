import json, inspect
from vnstock import Trading
out={}
try:
 t=Trading(symbol='FPT',source='VCI')
 for n in ['prop_trade','foreign_trade','price_history','price_board']:
  try: out[n+'_signature']=str(inspect.signature(getattr(t,n)))
  except Exception as e: out[n+'_signature_error']=str(e)
 for n,args in [('prop_trade',{}),('price_history',{})]:
  try:
   z=getattr(t,n)(**args);out[n]={'ok':True,'rows':len(z),'columns':[str(c) for c in z.columns],'head':z.head(2).to_dict('records')}
  except Exception as e:out[n]={'ok':False,'error':repr(e)}
except Exception as e:out['init_error']=repr(e)
print(json.dumps(out,ensure_ascii=False,default=str))
