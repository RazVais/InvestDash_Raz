"""Technical analysis helpers — pure pandas, no Streamlit caching.
Callers pass a pd.Series of closing prices and receive pd.Series back.
"""

import numpy as np
import pandas as pd


def sma(close, window):
    """Simple moving average."""
    return close.rolling(window=window, min_periods=1).mean()


def ema(close, window):
    """Exponential moving average."""
    return close.ewm(span=window, adjust=False).mean()


def compute_rsi(close, period=14):
    """RSI(period) — returns values 0-100."""
    delta  = close.diff()
    gain   = delta.clip(lower=0)
    loss   = (-delta).clip(lower=0)
    avg_g  = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_l  = loss.ewm(com=period - 1, min_periods=period).mean()
    rs     = avg_g / avg_l.replace(0, np.nan)
    rsi    = 100 - (100 / (1 + rs))
    return rsi


def bollinger(close, window=20, num_std=2):
    """Bollinger Bands — returns (mid, upper, lower)."""
    mid   = sma(close, window)
    std   = close.rolling(window=window, min_periods=1).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return mid, upper, lower


def compute_relative_strength(ticker_close, benchmark_close):
    """
    Relative strength of ticker vs benchmark, rebased to 100.
    Returns pd.Series indexed like ticker_close.
    """
    aligned = pd.concat(
        [ticker_close.rename("t"), benchmark_close.rename("b")],
        axis=1,
    ).dropna()
    if aligned.empty or aligned["b"].iloc[0] == 0:
        return pd.Series(dtype=float)
    t_ret = aligned["t"] / aligned["t"].iloc[0]
    b_ret = aligned["b"] / aligned["b"].iloc[0]
    return (t_ret / b_ret * 100).rename("rel_strength")


def compute_correlation_matrix(prices_dict):
    """
    Build a correlation matrix from {ticker: close_series}.
    Returns pd.DataFrame (tickers × tickers), NaN where < 30 overlapping days.
    """
    series = {}
    for t, s in prices_dict.items():
        if s is not None and len(s) > 0:
            series[t] = s.pct_change().dropna()

    if not series:
        return pd.DataFrame()

    df = pd.DataFrame(series)
    return df.corr(min_periods=30)
