"""Stops / trailing stops / price alerts are evaluated as red flags (src/tabs/red_flags.py)."""

import pandas as pd
import pytest

from src.tabs.red_flags import _alert_flags, get_all_flag_statuses, get_flag_summary


def _entry(closes, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(closes), freq="B")
    hist = pd.Series(closes, index=idx, dtype=float)
    return {"price": float(closes[-1]), "history": hist, "high_52w": float(hist.max()),
            "currency": "USD"}


def _pf(alerts, buy_date="2024-01-01"):
    return {"layers": {"L": [{"ticker": "AMD", "shares": 1.0, "buy_date": buy_date}]},
            "alerts": {"AMD": alerts}}


def _one(flags, word):
    hits = [f for f in flags if word in f["flag"]]
    assert len(hits) == 1, flags
    return hits[0]


@pytest.mark.parametrize("price, expected", [(90.0, "triggered"), (97.0, "watch"), (110.0, "ok")])
def test_stop_loss(price, expected):
    flags = _alert_flags(_pf({"stop_loss": 95.0}), {"AMD": _entry([100.0, price])})
    assert _one(flags, "סטופ לוס")["status"] == expected


def test_trailing_stop_uses_peak_since_buy():
    # peak 200 before the buy, 120 after; 10% trail from 120 → 108
    closes = [200.0, 150.0, 120.0, 110.0, 107.0]
    flags = _alert_flags(_pf({"trailing_stop_pct": 10.0}, buy_date="2024-01-03"),
                         {"AMD": _entry(closes)})
    f = _one(flags, "נגרר")
    assert f["status"] == "triggered"
    assert "$108.00" in f["threshold"]


def test_price_alert_above_and_below():
    alerts = {"price_alerts": [{"price": 150.0, "direction": "above"},
                               {"price": 90.0, "direction": "below", "note": "add more"}]}
    flags = _alert_flags(_pf(alerts), {"AMD": _entry([140.0, 151.0])})
    up   = next(f for f in flags if "↑" in f["flag"])
    down = next(f for f in flags if "↓" in f["flag"])
    assert up["status"] == "triggered"
    assert down["status"] == "ok"
    assert down["threshold"] == "add more"


def test_no_price_is_nodata():
    flags = _alert_flags(_pf({"stop_loss": 95.0}), {})
    assert _one(flags, "סטופ לוס")["status"] == "nodata"


def test_malformed_price_alert_is_skipped():
    flags = _alert_flags(_pf({"price_alerts": [{"direction": "above"}]}), {"AMD": _entry([1.0, 2.0])})
    assert flags == []


def test_alerts_flow_into_all_statuses_and_summary(mock_data):
    portfolio = {"layers": {"Core": [{"ticker": "VOO", "shares": 10.0, "buy_date": "2024-01-15"}]},
                 "alerts": {"VOO": {"stop_loss": 10_000.0}}}  # far above price → triggered
    flags = get_all_flag_statuses(portfolio, mock_data)
    assert any(f["flag"] == "סטופ לוס" and f["status"] == "triggered" for f in flags)
    n_trig, _ = get_flag_summary(portfolio, mock_data)
    assert n_trig >= 1
