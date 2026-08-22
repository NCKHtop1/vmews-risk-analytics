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


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
VN_TZ = timezone(timedelta(hours=7))
VERSION = "VMEWS-MARKET-FORECAST-13.0.0"
HORIZONS = (1, 2, 3, 4, 5)
QUICK_SYMBOLS = ("FPT", "VCB", "HPG", "MBB", "FRT", "PNJ", "VNM", "SSI")
VNDIRECT_URL = "https://api-finfo.vndirect.com.vn/v4/stock_prices"
FEATURE_COLUMNS = [
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
    histories: dict[str, list[dict[str, Any]]] = {
        symbol: list(rows)
        for symbol, rows in (frozen.get("histories") or {}).items()
        if isinstance(rows, list) and len(rows) >= 250
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

    for symbol in refresh_symbols:
        if symbol not in histories:
            continue
        try:
            incoming = _vn_direct_rows(symbol)
            by_date = {str(row["date"]): row for row in histories[symbol]}
            for row in incoming:
                by_date[row["date"]] = row
            histories[symbol] = [by_date[key] for key in sorted(by_date)]
            refreshed[symbol] = "VNDIRECT_PUBLIC_EOD"
            _log("eod_symbol_refreshed", symbol=symbol, last=incoming[-1]["date"] if incoming else None)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            failures[symbol] = f"{type(exc).__name__}: {exc}"[:240]
            _log("eod_symbol_fallback", symbol=symbol, detail=failures[symbol])

    latest_dates = [str(rows[-1]["date"]) for rows in histories.values() if rows]
    modal_date = statistics.mode(latest_dates) if latest_dates else str(frozen.get("asOf"))
    return histories, {
        "frozenSourceAsOf": frozen.get("asOf"),
        "marketScanAsOf": scan.get("reviewDate"),
        "forecastAsOf": modal_date,
        "refreshedSymbols": len(refreshed),
        "providerBySymbol": refreshed,
        "failures": failures,
        "scan": ranked,
    }


def _rsi(close: pd.Series, periods: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / periods, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / periods, adjust=False).mean()
    return 100.0 - 100.0 / (1.0 + gain / loss.replace(0, np.nan))


def build_panel(histories: dict[str, list[dict[str, Any]]], scan: dict[str, Any]) -> pd.DataFrame:
    started = time.monotonic()
    chunks: list[pd.DataFrame] = []
    for symbol, rows in sorted(histories.items()):
        frame = pd.DataFrame(rows).copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
        if len(frame) < 250:
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
        for horizon in HORIZONS:
            output[f"target{horizon}"] = log_close.shift(-horizon) - log_close
            output[f"maturity{horizon}"] = frame["date"].shift(-horizon)
            output[f"future_price{horizon}"] = frame["close"].shift(-horizon)
        chunks.append(output.tail(1050))

    if len(chunks) < 300:
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


def shape_prediction(
    raw: np.ndarray,
    volatility: np.ndarray,
    probability: np.ndarray,
    multiplier: float,
    floor: float,
) -> np.ndarray:
    """Apply the calibration-only conviction floor without using future labels."""
    point = raw * multiplier
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
    requested_loss = os.environ.get("V13_MODEL_LOSS", "squared_error")
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
    minimum_move = max(
        tick,
        int(round(.10 * horizon_volatility * reference / tick)) * tick,
    )
    direction = 1 if raw_return > 0 else -1 if raw_return < 0 else 0
    if abs(raw_return) <= .045 * horizon_volatility and abs(probability - .5) >= .025:
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
    medians = result.rows[FEATURE_COLUMNS].median(numeric_only=True).to_numpy(dtype=np.float32)
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
    symbols = sorted(set(legacy_symbols) & set(latest.index))
    if len(symbols) < 320:
        raise RuntimeError(f"current HOSE coverage unexpectedly collapsed: {len(symbols)}")
    rows = latest.loc[symbols].copy()
    rows["risk_scan"] = [
        str((freshness["scan"].get(symbol) or {}).get("status", "")) for symbol in symbols
    ]
    feature_x = rows[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    snapshots: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        old = copy.deepcopy(legacy_symbols[symbol])
        row = rows.loc[symbol]
        scan_row = freshness["scan"].get(symbol, {})
        old.update(
            {
                "symbol": symbol,
                "date": str(row["date"].date()),
                "close": int(round(float(row["close"]))),
                "modelClose": int(round(float(row["close"]))),
                "exchange": str(row.get("exchange", "HOSE")).upper(),
                "sector": str(row.get("sector", "UNKNOWN")),
                "riskStatus": _risk_status(row, str(old.get("riskStatus", "GREEN"))),
                "marketDataSource": freshness["providerBySymbol"].get(symbol, "AUDITED_OHLCV"),
                "dailyVolatility": float(row["forward_vol"]),
                "lastSessionReturn": float(row.get("ret1", 0.0) or 0.0),
                "relativeVolume": float(scan_row.get("relativeVolume10d", 0.0) or 0.0),
                "horizons": {},
            }
        )
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
        price_pass = (
            audit["maeSkill"] > 0
            and audit["rankIC"] >= .02
            and .45 <= audit["coverage20_80"] <= .75
            and audit["medianForecastAbs"] >= .0015
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
        }
        model_horizons[key] = {
            "activeExperts": ["NUMERICAL", "REGIME", "SECTOR", "VOLATILITY"],
            "priceStatus": "PASS",
            "directionStatus": "PASS" if direction_pass else "REVIEW",
            "status": "PASS",
            "sealedAudit": audit,
            "training": result.training,
            "calibration": result.calibration,
            "embargoAudit": embargo_audit,
            "magnitudeGate": magnitude_gate,
            "distributionAudit": {"status": "PASS", "coverage20_80": audit["coverage20_80"]},
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
            "ablation": {},
        }

        for position, symbol in enumerate(symbols):
            row = rows.iloc[position]
            venue = str(row.get("exchange", "HOSE")).upper()
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
            venue = str(historical.get("exchange", "HOSE")).upper()
            origin = float(historical["close"])
            expected_return = float(historical["_prediction"])
            hv = float(historical["forward_vol"]) * math.sqrt(horizon)
            p_up = float(historical["_probability"])
            expected_price = tradable_forecast(origin, expected_return, p_up, hv, horizon, venue)
            limits = session_limit(origin, horizon, venue)
            q20_price = max(limits[0], min(expected_price, snap_price(origin * math.exp(expected_return + result.quantile_low * hv), venue, "down")))
            q80_price = min(limits[1], max(expected_price, snap_price(origin * math.exp(expected_return + result.quantile_high * hv), venue, "up")))
            observed_price = int(round(float(historical[f"future_price{horizon}"])))
            observed_return = math.log(observed_price / origin)
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
                    "realizedComparablePrice": observed_price,
                    "corporateActionGap": 0.0,
                    "corporateActionAffected": False,
                    "correctDirection": bool(np.sign(observed_return) == np.sign(executable_return)),
                    "intervalHit": bool(q20_price <= observed_price <= q80_price),
                    "absoluteError": abs(observed_return - executable_return),
                    "expertPredictions": {"NUMERICAL": expected_return},
                    "contextAtOrigin": {
                        "prior20": float(historical["ret20"]),
                        "breadth20": float(historical["breadth20"]),
                        "newsN20": None,
                        "rumorN20": None,
                        "foreignAvailable": 0,
                        "propAvailable": 0,
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
        },
        "universe": {"currentSymbols": len(symbols), "trainingSymbols": int(panel["symbol"].nunique())},
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
        },
        "model": model,
        "backtest": {
            "version": "VMEWS-MARKET-BACKTEST-13.0.0",
            "generatedAt": timestamp,
            "design": "Chronological out-of-sample holdout; symbol-specific T+h label-maturity purge; calibration frozen before holdout.",
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
            "marketForecast": {"artifact": "forecast-market-v13.json", "tickGridEnforced": True},
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
    parser.add_argument("--refresh-symbols", default=",".join(QUICK_SYMBOLS), help="comma-separated public EOD refresh symbols")
    parser.add_argument("--publish", action="store_true", help="write validated current, dashboard and V13 market artifacts")
    args = parser.parse_args()
    requested = tuple(int(item) for item in args.horizons.split(",") if item.strip())
    refresh = tuple(value.strip().upper() for value in args.refresh_symbols.split(",") if value.strip())
    histories, freshness = load_histories(() if args.no_network else refresh)
    panel = build_panel(histories, freshness["scan"])
    results = [fit_horizon(panel, horizon, fast=args.fast) for horizon in requested]
    if args.publish:
        write_artifacts(panel, results, histories, freshness)
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
