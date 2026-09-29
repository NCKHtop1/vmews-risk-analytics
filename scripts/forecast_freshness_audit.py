"""Audit each published price, history endpoint and forecast target before commit."""
import argparse
import json
from datetime import datetime
from pathlib import Path
from vn_exchange_calendar import VN_TZ, latest_completed_session, next_trading_dates

DATA = Path(__file__).resolve().parents[1] / 'data'


def audit(dashboard, current, market, now=None):
    expected = latest_completed_session(now).isoformat()
    errors = []
    symbols = dashboard.get('symbols') or {}
    if not symbols:
        errors.append('EMPTY_UNIVERSE')
    for name, artifact in [('dashboard', dashboard), ('current', current), ('market', market)]:
        if artifact.get('asOf') != expected:
            errors.append(f'{name}: session {artifact.get("asOf")} != {expected}')
        if artifact.get('generatedAt') != dashboard.get('generatedAt'):
            errors.append(f'{name}: mixed generation')
    if set(symbols) != set(current.get('symbols') or {}):
        errors.append('current/dashboard symbol mismatch')
    targets = next_trading_dates(expected, 5)
    rows = []
    for symbol, row in sorted(symbols.items()):
        issues = []
        if row.get('date') != expected or row.get('dataFreshness') != 'CURRENT':
            issues.append('STALE_PRICE')
        history = (dashboard.get('charts') or {}).get(symbol) or []
        if not history or history[-1].get('date') != expected:
            issues.append('STALE_CHART')
        elif history[-1].get('close') != row.get('close'):
            issues.append('PRICE_CHART_MISMATCH')
        if row != (current.get('symbols') or {}).get(symbol):
            issues.append('SNAPSHOT_MISMATCH')
        for horizon in range(1, 6):
            forecast = (row.get('horizons') or {}).get(str(horizon)) or {}
            if forecast.get('targetDate') != targets[horizon - 1]:
                issues.append(f'T+{horizon}_TARGET_MISMATCH')
        if issues:
            errors.append(f'{symbol}: {", ".join(issues)}')
        rows.append({'symbol': symbol, 'date': row.get('date'), 'status': 'FAIL' if issues else 'PASS', 'issues': issues})
    universe = (market.get('model') or {}).get('universe') or {}
    return {'status': 'FAIL' if errors else 'PASS', 'checkedAt': (now or datetime.now(VN_TZ)).isoformat(),
            'expectedSession': expected, 'publishedSession': dashboard.get('asOf'), 'checkedSymbols': len(rows),
            'listedSymbols': universe.get('listedHOSE'), 'excludedUnverified': universe.get('staleOrUnverifiedSymbols', []),
            'insufficientHistory': universe.get('insufficientHistorySymbols', []), 'errors': errors, 'symbols': rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    documents = [json.loads((DATA / name).read_text()) for name in
                 ['forecast-dashboard-v12.json', 'forecast-current-v12.json', 'forecast-market-v13.json']]
    result = audit(*documents)
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'symbols'}, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
