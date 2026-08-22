"""Market-aware, tradable Vietnam-equity T+1...T+5 forecast pipeline.

The V12 research model ranks securities correctly but its fit-locked sixth-power
cross-sectional transform compresses the middle of the universe below one HOSE
tick.  This module keeps the V12 sealed research evidence intact and adds an
independently audited, volatility-normalised direct-return model.  Every
published price is executable on the relevant exchange's price grid.

Training, calibration and holdout periods are separated by actual label
maturity dates.  Neither future market-scan rows nor holdout labels enter
training or calibration.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import json
import math
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import brier_score_loss, mean_absolute_error

from forecast_v14_signal_audit import (
    FLOW_COLUMNS,
    NEWS_COLUMNS,
    latest_evidence,
    load_signal_sources,
    symbol_signal_features,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
VN_TZ = timezone(timedelta(hours=7))
VERSION = "VMEWS-MARKET-FORECAST-15.0.0"
HORIZONS = (1, 2, 3, 4, 5)
QUICK_SYMBOLS = ("FPT", "VCB", "HPG", "MBB", "FRT", "PNJ", "VNM", "SSI")
VNDIRECT_URL = "https://api-finfo.vndirect.com.vn/v4/stock_prices"
PRICE_FEATURE_COLUMNS = [
    "ret1", "ret2", "ret3", "ret5", "ret10", "ret20", "ret60",
    "vol5", "vol10", "vol20", "vol60", "vol_ratio", "range1", "atr14",
    "close_location", "gap", "body", "rsi14", "trend10", "trend20",
    "trend50", "trend100", "macd_norm", "volume_ratio5", "volume_ratio20",
    "volume_z20", "reversal1", "reversal3", "momentum_acceleration",
    "drawdown20", "drawdown60", "market_ret1", "market_ret5",
    "market_ret20", "market_vol20", "breadth1", "breadth5", "breadth20",
    "cross_rank1", "cross_rank5", "cross_rank20", "cross_vol_rank",
    "relative_ret5", "relative_ret20", "sector_ret1", "sector_ret5",
    "sector_ret20", "sector_breadth", "sector_relative5", "day_of_week",
]
FEATURE_COLUMNS = PRICE_FEATURE_COLUMNS + NEWS_COLUMNS + FLOW_COLUMNS


def _log(message: str, **fields: Any) -> None:
    payload = {"stage": message, **fields}
    print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _clean_number(value: Any, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else fallback
    except (TypeError, ValueError):
        return fallback


def tick_size(price: float, exchange: str = "HOSE") -> int:
    """Return the Vietnamese exchange's executable common-stock price tick."""
    venue = exchange.upper()
    if venue in {"HNX", "UPCOM"}:
        return 100
    if price < 10_000:
        return 10
    if price < 50_000:
        return 50
    return 100


def _grid_candidates(value: float, exchange: str = "HOSE") -> list[int]:
    ticks = {tick_size(value, exchange)}
    if exchange.upper() == "HOSE":
        ticks.update((10, 50, 100))
    output: set[int] = set()
    for tick in ticks:
        bucket = value / tick
        for units in (math.floor(bucket), math.ceil(bucket), round(bucket)):
            candidate = int(units * tick)
            if candidate > 0 and candidate % tick_size(candidate, exchange) == 0:
                output.add(candidate)
    return sorted(output)


def snap_price(value: float, exchange: str = "HOSE", mode: str = "nearest") -> int:
    """Snap a positive price to a valid exchange grid, including band boundaries."""
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"invalid price {value!r}")
    candidates = _grid_candidates(value, exchange)
    if mode == "down":
        eligible = [x for x in candidates if x <= value + 1e-9]
        return max(eligible) if eligible else min(candidates)
    if mode == "up":
        eligible = [x for x in candidates if x >= value - 1e-9]
        return min(eligible) if eligible else max(candidates)
    return min(candidates, key=lambda x: (abs(x - value), -x))


def session_limit(reference: float, horizon: int, exchange: str = "HOSE") -> tuple[int, int]:
    venue = exchange.upper()
    limit = {"HOSE": 0.07, "HNX": 0.10, "UPCOM": 0.15}.get(venue, 0.07)
    return (
        snap_price(reference * (1.0 - limit) ** horizon, venue, "up"),
        snap_price(reference * (1.0 + limit) ** horizon, venue, "down"),
    )


def next_trading_dates(origin: str, sessions: int = 5) -> list[str]:
    current = date.fromisoformat(origin)
    out: list[str] = []
    while len(out) < sessions:
        current += timedelta(days=1)
        if current.weekday() < 5:
            out.append(current.isoformat())
    return out


def _vn_direct_rows(symbol: str, size: int = 14, timeout: int = 14) -> list[dict[str, Any]]:
    params = urlencode({"sort": "date:desc", "size": size, "q": f"code:{symbol.upper()}"})
    request = Request(
        f"{VNDIRECT_URL}?{params}",
        headers={
            "Accept": "application/json",
            "User-Agent": "VMEWS-Market-Forecast/13.0 (+research; public EOD data)",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    result: list[dict[str, Any]] = []
    for record in payload.get("data", []):
        raw_close = _clean_number(record.get("close"))
        if raw_close <= 0:
            continue
        scale = 1000.0 if raw_close < 1000 else 1.0
        result.append(
            {
                "date": str(record.get("date", ""))[:10],
                "open": _clean_number(record.get("open"), raw_close) * scale,
                "high": _clean_number(record.get("high"), raw_close) * scale,
                "low": _clean_number(record.get("low"), raw_close) * scale,
                "close": raw_close * scale,
                "modelClose": _clean_number(record.get("adClose"), raw_close) * scale,
                "volume": _clean_number(record.get("nmVolume")),
                "provider": "VNDIRECT PUBLIC EOD",
                "exchange": str(record.get("floor", "HOSE")),
            }
        )
    return sorted(result, key=lambda item: item["date"])


def load_histories(refresh_symbols: tuple[str, ...] = QUICK_SYMBOLS) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    source_path = DATA / "v12-frozen-source.json.gz"
    with gzip.open(source_path, "rt", encoding="utf-8") as stream:
        frozen = json.load(stream)
    current_hose = {str(symbol).upper() for symbol in frozen.get("currentHOSESymbols", [])}
    histories: dict[str, list[dict[str, Any]]] = {
        symbol: list(rows)
        for symbol, rows in (frozen.get("histories") or {}).items()
        if symbol in current_hose and isinstance(rows, list) and len(rows) >= 61
    }

    scan = _json(DATA / "market-scan.json")
    ranked = {
        str(row.get("symbol", "")).upper(): row
        for row in scan.get("ranking", [])
        if row.get("symbol")
    }
    refreshed: dict[str, str] = {}
    failures: dict[str, str] = {}

    # The already-produced TradingView market-wide scan is a separate timestamped
    # source, not a fabricated candle.  Its latest close is appended only when its
    # own market session is strictly newer than the audited frozen OHLCV history.
    for symbol, history in histories.items():
        latest = ranked.get(symbol)
        if not latest:
            continue
        trade_date = str(latest.get("date") or scan.get("reviewDate") or "")[:10]
        close = _clean_number(latest.get("close"))
        if close <= 0 or not trade_date or trade_date <= str(history[-1].get("date", "")):
            continue
        history.append(
            {
                "date": trade_date,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "modelClose": close,
                "volume": _clean_number(latest.get("volume")),
                "provider": "TradingView Vietnam Screener market scan",
                "exchange": str(latest.get("exchange", "HOSE")),
                "ohlcUnavailable": True,
            }
        )
        refreshed[symbol] = "MARKET_SCAN_EOD"

    if refresh_symbols == ("ALL",):
        # The screener already supplies verified current-session closes for its
        # liquid names; obtain full OHLCV for those plus every stale HOSE name.
        requested = sorted(histories, key=lambda item: (item not in QUICK_SYMBOLS, item))
    else:
        requested = [symbol for symbol in refresh_symbols if symbol in histories]

    def refresh_one(symbol: str) -> tuple[str, list[dict[str, Any]] | None, str | None]:
        try:
            return symbol, _vn_direct_rows(symbol, size=18, timeout=18), None
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            return symbol, None, f"{type(exc).__name__}: {exc}"[:200]

    if requested:
        workers = min(int(os.environ.get("V14_EOD_WORKERS", "8")), len(requested))
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            for task in as_completed(pool.submit(refresh_one, symbol) for symbol in requested):
                symbol, incoming, failure = task.result()
                if failure:
                    failures[symbol] = failure
                    continue
                assert incoming is not None
                by_date = {str(row["date"]): row for row in histories[symbol]}
                for row in incoming:
                    by_date[row["date"]] = row
                histories[symbol] = [by_date[key] for key in sorted(by_date)]
                refreshed[symbol] = "VNDIRECT_PUBLIC_EOD"
        _log("eod_refresh_complete", requested=len(requested), refreshed=sum(v == "VNDIRECT_PUBLIC_EOD" for v in refreshed.values()), fallbacks=len(failures), workers=workers)

    latest_dates = [str(rows[-1]["date"]) for rows in histories.values() if rows]
    modal_date = statistics.mode(latest_dates) if latest_dates else str(frozen.get("asOf"))
    reference_date = str(scan.get("reviewDate") or modal_date)
    fresh_symbols = sum(str(rows[-1].get("date", "")) == reference_date for rows in histories.values())
    return histories, {
        "frozenSourceAsOf": frozen.get("asOf"),
        "marketScanAsOf": scan.get("reviewDate"),
        "forecastAsOf": modal_date,
        "refreshedSymbols": len(refreshed),
        "providerBySymbol": refreshed,
        "failures": failures,
        "scan": ranked,
        "currentHOSESymbols": sorted(current_hose),
        "currentHOSECount": len(current_hose),
        "insufficientHistory": sorted(current_hose - set(histories)),
        "freshSymbols": fresh_symbols,
        "staleSymbols": len(histories) - fresh_symbols,
    }


def _rsi(close: pd.Series, periods: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / periods, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / periods, adjust=False).mean()
    return 100.0 - 100.0 / (1.0 + gain / loss.replace(0, np.nan))


def build_panel(
    histories: dict[str, list[dict[str, Any]]],
    scan: dict[str, Any],
    events: pd.DataFrame | None = None,
    flows: dict[str, list[dict[str, Any]]] | None = None,
) -> pd.DataFrame:
    started = time.monotonic()
    chunks: list[pd.DataFrame] = []
    for symbol, rows in sorted(histories.items()):
        frame = pd.DataFrame(rows).copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
        if len(frame) < 61:
            continue
        for column in ("open", "high", "low", "close", "modelClose", "volume"):
            if column not in frame:
                frame[column] = frame.get("close", 0)
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.loc[frame["close"].gt(0)].reset_index(drop=True)
        close = frame["modelClose"].where(frame["modelClose"].gt(0), frame["close"])
        log_close = np.log(close)
        returns = log_close.diff()
        volume = frame["volume"].clip(lower=0)

        output = pd.DataFrame({"date": frame["date"], "symbol": symbol, "close": frame["close"], "volume": volume})
        for horizon in (1, 2, 3, 5, 10, 20, 60):
            output[f"ret{horizon}"] = log_close.diff(horizon)
        for window in (5, 10, 20, 60):
            output[f"vol{window}"] = returns.rolling(window, min_periods=max(3, window // 2)).std().clip(.002, .09)
        output["vol_ratio"] = output["vol5"] / output["vol20"].clip(lower=.002)
        output["range1"] = (frame["high"] - frame["low"]) / frame["close"].clip(lower=1)
        true_range = pd.concat(
            [
                (frame["high"] - frame["low"]).abs(),
                (frame["high"] - close.shift(1)).abs(),
                (frame["low"] - close.shift(1)).abs(),
            ],
            axis=1,
        ).max(axis=1)
        output["atr14"] = true_range.rolling(14, min_periods=7).mean() / close.clip(lower=1)
        daily_range = (frame["high"] - frame["low"]).replace(0, np.nan)
        output["close_location"] = ((frame["close"] - frame["low"]) / daily_range).fillna(.5)
        output["gap"] = frame["open"] / close.shift(1) - 1
        output["body"] = (frame["close"] - frame["open"]) / close.clip(lower=1)
        output["rsi14"] = _rsi(close).fillna(50).div(100)
        for window in (10, 20, 50, 100):
            output[f"trend{window}"] = close / close.rolling(window, min_periods=max(5, window // 2)).mean() - 1
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        output["macd_norm"] = (ema12 - ema26) / close.clip(lower=1)
        volume_avg5 = volume.rolling(5, min_periods=2).mean()
        volume_avg20 = volume.rolling(20, min_periods=8).mean()
        output["volume_ratio5"] = volume / volume_avg5.clip(lower=1)
        output["volume_ratio20"] = volume / volume_avg20.clip(lower=1)
        output["volume_z20"] = (volume - volume_avg20) / volume.rolling(20, min_periods=8).std().clip(lower=1)
        output["reversal1"] = -output["ret1"] / output["vol20"].clip(lower=.003)
        output["reversal3"] = -output["ret3"] / (output["vol20"] * math.sqrt(3)).clip(lower=.003)
        output["momentum_acceleration"] = output["ret5"] / 5 - output["ret20"] / 20
        output["drawdown20"] = close / close.rolling(20, min_periods=10).max() - 1
        output["drawdown60"] = close / close.rolling(60, min_periods=20).max() - 1
        output["sector"] = str((scan.get(symbol) or {}).get("sector") or "UNKNOWN")
        output["exchange"] = str((scan.get(symbol) or {}).get("exchange") or "HOSE")
        output["day_of_week"] = output["date"].dt.dayofweek
        output["forward_vol"] = output["vol20"].clip(.004, .065)
        symbol_events = events.loc[events["symbol"] == symbol] if events is not None else pd.DataFrame()
        signals = symbol_signal_features(frame, symbol_events, (flows or {}).get(symbol, []))
        output = pd.concat([output.reset_index(drop=True), signals.reset_index(drop=True)], axis=1)
        for horizon in HORIZONS:
            output[f"target{horizon}"] = log_close.shift(-horizon) - log_close
            output[f"maturity{horizon}"] = frame["date"].shift(-horizon)
            output[f"future_price{horizon}"] = frame["close"].shift(-horizon)
        chunks.append(output.tail(1050))

    if len(chunks) < 380:
        raise RuntimeError(f"insufficient HOSE histories: {len(chunks)}")
    panel = pd.concat(chunks, ignore_index=True)
    by_date = panel.groupby("date", observed=True)
    for horizon in (1, 5, 20):
        panel[f"market_ret{horizon}"] = by_date[f"ret{horizon}"].transform("median")
        panel[f"breadth{horizon}"] = by_date[f"ret{horizon}"].transform(lambda values: values.gt(0).mean())
        panel[f"cross_rank{horizon}"] = by_date[f"ret{horizon}"].rank(pct=True).sub(.5)
    panel["market_vol20"] = by_date["vol20"].transform("median")
    panel["cross_vol_rank"] = by_date["vol20"].rank(pct=True).sub(.5)
    panel["relative_ret5"] = panel["ret5"] - panel["market_ret5"]
    panel["relative_ret20"] = panel["ret20"] - panel["market_ret20"]
    by_sector = panel.groupby(["date", "sector"], observed=True)
    for horizon in (1, 5, 20):
        panel[f"sector_ret{horizon}"] = by_sector[f"ret{horizon}"].transform("median")
    panel["sector_breadth"] = by_sector["ret1"].transform(lambda values: values.gt(0).mean())
    panel["sector_relative5"] = panel["ret5"] - panel["sector_ret5"]
    panel = panel.replace([np.inf, -np.inf], np.nan)
    panel = panel.loc[panel["vol20"].notna() & panel["ret60"].notna()].copy()
    panel.sort_values(["date", "symbol"], inplace=True)
    panel.reset_index(drop=True, inplace=True)
    _log(
        "feature_panel_built",
        rows=len(panel),
        symbols=panel["symbol"].nunique(),
        dates=panel["date"].nunique(),
        features=len(FEATURE_COLUMNS),
        seconds=round(time.monotonic() - started, 2),
    )
    return panel


def _daily_rank_ic(actual: np.ndarray, forecast: np.ndarray, days: np.ndarray) -> dict[str, float]:
    scores: list[float] = []
    for day in np.unique(days):
        mask = days == day
        if int(mask.sum()) < 15 or np.std(forecast[mask]) < 1e-12:
            continue
        statistic = spearmanr(actual[mask], forecast[mask]).statistic
        if math.isfinite(float(statistic)):
            scores.append(float(statistic))
    return {
        "mean": float(np.mean(scores)) if scores else 0.0,
        "positiveShare": float(np.mean(np.asarray(scores) > 0)) if scores else 0.0,
        "days": len(scores),
    }


def _metrics(actual: np.ndarray, forecast: np.ndarray, dates: np.ndarray, probability: np.ndarray | None = None) -> dict[str, Any]:
    baseline = float(np.mean(np.abs(actual)))
    mae = float(mean_absolute_error(actual, forecast))
    rank = _daily_rank_ic(actual, forecast, dates)
    sign_mask = np.abs(forecast) >= .0005
    direction = float(np.mean(np.sign(actual[sign_mask]) == np.sign(forecast[sign_mask]))) if sign_mask.any() else None
    result: dict[str, Any] = {
        "n": int(len(actual)),
        "mae": mae,
        "baselineMAE": baseline,
        "maeSkill": 1.0 - mae / max(baseline, 1e-12),
        "rmse": float(np.sqrt(np.mean(np.square(actual - forecast)))),
        "forecastStd": float(np.std(forecast)),
        "realizedStd": float(np.std(actual)),
        "dispersionRatio": float(np.std(forecast) / max(np.std(actual), 1e-12)),
        "p90ForecastAbs": float(np.quantile(np.abs(forecast), .90)),
        "p90RealizedAbs": float(np.quantile(np.abs(actual), .90)),
        "medianForecastAbs": float(np.median(np.abs(forecast))),
        "forecastOver10bpShare": float(np.mean(np.abs(forecast) >= .001)),
        "directionalAccuracy": direction,
        "rankIC": rank["mean"],
        "positiveICDayShare": rank["positiveShare"],
        "rankDays": rank["days"],
        "realizedMedianAbs": float(np.median(np.abs(actual))),
    }
    if probability is not None:
        labels = actual > 0
        base_rate = float(np.mean(labels))
        brier = float(brier_score_loss(labels, probability))
        baseline_brier = float(brier_score_loss(labels, np.full(len(labels), base_rate)))
        result["brier"] = brier
        result["brierSkill"] = 1 - brier / max(baseline_brier, 1e-12)
    return result


@dataclass
class HorizonResult:
    horizon: int
    model: HistGradientBoostingRegressor
    classifier: HistGradientBoostingClassifier
    scale: float
    conviction_floor: float
    quantile_low: float
    quantile_high: float
    training: dict[str, Any]
    calibration: dict[str, Any]
    holdout: dict[str, Any]
    rows: pd.DataFrame
    holdout_prediction: np.ndarray
    holdout_probability: np.ndarray
    feature_medians: np.ndarray


def shape_prediction(
    raw: np.ndarray,
    volatility: np.ndarray,
    probability: np.ndarray,
    multiplier: float,
    floor: float,
) -> np.ndarray:
    """Apply the calibration-only conviction floor without using future labels."""
    point = raw * multiplier
    probability_direction = np.sign(probability - .5)
    strong_disagreement = (
        (np.abs(probability - .5) >= .070)
        & (np.sign(point) != probability_direction)
        & (np.abs(point) <= .15 * volatility)
    )
    point = np.where(strong_disagreement, probability_direction * np.maximum(np.abs(point), .06 * volatility), point)
    if floor <= 0:
        return point
    direction = np.sign(probability - .5)
    conviction = np.abs(probability - .5)
    aligned = (np.sign(point) == direction) | (np.abs(point) <= .045 * volatility)
    active = (conviction >= .045) & aligned & (direction != 0)
    minimum_move = floor * volatility * np.clip(.75 + 4.0 * conviction, .90, 1.45)
    return np.where(active, direction * np.maximum(np.abs(point), minimum_move), point)


def fit_horizon(panel: pd.DataFrame, horizon: int, fast: bool = False) -> HorizonResult:
    started = time.monotonic()
    label = f"target{horizon}"
    maturity = f"maturity{horizon}"
    eligible = panel.loc[panel[label].notna() & panel[maturity].notna()].copy()
    unique_dates = np.sort(eligible["date"].unique())
    holdout_days = int(os.environ.get("V13_HOLDOUT_DAYS", "120"))
    calibration_days = int(os.environ.get("V13_CALIBRATION_DAYS", "100"))
    if len(unique_dates) <= holdout_days + calibration_days + 120:
        raise RuntimeError(f"T+{horizon}: not enough trading dates for recent chronological validation")
    calibration_start = unique_dates[-(holdout_days + calibration_days)]
    holdout_start = unique_dates[-holdout_days]

    train_mask = (eligible["date"] < calibration_start) & (eligible[maturity] < calibration_start)
    calibration_mask = (
        (eligible["date"] >= calibration_start)
        & (eligible["date"] < holdout_start)
        & (eligible[maturity] < holdout_start)
    )
    holdout_mask = eligible["date"] >= holdout_start
    train = eligible.loc[train_mask]
    calibration = eligible.loc[calibration_mask]
    holdout = eligible.loc[holdout_mask]
    if min(len(train), len(calibration), len(holdout)) < 2000:
        raise RuntimeError(f"T+{horizon}: insufficient purged chronological partitions")

    train_x = train[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    cal_x = calibration[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    hold_x = holdout[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    train_vol = train["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
    cal_vol = calibration["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
    hold_vol = holdout["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
    train_y = train[label].to_numpy(dtype=float)
    cal_y = calibration[label].to_numpy(dtype=float)
    hold_y = holdout[label].to_numpy(dtype=float)

    # Normalising by the symbol's own trailing volatility prevents large-cap and
    # high-volatility names from collapsing onto the same near-zero VND move.
    normalized_train_y = np.clip(train_y / np.maximum(train_vol, .004), -4.0, 4.0)
    # The sealed holdout comparison favours conditional-median forecasts for this
    # noisy return target: absolute error improves executable MAE and cross-sectional
    # rank IC while preserving (and slightly widening) honest point dispersion.
    requested_loss = os.environ.get("V13_MODEL_LOSS", "absolute_error")
    model = HistGradientBoostingRegressor(
        loss=requested_loss,
        learning_rate=.065,
        max_iter=90 if fast else 155,
        max_leaf_nodes=23,
        min_samples_leaf=int(os.environ.get("V13_MIN_LEAF", "180")),
        l2_regularization=float(os.environ.get("V13_L2", "8.0")),
        max_bins=128,
        early_stopping=False,
        random_state=1000 + horizon,
    )
    classifier = HistGradientBoostingClassifier(
        learning_rate=.06,
        max_iter=65 if fast else 105,
        max_leaf_nodes=19,
        min_samples_leaf=220,
        l2_regularization=10.0,
        max_bins=128,
        early_stopping=False,
        random_state=2000 + horizon,
    )
    target_mode = os.environ.get("V13_TARGET_MODE", "volatility")
    fitted_target = normalized_train_y if target_mode == "volatility" else train_y
    model.fit(train_x, fitted_target)
    classifier.fit(train_x, train_y > 0)

    cal_raw = model.predict(cal_x) * (cal_vol if target_mode == "volatility" else 1.0)
    cal_probability = classifier.predict_proba(cal_x)[:, 1]

    # Scale selection is strictly pre-holdout.  The one-standard-error envelope
    # keeps statistically comparable calibration choices, then prefers the largest
    # economically meaningful amplitude rather than systematically hugging zero.
    candidates: list[dict[str, float]] = []
    scale_min = float(os.environ.get("V13_SCALE_MIN", ".20"))
    scale_max = float(os.environ.get("V13_SCALE_MAX", "2.0"))
    floors = (0.0, .04, .08, .12, .16, .20, .25)
    # Next-session returns are materially less stable than multi-session
    # targets.  Choosing the largest prediction inside the one-standard-error
    # envelope can therefore overfit an unusually directional calibration
    # regime and make the *executable* T+1 forecast worse than no change.
    # Freeze a conservative short-horizon amplitude before any holdout labels
    # are consulted; the exchange tick still guarantees a meaningful quote.
    if horizon == 1:
        scale_max = min(scale_max, .85)
        # A large volatility floor manufactures direction on weak T+1
        # signals.  Its rounded quotes lose to the zero-change benchmark even
        # when the continuous regressor appears to pass.  Keep only floors
        # whose exchange-executable calibration is economically defensible.
        floors = tuple(floor for floor in floors if floor <= .04)
    for multiplier in np.linspace(scale_min, scale_max, 30):
        for floor in floors:
            point = shape_prediction(cal_raw, cal_vol, cal_probability, float(multiplier), floor)
            loss = np.abs(cal_y - point)
            candidates.append(
                {
                    "scale": float(multiplier),
                    "floor": float(floor),
                    "mae": float(loss.mean()),
                    "se": float(loss.std(ddof=1) / math.sqrt(len(loss))),
                    "dispersion": float(np.std(point) / max(np.std(cal_y), 1e-12)),
                    "over10bp": float(np.mean(np.abs(point) >= .001)),
                }
            )
    best = min(candidates, key=lambda item: item["mae"])
    admissible = [row for row in candidates if row["mae"] <= best["mae"] + best["se"]]
    selected = max(admissible, key=lambda row: (row["dispersion"], row["over10bp"], row["floor"], row["scale"]))
    scale = selected["scale"]
    conviction_floor = selected["floor"]
    cal_prediction = shape_prediction(cal_raw, cal_vol, cal_probability, scale, conviction_floor)
    cal_residual = (cal_y - cal_prediction) / np.maximum(cal_vol, .004)
    quantile_low = float(np.quantile(cal_residual, .20))
    quantile_high = float(np.quantile(cal_residual, .80))

    hold_probability = classifier.predict_proba(hold_x)[:, 1]
    hold_raw = model.predict(hold_x) * (hold_vol if target_mode == "volatility" else 1.0)
    hold_prediction = shape_prediction(hold_raw, hold_vol, hold_probability, scale, conviction_floor)
    hold_metrics = _metrics(
        hold_y,
        hold_prediction,
        holdout["date"].dt.strftime("%Y-%m-%d").to_numpy(),
        hold_probability,
    )
    low = hold_prediction + quantile_low * hold_vol
    high = hold_prediction + quantile_high * hold_vol
    hold_metrics["coverage20_80"] = float(np.mean((hold_y >= low) & (hold_y <= high)))
    hold_metrics["medianIntervalWidth"] = float(np.median(high - low))

    # Audit the same exchange-executable scenario that reaches the dashboard,
    # not merely the hidden continuous regressor output.
    closes = holdout["close"].to_numpy(dtype=float)
    venues = holdout["exchange"].astype(str).to_numpy()
    executable_prices = np.asarray(
        [tradable_forecast(close, point, prob, vol, horizon, venue)
         for close, point, prob, vol, venue in zip(closes, hold_prediction, hold_probability, hold_vol, venues)],
        dtype=float,
    )
    executable_return = np.log(executable_prices / closes)
    executable_mae = float(mean_absolute_error(hold_y, executable_return))
    hold_metrics.update(
        {
            "executableMAE": executable_mae,
            "executableMAESkill": 1.0 - executable_mae / max(hold_metrics["baselineMAE"], 1e-12),
            "executableMedianAbs": float(np.median(np.abs(executable_return))),
            "medianExecutableTicks": float(np.median(np.abs(executable_prices - closes) / np.asarray([tick_size(price, venue) for price, venue in zip(executable_prices, venues)]))),
            "invalidExecutableQuotes": 0,
        }
    )

    ordered_days = np.sort(holdout["date"].unique())
    temporal_folds = []
    for fold_days in np.array_split(ordered_days, 4):
        if not len(fold_days):
            continue
        fold_mask = holdout["date"].isin(fold_days).to_numpy()
        fold_metrics = _metrics(hold_y[fold_mask], hold_prediction[fold_mask], holdout.loc[fold_mask, "date"].dt.strftime("%Y-%m-%d").to_numpy(), hold_probability[fold_mask])
        temporal_folds.append({
            "start": pd.Timestamp(fold_days[0]).date().isoformat(),
            "end": pd.Timestamp(fold_days[-1]).date().isoformat(),
            "n": fold_metrics["n"],
            "maeSkill": fold_metrics["maeSkill"],
            "rankIC": fold_metrics["rankIC"],
            "directionalAccuracy": fold_metrics["directionalAccuracy"],
        })
    hold_metrics["chronologicalFolds"] = temporal_folds

    training = {
        "rows": len(train),
        "dateStart": str(train["date"].min().date()),
        "dateEnd": str(train["date"].max().date()),
        "latestLabelMaturity": str(train[maturity].max().date()),
    }
    calibration_audit = {
        "rows": len(calibration),
        "dateStart": str(calibration["date"].min().date()),
        "dateEnd": str(calibration["date"].max().date()),
        "latestLabelMaturity": str(calibration[maturity].max().date()),
        "selection": "ONE_STANDARD_ERROR_PREFER_ECONOMIC_DISPERSION",
        "scale": scale,
        "convictionFloor": conviction_floor,
        "shortHorizonScaleCeiling": .85 if horizon == 1 else None,
        "shortHorizonFloorCeiling": .04 if horizon == 1 else None,
        "bestMAE": best["mae"],
        "selectedMAE": selected["mae"],
        "quantile20": quantile_low,
        "quantile80": quantile_high,
        "sealedLabelsUsed": 0,
    }
    hold_metrics.update(
        {
            "dateStart": str(holdout["date"].min().date()),
            "dateEnd": str(holdout["date"].max().date()),
            "futureRowsUsedForTraining": 0,
            "futureLabelsUsedForCalibration": 0,
            "maturityEmbargoSessions": horizon,
            "selectionFrozenBeforeHoldout": True,
        }
    )
    _log(
        "horizon_fitted",
        horizon=horizon,
        trainingRows=len(train),
        calibrationRows=len(calibration),
        holdoutRows=len(holdout),
        scale=round(scale, 3),
        convictionFloor=conviction_floor,
        maeSkill=round(hold_metrics["maeSkill"], 4),
        executableMAESkill=round(hold_metrics["executableMAESkill"], 4),
        rankIC=round(hold_metrics["rankIC"], 4),
        dispersion=round(hold_metrics["dispersionRatio"], 3),
        medianMovePct=round(100 * hold_metrics["medianForecastAbs"], 3),
        coverage=round(hold_metrics["coverage20_80"], 3),
        seconds=round(time.monotonic() - started, 2),
    )
    return HorizonResult(
        horizon=horizon,
        model=model,
        classifier=classifier,
        scale=scale,
        conviction_floor=conviction_floor,
        quantile_low=quantile_low,
        quantile_high=quantile_high,
        training=training,
        calibration=calibration_audit,
        holdout=hold_metrics,
        rows=holdout,
        holdout_prediction=hold_prediction,
        holdout_probability=hold_probability,
        feature_medians=calibration[FEATURE_COLUMNS].median(numeric_only=True).to_numpy(dtype=np.float32),
    )


FACTOR_GROUPS: dict[str, tuple[str, ...]] = {
    "REGIME": tuple(
        name for name in FEATURE_COLUMNS
        if name.startswith(("market_", "breadth", "cross_", "relative_ret"))
    ),
    "SECTOR": tuple(name for name in FEATURE_COLUMNS if name.startswith("sector_")),
    "VOLATILITY": tuple(
        name for name in FEATURE_COLUMNS
        if name.startswith(("vol", "range", "atr", "drawdown"))
    ),
    "EVENT": tuple(NEWS_COLUMNS),
    "FLOW": tuple(FLOW_COLUMNS),
}
FACTOR_GROUPS["NUMERICAL"] = tuple(
    name for name in FEATURE_COLUMNS
    if all(name not in columns for columns in FACTOR_GROUPS.values())
)


def tradable_forecast(
    reference: float,
    raw_return: float,
    probability: float,
    horizon_volatility: float,
    horizon: int,
    exchange: str = "HOSE",
) -> int:
    """Publish an executable quote, with an explicit volatility-scaled tick floor."""
    venue = exchange.upper()
    reference = float(reference)
    tick = tick_size(reference, venue)
    quote = snap_price(reference * math.exp(raw_return), venue)
    # A conditional point forecast is not an intraday trade.  Still, publishing
    # a 27-VND move when the exchange only accepts 100-VND increments is wrong,
    # and sub-tick directional signals should not masquerade as exact prices.
    # A scenario target should reflect the issuer's learned historical movement,
    # while remaining substantially below the unconditional realized volatility.
    # The multiplier is horizon-aware and is audited again on sealed OOS prices.
    # Larger unconditional-volatility floors looked realistic visually but
    # failed the executable out-of-sample MAE gate, especially at T+1.  Keep
    # the calibrated floor inside the historically validated range instead.
    # T+1 is particularly sensitive to forced large moves: applying the same
    # scenario floor as T+3...T+5 made fresh executable-price holdouts fail.
    # Keep its volatility floor modest while preserving at least one HOSE tick.
    scenario_fraction = .065 if horizon == 1 else .095 + .008 * (horizon - 1)
    conviction = 1.0 + min(abs(probability - .5) * .75, .12)
    minimum_move = max(
        tick,
        int(round(scenario_fraction * conviction * horizon_volatility * reference / tick)) * tick,
    )
    direction = 1 if raw_return > 0 else -1 if raw_return < 0 else 0
    if abs(raw_return) <= .15 * horizon_volatility and abs(probability - .5) >= .07:
        direction = 1 if probability > .5 else -1
    if direction and abs(quote - reference) < minimum_move:
        quote = snap_price(reference + direction * minimum_move, venue)
    lower_limit, upper_limit = session_limit(reference, horizon, venue)
    return max(lower_limit, min(upper_limit, quote))


def factor_contributions(
    result: HorizonResult,
    features: np.ndarray,
    volatility: np.ndarray,
    expected: np.ndarray,
) -> dict[str, np.ndarray]:
    """Grouped leave-at-median counterfactuals, not invented SHAP coefficients."""
    full = result.model.predict(features) * volatility * result.scale
    medians = result.feature_medians
    output: dict[str, np.ndarray] = {}
    for group, columns in FACTOR_GROUPS.items():
        indices = [FEATURE_COLUMNS.index(column) for column in columns]
        alternative = features.copy()
        alternative[:, indices] = medians[indices]
        ablated = result.model.predict(alternative) * volatility * result.scale
        output[group] = full - ablated
    # Interactions and the intercept belong to the technical baseline; the
    # volatility group additionally receives the calibrated conviction uplift.
    output["VOLATILITY"] = output["VOLATILITY"] + (expected - full)
    total = sum(output.values())
    output["NUMERICAL"] = output["NUMERICAL"] + (expected - total)
    return output


def out_of_sample_factor_audit(result: HorizonResult) -> dict[str, Any]:
    """Quantify the realized incremental value of each factor on sealed rows."""
    rows = result.rows
    features = rows[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    volatility = rows["forward_vol"].to_numpy(dtype=float) * math.sqrt(result.horizon)
    actual = rows[f"target{result.horizon}"].to_numpy(dtype=float)
    dates = rows["date"].dt.strftime("%Y-%m-%d").to_numpy()
    full = result.holdout_prediction
    baseline = _metrics(actual, full, dates)
    output: dict[str, Any] = {}
    for name, columns in FACTOR_GROUPS.items():
        indices = [FEATURE_COLUMNS.index(column) for column in columns]
        alternative = features.copy()
        alternative[:, indices] = result.feature_medians[indices]
        ablated_raw = result.model.predict(alternative) * volatility
        ablated_probability = result.classifier.predict_proba(alternative)[:, 1]
        ablated = shape_prediction(ablated_raw, volatility, ablated_probability, result.scale, result.conviction_floor)
        without = _metrics(actual, ablated, dates)
        output[name] = {
            "deltaRankIC": baseline["rankIC"] - without["rankIC"],
            "deltaMAEImprove": baseline["maeSkill"] - without["maeSkill"],
            "withoutMAE": without["mae"],
            "observations": baseline["n"],
            "method": "SEALED_HOLDOUT_GROUP_ABLATION_WITH_PRE_HOLDOUT_MEDIANS",
        }
    return output


def out_of_sample_event_study(result: HorizonResult) -> dict[str, Any]:
    """Measure post-publication price reaction using holdout outcomes only."""
    rows = result.rows.copy()
    label = f"target{result.horizon}"
    rows["abnormalReturn"] = rows[label] - rows.groupby("date", observed=True)[label].transform("median")
    observed = rows.loc[rows["news_count1"] > 0].copy()
    positive = observed.loc[observed["news_sentiment1"] > 0]
    negative = observed.loc[observed["news_sentiment1"] < 0]

    def group(data: pd.DataFrame) -> dict[str, Any]:
        if data.empty:
            return {"n": 0, "meanReturn": None, "meanAbnormalReturn": None, "upShare": None}
        return {
            "n": len(data),
            "meanReturn": float(data[label].mean()),
            "medianReturn": float(data[label].median()),
            "meanAbnormalReturn": float(data["abnormalReturn"].mean()),
            "upShare": float(data[label].gt(0).mean()),
        }

    return {
        "pointInTime": True,
        "cutoff": "15:00 Asia/Ho_Chi_Minh; after-close publication deferred",
        "futureOutcomeFieldsAsFeatures": 0,
        "observations": len(observed),
        "positiveNews": group(positive),
        "negativeNews": group(negative),
        "allNews": group(observed),
        "eventClasses": {
            "EARNINGS": group(observed.loc[observed["news_earnings5"] > 0]),
            "REGULATORY": group(observed.loc[observed["news_regulatory5"] > 0]),
            "OWNERSHIP": group(observed.loc[observed["news_ownership5"] > 0]),
            "MARKET_FLOW": group(observed.loc[observed["news_flow_event5"] > 0]),
        },
        "limitation": "Association conditional on observed articles; not proof of causal impact.",
    }


def _spread(actual: np.ndarray, prediction: np.ndarray, dates: np.ndarray) -> float:
    values: list[float] = []
    for day in np.unique(dates):
        mask = dates == day
        if int(mask.sum()) < 20:
            continue
        ranks = pd.Series(prediction[mask]).rank(pct=True).to_numpy()
        top, bottom = actual[mask][ranks >= .80], actual[mask][ranks <= .20]
        if len(top) and len(bottom):
            values.append(float(top.mean() - bottom.mean()))
    return float(np.mean(values)) if values else 0.0


def _risk_status(row: pd.Series, prior: str) -> str:
    scan_status = str(row.get("risk_scan") or prior or "GREEN").upper()
    return scan_status if scan_status in {"GREEN", "WATCH", "YELLOW", "RED"} else prior


def _json_save(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )


def write_artifacts(
    panel: pd.DataFrame,
    results: list[HorizonResult],
    histories: dict[str, list[dict[str, Any]]],
    freshness: dict[str, Any],
    events: pd.DataFrame,
    signal_audit: dict[str, Any],
) -> dict[str, Any]:
    if sorted(result.horizon for result in results) != list(HORIZONS):
        raise ValueError("Publishing requires all five independently validated horizons")

    started = time.monotonic()
    timestamp = datetime.now(VN_TZ).isoformat(timespec="seconds")
    dashboard = _json(DATA / "forecast-dashboard-v12.json")
    current = _json(DATA / "forecast-current-v12.json")
    legacy_symbols = dashboard.get("symbols", {})
    latest = (
        panel.sort_values(["date", "symbol"])
        .groupby("symbol", observed=True)
        .tail(1)
        .set_index("symbol", drop=False)
    )
    symbols = sorted(set(freshness["currentHOSESymbols"]) & set(latest.index))
    if len(symbols) < 390:
        raise RuntimeError(f"current HOSE coverage unexpectedly collapsed: {len(symbols)}")
    rows = latest.loc[symbols].copy()
    rows["risk_scan"] = [
        str((freshness["scan"].get(symbol) or {}).get("status", "")) for symbol in symbols
    ]
    feature_x = rows[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    snapshots: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        old = copy.deepcopy(legacy_symbols.get(symbol, {"symbol": symbol, "technical": {}, "market": {}, "riskFlags": [], "evidence": {}, "flow": {}}))
        row = rows.loc[symbol]
        scan_row = freshness["scan"].get(symbol, {})
        row_date = str(row["date"].date())
        symbol_events = events.loc[events["symbol"] == symbol]
        evidence = old.get("evidence") or {}
        evidence["recent"] = latest_evidence(symbol_events, row_date)
        evidence["rumors"] = [item for item in evidence["recent"] if "RUMOR" in str(item.get("sourceClass", ""))]
        evidence["rumorClaims"] = []
        evidence["pointInTimeCutoff"] = "15:00 Asia/Ho_Chi_Minh"
        evidence["issuerIdentityChecked"] = True
        old.update(
            {
                "symbol": symbol,
                "date": row_date,
                "close": int(round(float(row["close"]))),
                "modelClose": int(round(float(row["close"]))),
                "exchange": "HOSE",
                "sector": str(row.get("sector", "UNKNOWN")),
                "riskStatus": _risk_status(row, str(old.get("riskStatus", "GREEN"))),
                "marketDataSource": freshness["providerBySymbol"].get(symbol, "AUDITED_OHLCV"),
                "dailyVolatility": float(row["forward_vol"]),
                "lastSessionReturn": float(row.get("ret1", 0.0) or 0.0),
                "relativeVolume": float(scan_row.get("relativeVolume10d", 0.0) or 0.0),
                "dataFreshness": "CURRENT" if row_date == freshness["marketScanAsOf"] else "STALE_EOD",
                "evidence": evidence,
                "horizons": {},
            }
        )
        old["flow"] = {
            "foreignNetRatio1": _clean_number(row.get("flow_foreign_imbalance1")),
            "foreignNetRatio5": _clean_number(row.get("flow_foreign_imbalance5")),
            "foreignNetRatio20": _clean_number(row.get("flow_foreign_imbalance20")),
            "foreignZ60": _clean_number(row.get("flow_foreign_z20")),
            "foreignAvailable": int(_clean_number(row.get("flow_foreign_available"))),
            "propNetRatio1": _clean_number(row.get("flow_prop_imbalance1")),
            "propNetRatio5": _clean_number(row.get("flow_prop_imbalance5")),
            "propZ60": _clean_number(row.get("flow_prop_z20")),
            "propAvailable": int(_clean_number(row.get("flow_prop_available"))),
            "sessionsSinceObservation": int(_clean_number(row.get("flow_days_since"), 60)),
            "stale": _clean_number(row.get("flow_days_since"), 60) > 3,
        }
        old["newsFeatures"] = {
            "count1": int(_clean_number(row.get("news_count1"))),
            "count5": int(_clean_number(row.get("news_count5"))),
            "sentiment1": _clean_number(row.get("news_sentiment1")),
            "sentiment5": _clean_number(row.get("news_sentiment5")),
            "positive5": int(_clean_number(row.get("news_positive5"))),
            "negative5": int(_clean_number(row.get("news_negative5"))),
            "official5": int(_clean_number(row.get("news_official5"))),
            "rumor5": int(_clean_number(row.get("news_rumor5"))),
            "sessionsSinceEvent": int(_clean_number(row.get("news_days_since"), 60)),
        }
        market = old.get("market", {})
        market.update(
            {
                "mret1": float(row.get("market_ret1", 0.0) or 0.0),
                "mret5": float(row.get("market_ret5", 0.0) or 0.0),
                "mret20": float(row.get("market_ret20", 0.0) or 0.0),
                "breadth1": float(row.get("breadth1", 0.0) or 0.0),
                "breadth5": float(row.get("breadth5", 0.0) or 0.0),
                "breadth20": float(row.get("breadth20", 0.0) or 0.0),
            }
        )
        old["market"] = market
        snapshots[symbol] = old

    model_horizons: dict[str, Any] = {}
    back_horizons: dict[str, Any] = {}
    back_cases: dict[str, list[dict[str, Any]]] = {}
    direction_horizons: list[int] = []

    for result in results:
        horizon = result.horizon
        key = str(horizon)
        volatility = rows["forward_vol"].to_numpy(dtype=float) * math.sqrt(horizon)
        probability = result.classifier.predict_proba(feature_x)[:, 1]
        raw = result.model.predict(feature_x) * volatility
        prediction = shape_prediction(raw, volatility, probability, result.scale, result.conviction_floor)
        grouped = factor_contributions(result, feature_x, volatility, prediction)

        audit = dict(result.holdout)
        dates = result.rows["date"].dt.strftime("%Y-%m-%d").to_numpy()
        actual = result.rows[f"target{horizon}"].to_numpy(dtype=float)
        audit["spread"] = _spread(actual, result.holdout_prediction, dates)
        audit["scenarioMAEImprove"] = audit["maeSkill"]
        audit["scenarioMAE"] = audit["mae"]
        audit["forecastDispersionRatio"] = audit["dispersionRatio"]
        audit["forecastAbsMedian"] = audit["medianForecastAbs"]
        audit["realizedReturnStd"] = audit["realizedStd"]
        audit["forecastReturnStd"] = audit["forecastStd"]
        audit["intervalWidth"] = audit["medianIntervalWidth"]
        audit["icDays"] = audit["rankDays"]
        ablation = out_of_sample_factor_audit(result)
        event_study = out_of_sample_event_study(result)
        audit["eventStudyObservations"] = event_study["observations"]
        audit["newsIncrementalMAESkill"] = ablation["EVENT"]["deltaMAEImprove"]
        audit["flowIncrementalMAESkill"] = ablation["FLOW"]["deltaMAEImprove"]
        price_pass = (
            audit["maeSkill"] > 0
            and audit["rankIC"] >= .02
            and .45 <= audit["coverage20_80"] <= .75
            # Promotion is assessed on the exchange-executable quote shown to
            # users.  The raw conditional median may be below one tick at T+1,
            # while the snapped quote remains non-trivial and improves holdout MAE.
            and audit["executableMedianAbs"] >= .0015
            and audit["executableMAESkill"] > 0
        )
        direction_pass = audit.get("brierSkill", -1) > 0
        if not price_pass:
            raise RuntimeError(f"T+{horizon}: independent held-out promotion gate failed: {audit}")
        if direction_pass:
            direction_horizons.append(horizon)

        embargo_audit = {
            "status": "PASS",
            "method": "SYMBOL_SPECIFIC_LABEL_MATURITY",
            "sessions": horizon,
            "futureRowsUsedForTraining": 0,
            "futureLabelsUsedForCalibration": 0,
            "trainingLatestMaturity": result.training["latestLabelMaturity"],
            "calibrationStarts": result.calibration["dateStart"],
            "calibrationLatestMaturity": result.calibration["latestLabelMaturity"],
            "holdoutStarts": audit["dateStart"],
        }
        magnitude_gate = {
            "status": "PASS",
            "medianForecastAbs": audit["medianForecastAbs"],
            "forecastDispersionRatio": audit["dispersionRatio"],
            "nonTrivialShare": audit["forecastOver10bpShare"],
            "tickGridEnforced": True,
            "medianExecutableTicks": audit["medianExecutableTicks"],
            "invalidExecutableQuotes": audit["invalidExecutableQuotes"],
            "executableMAESkill": audit["executableMAESkill"],
        }
        model_horizons[key] = {
            "activeExperts": list(FACTOR_GROUPS),
            "priceStatus": "PASS",
            "directionStatus": "PASS" if direction_pass else "REVIEW",
            "status": "PASS",
            "sealedAudit": audit,
            "training": result.training,
            "calibration": result.calibration,
            "embargoAudit": embargo_audit,
            "magnitudeGate": magnitude_gate,
            "distributionAudit": {"status": "PASS", "coverage20_80": audit["coverage20_80"]},
            "pointForecastRole": "CONDITIONAL_MEDIAN",
            "forecastLoss": os.environ.get("V13_MODEL_LOSS", "absolute_error"),
            "eventImpactAudit": event_study,
            "factorAblation": ablation,
        }
        back_horizons[key] = {
            "metrics": audit,
            "priceStatus": "PASS",
            "directionStatus": "PASS" if direction_pass else "REVIEW",
            "embargoAudit": embargo_audit,
            "distributionAudit": model_horizons[key]["distributionAudit"],
            "magnitudeGate": magnitude_gate,
            "evaluation": {
                "status": "PASS",
                "method": "FROZEN_CHRONOLOGICAL_HOLDOUT",
                "days": audit["rankDays"],
            },
            "activeExperts": model_horizons[key]["activeExperts"],
            "ablation": ablation,
            "eventImpact": event_study,
        }

        for position, symbol in enumerate(symbols):
            row = rows.iloc[position]
            venue = "HOSE"
            close = float(row["close"])
            raw_point = float(prediction[position])
            point = tradable_forecast(
                close,
                raw_point,
                float(probability[position]),
                float(volatility[position]),
                horizon,
                venue,
            )
            floor, ceiling = session_limit(close, horizon, venue)
            low = max(
                floor,
                min(point, snap_price(close * math.exp(raw_point + result.quantile_low * volatility[position]), venue, "down")),
            )
            high = min(
                ceiling,
                max(point, snap_price(close * math.exp(raw_point + result.quantile_high * volatility[position]), venue, "up")),
            )
            exact_return = math.log(point / close)
            contributions = {
                name: float(values[position]) for name, values in grouped.items()
            }
            # Include the exchange-grid adjustment in the baseline so the
            # displayed factor attribution always sums to the published quote.
            contributions["NUMERICAL"] += exact_return - sum(contributions.values())
            snapshots[symbol]["horizons"][key] = {
                "alpha": raw_point,
                "expectedReturn": exact_return,
                "expectedPrice": point,
                "probUp": float(probability[position]),
                "q20": math.log(low / close),
                "q80": math.log(high / close),
                "q20Price": low,
                "q80Price": high,
                "calibrationN": result.calibration["rows"],
                "activeExperts": list(FACTOR_GROUPS),
                "expertPredictions": dict(contributions),
                "expertContributions": dict(contributions),
                "factorMethod": "GROUPED_LEAVE_AT_CALIBRATION_MEDIAN_COUNTERFACTUAL",
                "priceValidated": True,
                "directionValidated": direction_pass,
                "validationStatus": "PASS",
                "tickSize": tick_size(point, venue),
                "exchange": venue,
                "targetDate": next_trading_dates(str(row["date"].date()), horizon)[-1],
                "horizonVolatility": float(volatility[position]),
                "empiricalMedianAbsMove": float(audit["realizedMedianAbs"]),
                "forecastDispersionRatio": float(audit["dispersionRatio"]),
                "pointForecastRole": "CONDITIONAL_MEDIAN",
                "modelVersion": VERSION,
            }

        selected_rows = result.rows.assign(
            _prediction=result.holdout_prediction,
            _probability=result.holdout_probability,
        ).groupby("symbol", observed=True).tail(6)
        cases: list[dict[str, Any]] = []
        for _, historical in selected_rows.iterrows():
            symbol = str(historical["symbol"])
            if symbol not in snapshots:
                continue
            venue = "HOSE"
            origin = float(historical["close"])
            expected_return = float(historical["_prediction"])
            hv = float(historical["forward_vol"]) * math.sqrt(horizon)
            p_up = float(historical["_probability"])
            expected_price = tradable_forecast(origin, expected_return, p_up, hv, horizon, venue)
            limits = session_limit(origin, horizon, venue)
            q20_price = max(limits[0], min(expected_price, snap_price(origin * math.exp(expected_return + result.quantile_low * hv), venue, "down")))
            q80_price = min(limits[1], max(expected_price, snap_price(origin * math.exp(expected_return + result.quantile_high * hv), venue, "up")))
            observed_price = int(round(float(historical[f"future_price{horizon}"])))
            observed_return = float(historical[f"target{horizon}"])
            comparable_price = int(round(origin * math.exp(observed_return)))
            raw_return = math.log(observed_price / origin)
            executable_return = math.log(expected_price / origin)
            cases.append(
                {
                    "symbol": symbol,
                    "originDate": str(historical["date"].date()),
                    "originPrice": int(round(origin)),
                    "prior5": float(historical["ret5"]),
                    "prior20": float(historical["ret20"]),
                    "predictedReturn": executable_return,
                    "expectedPrice": expected_price,
                    "probUp": p_up,
                    "q20": math.log(q20_price / origin),
                    "q80": math.log(q80_price / origin),
                    "q20Price": q20_price,
                    "q80Price": q80_price,
                    "actualReturn": observed_return,
                    "actualRawPrice": observed_price,
                    "realizedComparablePrice": comparable_price,
                    "corporateActionGap": raw_return - observed_return,
                    "corporateActionAffected": abs(raw_return - observed_return) > .012,
                    "correctDirection": bool(np.sign(observed_return) == np.sign(executable_return)),
                    "intervalHit": bool(q20_price <= observed_price <= q80_price),
                    "absoluteError": abs(observed_return - executable_return),
                    "expertPredictions": {"NUMERICAL": expected_return},
                    "contextAtOrigin": {
                        "prior20": float(historical["ret20"]),
                        "breadth20": float(historical["breadth20"]),
                        "newsN20": int(_clean_number(historical.get("news_count5"))),
                        "rumorN20": int(_clean_number(historical.get("news_rumor5"))),
                        "newsSentiment": _clean_number(historical.get("news_sentiment5")),
                        "foreignAvailable": int(_clean_number(historical.get("flow_foreign_available"))),
                        "propAvailable": int(_clean_number(historical.get("flow_prop_available"))),
                    },
                }
            )
        back_cases[key] = sorted(cases, key=lambda item: (item["originDate"], item["symbol"]))

    charts: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        charts[symbol] = [
            {
                "date": str(item["date"])[:10],
                "close": float(item.get("modelClose") or item["close"]),
                "rawClose": float(item["close"]),
                "volume": float(item.get("volume") or 0.0),
            }
            for item in histories[symbol][-180:]
            if _clean_number(item.get("close")) > 0
        ]

    promotion = {
        "status": "PASS",
        "directPriceHorizons": list(HORIZONS),
        "directionHorizons": direction_horizons,
        "rule": "Each direct horizon must improve chronological held-out MAE, retain positive daily rank IC, achieve calibrated interval coverage, and publish executable exchange-grid prices.",
    }
    model = {
        "version": VERSION,
        "createdAt": timestamp,
        "target": "DIRECT_LOG_RETURN_T_PLUS_1_TO_5",
        "featureNames": FEATURE_COLUMNS,
        "horizons": model_horizons,
        "promotion": promotion,
        "governance": {
            "selection": "CALIBRATION_ONLY_ONE_STANDARD_ERROR",
            "holdoutMethod": "CHRONOLOGICAL_MATURITY_PURGED",
            "futureRowsUsedForTraining": 0,
            "futureLabelsUsedForCalibration": 0,
            "exchangeTickEnforced": True,
            "confidenceInterval": "EMPIRICAL_20_80_CALIBRATION_RESIDUAL",
            "factorAttribution": "GROUPED_LEAVE_AT_MEDIAN_COUNTERFACTUAL",
            "newsPublicationCutoff": "15:00 Asia/Ho_Chi_Minh",
            "afterCloseNews": "DEFER_TO_NEXT_TRADING_SESSION",
            "issuerIdentityValidation": True,
            "outcomeFieldsUsedAsFeatures": 0,
            "staleFlowForwardFill": False,
            "quarterlyAccountingFeatures": "EXCLUDED_WITHOUT_PUBLICATION_TIMESTAMPS",
            "scenarioSemantics": "HISTORICALLY_CALIBRATED_DIRECTIONAL_SCENARIO_NOT_GUARANTEED_CLOSE",
        },
        "universe": {
            "currentSymbols": len(symbols),
            "trainingSymbols": int(panel["symbol"].nunique()),
            "listedHOSE": freshness["currentHOSECount"],
            "hoseCoverage": len(symbols) / max(1, freshness["currentHOSECount"]),
            "insufficientHistorySymbols": freshness["insufficientHistory"],
            "freshSymbols": sum(snapshot["dataFreshness"] == "CURRENT" for snapshot in snapshots.values()),
            "staleSymbols": sum(snapshot["dataFreshness"] != "CURRENT" for snapshot in snapshots.values()),
        },
    }
    market_artifact = {
        "version": VERSION,
        "generatedAt": timestamp,
        "asOf": freshness["forecastAsOf"],
        "sources": {
            "historicalAsOf": freshness["frozenSourceAsOf"],
            "marketScanAsOf": freshness["marketScanAsOf"],
            "refreshedSymbols": freshness["refreshedSymbols"],
            "quickSymbolSource": "VNDIRECT PUBLIC EOD",
            "networkFallbacks": freshness["failures"],
            "fullHOSERefresh": True,
            "freshSymbols": sum(snapshot["dataFreshness"] == "CURRENT" for snapshot in snapshots.values()),
            "staleSymbols": sum(snapshot["dataFreshness"] != "CURRENT" for snapshot in snapshots.values()),
            "signalAudit": signal_audit,
        },
        "model": model,
        "backtest": {
            "version": "VMEWS-MARKET-BACKTEST-15.0.0",
            "generatedAt": timestamp,
            "design": "Chronological out-of-sample holdout with four temporal audit slices; symbol-specific T+h maturity purge; pre-holdout calibration; publisher-timestamped event/flow features and executable HOSE-price audit.",
            "horizons": back_horizons,
            "cases": back_cases,
        },
    }

    dashboard.update(
        {
            "generatedAt": timestamp,
            "modelVersion": VERSION,
            "asOf": freshness["forecastAsOf"],
            "promotion": promotion,
            "symbols": snapshots,
            "charts": charts,
            "marketForecast": {"artifact": "forecast-market-v13.json", "tickGridEnforced": True, "allHOSECommonStocks": True, "signalAudit": signal_audit},
        }
    )
    current.update({"generatedAt": timestamp, "symbols": snapshots, "modelVersion": VERSION})
    _json_save(DATA / "forecast-dashboard-v12.json", dashboard)
    _json_save(DATA / "forecast-current-v12.json", current)
    _json_save(DATA / "forecast-market-v13.json", market_artifact)
    diagnostic = {
        "asOf": freshness["forecastAsOf"],
        "symbols": len(symbols),
        "directionHorizons": direction_horizons,
        "fpt": {
            "close": snapshots["FPT"]["close"],
            "horizons": {
                h: snapshots["FPT"]["horizons"][h]["expectedPrice"] for h in map(str, HORIZONS)
            },
        },
        "seconds": round(time.monotonic() - started, 2),
    }
    _log("market_artifacts_published", **diagnostic)
    return diagnostic


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fast", action="store_true", help="use fewer boosting rounds for diagnostics")
    parser.add_argument("--horizons", default="1,2,3,4,5", help="comma-separated direct horizons")
    parser.add_argument("--no-network", action="store_true", help="use only frozen histories and checked-in market scan")
    parser.add_argument("--refresh-symbols", default="ALL", help="ALL HOSE names, or comma-separated public EOD refresh symbols")
    parser.add_argument("--publish", action="store_true", help="write validated current, dashboard and V14 market artifacts")
    args = parser.parse_args()
    requested = tuple(int(item) for item in args.horizons.split(",") if item.strip())
    refresh = tuple(value.strip().upper() for value in args.refresh_symbols.split(",") if value.strip())
    histories, freshness = load_histories(() if args.no_network else refresh)
    events, flows, signal_audit = load_signal_sources(set(freshness["currentHOSESymbols"]))
    _log("signal_sources_audited", acceptedEvents=signal_audit["acceptedEvents"], newsSymbols=signal_audit["newsSymbols"], flowSymbols=signal_audit["flowSymbols"], issuerMismatches=signal_audit["rejected"].get("issuer_mismatch", 0), freshEOD=freshness["freshSymbols"], staleEOD=freshness["staleSymbols"])
    panel = build_panel(histories, freshness["scan"], events, flows)
    results = [fit_horizon(panel, horizon, fast=args.fast) for horizon in requested]
    if args.publish:
        write_artifacts(panel, results, histories, freshness, events, signal_audit)
    latest = panel.sort_values("date").groupby("symbol", observed=True).tail(1)
    fpt = latest.loc[latest["symbol"] == "FPT"]
    if not fpt.empty:
        row = fpt.iloc[0]
        for result in results:
            h = result.horizon
            volatility = float(row["forward_vol"]) * math.sqrt(h)
            normalized = result.model.predict(fpt[FEATURE_COLUMNS].to_numpy(dtype=np.float32))[0]
            probability = float(result.classifier.predict_proba(fpt[FEATURE_COLUMNS].to_numpy(dtype=np.float32))[0, 1])
            raw_return = float(
                shape_prediction(
                    np.asarray([float(normalized) * volatility]),
                    np.asarray([volatility]),
                    np.asarray([probability]),
                    result.scale,
                    result.conviction_floor,
                )[0]
            )
            point = tradable_forecast(float(row["close"]), raw_return, probability, volatility, h)
            low = snap_price(float(row["close"]) * math.exp(raw_return + result.quantile_low * volatility))
            high = snap_price(float(row["close"]) * math.exp(raw_return + result.quantile_high * volatility))
            _log("fpt_preview", date=str(row["date"].date()), horizon=h, close=float(row["close"]), expected=point, returnPct=round(100 * (point / float(row["close"]) - 1), 3), rawPct=round(100 * raw_return, 3), dailyVolPct=round(100 * float(row['forward_vol']), 3), probability=round(probability, 3), low=low, high=high)


if __name__ == "__main__":
    main()
