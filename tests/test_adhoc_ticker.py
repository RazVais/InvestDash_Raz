"""מניה page — ad-hoc ticker helpers (src/tabs/ticker_tab.py)."""

import pytest

from src.tabs.ticker_tab import merge_data, normalize_ticker


@pytest.mark.parametrize("raw, expected", [
    ("tsla", "TSLA"),
    ("  pltr ", "PLTR"),
    ("$nvda", "NVDA"),
    ("BRK.B", "BRK.B"),
    ("1159250", "1159250"),          # TASE numeric ID
    ("", None),
    ("<script>", None),
    ("TOO-LONG-TICKER", None),
    ("1AB", None),
])
def test_normalize_ticker(raw, expected):
    assert normalize_ticker(raw) == expected


def test_merge_data_layers_extra_without_mutating():
    data = {"prices": {"VOO": 1}, "targets": {"VOO": 2}, "macro": {"vix": 15}}
    extra = {"prices": {"TSLA": 9}, "targets": {"TSLA": 8}, "news": {"TSLA": []}}
    out = merge_data(data, extra)
    assert out["prices"] == {"VOO": 1, "TSLA": 9}
    assert out["news"] == {"TSLA": []}
    assert out["macro"] is data["macro"]
    assert data["prices"] == {"VOO": 1}           # original untouched
    assert "news" not in data
