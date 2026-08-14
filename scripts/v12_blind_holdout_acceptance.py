import json
import pathlib
from datetime import datetime, timezone

DATA=pathlib.Path('data')
model=json.loads((DATA/'forecast-model-v12.json').read_text(encoding='utf-8'))
back=json.loads((DATA/'forecast-backtest-v12.json').read_text(encoding='utf-8'))
checks={};detail={}

for h in range(1,6):
    z=(model.get('horizons') or {}).get(str(h)) or {}
    replay=z.get('walkForwardReplay') or {}
    blind=replay.get('fixedBlindHoldout') or {}
    blocks=blind.get('blocks') or []
    gates=z.get('gates') or {}
    hchecks={
        'fixedBlindPass': blind.get('status')=='PASS',
        'generalizationGatePass': gates.get('generalization') is True,
        'blindGatePass': gates.get('blindHoldout') is True,
        'chronologyVerified': blind.get('chronologyVerified') is True,
        'zeroBlindLabelsUsedForSelectionOrCalibration': int(blind.get('futureBlindLabelsUsedForSelectionOrCalibration') or 0)==0,
        'enoughBlindRows': int(blind.get('rows') or 0)>=3000,
        'fourChronologicalBlocks': len(blocks)==4 and all(int(x.get('n') or 0)>=500 for x in blocks),
        'positiveSkillOverall': bool((blind.get('checks') or {}).get('overallPositiveSkill')),
        'subBlockStability': bool((blind.get('checks') or {}).get('fourBlockStability')),
        'literalReplayPass': bool((blind.get('checks') or {}).get('literalWalkForwardReplay')),
        'preBlindCalibrationMaturity': bool((blind.get('checks') or {}).get('preBlindCalibrationMaturity')),
    }
    checks[f'T+{h}']=all(hchecks.values())
    detail[f'T+{h}']={'checks':hchecks,'blind':blind}

back_h=back.get('horizons') or {}
checks['backtestCarriesBlindEvidence']=all((((back_h.get(str(h)) or {}).get('walkForwardReplay') or {}).get('fixedBlindHoldout') or {}).get('status')=='PASS' for h in range(1,6))
promotion=model.get('promotion') or {}
checks['allPriceHorizonsPromoted']=promotion.get('status')=='PASS' and promotion.get('directPriceHorizons')==[1,2,3,4,5]

out={
    'version':'VMEWS-FIXED-BLIND-HOLDOUT-GATE-12.0.0',
    'generatedAt':datetime.now(timezone.utc).isoformat(),
    'status':'PASS' if all(checks.values()) else 'FAIL',
    'checks':checks,
    'horizons':detail,
    'policy':'A numerical forecast may be published only when all five horizons pass a frozen 90-100% holdout that never participates in model-family selection, expert promotion, meta fitting or calibration, plus literal maturity-aware walk-forward replay and all other model-risk gates.'
}
(DATA/'blind-holdout-gate-v12.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if out['status']=='PASS' else 1)
