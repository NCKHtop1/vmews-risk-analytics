import json
from vnstock import Trading
SYMS=['FPT','VCB','HPG','PNJ','SSI','VIC','VHM','MWG','MBB','STB']
out={'symbols':{}}
for s in SYMS:
 r={};out['symbols'][s]=r
 try:
  t=Trading(symbol=s,source='VCI')
  z=t.prop_trade(symbol=s,start='2018-01-01',end='2026-08-13',page_size=1000,get_all=True)
  r['ok']=True;r['rows']=len(z);r['columns']=[str(c) for c in z.columns]
  if len(z):
   ds=z['date'].astype(str) if 'date' in z.columns else []
   r['minDate']=min(ds) if len(ds) else None;r['maxDate']=max(ds) if len(ds) else None;r['duplicateDates']=int(z.duplicated(['date']).sum()) if 'date' in z.columns else None
   for c in ['net_foreign_value','net_foreign_volume','total_prop_trade_net','foreign_buy_value','foreign_sell_value']:
    if c in z.columns:r[c+'_nonnull']=int(z[c].notna().sum())
 except Exception as e:r['ok']=False;r['error']=repr(e)
print(json.dumps(out,ensure_ascii=False,default=str))
