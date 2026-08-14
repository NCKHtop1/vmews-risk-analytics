import json, os
from pathlib import Path
import train_forecast_v10 as v
v.FEATURES = list(v.BASE)
v.train(os.environ.get('GITHUB_WORKSPACE', '.'))
p = Path(os.environ.get('GITHUB_WORKSPACE', '.'), 'data/forecast-model-v10.json')
z = json.loads(p.read_text(encoding='utf-8'))
z['governance']['featureParity'] = 'Numerical forecast uses stock-local BASE features only; cross-sectional scan, macro, risk, flow and news are independent context.'
z['governance']['crossSectionalFeaturesInNumericalModel'] = False
p.write_text(json.dumps(z, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'featureCount': len(z['featureNames']), 'promotion': z['promotion']}, ensure_ascii=False))
