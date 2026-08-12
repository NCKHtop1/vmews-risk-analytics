import importlib.util
import json
import math
import pathlib
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss, precision_score, recall_score, confusion_matrix
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'pooled-hose'
OUT.mkdir(parents=True, exist_ok=True)
VN_TZ = timezone(timedelta(hours=7))
VERSION = 'VMEWS-POOLED-HOSE-1.0.0'
FEATURE_VERSION = 'PANEL-PIT-PRICE-LIQUIDITY-1.0'
SEED = 20260812
HORIZON = 20
CRASH_THRESHOLD = -0.12
CORP_GUARD = 0.22
MIN_TURNOVER = 500_000_000.0
SAMPLE_STEP = 5
MIN_CROSS_SECTION = 80
PURGE_SESSIONS = 20


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


core = load_module('vmews_pool_core', ROOT / 'api' / 'stocks.py')


def clean(v):
    import re
    return re.sub(r'[^A-Z0-9]', '', str(v or '').upper())[:8]


def hose_universe():
    from vnstock import Listing
    df = Listing(source='VCI').symbols_by_exchange(show_log=False)
    cols = {str(c).lower(): c for c in df.columns}
    sc = cols.get('symbol')
    ec = cols.get('exchange') or cols.get('board')
    nc = cols.get('organ_name') or cols.get('organ_short_name')
    tc = cols.get('type')
    if sc is None or ec is None:
        raise RuntimeError(f'Unexpected VCI listing columns: {list(df.columns)}')
    out = []
    for _, row in df.iterrows():
        sym = clean(row.get(sc))
        ex = str(row.get(ec) or '').upper().strip()
        ex = {'HSX': 'HOSE', 'HOCHIMINH': 'HOSE'}.get(ex, ex)
        typ = str(row.get(tc, 'STOCK')).upper() if tc is not None else 'STOCK'
        if sym and ex == 'HOSE' and typ == 'STOCK':
            out.append({'symbol': sym, 'name': str(row.get(nc, sym) or sym).strip() if nc is not None else sym})
    out = list({x['symbol']: x for x in out}.values())
    if len(out) < 250:
        raise RuntimeError(f'HOSE universe unexpectedly small: {len(out)}')
    return sorted(out, key=lambda x: x['symbol'])


def completed_rows(rows):
    rows = [dict(x) for x in rows if x.get('date') and float(x.get('close') or 0) > 0]
    rows.sort(key=lambda x: x['date'])
    now = datetime.now(VN_TZ)
    today = now.date().isoformat()
    # Before the Vietnam cash session is safely complete, never treat today's partial bar as EOD.
    if now.weekday() < 5 and (now.hour < 15 or (now.hour == 15 and now.minute < 20)):
        rows = [x for x in rows if x['date'] < today]
    return rows


def fallback_rows(symbol):
    p = ROOT / 'data' / 'hose-fallbacks' / f'{symbol}.json'
    if not p.exists():
        return None, None
    try:
        q = json.loads(p.read_text(encoding='utf-8'))
        rows = completed_rows(q.get('history') or [])
        if rows:
            return rows, f"{q.get('source',{}).get('price') or 'Vnstock/CDN fallback'}"
    except Exception:
        pass
    return None, None


def fetch_one(meta):
    sym = meta['symbol']
    try:
        rows, _, host = core.yahoo_chart(sym, '10y', 10)
        rows = completed_rows(rows)
        if len(rows) >= 240:
            return sym, rows, f'Yahoo Finance · {host}', None
    except Exception as e:
        err = str(e)
    else:
        err = f'Yahoo history only {len(rows)} rows'
    rows, source = fallback_rows(sym)
    if rows and len(rows) >= 240:
        return sym, rows, source, None
    return sym, None, None, err


def adjust_rows(rows):
    if not rows:
        return [], []
    out = [dict(x) for x in rows]
    suspect = []
    model = float(out[0]['close'])
    out[0]['rawClose'] = float(out[0]['close'])
    out[0]['close'] = model
    for i in range(1, len(out)):
        raw = float(rows[i]['close'])
        prev_raw = float(rows[i-1]['close'])
        lr = math.log(raw / prev_raw) if raw > 0 and prev_raw > 0 else 0.0
        bad = abs(lr) > CORP_GUARD
        if bad:
            suspect.append({'date': rows[i]['date'], 'logReturn': lr})
        model *= math.exp(0.0 if bad else lr)
        out[i]['rawClose'] = raw
        out[i]['close'] = model
    return out, suspect


def median_turnover(raw_rows, i, n=20):
    z = []
    for r in raw_rows[max(0, i-n+1):i+1]:
        try:
            c = float(r.get('close') or 0)
            v = float(r.get('volume') or 0)
            if c > 0 and v > 0:
                z.append(c * v)
        except Exception:
            pass
    return statistics.median(z) if z else 0.0


def build_symbol_panel(symbol, raw_rows):
    adj, suspects = adjust_rows(raw_rows)
    fs = core.features(adj)
    if len(fs) < 25:
        return [], None, suspects
    samples = []
    for pos, f in enumerate(fs):
        if pos % SAMPLE_STEP:
            continue
        i = f['i']
        if i + HORIZON >= len(adj):
            continue
        base = float(adj[i]['close'])
        fwd = min(float(adj[j]['close']) / base - 1.0 for j in range(i+1, i+HORIZON+1))
        turnover = median_turnover(raw_rows, i)
        if turnover < MIN_TURNOVER:
            continue
        ret1 = float(adj[i]['close']) / float(adj[i-1]['close']) - 1.0 if i > 0 else 0.0
        samples.append({
            'symbol': symbol, 'date': f['date'], 'i': i,
            'ret1': ret1, 'ret5': f['ret5'], 'mom20': f['mom20'], 'dd60': f['dd60'],
            'trend50': f['trend50'], 'trend200': f['trend200'], 'rsi14': f['rsi14'],
            'logTurnover20': math.log1p(turnover), 'technical': f['technical'],
            'crash': 1 if fwd <= CRASH_THRESHOLD else 0, 'forwardDrawdown20': fwd,
        })
    last = fs[-1]
    liq = median_turnover(raw_rows, last['i'])
    current = None
    if liq >= MIN_TURNOVER:
        i = last['i']
        current = {
            'symbol': symbol, 'date': last['date'], 'i': i,
            'ret1': float(adj[i]['close']) / float(adj[i-1]['close']) - 1.0 if i > 0 else 0.0,
            'ret5': last['ret5'], 'mom20': last['mom20'], 'dd60': last['dd60'],
            'trend50': last['trend50'], 'trend200': last['trend200'], 'rsi14': last['rsi14'],
            'logTurnover20': math.log1p(liq), 'technical': last['technical'],
            'turnover20': liq,
        }
    return samples, current, suspects


def add_cross_section(df, labelled=True):
    if df.empty:
        return df
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    counts = df.groupby('date')['symbol'].transform('nunique')
    df = df[counts >= MIN_CROSS_SECTION].copy()
    if df.empty:
        return df
    g = df.groupby('date', group_keys=False)
    df['riskRankMom20'] = g['mom20'].rank(pct=True, ascending=False)
    df['riskRankDd60'] = g['dd60'].rank(pct=True, ascending=False)
    df['riskRankTrend50'] = g['trend50'].rank(pct=True, ascending=False)
    df['riskRankTrend200'] = g['trend200'].rank(pct=True, ascending=False)
    df['riskRankRsi'] = g['rsi14'].rank(pct=True, ascending=False)
    df['liquidityRank'] = g['logTurnover20'].rank(pct=True, ascending=True)
    df['technicalRank'] = g['technical'].rank(pct=True, ascending=True)
    breadth = df.groupby('date').agg(
        marketNegMomFrac=('mom20', lambda x: float((x < 0).mean())),
        marketBelow50Frac=('trend50', lambda x: float((x < 0).mean())),
        marketMedianMom20=('mom20', 'median'),
        marketMedianDd60=('dd60', 'median'),
        marketMomDisp=('mom20', 'std'),
        marketTechnicalMean=('technical', 'mean'),
    ).reset_index()
    df = df.merge(breadth, on='date', how='left')
    if labelled:
        df['crash'] = df['crash'].astype(int)
    return df.sort_values(['date', 'symbol']).reset_index(drop=True)


FEATURES = [
    'ret1', 'ret5', 'mom20', 'dd60', 'trend50', 'trend200', 'rsi14', 'logTurnover20', 'technical',
    'riskRankMom20', 'riskRankDd60', 'riskRankTrend50', 'riskRankTrend200', 'riskRankRsi',
    'liquidityRank', 'technicalRank', 'marketNegMomFrac', 'marketBelow50Frac', 'marketMedianMom20',
    'marketMedianDd60', 'marketMomDisp', 'marketTechnicalMean',
]


def model_factory(name):
    if name == 'logistic_l2':
        return Pipeline([
            ('scale', StandardScaler()),
            ('model', LogisticRegression(C=0.35, class_weight='balanced', max_iter=800, solver='lbfgs', random_state=SEED)),
        ])
    if name == 'hist_gbdt':
        return HistGradientBoostingClassifier(
            loss='log_loss', learning_rate=0.05, max_iter=180, max_depth=3,
            min_samples_leaf=80, l2_regularization=2.0, class_weight='balanced',
            early_stopping=False, random_state=SEED,
        )
    raise KeyError(name)


def predict_raw(model, frame):
    return model.predict_proba(frame[FEATURES])[:, 1]


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-5, 1-1e-5)
    return np.log(p / (1-p)).reshape(-1, 1)


def fit_platt(raw, y):
    y = np.asarray(y, dtype=int)
    if len(np.unique(y)) < 2 or y.sum() < 3:
        return None
    cal = LogisticRegression(C=1.0, solver='lbfgs', max_iter=500, random_state=SEED)
    cal.fit(logit(raw), y)
    return cal


def calibrate(cal, raw):
    if cal is None:
        return np.asarray(raw, dtype=float)
    return cal.predict_proba(logit(raw))[:, 1]


def choose_threshold(y, p, miss_cost=2.0, false_cost=1.0):
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    vals = np.unique(np.round(p, 4))
    if not len(vals):
        return 0.5
    best_t, best_loss = 0.5, float('inf')
    for t in vals:
        z = p >= t
        fn = int(((y == 1) & (~z)).sum())
        fp = int(((y == 0) & z).sum())
        loss = (miss_cost * fn + false_cost * fp) / max(1, len(y))
        if loss < best_loss or (loss == best_loss and t > best_t):
            best_t, best_loss = float(t), float(loss)
    return best_t


def episode_recall(frame, alerts):
    x = frame[['symbol', 'i', 'crash']].copy().reset_index(drop=True)
    x['alert'] = np.asarray(alerts, dtype=bool)
    episodes = hits = 0
    for _, g in x[x['crash'] == 1].groupby('symbol'):
        g = g.sort_values('i')
        cluster = []
        last = None
        for row in g.itertuples():
            if last is None or int(row.i) - last <= HORIZON:
                cluster.append(bool(row.alert))
            else:
                episodes += 1
                hits += int(any(cluster))
                cluster = [bool(row.alert)]
            last = int(row.i)
        if cluster:
            episodes += 1
            hits += int(any(cluster))
    return episodes, (hits / episodes if episodes else None)


def metrics(frame, p, threshold):
    y = frame['crash'].to_numpy(dtype=int)
    p = np.asarray(p, dtype=float)
    pred = p >= threshold
    base = float(y.mean()) if len(y) else 0.0
    ap = float(average_precision_score(y, p)) if y.sum() and y.sum() < len(y) else None
    auc = float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None
    br = float(brier_score_loss(y, p)) if len(y) else None
    base_br = float(brier_score_loss(y, np.full(len(y), base))) if len(y) else None
    skill = 1.0 - br / base_br if base_br and br is not None else None
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    episodes, ep_recall = episode_recall(frame, pred)
    precision = float(precision_score(y, pred, zero_division=0))
    recall = float(recall_score(y, pred, zero_division=0))
    return {
        'n': int(len(y)), 'symbols': int(frame['symbol'].nunique()), 'events': int(y.sum()),
        'eventEpisodes': int(episodes), 'baseRate': base, 'prAuc': ap, 'rocAuc': auc,
        'brier': br, 'baseRateBrier': base_br, 'brierSkill': skill,
        'threshold': float(threshold), 'precision': precision, 'recall': recall,
        'falsePositiveRate': float(fp / max(1, fp + tn)), 'alertRate': float(pred.mean()),
        'missRate': float(fn / max(1, fn + tp)), 'episodeRecall': ep_recall,
        'precisionEnrichment': float(precision / base) if base > 0 else None,
    }


def bootstrap_pr_ci(frame, p, reps=120):
    frame = frame.reset_index(drop=True)
    p = np.asarray(p, dtype=float)
    by_date = {d: idx.to_numpy() for d, idx in frame.groupby('date').groups.items()}
    dates = list(by_date)
    if len(dates) < 20:
        return None
    rng = np.random.default_rng(SEED)
    vals = []
    for _ in range(reps):
        picked = rng.choice(dates, size=len(dates), replace=True)
        ids = np.concatenate([by_date[d] for d in picked])
        y = frame.iloc[ids]['crash'].to_numpy(dtype=int)
        if y.sum() == 0 or y.sum() == len(y):
            continue
        vals.append(float(average_precision_score(y, p[ids])))
    if not vals:
        return None
    return {'low': float(np.quantile(vals, .025)), 'high': float(np.quantile(vals, .975)), 'reps': len(vals), 'unit': 'date-block bootstrap'}


def date_slice(df, start_idx, end_idx, dates):
    if start_idx >= end_idx:
        return df.iloc[0:0].copy()
    lo, hi = dates[start_idx], dates[end_idx-1]
    return df[(df['date'] >= lo) & (df['date'] <= hi)].copy()


def eval_split(name, train, cal, test):
    model = model_factory(name)
    model.fit(train[FEATURES], train['crash'])
    raw_cal = predict_raw(model, cal)
    calibrator = fit_platt(raw_cal, cal['crash'])
    p_cal = calibrate(calibrator, raw_cal)
    threshold = choose_threshold(cal['crash'], p_cal)
    raw_test = predict_raw(model, test)
    p_test = calibrate(calibrator, raw_test)
    out = metrics(test, p_test, threshold)
    out['calibrationN'] = int(len(cal))
    out['calibrationEvents'] = int(cal['crash'].sum())
    out['prAucCI95'] = bootstrap_pr_ci(test, p_test)
    return out, model, calibrator, p_test


def development_folds(df, sealed_idx, dates, model_name):
    dev_n = sealed_idx
    folds = []
    specs = [(0.42, 0.54, 0.66), (0.54, 0.66, 0.78), (0.66, 0.78, 0.94)]
    for a, b, c in specs:
        train_end = int(dev_n * a)
        cal_start = min(dev_n, train_end + PURGE_SESSIONS)
        cal_end = int(dev_n * b)
        test_start = min(dev_n, cal_end + PURGE_SESSIONS)
        test_end = int(dev_n * c)
        tr = date_slice(df, 0, train_end, dates)
        ca = date_slice(df, cal_start, cal_end, dates)
        te = date_slice(df, test_start, test_end, dates)
        if len(tr) < 5000 or len(ca) < 1000 or len(te) < 1000 or ca['crash'].sum() < 20 or te['crash'].sum() < 20:
            continue
        m, _, _, _ = eval_split(model_name, tr, ca, te)
        m.update({'trainTo': str(dates[train_end-1].date()), 'calFrom': str(dates[cal_start].date()),
                  'calTo': str(dates[cal_end-1].date()), 'testFrom': str(dates[test_start].date()),
                  'testTo': str(dates[test_end-1].date()), 'purgeSessions': PURGE_SESSIONS})
        folds.append(m)
    if not folds:
        raise RuntimeError(f'No valid development folds for {model_name}')
    def avg(k):
        z = [x[k] for x in folds if x.get(k) is not None and math.isfinite(float(x[k]))]
        return float(np.mean(z)) if z else None
    base = avg('baseRate') or 0.0
    pr = avg('prAuc') or 0.0
    skill = (pr - base) / max(.05, 1-base)
    brier = avg('brierSkill') or 0.0
    return {'folds': folds, 'meanPrAuc': pr, 'meanBaseRate': base, 'meanPrSkill': skill,
            'meanBrierSkill': brier, 'selectionScore': skill + .25 * max(0.0, brier)}


def sealed_split(df, dates, sealed_idx):
    cal_end = sealed_idx - PURGE_SESSIONS
    cal_start = max(int(sealed_idx * .68), cal_end - 126)
    train_end = cal_start - PURGE_SESSIONS
    tr = date_slice(df, 0, train_end, dates)
    ca = date_slice(df, cal_start, cal_end, dates)
    te = date_slice(df, sealed_idx, len(dates), dates)
    return tr, ca, te, {'trainTo': str(dates[train_end-1].date()), 'calFrom': str(dates[cal_start].date()),
                        'calTo': str(dates[cal_end-1].date()), 'sealedFrom': str(dates[sealed_idx].date()),
                        'sealedTo': str(dates[-1].date()), 'purgeSessions': PURGE_SESSIONS}


def structural_eval(cal, test):
    raw_cal = np.clip(cal['technical'].to_numpy(dtype=float) / 100.0, 1e-5, 1-1e-5)
    platt = fit_platt(raw_cal, cal['crash'])
    p_cal = calibrate(platt, raw_cal)
    threshold = choose_threshold(cal['crash'], p_cal)
    raw_test = np.clip(test['technical'].to_numpy(dtype=float) / 100.0, 1e-5, 1-1e-5)
    p_test = calibrate(platt, raw_test)
    m = metrics(test, p_test, threshold)
    m['prAucCI95'] = bootstrap_pr_ci(test, p_test)
    return m


def promotion_gate(champ, baseline):
    reasons = []
    if champ['eventEpisodes'] < 100:
        reasons.append(f"sealed event episodes {champ['eventEpisodes']} < 100")
    if champ['prAuc'] is None or champ['prAuc'] <= champ['baseRate'] + .02:
        reasons.append('sealed PR-AUC does not exceed base rate by > 0.02')
    if baseline.get('prAuc') is not None and champ.get('prAuc') is not None and champ['prAuc'] < baseline['prAuc'] + .005:
        reasons.append('pooled champion does not improve sealed PR-AUC over structural baseline by >= 0.005')
    if champ.get('brierSkill') is None or champ['brierSkill'] <= 0:
        reasons.append('sealed Brier skill is not positive')
    if champ.get('rocAuc') is None or champ['rocAuc'] < .58:
        reasons.append('sealed ROC-AUC < 0.58')
    if champ.get('episodeRecall') is None or champ['episodeRecall'] < .35:
        reasons.append('sealed event-episode recall < 35%')
    return len(reasons) == 0, reasons


def percentile(ref, x):
    ref = np.asarray(ref, dtype=float)
    if not len(ref):
        return .5
    return float((np.sum(ref < x) + .5 * np.sum(ref == x)) / len(ref))


def main():
    universe = hose_universe()
    rows_by_symbol = {}
    sources = {}
    errors = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        fut = {ex.submit(fetch_one, m): m for m in universe}
        for f in as_completed(fut):
            sym, rows, source, err = f.result()
            if rows:
                rows_by_symbol[sym] = rows
                sources[sym] = source
            else:
                errors.append({'symbol': sym, 'error': err})
    if len(rows_by_symbol) / len(universe) < .90:
        raise RuntimeError(f'Price-history coverage too low: {len(rows_by_symbol)}/{len(universe)}')

    panel_rows = []
    current_rows = []
    corp_suspects = 0
    for sym, rows in rows_by_symbol.items():
        samples, current, suspects = build_symbol_panel(sym, rows)
        panel_rows.extend(samples)
        if current:
            current_rows.append(current)
        corp_suspects += len(suspects)

    panel = add_cross_section(pd.DataFrame(panel_rows), labelled=True)
    current = add_cross_section(pd.DataFrame(current_rows), labelled=False)
    if len(panel) < 30000 or panel['symbol'].nunique() < 150:
        raise RuntimeError(f'Pooled panel unexpectedly small: {len(panel)} states / {panel.symbol.nunique()} symbols')

    dates = sorted(panel['date'].drop_duplicates().tolist())
    if len(dates) < 900:
        raise RuntimeError(f'Not enough unique panel dates: {len(dates)}')
    sealed_idx = int(len(dates) * .85)
    candidates = {}
    for name in ('logistic_l2', 'hist_gbdt'):
        candidates[name] = development_folds(panel, sealed_idx, dates, name)
    champion = max(candidates, key=lambda k: candidates[k]['selectionScore'])

    tr, ca, te, split_meta = sealed_split(panel, dates, sealed_idx)
    sealed, sealed_model, sealed_cal, sealed_p = eval_split(champion, tr, ca, te)
    baseline = structural_eval(ca, te)
    promoted, gate_reasons = promotion_gate(sealed, baseline)

    # Final production fit: champion architecture is frozen by development folds + sealed test.
    # The most recent 126 completed panel dates are kept as a chronological probability-calibration window.
    prod_cal_end = len(dates)
    prod_cal_start = max(0, prod_cal_end - 126)
    prod_train_end = max(0, prod_cal_start - PURGE_SESSIONS)
    prod_train = date_slice(panel, 0, prod_train_end, dates)
    prod_cal = date_slice(panel, prod_cal_start, prod_cal_end, dates)
    prod_model = model_factory(champion)
    prod_model.fit(prod_train[FEATURES], prod_train['crash'])
    prod_raw_cal = predict_raw(prod_model, prod_cal)
    prod_platt = fit_platt(prod_raw_cal, prod_cal['crash'])
    if prod_platt is None:
        raise RuntimeError('Production Platt calibration could not be fit')
    prod_p_cal = calibrate(prod_platt, prod_raw_cal)
    prod_threshold = choose_threshold(prod_cal['crash'], prod_p_cal)

    current_scores = {}
    modal_date = None
    if not current.empty:
        modal_date = current['date'].value_counts().idxmax()
        cframe = current[current['date'] == modal_date].copy()
        if len(cframe) >= MIN_CROSS_SECTION:
            raw = predict_raw(prod_model, cframe)
            prob = calibrate(prod_platt, raw)
            for row, rr, pp in zip(cframe.to_dict('records'), raw, prob):
                current_scores[row['symbol']] = {
                    'symbol': row['symbol'], 'modelAsOf': str(pd.Timestamp(row['date']).date()),
                    'rawScore': float(rr), 'crashProbability': float(pp) if promoted else None,
                    'probabilityUsable': bool(promoted), 'riskPercentile': percentile(sealed_p, pp),
                    'relativeRisk': float(pp / sealed['baseRate']) if sealed['baseRate'] > 0 else None,
                    'technical': float(row['technical']), 'turnover20': float(math.expm1(row['logTurnover20'])),
                    'domain': 'HOSE_CURRENT_LIQUID_PIT',
                }

    validation = {
        'version': VERSION, 'featureVersion': FEATURE_VERSION, 'generatedAt': datetime.now(timezone.utc).isoformat(),
        'researchDesign': 'Current-HOSE pooled panel; weekly PIT states; date-based expanding development folds; 20-session purge; sealed last-15% date test; chronological Platt calibration.',
        'eventDefinition': {'horizonSessions': HORIZON, 'forwardDrawdownThreshold': CRASH_THRESHOLD},
        'universe': {'reference': len(universe), 'historyCovered': len(rows_by_symbol), 'historyCoverageRatio': len(rows_by_symbol)/len(universe),
                     'panelSymbols': int(panel['symbol'].nunique()), 'currentScored': len(current_scores), 'currentModelDate': str(pd.Timestamp(modal_date).date()) if modal_date is not None else None},
        'dataset': {'states': int(len(panel)), 'positiveStates': int(panel['crash'].sum()), 'baseRate': float(panel['crash'].mean()),
                    'uniqueDates': len(dates), 'start': str(dates[0].date()), 'end': str(dates[-1].date()),
                    'sampleStepSessions': SAMPLE_STEP, 'minTurnoverVnd': MIN_TURNOVER, 'corporateActionSuspectsNeutralized': corp_suspects},
        'candidateDevelopment': candidates, 'champion': champion, 'sealedSplit': split_meta,
        'sealedTest': sealed, 'structuralBaselineSealed': baseline,
        'incremental': {'deltaPrAucVsStructural': float(sealed['prAuc'] - baseline['prAuc']),
                        'deltaBrierSkillVsStructural': float((sealed['brierSkill'] or 0) - (baseline['brierSkill'] or 0))},
        'promotionGate': {'passed': promoted, 'reasons': gate_reasons,
                          'rule': '>=100 sealed event episodes; PR-AUC > base+0.02 and >= structural+0.005; positive Brier skill; ROC-AUC >=0.58; episode recall >=35%.'},
        'production': {'trainTo': str(dates[prod_train_end-1].date()), 'calibrationFrom': str(dates[prod_cal_start].date()),
                       'calibrationTo': str(dates[-1].date()), 'calibrationN': int(len(prod_cal)),
                       'calibrationEvents': int(prod_cal['crash'].sum()), 'decisionThreshold': float(prod_threshold)},
        'features': FEATURES,
        'sources': {'listingReference': 'VCI via vnstock', 'priceHistory': 'Yahoo Finance primary; existing Vnstock/CDN fallback for Yahoo gaps'},
        'limitations': [
            'Historical panel is built from the current HOSE reference universe; delisted historical constituents are not yet reconstructed, so survivorship bias is not claimed away.',
            'Corporate actions use the same 22% one-day discontinuity research guard; authoritative adjusted-price/corporate-action data remain preferable.',
            'The pooled model is a risk-research classifier for a 20-session drawdown event, not a buy/sell model or guaranteed forecast.',
            'Model promotion is based on a sealed chronological test; future live performance must still be monitored for drift.'
        ],
        'fetchErrors': errors[:40],
    }

    model_bundle = {
        'version': VERSION, 'featureVersion': FEATURE_VERSION, 'champion': champion, 'features': FEATURES,
        'model': prod_model, 'platt': prod_platt, 'promotionPassed': promoted,
        'sealedBaseRate': sealed['baseRate'], 'sealedReferenceProbabilities': np.asarray(sealed_p, dtype=float),
        'productionThreshold': prod_threshold, 'trainingCutoff': str(dates[prod_train_end-1].date()),
        'calibrationCutoff': str(dates[-1].date()),
    }
    joblib.dump(model_bundle, OUT / 'model.joblib', compress=3)
    (OUT / 'validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    (OUT / 'current-scores.json').write_text(json.dumps({
        'version': VERSION, 'generatedAt': datetime.now(timezone.utc).isoformat(),
        'modelAsOf': str(pd.Timestamp(modal_date).date()) if modal_date is not None else None,
        'champion': champion, 'promotionPassed': promoted, 'sealedTest': sealed,
        'scores': current_scores,
    }, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    meta = {
        'version': VERSION, 'featureVersion': FEATURE_VERSION, 'champion': champion, 'promotionPassed': promoted,
        'features': FEATURES, 'trainingCutoff': model_bundle['trainingCutoff'], 'calibrationCutoff': model_bundle['calibrationCutoff'],
        'sealedTest': sealed, 'structuralBaselineSealed': baseline,
    }
    (OUT / 'model-meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

    summary = {
        'version': VERSION, 'panelStates': len(panel), 'panelSymbols': int(panel['symbol'].nunique()),
        'positiveStates': int(panel['crash'].sum()), 'champion': champion, 'promotionPassed': promoted,
        'sealedPrAuc': sealed['prAuc'], 'sealedBaseRate': sealed['baseRate'], 'sealedBrierSkill': sealed['brierSkill'],
        'sealedEpisodes': sealed['eventEpisodes'], 'sealedEpisodeRecall': sealed['episodeRecall'],
        'baselinePrAuc': baseline['prAuc'], 'deltaPrAuc': sealed['prAuc'] - baseline['prAuc'],
        'currentScored': len(current_scores), 'gateReasons': gate_reasons,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not promoted:
        raise RuntimeError('Pooled model did not pass the sealed promotion gate: ' + ' | '.join(gate_reasons))


if __name__ == '__main__':
    main()
