"""Manual historic trades: portfolio helpers + journal validation/parsing."""

import datetime as dt

import pytest

import src.portfolio as pm
from src.tabs.trading_journal_tab import _history_to_closed_trades, _validate_historic_trade

D = dt.date


@pytest.fixture
def pf(nosave):
    return {"layers": {"Core": [{"ticker": "VOO", "shares": 1.0, "buy_date": "2024-01-01"}]},
            "trade_history": []}


def test_add_closed_trade_nets_fees_and_keeps_setup(pf):
    pm.add_closed_trade(pf, "nvda", 10, 100.0, D(2025, 1, 2), 120.0, D(2025, 2, 3), "Compute",
                        fees=15.0, setup_type="breakout", note="  earnings run  ")
    e = pf["trade_history"][0]
    assert e["ticker"] == "NVDA"
    assert e["pnl"] == pytest.approx(185.0)        # 200 gross − 15 fees
    assert e["fees"] == 15.0
    assert e["setup_type"] == "breakout"
    assert e["note"] == "earnings run"
    assert e["source"] == "manual"


def test_optional_fields_omitted_when_empty(pf):
    pm.add_closed_trade(pf, "AMD", 1, 10.0, D(2025, 1, 2), 9.0, D(2025, 1, 3), "L")
    e = pf["trade_history"][0]
    assert "fees" not in e and "setup_type" not in e and "note" not in e
    assert e["pnl"] == pytest.approx(-1.0)


def test_remove_closed_trade(pf):
    pm.add_closed_trade(pf, "AMD", 1, 10.0, D(2025, 1, 2), 12.0, D(2025, 1, 3), "L")
    assert pm.remove_closed_trade(pf, "amd", "2025-01-02", "2025-01-03") is True
    assert pf["trade_history"] == []
    assert pm.remove_closed_trade(pf, "AMD", "2025-01-02", "2025-01-03") is False


def test_history_frame_carries_setup_and_net_pnl(pf):
    pm.add_closed_trade(pf, "NVDA", 10, 100.0, D(2025, 1, 2), 120.0, D(2025, 2, 3), "Compute",
                        fees=15.0, setup_type="vcp")
    df = _history_to_closed_trades(pf)
    row = df.iloc[0]
    assert row["setup_type"] == "vcp"
    assert row["pnl"] == pytest.approx(185.0)
    assert bool(row["is_win"]) is True


@pytest.mark.parametrize("kwargs, ok", [
    ({}, True),
    ({"ticker": ""}, False),
    ({"shares": 0}, False),
    ({"sell_price": 0}, False),
    ({"sell_date": D(2025, 1, 1)}, False),            # before buy
    ({"sell_date": D(2025, 1, 2)}, True),             # same-day trade allowed
    ({"sell_date": D(2099, 1, 1)}, False),            # future
])
def test_validation(pf, kwargs, ok):
    args = {"ticker": "NVDA", "shares": 1, "buy_price": 10.0, "sell_price": 11.0,
            "buy_date": D(2025, 1, 2), "sell_date": D(2025, 3, 1)}
    args.update(kwargs)
    err = _validate_historic_trade(pf, today=D(2026, 1, 1), **args)
    assert (err is None) is ok


def test_validation_rejects_duplicate(pf):
    pm.add_closed_trade(pf, "NVDA", 1, 10.0, D(2025, 1, 2), 11.0, D(2025, 3, 1), "L")
    err = _validate_historic_trade(pf, "NVDA", 1, 10.0, 11.0, D(2025, 1, 2), D(2025, 3, 1),
                                   today=D(2026, 1, 1))
    assert err is not None
