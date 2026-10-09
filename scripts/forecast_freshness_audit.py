"""Audit each published price, history endpoint and forecast target before commit."""
import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from vn_exchange_calendar import VN_TZ, latest_completed_session, next_trading_dates

DATA = Path(__file__).resolve().parents[1] / 'data'


def executable_close(value):
    """Only a finite observed/executable close can validate a chart endpoint.

    Chart 'close' is modelClose (corporate-action adjusted) and MUST NOT be
    compared to the integer-VND snapshot close. Keep rawClose independently
    validated; never overwrite either price or waive a real mismatch.
    """
    if isinstance(value, bool):
        return None
    try:
        price = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return int(round(price)) if math.isfinite(price) and price > 0 else None


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
        else:
            # The model series is adjusted for training, while the executable
            # chart endpoint has its own rawClose field. Compare like for like.
            observed_close = executable_close(history[-1].get('rawClose'))
            snapshot_close = executable_close(row.get('close'))
            if observed_close is None or snapshot_close is None:
                issues.append('UNVERIFIED_EXECUTABLE_CHART_CLOSE')
            elif observed_close != snapshot_close:
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
