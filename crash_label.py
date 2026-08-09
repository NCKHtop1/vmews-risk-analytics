"""Crash-labelling utilities based on the thesis CRASH / COUNT methodology."""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

SIGMA_THRESHOLD = 3.09


def volume_weighted_sector_price(prices: pd.DataFrame, price_col="close", volume_col="volume") -> float:
    """Equation (1): sector price = sum(w_i * P_i) / sum(w_i), with volume as weight."""
    p = prices[[price_col, volume_col]].dropna()
    denom = p[volume_col].sum()
    return float((p[price_col] * p[volume_col]).sum() / denom) if denom else float("nan")


def log_return(price: pd.Series) -> pd.Series:
    """Equation (2): R_t = ln(P_t/P_{t-1})."""
    return np.log(price / price.shift(1))


def expanded_market_residuals(sector_return: pd.Series, market_return: pd.Series) -> pd.Series:
    """Approximate Equation (3) with market leads/lags w-2 ... w+2.

    The thesis text mentions industry controls as well, but the displayed equation shows
    market return leads/lags. This function follows the displayed equation only.
    """
    frame = pd.DataFrame({"r": sector_return, "m": market_return})
    for lag in [-2, -1, 0, 1, 2]:
        frame[f"m_{lag:+d}"] = frame["m"].shift(-lag)
    frame = frame.dropna()
    X = frame[[f"m_{lag:+d}" for lag in [-2,-1,0,1,2]]]
    y = frame["r"]
    lr = LinearRegression().fit(X, y)
    resid = pd.Series(y - lr.predict(X), index=frame.index, name="residual")
    return resid


def specific_weekly_return(residual: pd.Series) -> pd.Series:
    """Equation (4): R_w = ln(1 + e_w). Values <= -1 are not defined."""
    r = residual.where(residual > -1)
    return np.log1p(r)


def crash_flags(specific_return: pd.Series, sigma: float = SIGMA_THRESHOLD) -> pd.DataFrame:
    """Equation (5): flag when R_w < mean(R) - 3.09 * std(R).

    Threshold is estimated per calendar year to reflect the thesis firm/sector-year wording.
    """
    s = specific_return.dropna().copy()
    if not isinstance(s.index, pd.DatetimeIndex):
        raise TypeError("specific_return index must be DatetimeIndex")
    df = s.to_frame("specific_return")
    g = df.groupby(df.index.year)["specific_return"]
    df["year_mean"] = g.transform("mean")
    df["year_std"] = g.transform("std")
    df["threshold"] = df["year_mean"] - sigma * df["year_std"]
    df["crash"] = (df["specific_return"] < df["threshold"]).astype(int)
    return df


def direct_index_crash_flags(weekly_index_close: pd.Series, sigma: float = SIGMA_THRESHOLD) -> pd.DataFrame:
    """Operational approximation for VN-Index when no separate market factor exists.

    It applies the same 3.09-sigma logic directly to weekly log returns. This is not claimed
    to reproduce the thesis' full VNIndex crash-identification code.
    """
    r = log_return(weekly_index_close)
    return crash_flags(r, sigma=sigma)
