"""Market-data adapter and feature engineering for VMEWS.

This file is intentionally independent from the browser dashboard. It can be used to
materialise a daily VN-Index dataset for offline model experiments.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Iterable
import numpy as np
import pandas as pd
import requests

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVNINDEX.VN"


def fetch_vnindex(range_: str = "max", interval: str = "1d") -> pd.DataFrame:
    params = {"range": range_, "interval": interval, "includePrePost": "false", "events": "div,splits"}
    r = requests.get(YAHOO_CHART, params=params, timeout=30, headers={"User-Agent": "Mozilla/5.0 VMEWS/1.0"})
    r.raise_for_status()
    result = r.json()["chart"]["result"][0]
    q = result["indicators"]["quote"][0]
    df = pd.DataFrame({
        "date": pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_convert("Asia/Ho_Chi_Minh").date,
        "open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"], "volume": q["volume"],
    })
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["close"]).drop_duplicates("date").sort_values("date").reset_index(drop=True)
    if (df["close"] <= 0).any():
        raise ValueError("Non-positive close prices found")
    return df


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create transparent daily features for experimentation.

    These are portfolio implementation features. They are not claimed to be the exact
    unpublished feature matrix used in the thesis.
    """
    x = df.copy()
    x["log_return"] = np.log(x["close"] / x["close"].shift(1))
    x["vol_5"] = x["log_return"].rolling(5).std() * math.sqrt(252)
    x["vol_20"] = x["log_return"].rolling(20).std() * math.sqrt(252)
    x["momentum_5"] = x["close"].pct_change(5)
    x["momentum_20"] = x["close"].pct_change(20)
    x["ma_20"] = x["close"].rolling(20).mean()
    x["ma_60"] = x["close"].rolling(60).mean()
    x["drawdown_60"] = x["close"] / x["close"].rolling(60).max() - 1
    x["rsi_14"] = _rsi(x["close"], 14)
    ema12 = x["close"].ewm(span=12, adjust=False).mean()
    ema26 = x["close"].ewm(span=26, adjust=False).mean()
    x["macd"] = ema12 - ema26
    x["macd_signal"] = x["macd"].ewm(span=9, adjust=False).mean()
    x["macd_hist"] = x["macd"] - x["macd_signal"]
    low14 = x["low"].rolling(14).min()
    high14 = x["high"].rolling(14).max()
    x["stoch_k"] = 100 * (x["close"] - low14) / (high14 - low14).replace(0, np.nan)
    x["stoch_d"] = x["stoch_k"].rolling(3).mean()
    if "volume" in x.columns and x["volume"].fillna(0).sum() > 0:
        v = x["volume"].replace(0, np.nan)
        x["volume_z20"] = (v - v.rolling(20).mean()) / v.rolling(20).std()
    else:
        x["volume_z20"] = 0.0
    return x.replace([np.inf, -np.inf], np.nan)


if __name__ == "__main__":
    df = make_features(fetch_vnindex("max"))
    out = "data/vnindex_live_features.csv"
    df.to_csv(out, index=False)
    print(f"Saved {len(df):,} rows -> {out}")
