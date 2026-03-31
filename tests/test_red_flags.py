"""Tests for src/tabs/red_flags.py — all flag evaluation branches."""


import pandas as pd

from src.config import FLAG_THRESHOLDS
from src.tabs.red_flags import (
    _analyst_proxy,
    _check_major_sell,
    _check_price_drop,
    _check_price_drop_plus_downgrades,
    _check_thesis,
    _check_voo_allocation,
    _count_downgrades,
    get_flag_summary,
)

_PRX = FLAG_THRESHOLDS["_proxy"]
_PTF = FLAG_THRESHOLDS["_portfolio"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_history(current_price, peak_price, n=252):
    """Create a price history that peaked at peak_price, now at current_price."""
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    # Rise to peak, then fall to current
    mid = n // 2
    up   = [peak_price * i / mid for i in range(1, mid + 1)]
    down = [peak_price - (peak_price - current_price) * i / (n - mid)
            for i in range(n - mid)]
    values = up + down
    return pd.Series(values[:n], index=idx)


def _price_entry(price, history=None):
    if history is None:
        history = pd.Series([price] * 30, index=pd.date_range("2024-01-01", periods=30, freq="B"))
    return {
        "price": price, "change": 0.0, "beta": 1.0, "div_yield": 0.0,
        "ohlcv": pd.DataFrame({"Close": history}, index=history.index),
        "history": history, "high_52w": float(history.max()), "low_52w": float(history.min()),
    }


def _empty_upgrades():
    return pd.DataFrame(columns=["date", "firm", "action", "from_grade", "to_grade"])


def _make_downgrade_row(firm, action, to_grade, days_ago=5):
    ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days_ago)
    return {"date": ts, "firm": firm, "action": action,
            "from_grade": "Buy", "to_grade": to_grade}


def _upgrades_df(*rows):
    return pd.DataFrame(list(rows))


def _consensus(label, sell=0, strong_sell=0, total=10):
    buy = total - sell - strong_sell
    return {
        "strong_buy": 0, "buy": buy, "hold": 0,
        "sell": sell, "strong_sell": strong_sell,
        "total": total, "label": label,
    }


# ── _check_price_drop ─────────────────────────────────────────────────────────

def test_price_drop_ok_at_peak():
    prices = {"VOO": _price_entry(100.0)}
    # price == high_52w, drop = 0
    status, _ = _check_price_drop("VOO", prices, trigger_pct=10.0, warn_pct=7.0)
    assert status == "ok"


def test_price_drop_watch_at_8pct():
    hist = _make_history(current_price=92.0, peak_price=100.0)
    prices = {"VOO": _price_entry(92.0, hist)}
    status, detail = _check_price_drop("VOO", prices, trigger_pct=10.0, warn_pct=7.0)
    assert status == "watch"
    assert "8.0%" in detail


def test_price_drop_triggered_at_12pct():
    hist = _make_history(current_price=88.0, peak_price=100.0)
    prices = {"VOO": _price_entry(88.0, hist)}
    status, _ = _check_price_drop("VOO", prices, trigger_pct=10.0, warn_pct=7.0)
    assert status == "triggered"


def test_price_drop_nodata_missing_ticker():
    status, detail = _check_price_drop("VOO", {}, trigger_pct=10.0, warn_pct=7.0)
    assert status == "nodata"
    assert detail == ""


def test_price_drop_nodata_empty_history():
    prices = {"VOO": {"price": 100.0, "history": pd.Series(dtype=float), "ohlcv": None}}
    status, _ = _check_price_drop("VOO", prices, trigger_pct=10.0, warn_pct=7.0)
    assert status == "nodata"


# ── _analyst_proxy ────────────────────────────────────────────────────────────

def _proxy_inputs(label="Buy", sell=0, total=10, downgrades=None, drop_pct=0):
    """Build minimal inputs for _analyst_proxy."""
    prices = {}
    if drop_pct > 0:
        hist = _make_history(current_price=100.0 - drop_pct, peak_price=100.0)
        prices["AMD"] = _price_entry(100.0 - drop_pct, hist)
    else:
        prices["AMD"] = _price_entry(100.0)

    upgrades = {}
    if downgrades:
        rows = [_make_downgrade_row(*d) for d in downgrades]
        upgrades["AMD"] = _upgrades_df(*rows)
    else:
        upgrades["AMD"] = _empty_upgrades()

    consensus = {"AMD": _consensus(label, sell=sell, total=total)}
    return prices, upgrades, consensus


def test_proxy_sell_label_triggers():
    prices, upgrades, consensus = _proxy_inputs(label="Sell")
    status, _ = _analyst_proxy("AMD", prices, upgrades, consensus, _PRX)
    assert status == "triggered"


def test_proxy_hold_label_watch():
    prices, upgrades, consensus = _proxy_inputs(label="Hold")
    status, _ = _analyst_proxy("AMD", prices, upgrades, consensus, _PRX)
    assert status == "watch"


def test_proxy_buy_ok():
    prices, upgrades, consensus = _proxy_inputs(label="Buy")
    status, _ = _analyst_proxy("AMD", prices, upgrades, consensus, _PRX)
    assert status == "ok"


def test_proxy_nodata_when_no_signals():
    # No price, no consensus, no upgrades
    status, _ = _analyst_proxy("AMD", {}, {"AMD": _empty_upgrades()},
                                {"AMD": _consensus("N/A", total=0)}, _PRX)
    assert status == "nodata"


def test_proxy_high_sell_fraction_triggers():
    # 4/10 = 40% sell fraction > threshold (30%)
    prices, upgrades, consensus = _proxy_inputs(label="Buy", sell=4, total=10)
    status, _ = _analyst_proxy("AMD", prices, upgrades, consensus, _PRX)
    assert status == "triggered"


def test_proxy_three_downgrades_triggers():
    downgrades = [
        ("JPMorgan", "Downgrade", "Underperform"),
        ("Goldman Sachs", "Downgrade", "Sell"),
        ("Morgan Stanley", "Downgrade", "Underperform"),
    ]
    prices, upgrades, consensus = _proxy_inputs(label="Buy", downgrades=downgrades)
    status, _ = _analyst_proxy("AMD", prices, upgrades, consensus, _PRX)
    assert status == "triggered"


def test_proxy_one_downgrade_watch():
    downgrades = [("JPMorgan", "Downgrade", "Underperform")]
    prices, upgrades, consensus = _proxy_inputs(label="Buy", downgrades=downgrades)
    status, _ = _analyst_proxy("AMD", prices, upgrades, consensus, _PRX)
    assert status == "watch"


def test_proxy_20pct_drop_triggers():
    prices, upgrades, consensus = _proxy_inputs(drop_pct=21)
    status, _ = _analyst_proxy("AMD", prices, upgrades, consensus, _PRX)
    assert status == "triggered"


def test_proxy_12pct_drop_watch():
    prices, upgrades, consensus = _proxy_inputs(drop_pct=13)
    status, _ = _analyst_proxy("AMD", prices, upgrades, consensus, _PRX)
    assert status == "watch"


# ── _check_price_drop_plus_downgrades (ESLT) ──────────────────────────────────

def _eslt_inputs(drop_pct=0, n_downgrades=0):
    if drop_pct > 0:
        hist = _make_history(current_price=100.0 - drop_pct, peak_price=100.0)
        prices = {"ESLT": _price_entry(100.0 - drop_pct, hist)}
    else:
        prices = {"ESLT": _price_entry(100.0)}

    if n_downgrades > 0:
        rows = [_make_downgrade_row("Firm", "Downgrade", "Sell") for _ in range(n_downgrades)]
        upgrades = {"ESLT": _upgrades_df(*rows)}
    else:
        upgrades = {"ESLT": _empty_upgrades()}

    return prices, upgrades


def test_eslt_large_drop_triggers():
    prices, upgrades = _eslt_inputs(drop_pct=25)
    status, _ = _check_price_drop_plus_downgrades("ESLT", prices, upgrades, _PRX)
    assert status == "triggered"


def test_eslt_small_drop_one_downgrade_watch():
    prices, upgrades = _eslt_inputs(drop_pct=5, n_downgrades=1)
    status, _ = _check_price_drop_plus_downgrades("ESLT", prices, upgrades, _PRX)
    assert status == "watch"


def test_eslt_no_drop_no_downgrades_ok():
    prices, upgrades = _eslt_inputs(drop_pct=0, n_downgrades=0)
    status, _ = _check_price_drop_plus_downgrades("ESLT", prices, upgrades, _PRX)
    assert status == "ok"


def test_eslt_no_price_data_nodata():
    upgrades = {"ESLT": _empty_upgrades()}
    status, _ = _check_price_drop_plus_downgrades("ESLT", {}, upgrades, _PRX)
    assert status == "nodata"


# ── _count_downgrades ─────────────────────────────────────────────────────────

def test_count_downgrades_empty_df():
    upgrades = {"AMD": _empty_upgrades()}
    assert _count_downgrades("AMD", upgrades) == []


def test_count_downgrades_action_downgrade():
    row = _make_downgrade_row("JPMorgan", "Downgrade", "Hold")
    upgrades = {"AMD": _upgrades_df(row)}
    hits = _count_downgrades("AMD", upgrades)
    assert len(hits) == 1
    assert "JPMorgan" in hits[0]


def test_count_downgrades_action_upgrade_not_counted():
    row = _make_downgrade_row("Goldman", "Upgrade", "Buy")
    upgrades = {"AMD": _upgrades_df(row)}
    assert _count_downgrades("AMD", upgrades) == []


def test_count_downgrades_sell_grade_counted():
    row = _make_downgrade_row("UBS", "Initiated", "Underperform")
    upgrades = {"AMD": _upgrades_df(row)}
    hits = _count_downgrades("AMD", upgrades)
    assert len(hits) == 1


def test_count_downgrades_missing_ticker():
    assert _count_downgrades("NVDA", {"AMD": _empty_upgrades()}) == []


# ── _check_major_sell ─────────────────────────────────────────────────────────

def test_major_sell_zero_ok():
    upgrades = {"AMD": _empty_upgrades(), "VOO": _empty_upgrades()}
    status, _ = _check_major_sell(upgrades, _PTF)
    assert status == "ok"


def test_major_sell_one_watch():
    row = _make_downgrade_row("JPMorgan", "Downgrade", "Underperform")
    upgrades = {"AMD": _upgrades_df(row), "VOO": _empty_upgrades()}
    status, _ = _check_major_sell(upgrades, _PTF)
    assert status == "watch"


def test_major_sell_two_triggered():
    r1 = _make_downgrade_row("JPMorgan", "Downgrade", "Sell")
    r2 = _make_downgrade_row("Goldman Sachs", "Downgrade", "Underperform")
    upgrades = {"AMD": _upgrades_df(r1), "VOO": _upgrades_df(r2)}
    status, _ = _check_major_sell(upgrades, _PTF)
    assert status == "triggered"


def test_major_sell_unknown_firm_not_counted():
    row = _make_downgrade_row("Random Small Firm", "Downgrade", "Sell")
    upgrades = {"AMD": _upgrades_df(row)}
    status, _ = _check_major_sell(upgrades, _PTF)
    assert status == "ok"


# ── _check_voo_allocation ─────────────────────────────────────────────────────

def _simple_prices(*tickers, price=100.0):
    return {t: {"price": price} for t in tickers}


def _pf_with_shares(voo_shares, other_shares):
    """Portfolio where VOO allocation is voo_shares*100 / (voo_shares+other_shares)*100."""
    return {
        "layers": {
            "Core": [{"ticker": "VOO", "shares": float(voo_shares), "buy_date": "2024-01-01"}],
            "Other": [{"ticker": "AMD", "shares": float(other_shares), "buy_date": "2024-01-01"}],
        }
    }


def test_voo_allocation_ok():
    # VOO=10, AMD=6 at price 100 → VOO=62.5% → ok
    p = _pf_with_shares(10, 6)
    prices = _simple_prices("VOO", "AMD")
    status, detail = _check_voo_allocation(p, prices, _PTF)
    assert status == "ok"
    assert "62.5%" in detail


def test_voo_allocation_watch():
    # VOO=10, AMD=13 at price 100 → VOO=43.5% → between 40% and 45% → watch
    p = _pf_with_shares(10, 13)
    prices = _simple_prices("VOO", "AMD")
    status, _ = _check_voo_allocation(p, prices, _PTF)
    assert status == "watch"


def test_voo_allocation_triggered():
    # VOO=10, AMD=16 at price 100 → VOO=38.5% → below 40% → triggered
    p = _pf_with_shares(10, 16)
    prices = _simple_prices("VOO", "AMD")
    status, _ = _check_voo_allocation(p, prices, _PTF)
    assert status == "triggered"


def test_voo_allocation_nodata_empty_portfolio():
    p = {"layers": {}}
    status, _ = _check_voo_allocation(p, {}, _PTF)
    assert status == "nodata"


def test_voo_allocation_nodata_no_prices():
    p = _pf_with_shares(10, 5)
    status, _ = _check_voo_allocation(p, {}, _PTF)
    assert status == "nodata"


# ── _check_thesis ─────────────────────────────────────────────────────────────

def _thesis_portfolio(*tickers):
    return {
        "layers": {
            "L": [{"ticker": t, "shares": 1.0, "buy_date": "2024-01-01"} for t in tickers]
        }
    }


def test_thesis_all_buy_ok():
    p = _thesis_portfolio("VOO", "AMD", "AMZN")
    consensus = {
        "AMD":  _consensus("Buy"),
        "AMZN": _consensus("Buy"),
    }
    status, _ = _check_thesis(p, consensus, _PTF)
    assert status == "ok"


def test_thesis_one_sell_watch():
    p = _thesis_portfolio("VOO", "AMD", "AMZN")
    consensus = {
        "AMD":  _consensus("Sell", sell=5, total=10),
        "AMZN": _consensus("Buy"),
    }
    status, _ = _check_thesis(p, consensus, _PTF)
    assert status == "watch"


def test_thesis_two_sell_triggered():
    p = _thesis_portfolio("VOO", "AMD", "AMZN", "GOOGL")
    consensus = {
        "AMD":   _consensus("Sell", sell=5),
        "AMZN":  _consensus("Sell", sell=5),
        "GOOGL": _consensus("Buy"),
    }
    status, _ = _check_thesis(p, consensus, _PTF)
    assert status == "triggered"


def test_thesis_nodata_no_consensus():
    p = _thesis_portfolio("VOO", "AMD")
    consensus = {"AMD": _consensus("N/A", total=0)}
    status, _ = _check_thesis(p, consensus, _PTF)
    assert status == "nodata"


def test_thesis_voo_excluded():
    # Even if VOO had a "Sell" label it would be excluded from check
    p = _thesis_portfolio("VOO")
    consensus = {"VOO": _consensus("Sell", sell=5)}
    status, _ = _check_thesis(p, consensus, _PTF)
    # Only VOO in portfolio (and it's excluded) → nodata
    assert status == "nodata"


def test_thesis_high_sell_fraction_watch():
    p = _thesis_portfolio("VOO", "AMD")
    consensus = {"AMD": _consensus("Hold", sell=4, total=10)}  # sell_frac=40% > 30%
    status, _ = _check_thesis(p, consensus, _PTF)
    assert status == "watch"


# ── get_flag_summary ──────────────────────────────────────────────────────────

def test_flag_summary_all_ok(portfolio, mock_data):
    n_trig, n_watch = get_flag_summary(portfolio, mock_data)
    assert n_trig == 0
    assert n_watch == 0


def test_flag_summary_triggered_counted(portfolio, mock_data):
    # Make AMD consensus Sell → _analyst_proxy triggers
    mock_data["consensus"]["AMD"] = _consensus("Sell", sell=6, total=10)
    n_trig, n_watch = get_flag_summary(portfolio, mock_data)
    assert n_trig >= 1
