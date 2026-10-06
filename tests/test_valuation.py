"""Tests for src/valuation.py — currency-aware holdings totals."""

import pandas as pd
import pytest

from src.config import FLAG_THRESHOLDS
from src.tabs.red_flags import _check_voo_allocation
import src.valuation as val

RATE = 0.25  # 1 NIS = 0.25 USD, round number for easy arithmetic


def _entry(price, currency="USD"):
    idx = pd.date_range("2024-01-01", periods=5, freq="B")
    close = pd.Series([price] * 5, index=idx)
    return {"price": price, "currency": currency, "history": close,
            "ohlcv": pd.DataFrame({"Close": close})}


@pytest.fixture
def mixed():
    portfolio = {"layers": {
        "Core (50%)": [
            {"ticker": "VOO", "shares": 10.0, "buy_date": "2024-01-01", "buy_price": 400.0},
            {"ticker": "1146356", "shares": 100.0, "buy_date": "2024-01-01", "buy_price": 20.0},
        ],
        "Compute": [
            {"ticker": "AMD", "shares": 2.0, "buy_date": "2024-01-01", "buy_price": 100.0},
            {"ticker": "GOOGL", "shares": 0.0, "buy_date": "2024-01-01"},  # watch-only
        ],
    }}
    prices = {
        "VOO": _entry(500.0),
        "1146356": _entry(30.0, "ILS"),
        "AMD": _entry(150.0),
        "GOOGL": _entry(170.0),
    }
    return portfolio, prices


def test_tase_value_converted_to_usd(mixed):
    portfolio, prices = mixed
    h = val.compute_holdings(portfolio, prices, RATE)
    tase = h["tickers"]["1146356"]
    assert tase["currency"] == "ILS"
    assert tase["value_native"] == pytest.approx(3000.0)       # 100 × ₪30
    assert tase["market_value_usd"] == pytest.approx(750.0)    # × 0.25
    assert tase["cost_usd"] == pytest.approx(500.0)            # 100 × ₪20 × 0.25


def test_totals_mix_usd_and_converted_nis(mixed):
    portfolio, prices = mixed
    h = val.compute_holdings(portfolio, prices, RATE)
    # VOO 5000 + AMD 300 + TASE 750
    assert h["market_value_usd"] == pytest.approx(6050.0)
    # VOO 4000 + AMD 200 + TASE 500
    assert h["cost_usd"] == pytest.approx(4700.0)
    assert h["layers"]["Core (50%)"] == pytest.approx(5750.0)


def test_watch_only_lots_excluded(mixed):
    portfolio, prices = mixed
    h = val.compute_holdings(portfolio, prices, RATE)
    assert "GOOGL" not in h["tickers"]


def test_lot_without_buy_price_counts_in_market_value_only(monkeypatch):
    monkeypatch.setattr(val, "lookup_buy_price", lambda *a, **k: None)
    portfolio = {"layers": {"L": [{"ticker": "AMD", "shares": 2.0, "buy_date": "2024-01-01"}]}}
    h = val.compute_holdings(portfolio, {"AMD": _entry(150.0)}, RATE)
    assert h["market_value_usd"] == pytest.approx(300.0)
    assert h["cost_usd"] == 0.0
    assert h["value_usd"] == 0.0   # P&L basis excludes lots with unknown cost


def test_stored_buy_price_wins(monkeypatch):
    called = []
    monkeypatch.setattr(val, "lookup_buy_price", lambda *a, **k: called.append(1) or 1.0)
    portfolio = {"layers": {"L": [{"ticker": "AMD", "shares": 1.0, "buy_date": "2024-01-01",
                                   "buy_price": 90.0}]}}
    h = val.compute_holdings(portfolio, {"AMD": _entry(150.0)}, RATE)
    assert h["cost_usd"] == pytest.approx(90.0)
    assert called == []


def test_missing_rate_uses_fallback(mixed):
    portfolio, prices = mixed
    h = val.compute_holdings(portfolio, prices, None)
    assert h["ils_usd"] == pytest.approx(val.ILS_USD_FALLBACK)


def test_voo_allocation_flag_converts_tase(mixed):
    portfolio, prices = mixed
    ptf = FLAG_THRESHOLDS["_portfolio"]
    status, detail = _check_voo_allocation(portfolio, prices, ptf, RATE)
    # VOO 5000 / 6050 = 82.6% — would read 5000 / 8300 = 60.2% if NIS were added as USD
    assert "82.6%" in detail
    assert status == "ok"
