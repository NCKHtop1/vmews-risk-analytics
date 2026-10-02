#!/usr/bin/env bash
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel)"
OUT="/tmp/market-live"
INTERVAL_SECONDS="${MARKET_LOOP_SECONDS:-300}"
MAX_AGE_MINUTES="${MARKET_MAX_QUOTE_AGE_MINUTES:-18}"
FORCE_ONESHOT="${FORCE_ONESHOT:-0}"
GH_REPO="${GH_REPO:-NCKHtop1/vmews-risk-analytics}"

vn_minutes() {
  local hh mm
  hh="$(TZ=Asia/Ho_Chi_Minh date +%H)"
  mm="$(TZ=Asia/Ho_Chi_Minh date +%M)"
  echo $((10#$hh * 60 + 10#$mm))
}

session_end_minutes() {
  local now_min="$1"
  if [ "$now_min" -ge 540 ] && [ "$now_min" -le 700 ]; then
    echo 700
    return 0
  fi
  if [ "$now_min" -ge 775 ] && [ "$now_min" -le 905 ]; then
    echo 905
    return 0
  fi
  return 1
}

setup_market_worktree() {
  rm -rf "$OUT"
  git fetch origin financial-market-data
  git worktree add "$OUT" origin/financial-market-data
  git -C "$OUT" sparse-checkout set market
  mkdir -p "$OUT/market"
  git -C "$OUT" config user.name 'github-actions[bot]'
  git -C "$OUT" config user.email '41898282+github-actions[bot]@users.noreply.github.com'
}

sync_market_worktree() {
  git -C "$OUT" fetch origin financial-market-data
  git -C "$OUT" reset --hard origin/financial-market-data
  git -C "$OUT" clean -fd
}

validate_snapshot() {
  SNAPSHOT_DIR="$OUT/market" MAX_AGE_MINUTES="$MAX_AGE_MINUTES" python - <<'PY'
import json, math, os
from datetime import datetime, timezone
from pathlib import Path

root=Path(os.environ['SNAPSHOT_DIR'])
max_age=float(os.environ.get('MAX_AGE_MINUTES','18'))
now=datetime.now(timezone.utc)

def load(name):
    return json.loads((root/name).read_text())

def age(value):
    if not value:
        return math.inf
    dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if dt.tzinfo is None:
        dt=dt.replace(tzinfo=timezone.utc)
    minutes=(now-dt.astimezone(timezone.utc)).total_seconds()/60
    return minutes if minutes >= -5 else math.inf

quotes=load('quotes.json')
scanner=load('technical-signals.json')
strategy=load('strategy-indicators.json')
watch=load('watch-today.json')
status=load('prices-status.json')
drivers=load('drivers.json')

expected=max(1,int(quotes.get('expected') or 0))
required=max(1,math.ceil(expected*.90))
fresh=[
    q for q in (quotes.get('quotes') or {}).values()
    if q.get('status')!='retained' and age(q.get('sourceTime') or q.get('collectedAt'))<=max_age
]
latest=quotes.get('latestSourceTime')
if quotes.get('status')!='ok' or len(fresh)<required:
    raise SystemExit(f'fresh quote coverage below 90%: {len(fresh)}/{expected}')
if age(latest)>max_age:
    raise SystemExit(f'latest quote source is stale: {age(latest):.1f} minutes')
if age(quotes.get('checkedAt'))>10:
    raise SystemExit(f'quote collector heartbeat stale: {age(quotes.get("checkedAt")):.1f} minutes')

scanner_universe=max(1,int(scanner.get('universe') or 0))
scanner_required=max(1,math.ceil(scanner_universe*.90))
if scanner.get('status')!='ok' or int(scanner.get('coverage') or 0)<scanner_required:
    raise SystemExit(f'scanner coverage below 90%: {scanner.get("coverage")}/{scanner_universe}')
if strategy.get('status')!='ok' or int(strategy.get('coverage') or 0)<scanner_required:
    raise SystemExit(f'strategy coverage below 90%: {strategy.get("coverage")}/{scanner_universe}')

for label,data in [('scanner',scanner),('strategy',strategy),('watch',watch)]:
    if data.get('status')!='ok':
        raise SystemExit(f'{label} status is not ok')
    if str(data.get('sourceTime') or '') != str(latest or ''):
        raise SystemExit(f'{label} sourceTime is not aligned with quotes')
    if age(data.get('checkedAt'))>10:
        raise SystemExit(f'{label} heartbeat stale: {age(data.get("checkedAt")):.1f} minutes')

if status.get('status')!='ok' or age(status.get('checkedAt'))>10:
    raise SystemExit('prices-status heartbeat is stale')
if age(drivers.get('generatedAt'))>10:
    raise SystemExit('drivers snapshot heartbeat is stale')

print({
    'freshQuotes':len(fresh),
    'expected':expected,
    'latestSourceTime':latest,
    'latestAgeMin':round(age(latest),1),
    'scanner':scanner.get('coverage'),
    'strategy':strategy.get('coverage'),
    'watch':len(watch.get('items') or []),
    'drivers':len(drivers.get('symbols') or {}),
})
PY
}

publish_snapshot() {
  git -C "$OUT" add --sparse     market/quotes.json market/prices-status.json market/drivers.json     market/technical-signals.json market/technical-evidence.json     market/strategy-indicators.json market/watch-today.json     market/universe.json market/history-status.json market/history

  if git -C "$OUT" diff --cached --quiet; then
    echo "No live market changes to publish"
    return 0
  fi

  git -C "$OUT" commit -m 'Refresh live HOSE Core + Liquid prices [data-only]'
  for attempt in 1 2 3; do
    git -C "$OUT" fetch origin financial-market-data
    if git -C "$OUT" rebase origin/financial-market-data && git -C "$OUT" push origin HEAD:refs/heads/financial-market-data; then
      return 0
    fi
    git -C "$OUT" rebase --abort || true
    sleep $((attempt * 2))
  done
  echo "Unable to publish live market snapshot after retries" >&2
  return 1
}

supervise_news() {
  if [ -z "${GH_TOKEN:-}" ]; then
    return 0
  fi
  if NEWS_URL="https://raw.githubusercontent.com/$GH_REPO/financial-market-data/market/news.json?heartbeat=$(date +%s)" python - <<'PY'
import json, os, urllib.request
from datetime import datetime, timezone
url=os.environ['NEWS_URL']
try:
    with urllib.request.urlopen(url,timeout=12) as r:
        data=json.load(r)
    stamp=datetime.fromisoformat(str(data.get('checkedAt')).replace('Z','+00:00'))
    if stamp.tzinfo is None:
        stamp=stamp.replace(tzinfo=timezone.utc)
    age=(datetime.now(timezone.utc)-stamp.astimezone(timezone.utc)).total_seconds()/60
    if data.get('status')=='ok' and data.get('items') and age<=20:
        print('News heartbeat OK',round(age,1),'minutes')
        raise SystemExit(0)
except Exception as exc:
    print('News heartbeat stale/unavailable:',exc)
raise SystemExit(1)
PY
  then
    return 0
  fi

  local active
  active="$(gh run list --repo "$GH_REPO" --workflow market-news-live.yml --limit 10 --json status --jq 'any(.[]; .status=="queued" or .status=="in_progress" or .status=="waiting" or .status=="pending")' 2>/dev/null || echo false)"
  if [ "$active" = "true" ]; then
    echo "News publisher is already active"
    return 0
  fi
  gh workflow run market-news-live.yml --repo "$GH_REPO" --ref main
  echo "Dispatched stale-news recovery"
}

collect_validate_publish() {
  local ok=1
  for attempt in 1 2; do
    echo "=== Intraday refresh attempt $attempt at $(TZ=Asia/Ho_Chi_Minh date '+%H:%M:%S %d/%m/%Y') ==="
    sync_market_worktree
    if MARKET_REQUIRE_TODAY=1 MARKET_MAX_QUOTE_AGE_MINUTES="$MAX_AGE_MINUTES"       python -u "$ROOT/financial-report/scripts/refresh_market.py" --output "$OUT/market" --mode prices       && python -u "$ROOT/financial-report/scripts/build_technical_evidence.py" --output "$OUT/market"       && node "$ROOT/financial-report/scripts/build_strategy_snapshot.cjs" "$OUT/market"       && validate_snapshot       && publish_snapshot; then
      ok=0
      break
    fi
    echo "::warning::Intraday refresh attempt $attempt failed validation; stale data was not published."
    sleep 45
  done
  supervise_news || true
  return "$ok"
}

now_min="$(vn_minutes)"
if end_min="$(session_end_minutes "$now_min")"; then
  :
elif [ "$FORCE_ONESHOT" = "1" ]; then
  end_min="$now_min"
else
  echo "Outside Vietnam live/close-catch window; nothing to publish."
  exit 0
fi

setup_market_worktree
failures=0
iterations=0

while true; do
  iterations=$((iterations + 1))
  if ! collect_validate_publish; then
    failures=$((failures + 1))
  fi

  now_min="$(vn_minutes)"
  if [ "$FORCE_ONESHOT" = "1" ] || [ "$now_min" -ge "$end_min" ]; then
    break
  fi
  sleep "$INTERVAL_SECONDS"
done

echo "Session publisher finished: iterations=$iterations failures=$failures"
if [ "$iterations" -gt 0 ] && [ "$failures" -ge "$iterations" ]; then
  echo "Every intraday refresh attempt failed." >&2
  exit 1
fi
