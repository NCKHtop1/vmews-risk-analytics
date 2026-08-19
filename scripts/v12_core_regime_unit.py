import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
parts = sorted((ROOT / 'v12_train_parts').glob('*.pyinc'))
code = '\n'.join(p.read_text(encoding='utf-8') for p in parts)
ns = {'__name__': 'v12_core_regime_unit', '__file__': str(ROOT / 'train_forecast_v12.py')}
exec(compile(code, 'v12-core-regime-unit-assembled.py', 'exec'), ns, ns)

assert callable(ns.get('_core_regime_decision'))

rng = np.random.default_rng(1207)
# The production gate requires >=15 daily cross-sections for the HAC/bootstrap test.
# Use 40 synthetic dates so the explicit test window contains 20 days and exercises
# the real statistical branch rather than the insufficient-evidence abstention path.
dates = np.asarray([f'2026-{1 + i // 28:02d}-{1 + i % 28:02d}' for i in range(40)], dtype=object)
D = np.repeat(dates, 36)
n = len(D)
train = np.isin(D, dates[:20])
test = np.isin(D, dates[20:])

latent = rng.normal(size=n)
y = 0.025 * latent + rng.normal(scale=0.025, size=n)
numerical = latent + rng.normal(scale=0.45, size=n)
regime_noise = rng.normal(size=n)
expert_pred = {'NUMERICAL': numerical, 'REGIME': regime_noise}
active, _, audit = ns['_core_regime_decision'](expert_pred, y, D, train, test)
assert active == ['NUMERICAL'], (active, audit)
assert audit['promoted'] is False, audit
assert audit['incrementalICTest']['days'] >= 15, audit
assert audit['selectionWindow'].startswith('70%-80%')
assert 'sealed' in audit['rule'].lower()

# A genuinely complementary regime component must remain admissible when the reserved
# pre-blind block demonstrates incremental cross-sectional value.
num_component = rng.normal(size=n)
reg_component = rng.normal(size=n)
y2 = 0.025 * num_component + 0.035 * reg_component + rng.normal(scale=0.006, size=n)
expert_pred2 = {
    'NUMERICAL': num_component + rng.normal(scale=0.10, size=n),
    'REGIME': reg_component + rng.normal(scale=0.08, size=n),
}
active2, _, audit2 = ns['_core_regime_decision'](expert_pred2, y2, D, train, test)
assert active2 == ['NUMERICAL', 'REGIME'], (active2, audit2)
assert audit2['promoted'] is True, audit2
assert audit2['incrementalICTest']['days'] >= 15, audit2
assert audit2['deltaIC'] > 0 and audit2['deltaMAEImprove'] > 0, audit2
assert audit2['incrementalICTest']['pValue'] < 0.05, audit2
assert audit2['incrementalICTest']['bootstrap90'][0] > 0, audit2

print('V12 CORE REGIME PRE-BLIND SELECTION PASS', {'rejectNoise': audit, 'acceptComplementary': audit2})
