"""Shared fixtures for the RazDashboard test suite."""

import pytest
import pandas as pd
import numpy as np


# ── Portfolio fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def portfolio():
    """In-memory portfolio with VOO (1 lot), AMD (2 lots), AMZN (1 lot)."""
    return {
        "layers": {
            "Core (50%)": [
                {"ticker": "VOO", "shares": 10.0, "buy_date": "2024-01-15"},
            ],
            "Compute & Platform": [
                {"ticker": "AMD",  "shares": 5.0, "buy_date": "2024-03-01"},
                {"ticker": "AMD",  "shares": 3.0, "buy_date": "2024-06-01"},
                {"ticker": "AMZN", "shares": 2.0, "buy_date": "2024-02-10"},
            ],
        }
    }


@pytest.fixture
def nosave(monkeypatch):
    """Patch save_portfolio to a no-op so mutations don't touch disk."""
    import src.portfolio as pm
    monkeypatch.setattr(pm, "save_portfolio", lambda p: None)


# ── Price fixtures ────────────────────────────────────────────────────────────

def _make_price_entry(start=100.0, trend=0.001, n=252):
    """Build a synthetic price entry dict with OHLCV history."""
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = pd.Series(
        [start * (1.0 + trend) ** i for i in range(n)],
        index=dates,
    )
    ohlcv = pd.DataFrame({
        "Open":   close * 0.99,
        "High":   close * 1.01,
        "Low":    close * 0.98,
        "Close":  close,
        "Volume": pd.Series([1_000_000.0] * n, index=dates),
    })
    return {
        "price":    float(close.iloc[-1]),
        "change":   0.5,
        "beta":     1.0,
        "div_yield": 0.0,
        "ohlcv":    ohlcv,
        "history":  close,
        "high_52w": float(close.max()),
        "low_52w":  float(close.min()),
    }


@pytest.fixture
def mock_prices():
    """Prices dict with synthetic up-trending history for VOO, AMD, AMZN."""
    return {
        "VOO":        _make_price_entry(400.0, 0.001),
        "AMD":        _make_price_entry(150.0, 0.0005),
        "AMZN":       _make_price_entry(180.0, 0.002),
        "__errors__": {},
    }


def _empty_upgrades(*tickers):
    """Return a dict of empty upgrade DataFrames for given tickers."""
    cols = ["date", "firm", "action", "from_grade", "to_grade"]
    return {t: pd.DataFrame(columns=cols) for t in tickers}


def _ok_consensus(*tickers):
    """Return a dict of all-Buy consensus dicts for given tickers."""
    return {
        t: {
            "strong_buy": 5, "buy": 3, "hold": 2,
            "sell": 0, "strong_sell": 0,
            "total": 10, "label": "Buy",
        }
        for t in tickers
    }


_ALL_FLAG_TICKERS = [
    "VOO", "CCJ", "FCX", "ETN", "VRT", "AMD",
    "AMZN", "GOOGL", "CRWD", "ESLT", "TEVA", "EQX",
]


@pytest.fixture
def mock_data(portfolio, mock_prices):
    """Full data dict with all-ok signals — no flags should trigger."""
    return {
        "prices":      mock_prices,
        "upgrades":    _empty_upgrades(*_ALL_FLAG_TICKERS),
        "consensus":   _ok_consensus(*_ALL_FLAG_TICKERS),
        "commodities": {"gold": 2500.0, "copper": 5.0, "uranium": 90.0},
        "_market_open": True,
    }
