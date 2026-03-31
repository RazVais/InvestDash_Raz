"""Tests for src/data/prices.py — lookup_buy_price (no network calls)."""

import pandas as pd

from src.data.prices import lookup_buy_price


def _make_ohlcv(start="2024-01-01", n=252, price=100.0):
    idx = pd.date_range(start, periods=n, freq="B")  # business days
    close = pd.Series([price] * n, index=idx)
    ohlcv = pd.DataFrame({
        "Open":   close,
        "High":   close * 1.01,
        "Low":    close * 0.99,
        "Close":  close,
        "Volume": pd.Series([1_000_000] * n, index=idx),
    })
    return ohlcv, close


def _price_entry(start="2024-01-01", n=252, price=100.0):
    ohlcv, close = _make_ohlcv(start=start, n=n, price=price)
    return {
        "price":    price,
        "change":   0.0,
        "beta":     1.0,
        "div_yield": 0.0,
        "ohlcv":    ohlcv,
        "history":  close,
        "high_52w": price,
        "low_52w":  price,
    }


# ── Date within OHLCV window ──────────────────────────────────────────────────

def test_buy_date_on_trading_day_returns_close():
    entry = _price_entry(start="2024-01-02", price=150.0)
    prices = {"AMD": entry}
    # 2024-01-02 is a Tuesday (business day) — should be in the OHLCV index
    result = lookup_buy_price("AMD", "2024-01-02", prices)
    assert result is not None
    assert abs(result - 150.0) < 1e-6


def test_buy_date_uses_next_trading_day_for_weekend():
    # OHLCV has business days starting 2024-01-02 (Tue)
    entry = _price_entry(start="2024-01-02", price=200.0)
    prices = {"VOO": entry}
    # 2024-01-06 is Saturday → lookup should return Monday 2024-01-08's close
    result = lookup_buy_price("VOO", "2024-01-06", prices)
    assert result is not None
    assert abs(result - 200.0) < 1e-6


def test_buy_date_at_start_of_window():
    entry = _price_entry(start="2024-03-01", price=300.0)
    prices = {"FCX": entry}
    result = lookup_buy_price("FCX", "2024-03-01", prices)
    assert result is not None
    assert abs(result - 300.0) < 1e-6


def test_buy_date_before_ohlcv_window_returns_first_close():
    """Date before OHLCV window → returns first available close (no fallback needed).
    The function finds the first trading day on-or-after buy_date; since every
    OHLCV date is after a very old buy_date, it returns the earliest close.
    """
    entry = _price_entry(start="2024-06-01", price=100.0)
    prices = {"AMD": entry}
    # buy_date 2023-01-01 is before the window — all OHLCV dates satisfy >= 2023-01-01
    result = lookup_buy_price("AMD", "2023-01-01", prices)
    assert result is not None
    assert abs(result - 100.0) < 1e-6


def test_none_prices_dict_falls_through(monkeypatch):
    """None prices_dict → falls through to get_buy_price()."""
    import src.data.prices as pm
    monkeypatch.setattr(pm, "get_buy_price", lambda t, d: 42.0)
    result = lookup_buy_price("AMD", "2024-01-15", None)
    assert result == 42.0


def test_missing_ticker_falls_through(monkeypatch):
    """Ticker not in prices_dict → falls through to get_buy_price()."""
    import src.data.prices as pm
    monkeypatch.setattr(pm, "get_buy_price", lambda t, d: 55.0)
    result = lookup_buy_price("NVDA", "2024-01-15", {"AMD": _price_entry()})
    assert result == 55.0


def test_empty_ohlcv_falls_through(monkeypatch):
    """Empty OHLCV DataFrame → falls through to get_buy_price()."""
    import src.data.prices as pm
    monkeypatch.setattr(pm, "get_buy_price", lambda t, d: 77.0)

    entry = {
        "price": 100.0, "change": 0.0, "beta": 1.0, "div_yield": 0.0,
        "ohlcv": pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"]),
        "history": pd.Series(dtype=float),
        "high_52w": 100.0, "low_52w": 100.0,
    }
    result = lookup_buy_price("AMD", "2024-01-15", {"AMD": entry})
    assert result == 77.0


def test_buy_date_after_all_ohlcv_dates_falls_through(monkeypatch):
    """buy_date after last OHLCV date → no future dates, falls through."""
    import src.data.prices as pm
    monkeypatch.setattr(pm, "get_buy_price", lambda t, d: 111.0)

    entry = _price_entry(start="2024-01-02", n=10, price=100.0)  # ends ~2024-01-15
    result = lookup_buy_price("AMD", "2099-01-01", {"AMD": entry})
    assert result == 111.0
