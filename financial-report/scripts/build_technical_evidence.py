#!/usr/bin/env python3
"""Build transparent historical evidence for the existing FinQuery Technical Scanner.

This DOES NOT change scanner rules or weights. It evaluates a daily-EOD proxy of
those rules on available market histories so the UI can distinguish heuristic
rule priority from empirical historical evidence.
"""
from __future__ import annotations
import argparse, importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKET = ROOT / "scripts" / "refresh_market.py"
spec = importlib.util.spec_from_file_location("finquery_refresh_market", MARKET)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

VN = timezone(timedelta(hours=7))
HORIZONS = (1, 3, 5)
DIRECTION = {
    "macd_cross_up": "up", "macd_near_up": "up",
    "rsi_exit_oversold": "up", "rsi_oversold": "up",
    "macd_cross_down": "down", "macd_near_down": "down",
    "rsi_exit_overbought": "down", "rsi_overbought": "down",
    "volume_spike": "neutral", "volume_elevated": "neutral",
}
LABELS = {
    "macd_cross_up": "MACD cắt lên Signal", "macd_cross_down": "MACD cắt xuống Signal",
    "macd_near_up": "MACD tiến sát giao cắt lên", "macd_near_down": "MACD tiến sát giao cắt xuống",
    "rsi_exit_oversold": "RSI thoát quá bán", "rsi_exit_overbought": "RSI rời quá mua",
    "rsi_oversold": "RSI quá bán", "rsi_overbought": "RSI quá mua",
    "volume_spike": "Volume >=1.5x TB20", "volume_elevated": "Volume >=1.2x TB20",
}

def read(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default

def write(path, payload):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

def median(values):
    a = sorted(values)
    if not a: return None
    n = len(a); k = n // 2
    return a[k] if n % 2 else (a[k-1] + a[k]) / 2

def ids_for(rows, bars, i):
    cur, prev = rows[i], rows[i-1]
    close = cur.get("close")
    if not close: return []
    hist, prev_hist = cur.get("hist"), prev.get("hist")
    rsi, prev_rsi = cur.get("rsi"), prev.get("rsi")
    ids = []
    hist_pct = hist / close * 100 if isinstance(hist, (int,float)) else None
    near = m.TECHNICAL_SCANNER_RULES["macd"]["nearCrossMaxSpreadPct"]
    if prev_hist is not None and hist is not None:
        if prev_hist <= 0 < hist: ids.append("macd_cross_up")
        elif prev_hist >= 0 > hist: ids.append("macd_cross_down")
        elif hist_pct is not None and hist < 0 and prev_hist < 0 and hist > prev_hist and abs(hist_pct) <= near: ids.append("macd_near_up")
        elif hist_pct is not None and hist > 0 and prev_hist > 0 and hist < prev_hist and abs(hist_pct) <= near: ids.append("macd_near_down")
    if rsi is not None:
        if rsi <= 30: ids.append("rsi_oversold")
        elif rsi >= 70: ids.append("rsi_overbought")
        if prev_rsi is not None and prev_rsi < 30 <= rsi: ids.append("rsi_exit_oversold")
        if prev_rsi is not None and prev_rsi > 70 >= rsi: ids.append("rsi_exit_overbought")
    completed = [max(0, m.number(x.get("volume")) or 0) for x in bars[max(0,i-20):i]]
    if len(completed) == 20 and any(completed):
        avg = sum(completed) / 20
        ratio = (m.number(bars[i].get("volume")) or 0) / avg if avg else None
        if ratio is not None and ratio >= 1.5: ids.append("volume_spike")
        elif ratio is not None and ratio >= 1.2: ids.append("volume_elevated")
    return ids

def main(out):
    today = datetime.now(VN).date().isoformat()
    histories = sorted((Path(out) / "history").glob("*.json"))
    existing = read(Path(out) / "technical-evidence.json", {})
    latest_candidates = []
    for path in histories:
        bars = read(path, {}).get("bars") or []
        completed = [b for b in bars if b.get("time") and b.get("time") != today and m.number(b.get("close"))]
        if completed: latest_candidates.append(str(completed[-1].get("time") or ""))
    latest_available = max(latest_candidates, default=None)
    if existing.get("status") == "ok" and existing.get("sourceDate") == latest_available and existing.get("signals"):
        print(json.dumps({"status":"cached","sourceDate":latest_available,"signals":len(existing.get("signals") or {})}))
        return
    samples = defaultdict(lambda: defaultdict(list))
    baseline = defaultdict(list)
    symbols_used = 0
    latest_bar = None
    for path in histories:
        bars = read(path, {}).get("bars") or []
        bars = [b for b in bars if b.get("time") and b.get("time") != today and m.number(b.get("close"))]
        if len(bars) < 45: continue
        symbols_used += 1
        latest_bar = max(latest_bar or "", str(bars[-1].get("time") or ""))
        rows = m._technical_indicator_rows(bars)
        if len(rows) != len(bars): continue
        for i in range(35, len(bars)-max(HORIZONS)):
            close = m.number(bars[i].get("close"))
            if not close: continue
            future = {}
            for h in HORIZONS:
                end = m.number(bars[i+h].get("close"))
                if end:
                    r = end / close - 1
                    future[h] = r
                    baseline[h].append(r)
            if not future: continue
            for sid in ids_for(rows, bars, i):
                for h,r in future.items():
                    samples[sid][h].append(r)
    base_stats = {}
    for h,vals in baseline.items():
        pos = sum(v > 0 for v in vals) / len(vals) if vals else None
        neg = sum(v < 0 for v in vals) / len(vals) if vals else None
        base_stats[str(h)] = {"n":len(vals),"positiveRate":pos,"negativeRate":neg,"medianReturn":median(vals)}
    signals = {}
    for sid,by_h in samples.items():
        direction = DIRECTION.get(sid, "neutral")
        horizons = {}
        for h,vals in by_h.items():
            if not vals: continue
            hit = None; lift = None
            if direction == "up":
                hit = sum(v > 0 for v in vals) / len(vals)
                lift = hit - (base_stats[str(h)]["positiveRate"] or 0)
            elif direction == "down":
                hit = sum(v < 0 for v in vals) / len(vals)
                lift = hit - (base_stats[str(h)]["negativeRate"] or 0)
            horizons[str(h)] = {
                "n":len(vals),
                "directionalHitRate":hit,
                "liftVsBaseline":lift,
                "meanReturn":sum(vals)/len(vals),
                "medianReturn":median(vals),
            }
        signals[sid] = {
            "id":sid,"label":LABELS.get(sid,sid),"direction":direction,
            "sample":max((x["n"] for x in horizons.values()), default=0),
            "horizons":horizons,
        }
    payload = {
        "version":"FINQUERY-TECHNICAL-EVIDENCE-1.0",
        "status":"ok" if signals else "insufficient",
        "generatedAt":datetime.now(timezone.utc).isoformat(),
        "sourceDate":latest_bar,
        "symbolsUsed":symbols_used,
        "method":"DAILY_EOD_PROXY",
        "rulesUnchanged":True,
        "note":"Evidence is a daily-EOD historical proxy for the existing scanner rules. It is not a live 15-minute success probability and does not change scanner priority weights.",
        "baseline":base_stats,
        "signals":signals,
    }
    write(Path(out) / "technical-evidence.json", payload)
    print(json.dumps({"status":payload["status"],"symbolsUsed":symbols_used,"signals":len(signals),"sourceDate":latest_bar}))

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--output",required=True,type=Path); a=p.parse_args(); main(a.output)
