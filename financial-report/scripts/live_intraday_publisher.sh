#!/usr/bin/env bash
set -euo pipefail

OUT="${1:-/tmp/market-intraday}"
INTERVAL_SECONDS="${INTRADAY_PUBLISH_INTERVAL_SECONDS:-600}"
MAX_FAILURES="${INTRADAY_MAX_CONSECUTIVE_FAILURES:-3}"
ONESHOT="${INTRADAY_ONESHOT:-0}"

vn_minutes() {
  TZ=Asia/Ho_Chi_Minh date +%H | awk -v m="$(TZ=Asia/Ho_Chi_Minh date +%M)" '{print ($1+0)*60+(m+0)}'
}

in_live_window() {
  local m="$1"
  { [ "$m" -ge 540 ] && [ "$m" -le 697 ]; } || { [ "$m" -ge 780 ] && [ "$m" -le 895 ]; }
}

in_prewarm_window() {
  local m="$1"
  { [ "$m" -ge 535 ] && [ "$m" -lt 540 ]; } || { [ "$m" -ge 775 ] && [ "$m" -lt 780 ]; }
}

sync_market_branch() {
  git -C "$OUT" fetch origin financial-market-data
  git -C "$OUT" reset --hard origin/financial-market-data
  mkdir -p "$OUT/market/intraday"
}

validate_status() {
  STATUS="$OUT/market/intraday-status.json" python - <<'PY'
import json, math, os
from datetime import datetime, timezone
from pathlib import Path
p=Path(os.environ['STATUS'])
if not p.exists():
    raise SystemExit('intraday status missing')
d=json.loads(p.read_text())
expected=int(d.get('expected') or 0)
success=int(d.get('success') or 0)
required=int(d.get('required') or math.ceil(expected*.90))
session_expected=int(d.get('sessionExpected') or 0)
session_fresh=int(d.get('sessionFresh') or 0)
session_required=int(d.get('sessionRequired') or (math.ceil(session_expected*.90) if session_expected else 0))
if expected <= 0:
    raise SystemExit('intraday expected universe missing')
checked=datetime.fromisoformat(str(d.get('checkedAt')).replace('Z','+00:00')).astimezone(timezone.utc)
age=(datetime.now(timezone.utc)-checked).total_seconds()/60
if age > 15:
    raise SystemExit(f'intraday collector heartbeat stale: {age:.1f}m')
if success < required:
    raise SystemExit(f'intraday fetch coverage low: {success}/{expected}; required={required}')
if session_expected and session_fresh < session_required:
    raise SystemExit(f'intraday live-bar coverage low: {session_fresh}/{session_expected}; required={session_required}')
if d.get('status') != 'ok':
    raise SystemExit(f'intraday status={d.get("status")}')
print('INTRADAY HEALTH', {
    'fetch': f'{success}/{expected}',
    'session': f'{session_fresh}/{session_expected}' if session_expected else 'n/a',
    'lagged': d.get('sessionLaggedCount'),
    'medianLagMinutes': d.get('sessionMedianLagMinutes'),
})
PY
}

publish_snapshot() {
  git -C "$OUT" restore --worktree market/universe.json market/history market/intraday-5m 2>/dev/null || true
  git -C "$OUT" add --sparse market/intraday-status.json market/intraday
  if git -C "$OUT" diff --cached --quiet; then
    echo "No minute-candle changes to publish."
    return 0
  fi
  git -C "$OUT" commit -m 'Refresh live HOSE minute candles [data-only]'
  local published=0
  for attempt in 1 2 3; do
    git -C "$OUT" fetch origin financial-market-data
    if git -C "$OUT" rebase origin/financial-market-data && git -C "$OUT" push origin HEAD:refs/heads/financial-market-data; then
      published=1
      break
    fi
    git -C "$OUT" rebase --abort || true
    sleep $((attempt * 2))
  done
  [ "$published" -eq 1 ]
}

run_cycle() {
  sync_market_branch
  local collect_rc=0 health_rc=0
  python -u financial-report/scripts/refresh_market.py --output "$OUT/market" --mode intraday || collect_rc=$?
  validate_status || health_rc=$?
  publish_snapshot
  if [ "$collect_rc" -ne 0 ] || [ "$health_rc" -ne 0 ]; then
    echo "Minute-candle cycle degraded: collector=$collect_rc health=$health_rc" >&2
    return 1
  fi
  return 0
}

failures=0
while true; do
  minute="$(vn_minutes)"
  if [ "$ONESHOT" != "1" ] && in_prewarm_window "$minute"; then
    echo "Minute publisher pre-warm; waiting for continuous session."
    sleep 60
    continue
  fi
  if [ "$ONESHOT" != "1" ] && ! in_live_window "$minute"; then
    echo "Outside live minute-candle window; publisher finished."
    exit 0
  fi

  if run_cycle; then
    failures=0
  else
    failures=$((failures + 1))
    if [ "$failures" -ge "$MAX_FAILURES" ]; then
      echo "Minute publisher failed $failures consecutive cycles." >&2
      exit 1
    fi
  fi

  if [ "$ONESHOT" = "1" ]; then
    [ "$failures" -eq 0 ]
    exit $?
  fi
  sleep "$INTERVAL_SECONDS"
done
