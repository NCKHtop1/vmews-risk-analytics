import os,json,time,pathlib,inspect
os.environ['VNSTOCK_TELEMETRY']='off'
from vnstock import Finance,Listing
from importlib.metadata import version
print('VERSION',version('vnstock'),flush=True)
from vnstock.config import Config
Config.REQUEST_TIMEOUT=15
out=pathlib.Path('/tmp/financial-probe');out.mkdir(exist_ok=True)
listing=Listing(source='VCI')
try:
 d=listing.symbols_by_group('VN100');print('VN100',str(type(d)),str(d)[:5000],flush=True);(out/'vn100.json').write_text(d.to_json(orient='records',force_ascii=False))
except Exception as e:print('listing error',repr(e),flush=True)
for source,period,kinds in [('VCI','quarter',['balance_sheet','income_statement','cash_flow','ratio']),('KBS','quarter',['ratio']),('VCI','year',['ratio'])]:
 f=Finance(source=source,symbol='VIC',period=period,get_all=True,show_log=False)
 for kind in kinds:
  time.sleep(3)
  try:
   kw={'period':period,'show_log':False}
   if source=='VCI':kw.update(lang='vi',dropna=False)
   elif kind=='ratio':kw.update(display_mode='all')
   d=getattr(f,kind)(**kw)
   print(source,period,kind,'cols',list(d.columns),'rows',len(d),'attrs',d.attrs,'sample',d.head(1).to_dict(orient='records'),flush=True)
   (out/f'{source}_{period}_{kind}.json').write_text(d.to_json(orient='split',force_ascii=False))
  except Exception as e:print(source,period,kind,'ERROR',repr(e),flush=True)
