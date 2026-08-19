from pathlib import Path

def replace_once(text,old,new,label):
    if old not in text:raise SystemExit(f'{label}: anchor not found')
    if text.count(old)!=1:raise SystemExit(f'{label}: anchor count {text.count(old)} != 1')
    return text.replace(old,new,1)

# Full candidate: current context must be produced from the exact model snapshot and persisted with it.
p=Path('.github/workflows/v12-methodfix-full.yml');s=p.read_text(encoding='utf-8')
s=replace_once(s,'scripts/v12_benchmark_unit.py scripts/train_forecast_v12.py','scripts/v12_benchmark_unit.py scripts/v12_current_context.py scripts/train_forecast_v12.py','full compile')
anchor="""      - name: Assert every research artifact materialized\n        run: |\n"""
insert="""      - name: Build current flow and VNStock financial context\n        env:\n          V12_FUNDAMENTAL_INTERVAL: '5.5'\n        run: PYTHONPATH=scripts python scripts/v12_current_context.py\n      - name: Assert every research artifact materialized\n        run: |\n"""
s=replace_once(s,anchor,insert,'full context step')
s=replace_once(s,"'event-intelligence-v12.json']","'event-intelligence-v12.json','current-context-v12.json']",'full materialization')
s=replace_once(s,'            data/event-intelligence-v12.json\n            data/phase-gates-v12.json','            data/event-intelligence-v12.json\n            data/current-context-v12.json\n            data/phase-gates-v12.json','full evidence')
s=replace_once(s,'data/data-audit-v12.json data/event-intelligence-v12.json data/phase-gates-v12.json','data/data-audit-v12.json data/event-intelligence-v12.json data/current-context-v12.json data/phase-gates-v12.json','full persist')

# Phase 1 and all model fitting must consume the immutable source freeze only.
s=replace_once(
    s,
    'scripts/v12_flow.py scripts/v12_source_probe.py scripts/v12_acceptance.py',
    'scripts/v12_flow.py scripts/v12_frozen_source_probe.py scripts/v12_acceptance.py',
    'full frozen source probe compile',
)
s=replace_once(
    s,
    '      - name: Phase 1 representative VNStock-first source probe\n        run: PYTHONPATH=scripts python scripts/v12_source_probe.py\n',
    '      - name: Phase 1 immutable frozen-source probe (no provider/network price fetch)\n        run: PYTHONPATH=scripts python scripts/v12_frozen_source_probe.py\n',
    'full frozen source probe step',
)
if 'scripts/v12_source_probe.py' in s:
    raise SystemExit('full workflow still references live v12_source_probe.py')
if 'scripts/v12_frozen_source_probe.py' not in s:
    raise SystemExit('full workflow frozen source probe integration missing')
p.write_text(s,encoding='utf-8')

# Immutable release: require non-collapsed magnitude authority and hash the new context payload.
p=Path('.github/workflows/v12-release-final.yml');s=p.read_text(encoding='utf-8')
loop="""          for h in range(1,6):\n              hz=(m.get('horizons') or {}).get(str(h),{})\n              assert (hz.get('gates') or {}).get('blindHoldout') is True,(h,hz.get('gates'))\n              assert (((hz.get('walkForwardReplay') or {}).get('fixedBlindHoldout') or {}).get('status'))=='PASS',(h,hz.get('walkForwardReplay'))\n"""
loop2=loop+"""              assert (hz.get('magnitudeGate') or {}).get('status')=='PASS',(h,hz.get('magnitudeGate'))\n"""
s=replace_once(s,loop,loop2,'release magnitude')
s=replace_once(s,"'forecast-polish-v12.js','data/forecast-model-v12.json'","'forecast-polish-v12.js','data/current-context-v12.json','data/forecast-model-v12.json'",'release context hash')
oldv='VMEWS-FORECAST-V12-IMMUTABLE-MANIFEST-1.5.0';newv='VMEWS-FORECAST-V12-IMMUTABLE-MANIFEST-1.6.0'
if s.count(oldv)<2:raise SystemExit(f'release manifest version anchors={s.count(oldv)}')
s=s.replace(oldv,newv)
s=replace_once(s,"assert 'forecast-polish-v12.js' in r['files']","assert 'forecast-polish-v12.js' in r['files'] and 'data/current-context-v12.json' in r['files']",'release manifest assets')
s=replace_once(s,"data/forecast-release-v12.json\n            data/benchmark-gate-v12.json","data/forecast-release-v12.json\n            data/current-context-v12.json\n            data/benchmark-gate-v12.json",'release evidence')
s=s.replace('PBO/generalization, distribution and embargo gates.','PBO/generalization, non-collapsed magnitude skill, distribution and embargo gates.')
p.write_text(s,encoding='utf-8')
print('V12 PIPELINE WORKFLOW PATCH PASS')
