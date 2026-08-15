import json,pathlib,math
ROOT=pathlib.Path('.');html=(ROOT/'forecast-final.html').read_text(encoding='utf-8');js=(ROOT/'forecast-final-v12.js').read_text(encoding='utf-8');polish=(ROOT/'forecast-polish-v12.js').read_text(encoding='utf-8')
assert 'forecast-final-v12.js' in html and 'forecast-polish-v12.js' in html
assert 'VMEWS Forecast V12' in html
for token in ['Dự báo giá T+1 → T+5','Backtest: dự báo tại T0','Kiểm định không nhìn trước tương lai','methodProof']:assert token in html,token
for banned in ['VNStock ưu tiên cho OHLCV Việt Nam','không nội suy','whisker =','Completed EOD snapshot','không phát lệnh mua/bán']:assert banned not in html,banned
for name in ['forecast-dashboard-v12.json','forecast-model-v12.json','forecast-backtest-v12.json','data-audit-v12.json','phase-gates-v12.json']:assert name in js,name
for name in ['blind-holdout-gate-v12.json','embargo-gate-v12.json','forecast-model-v12.json']:assert name in polish,name
assert 'vmews-risk-analytics-sojd.vercel.app' not in js+polish and '/api/' not in js+polish and 'fetch(' in js
for token in ['expectedPrice','q20Price','q80Price','probUp','expertContributions','priceValidated','directionValidated','actualRawPrice','contextAtOrigin','Direction gate REVIEW']:assert token in js,token
for token in ['futureRowsUsedForTraining','futureMetaRowsUsedForTraining','futureCalibrationRowsUsedForTraining','MutationObserver']:assert token in polish,token
assert 'mousemove' in js or 'pointermove' in js
files={n:json.loads((ROOT/'data'/n).read_text(encoding='utf-8')) for n in ['forecast-dashboard-v12.json','forecast-model-v12.json','forecast-backtest-v12.json','data-audit-v12.json','phase-gates-v12.json','blind-holdout-gate-v12.json','embargo-gate-v12.json']};dash=files['forecast-dashboard-v12.json'];model=files['forecast-model-v12.json'];bt=files['forecast-backtest-v12.json'];audit=files['data-audit-v12.json'];gates=files['phase-gates-v12.json'];blind=files['blind-holdout-gate-v12.json'];embargo=files['embargo-gate-v12.json']
assert gates.get('status')=='PASS',gates;assert blind.get('status')=='PASS',blind;assert embargo.get('status')=='PASS',embargo
assert model.get('promotion',{}).get('status')=='PASS',model.get('promotion');assert model.get('promotion',{}).get('directPriceHorizons')==[1,2,3,4,5],model.get('promotion');assert len(dash.get('symbols',{}))>=330
for hz in embargo.get('horizons') or []:
    c=hz.get('walkForwardChronology') or {}
    assert c.get('futureRowsUsedForTraining')==0,c
    assert c.get('futureMetaRowsUsedForTraining')==0,c
    assert c.get('futureCalibrationRowsUsedForTraining')==0,c
hist=set((audit.get('universeAudit') or {}).get('historicalOnly',{}));assert hist and not hist.intersection(dash.get('symbols',{})),hist.intersection(dash.get('symbols',{}))
for s in ('FPT','VCB','HPG','MBB'):
    assert s in dash['symbols'],s;z=dash['symbols'][s];assert len(dash.get('charts',{}).get(s,[]))>=80,s
    for h in ('1','2','3','4','5'):
        q=z.get('horizons',{}).get(h);assert q and q.get('priceValidated') is True,(s,h,q);assert all(isinstance(q.get(k),(int,float)) and math.isfinite(q[k]) for k in ('expectedReturn','expectedPrice','probUp','q20Price','q80Price')),(s,h);assert q['q20Price']<=q['expectedPrice']<=q['q80Price'],(s,h,q);assert isinstance(q.get('directionValidated'),bool),(s,h,q.get('directionValidated'))
for h in ('1','2','3','4','5'):
    cases=(bt.get('cases') or {}).get(h,[]);assert len(cases)>=50,h
    x=cases[0];assert isinstance(x.get('actualRawPrice'),(int,float)) and math.isfinite(x['actualRawPrice']),x;assert all(k in (x.get('contextAtOrigin') or {}) for k in ['prior20','breadth20','newsN20','rumorN20','foreignAvailable','propAvailable']),x.get('contextAtOrigin')
print(json.dumps({'staticSmoke':'PASS','symbols':len(dash['symbols']),'model':model.get('version'),'gates':gates.get('status'),'sealed':blind.get('status'),'embargo':embargo.get('status'),'historicalOnly':sorted(hist)},ensure_ascii=False))
