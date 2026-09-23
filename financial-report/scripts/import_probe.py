"""Import captured provider responses, retaining numeric evidence for regression checks."""
import sys,json,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import pandas as pd
from backend.vnstock_connector import normalize_frame,REPORTS
from backend.data_validator import validate_dataset
ROOT=pathlib.Path(__file__).resolve().parents[1]
source=pathlib.Path(sys.argv[1])
companies=json.loads((source/'companies.json').read_text())
companies=[{'symbol':c['symbol'],'name':c.get('organ_name') or c['symbol'],'exchange':{'HSX':'HOSE'}.get(c['exchange'],c['exchange'])} for c in companies if c.get('type')=='STOCK' and c.get('exchange') in ('HSX','HOSE','HNX','UPCOM')]
(ROOT/'data/companies.json').write_text(json.dumps(companies,ensure_ascii=False,separators=(',',':')))
meta={c['symbol']:c for c in companies}
for symbol in ['MBB','FPT','VCB']:
 sections=[]
 if symbol=='MBB':sections=json.loads((ROOT/'verified/MBB.json').read_text())['sections']
 else:
  for kind in ['balance_sheet','income_statement','cash_flow']:
   raw=json.loads((source/f'VCI_{symbol}_{kind}.json').read_text());df=pd.DataFrame(raw['data'],columns=raw['columns'])
   sections.append(normalize_frame(df,kind,'VCI'))
 raw=json.loads((source/f'KBS_{symbol}_ratio.json').read_text());df=pd.DataFrame(raw['data'],columns=raw['columns']);sections.append(normalize_frame(df,'ratios','KBS'))
 data=validate_dataset({'schemaVersion':1,'symbol':symbol,'name':meta[symbol]['name'],'exchange':meta[symbol]['exchange'],'updatedAt':'2026-09-23T02:32:00Z','sections':sections})
 (ROOT/'data'/f'{symbol}.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False))
 print(symbol,data['years'],[(s['id'],len(s['rows'])) for s in data['sections']])
manifest={'schemaVersion':1,'updatedAt':'2026-09-23T02:32:00Z','companies':[]}
for c in companies:
 p=ROOT/'data'/f"{c['symbol']}.json"
 if p.exists():
  d=json.loads(p.read_text());manifest['companies'].append({**c,'years':d['years'],'reports':{s['id']:s['years'] for s in d['sections']},'rows':sum(len(s['rows']) for s in d['sections'])})
(ROOT/'data/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')))
