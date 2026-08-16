from pathlib import Path

def replace_once(text,old,new,label):
    if old not in text:raise SystemExit(f'{label}: anchor not found')
    if text.count(old)!=1:raise SystemExit(f'{label}: anchor count {text.count(old)} != 1')
    return text.replace(old,new,1)

# Full candidate: current context must be produced from the exact model snapshot and persisted with it.
p=Path('.github/workflows/v12-methodfix-full.yml');s=p.read_text(encoding='utf-8')
s=replace_once(s,'scripts/v12_benchmark_unit.py scripts/train_forecast_v12.py','scripts/v12_benchmark_unit.py scripts/v12_current_context.py scripts/train_forecast_v12.py','full compile')
anchor="""      - name: Assert every research artifact materialized\n        run: |\n"""
insert="""      - name: Build current flow and VNStock financial context\n        env:\n          V12_FUNDAMENTAL_INTERVAL: '3.5'\n        run: PYTHONPATH=scripts python scripts/v12_current_context.py\n      - name: Assert every research artifact materialized\n        run: |\n"""
s=replace_once(s,anchor,insert,'full context step')
s=replace_once(s,"'event-intelligence-v12.json']","'event-intelligence-v12.json','current-context-v12.json']",'full materialization')
s=replace_once(s,'            data/event-intelligence-v12.json\n            data/phase-gates-v12.json','            data/event-intelligence-v12.json\n            data/current-context-v12.json\n            data/phase-gates-v12.json','full evidence')
s=replace_once(s,'data/data-audit-v12.json data/event-intelligence-v12.json data/phase-gates-v12.json','data/data-audit-v12.json data/event-intelligence-v12.json data/current-context-v12.json data/phase-gates-v12.json','full persist')
p.write_text(s,encoding='utf-8')

# Immutable release: require non-collapsed magnitude authority and hash the new context payload.
p=Path('.github/workflows/v12-release-final.yml');s=p.read_text(encoding='utf-8')
loop="""          for h in range(1,6):\n              hz=(m.get('horizons') or {}).get(str(h),{})\n              assert (hz.get('gates') or {}).get('blindHoldout') is True,(h,hz.get('gates'))\n              assert (((hz.get('walkForwardReplay') or {}).get('fixedBlindHoldout') or {}).get('status'))=='PASS',(h,hz.get('walkForwardReplay'))\n"""
loop2=loop+"""              assert (hz.get('magnitudeGate') or {}).get('status')=='PASS',(h,hz.get('magnitudeGate'))\n"""
s=replace_once(s,loop,loop2,'release magnitude')
s=replace_once(s,"'forecast-polish-v12.js','data/forecast-model-v12.json'","'forecast-polish-v12.js','data/current-context-v12.json','data/forecast-model-v12.json'",'release context hash')
s=replace_once(s,"'VMEWS-FORECAST-V12-IMMUTABLE-MANIFEST-1.5.0'","'VMEWS-FORECAST-V12-IMMUTABLE-MANIFEST-1.6.0'",'release manifest create')
s=replace_once(s,"assert r['version']=='VMEWS-FORECAST-V12-IMMUTABLE-MANIFEST-1.5.0'","assert r['version']=='VMEWS-FORECAST-V12-IMMUTABLE-MANIFEST-1.6.0'",'release manifest assert')
s=replace_once(s,"assert 'forecast-polish-v12.js' in r['files']","assert 'forecast-polish-v12.js' in r['files'] and 'data/current-context-v12.json' in r['files']",'release manifest assets')
s=replace_once(s,"data/forecast-release-v12.json\n            data/benchmark-gate-v12.json","data/forecast-release-v12.json\n            data/current-context-v12.json\n            data/benchmark-gate-v12.json",'release evidence')
# Strengthen manifest policy description without altering acceptance thresholds.
s=s.replace('PBO/generalization, distribution and embargo gates.','PBO/generalization, non-collapsed magnitude skill, distribution and embargo gates.')
p.write_text(s,encoding='utf-8')
print('V12 PIPELINE WORKFLOW PATCH PASS')
