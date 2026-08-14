import json,pathlib,math
ROOT=pathlib.Path('.');html=(ROOT/'forecast-final.html').read_text(encoding='utf-8');js=(ROOT/'forecast-final-v12.js').read_text(encoding='utf-8');assert 'forecast-final-v12.js' in html;assert 'VMEWS Forecast V12' in html
for name in ['forecast-dashboard-v12.json','forecast-model-v12.json','forecast-backtest-v12.json','data-audit-v12.json','phase-gates-v12.json']:assert name in js,name
assert 'vmews-risk-analytics-sojd.vercel.app' not in js and '/api/' not in js and 'fetch(' in js;assert all(x in js for x in ['expectedPrice','q20Price','q80Price','probUp','expertContributions','ablations']);assert 'mousemove' in js or 'pointermove' in js
files={n:json.loads((ROOT/'data'/n).read_text(encoding='utf-8')) for n in ['forecast-dashboard-v12.json','forecast-model-v12.json','forecast-backtest-v12.json','data-audit-v12.json','phase-gates-v12.json']};dash=files['forecast-dashboard-v12.json'];model=files['forecast-model-v12.json'];bt=files['forecast-backtest-v12.json'];gates=files['phase-gates-v12.json'];assert gates.get('status')=='PASS',gates;assert model.get('promotion',{}).get('status')=='PASS',model.get('promotion');assert len(dash.get('symbols',{}))>=330
for s in ('FPT','VCB','HPG','MBB'):
    assert s in dash['symbols'],s;z=dash['symbols'][s];assert len(dash.get('charts',{}).get(s,[]))>=80,s
    for h in ('1','2','3','4','5'):
        q=z.get('horizons',{}).get(h);assert q and all(isinstance(q.get(k),(int,float)) and math.isfinite(q[k]) for k in ('expectedReturn','expectedPrice','probUp','q20Price','q80Price')),(s,h);assert q['q20Price']<=q['expectedPrice']<=q['q80Price'],(s,h,q)
for h in ('1','2','3','4','5'):assert len((bt.get('cases') or {}).get(h,[]))>=50,h
print(json.dumps({'staticSmoke':'PASS','symbols':len(dash['symbols']),'model':model.get('version'),'gates':gates.get('status')},ensure_ascii=False))
