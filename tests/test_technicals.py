"""Tests for src/data/technicals.py — pure pandas, no mocking needed."""

import numpy as np
import pandas as pd

from src.data.technicals import (
    bollinger,
    compute_correlation_matrix,
    compute_relative_strength,
    compute_rsi,
    ema,
    sma,
)


def _series(values):
    return pd.Series(values, dtype=float)


def _date_series(values, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="B")
    return pd.Series(values, index=idx, dtype=float)


# ── SMA ───────────────────────────────────────────────────────────────────────

def test_sma_length_preserved():
    s = _series(range(20))
    result = sma(s, 5)
    assert len(result) == len(s)


def test_sma_full_window_value():
    s = _series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = sma(s, 3)
    # index 2: mean(1,2,3)=2; index 4: mean(3,4,5)=4
    assert abs(result.iloc[2] - 2.0) < 1e-9
    assert abs(result.iloc[4] - 4.0) < 1e-9


def test_sma_min_periods_one_no_nan():
    # min_periods=1 means no NaN values
    s = _series([10.0, 20.0, 30.0])
    result = sma(s, 5)
    assert not result.isna().any()


def test_sma_larger_window_than_series():
    s = _series([1.0, 2.0, 3.0])
    result = sma(s, 10)
    # min_periods=1: all values valid
    assert len(result) == 3
    assert not result.isna().any()


# ── EMA ───────────────────────────────────────────────────────────────────────

def test_ema_length_preserved():
    s = _series(range(50))
    result = ema(s, 12)
    assert len(result) == len(s)


def test_ema_no_nan():
    s = _series([1.0] * 30)
    result = ema(s, 12)
    assert not result.isna().any()


def test_ema_constant_series_equals_constant():
    s = _series([5.0] * 50)
    result = ema(s, 12)
    assert (result - 5.0).abs().max() < 1e-9


def test_ema_trending_up_less_than_current_price():
    # EMA lags — for an upward series EMA < last close
    s = _series([float(i) for i in range(1, 51)])
    result = ema(s, 12)
    assert result.iloc[-1] < s.iloc[-1]


# ── RSI ───────────────────────────────────────────────────────────────────────

def test_rsi_length_preserved():
    s = _series(range(1, 51))
    result = compute_rsi(s, period=14)
    assert len(result) == len(s)


def test_rsi_values_bounded():
    rng = np.random.default_rng(42)
    s = _series(rng.uniform(100, 200, 100).cumsum())
    result = compute_rsi(s, period=14)
    valid = result.dropna()
    assert (valid >= 0).all()
    assert (valid <= 100).all()


def test_rsi_all_up_above_70():
    # Strictly increasing series → gains only, RSI approaches 100
    s = _series([100.0 + i for i in range(50)])
    result = compute_rsi(s, period=14)
    valid = result.dropna()
    assert (valid > 70).all()


def test_rsi_all_down_below_30():
    # Strictly decreasing series → losses only, RSI approaches 0
    s = _series([100.0 - i for i in range(50)])
    result = compute_rsi(s, period=14)
    valid = result.dropna()
    assert (valid < 30).all()


# ── Bollinger Bands ───────────────────────────────────────────────────────────

def test_bollinger_returns_three_series():
    s = _series(range(1, 51))
    mid, upper, lower = bollinger(s, window=20)
    assert len(mid) == len(s)
    assert len(upper) == len(s)
    assert len(lower) == len(s)


def test_bollinger_upper_gt_lower():
    rng = np.random.default_rng(0)
    s = _series(rng.uniform(90, 110, 60).tolist())
    mid, upper, lower = bollinger(s, window=10)
    valid = ~(upper.isna() | lower.isna())
    # Upper always > lower where both are defined (requires variance)
    assert (upper[valid] >= lower[valid]).all()


def test_bollinger_mid_equals_sma():
    s = _series(range(1, 31))
    mid, _, _ = bollinger(s, window=10)
    expected = sma(s, 10)
    pd.testing.assert_series_equal(mid, expected)


# ── Relative strength ─────────────────────────────────────────────────────────

def test_relative_strength_same_series_equals_100():
    s = _date_series([100.0 + i for i in range(30)])
    rs = compute_relative_strength(s, s)
    assert (rs - 100.0).abs().max() < 1e-6


def test_relative_strength_empty_on_no_overlap():
    a = _date_series([1.0, 2.0, 3.0], start="2024-01-01")
    b = _date_series([1.0, 2.0, 3.0], start="2025-06-01")
    rs = compute_relative_strength(a, b)
    assert rs.empty


def test_relative_strength_outperformer_above_100():
    bench = _date_series([100.0] * 30)   # flat benchmark
    ticker = _date_series([100.0 + i for i in range(30)])  # rising ticker
    rs = compute_relative_strength(ticker, bench)
    assert rs.iloc[-1] > 100.0


def test_relative_strength_underperformer_below_100():
    bench = _date_series([100.0 + i for i in range(30)])  # rising benchmark
    ticker = _date_series([100.0] * 30)   # flat ticker
    rs = compute_relative_strength(ticker, bench)
    assert rs.iloc[-1] < 100.0


# ── Correlation matrix ────────────────────────────────────────────────────────

def test_correlation_matrix_diagonal_is_one():
    idx = pd.date_range("2024-01-01", periods=100, freq="B")
    s1 = pd.Series(range(100), index=idx, dtype=float)
    s2 = pd.Series([v * 2 for v in range(100)], index=idx, dtype=float)
    corr = compute_correlation_matrix({"A": s1, "B": s2})
    assert abs(corr.loc["A", "A"] - 1.0) < 1e-9
    assert abs(corr.loc["B", "B"] - 1.0) < 1e-9


def test_correlation_matrix_symmetric():
    idx = pd.date_range("2024-01-01", periods=100, freq="B")
    rng = np.random.default_rng(7)
    d = {t: pd.Series(rng.standard_normal(100), index=idx) for t in ["X", "Y", "Z"]}
    corr = compute_correlation_matrix(d)
    assert abs(corr.loc["X", "Y"] - corr.loc["Y", "X"]) < 1e-9


def test_correlation_matrix_nan_for_short_overlap():
    # Series with <30 overlapping points → NaN
    idx1 = pd.date_range("2024-01-01", periods=20, freq="B")
    idx2 = pd.date_range("2024-01-01", periods=20, freq="B")
    s1 = pd.Series(range(20), index=idx1, dtype=float)
    s2 = pd.Series(range(20), index=idx2, dtype=float)
    corr = compute_correlation_matrix({"A": s1, "B": s2})
    # Off-diagonal should be NaN (min_periods=30 not satisfied)
    assert pd.isna(corr.loc["A", "B"])


def test_correlation_matrix_empty_input():
    corr = compute_correlation_matrix({})
    assert corr.empty


def test_correlation_matrix_none_series_skipped():
    idx = pd.date_range("2024-01-01", periods=60, freq="B")
    s = pd.Series(range(60), index=idx, dtype=float)
    corr = compute_correlation_matrix({"A": s, "B": None})
    assert "B" not in corr.columns
    assert "A" in corr.columns
