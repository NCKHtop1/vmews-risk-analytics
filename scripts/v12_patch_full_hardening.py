"""One-shot exact patcher for the V12 full workflow hardening.

It refuses to edit if expected markers/counts do not match. Scientific acceptance
thresholds are untouched; changes are operational provenance + label-free output sanity.
"""
from pathlib import Path

P = Path('.github/workflows/v12-methodfix-full.yml')
text = P.read_text(encoding='utf-8')


def replace_between(src: str, start: str, end: str, replacement: str) -> str:
    if src.count(start) != 1:
        raise RuntimeError(f'expected exactly one start marker {start!r}, found {src.count(start)}')
    if src.count(end) != 1:
        raise RuntimeError(f'expected exactly one end marker {end!r}, found {src.count(end)}')
    a = src.index(start)
    b = src.index(end, a)
    return src[:a] + replacement + src[b:]


seed_start = '      - name: Restore historical PIT news and market evidence seed\n'
seed_end = '      - name: Phase 1 immutable frozen/no-network source probe\n'
seed_replacement = r'''      - name: Restore SHA-pinned historical PIT news and market evidence seed
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        shell: bash
        run: |
          set -euo pipefail
          rm -rf /tmp/v11-seed /tmp/v11-seed.zip
          mkdir -p /tmp/v11-seed data/v12-seed
          curl --fail-with-body --location --silent --show-error \
            --retry 5 --retry-all-errors --retry-delay 5 --retry-max-time 240 \
            -H "Authorization: Bearer ${GH_TOKEN}" \
            -H "Accept: application/vnd.github+json" \
            -H "X-GitHub-Api-Version: 2022-11-28" \
            -o /tmp/v11-seed.zip \
            "https://api.github.com/repos/NCKHtop1/vmews-risk-analytics/actions/artifacts/9215419805/zip"
          echo "b9c467dd623e73244ad173bcbc880045d814e9fc2dc37f96c939599fb85ea49a  /tmp/v11-seed.zip" | sha256sum -c -
          unzip -q /tmp/v11-seed.zip -d /tmp/v11-seed
          for f in sentiment-v11.json market-scan.json; do
            src=$(find /tmp/v11-seed -name "$f" -type f | head -1)
            test -n "$src"
            cp "$src" "data/v12-seed/$f"
          done
          echo "d94a4ca26ffd70d292e7fa0bea143baa877ec335ac6055b3a86c0ab24e319eed  data/v12-seed/sentiment-v11.json" | sha256sum -c -
          echo "3b4a10c99044ccf84762f58537eaaf29aae60e9011d84d43a621b2db436c7352  data/v12-seed/market-scan.json" | sha256sum -c -
          python - <<'PY'
          import hashlib,json
          from pathlib import Path
          expected={
            'sentiment-v11.json':'d94a4ca26ffd70d292e7fa0bea143baa877ec335ac6055b3a86c0ab24e319eed',
            'market-scan.json':'3b4a10c99044ccf84762f58537eaaf29aae60e9011d84d43a621b2db436c7352',
          }
          files={}
          for name,sha in expected.items():
              p=Path('data/v12-seed')/name
              z=json.loads(p.read_text(encoding='utf-8'))
              actual=hashlib.sha256(p.read_bytes()).hexdigest()
              assert actual==sha,(name,actual,sha)
              files[name]={'sha256':actual,'size':p.stat().st_size,'version':z.get('version')}
          provenance={
            'version':'VMEWS-V12-SEED-PROVENANCE-1.0.0',
            'repository':'NCKHtop1/vmews-risk-analytics',
            'sourceRunId':31790884093,
            'sourceHeadSha':'6f7b9f577a045e9fac882927315403eb8151c655',
            'artifactId':9215419805,
            'artifactName':'forecast-v11-final-evidence-31790884093',
            'artifactArchiveSha256':'b9c467dd623e73244ad173bcbc880045d814e9fc2dc37f96c939599fb85ea49a',
            'files':files,
            'runtimePriceSource':False,
            'role':'historical PIT news and market evidence seed only',
          }
          Path('data/v12-seed-provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
          print('V12 SHA-PINNED SEED PASS',json.dumps(provenance,ensure_ascii=False))
          PY
'''
text = replace_between(text, seed_start, seed_end, seed_replacement)

embargo = '      - name: Phase 7 explicit purge and embargo gate\n        run: PYTHONPATH=scripts python scripts/v12_embargo_acceptance.py\n'
if text.count(embargo) != 1:
    raise RuntimeError(f'embargo anchor count={text.count(embargo)}')
sanity = embargo + r'''      - name: Label-free current forecast structural and collapse sanity gate
        run: |
          python -m py_compile scripts/v12_forecast_output_sanity.py
          PYTHONPATH=scripts python scripts/v12_forecast_output_sanity.py
'''
text = text.replace(embargo, sanity, 1)

probe_path = '            data/v12-source-probe.json\n'
if text.count(probe_path) != 1:
    raise RuntimeError(f'probe artifact path count={text.count(probe_path)}')
text = text.replace(
    probe_path,
    probe_path + '            data/v12-seed-provenance.json\n            data/forecast-sanity-v12.json\n',
    1,
)

old_add = "          git add data/v12-source-probe.json data/forecast-model-v12.json data/forecast-current-v12.json data/forecast-dashboard-v12.json data/forecast-backtest-v12.json data/data-audit-v12.json data/event-intelligence-v12.json data/phase-gates-v12.json data/benchmark-gate-v12.json data/active-flow-gate-v12.json data/sector-gate-v12.json data/nested-selection-gate-v12.json data/blind-holdout-gate-v12.json data/embargo-gate-v12.json\n"
if text.count(old_add) != 1:
    raise RuntimeError(f'persist git-add count={text.count(old_add)}')
new_add = "          git add data/v12-source-probe.json data/v12-seed-provenance.json data/forecast-sanity-v12.json data/forecast-model-v12.json data/forecast-current-v12.json data/forecast-dashboard-v12.json data/forecast-backtest-v12.json data/data-audit-v12.json data/event-intelligence-v12.json data/phase-gates-v12.json data/benchmark-gate-v12.json data/active-flow-audit-v12.json data/active-flow-gate-v12.json data/sector-gate-v12.json data/nested-selection-gate-v12.json data/blind-holdout-gate-v12.json data/embargo-gate-v12.json data/vnindex-v12.json\n"
text = text.replace(old_add, new_add, 1)

# Explicitly require the hardened frozen-probe contract in Full itself.
old_probe_assert = "          assert all((z.get('sourceGates') or {}).values()),z.get('sourceGates')\n          snap=z.get('snapshot') or {}\n"
if text.count(old_probe_assert) != 1:
    raise RuntimeError(f'probe assert anchor count={text.count(old_probe_assert)}')
new_probe_assert = old_probe_assert + "          assert z.get('version')=='VMEWS-V12-FROZEN-SOURCE-PROBE-1.1.0',z.get('version')\n          assert snap.get('certificationVersion')=='VMEWS-FROZEN-SOURCE-CERTIFICATION-12.1.1',snap\n          assert snap.get('corporateActionGateCohort')=='CURRENT_HOSE_ORIGINAL_DEEP_HISTORY_BEFORE_CONTINUITY_TRUNCATION',snap\n          assert int(snap.get('corporateActionVerifiedCount') or 0)/max(1,int(snap.get('corporateActionGateDenominator') or 0))>=.98,snap\n"
text = text.replace(old_probe_assert, new_probe_assert, 1)

P.write_text(text, encoding='utf-8')
print('V12 FULL HARDENING PATCH APPLIED')
