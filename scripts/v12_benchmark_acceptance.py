import json
import math
import pathlib
from datetime import datetime, timezone

DATA = pathlib.Path('data')
audit = json.loads((DATA / 'data-audit-v12.json').read_text(encoding='utf-8'))
event = json.loads((DATA / 'event-intelligence-v12.json').read_text(encoding='utf-8'))
records = event.get('records') or []
summary = event.get('summary') or {}
idx = audit.get('index') or {}


def finite(v):
    return isinstance(v, (int, float)) and math.isfinite(float(v))


matured5 = [r for r in records if (r.get('priceAfter') or {}).get('5') is not None]
bench5 = [r for r in matured5 if (r.get('benchmarkAvailable') or {}).get('5') is True]
semantic_failures = []
for r in records:
    br = r.get('benchmarkReturn') or {}
    ba = r.get('benchmarkAvailable') or {}
    car = r.get('cumulativeAbnormalReturn') or {}
    for h in map(str, range(1, 6)):
        available = ba.get(h) is True
        benchmark_value = br.get(h)
        abnormal = car.get(h)
        if available:
            if not finite(benchmark_value):
                semantic_failures.append((r.get('newsId'), h, 'available_without_benchmark_value'))
            if abnormal is not None and not finite(abnormal):
                semantic_failures.append((r.get('newsId'), h, 'nonfinite_abnormal_return'))
        else:
            if benchmark_value is not None or abnormal is not None:
                semantic_failures.append((r.get('newsId'), h, 'raw_or_other_return_relabelled_as_abnormal'))

coverage = len(bench5) / max(1, len(matured5))
checks = {
    'indexHistoryAudited': int(idx.get('rows') or 0) >= 520,
    'indexRouteExplicit': idx.get('route') in {'VNSTOCK_INDEX_PRIMARY', 'YAHOO_INDEX_FALLBACK'},
    'eventBenchmarkIdentityVNINDEX': bool(records) and all(r.get('benchmark') == 'VNINDEX' for r in records),
    'benchmarkFieldsMaterialized': bool(records) and all(isinstance(r.get('benchmarkReturn'), dict) and isinstance(r.get('benchmarkAvailable'), dict) for r in records),
    'noRawReturnFallbackWhenBenchmarkMissing': not semantic_failures,
    'benchmarkH5CoverageAtLeast90Pct': bool(matured5) and coverage >= 0.90,
    'summaryMatchesComputedCoverage': int(summary.get('maturedH5Records') or 0) == len(matured5) and int(summary.get('benchmarkH5Available') or 0) == len(bench5) and abs(float(summary.get('benchmarkH5Coverage') or 0.0) - coverage) < 1e-12,
    'policyExplicitlyAbstainsOnMissingBenchmark': 'ABSTAIN_NOT_RAW_RETURN' in str((event.get('benchmarkPolicy') or {}).get('missingBenchmark') or ''),
}

out = {
    'version': 'VMEWS-VNINDEX-BENCHMARK-GATE-12.0.0',
    'generatedAt': datetime.now(timezone.utc).isoformat(),
    'status': 'PASS' if all(checks.values()) else 'FAIL',
    'benchmark': 'VNINDEX',
    'checks': checks,
    'indexAudit': idx,
    'maturedH5Records': len(matured5),
    'benchmarkH5Available': len(bench5),
    'benchmarkH5Coverage': coverage,
    'semanticFailures': semantic_failures[:50],
    'policy': 'Event abnormal returns are VNINDEX-relative only. Missing benchmark observations cause abstention; raw stock returns are never substituted or relabelled as abnormal returns.',
}
(DATA / 'benchmark-gate-v12.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if out['status'] == 'PASS' else 1)
