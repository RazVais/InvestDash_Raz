"""Tests for src/config.py — structural integrity checks."""

from src.config import (
    TICKERS_BY_LAYER, TICKER_NAMES, FLAG_THRESHOLDS,
    COLOR, SUGGESTIONS, COMMODITY_SYMBOLS, LAYER_COLORS,
)


# ── Ticker completeness ───────────────────────────────────────────────────────

def test_all_portfolio_tickers_have_display_names():
    for layer, tickers in TICKERS_BY_LAYER.items():
        for t in tickers:
            assert t in TICKER_NAMES, f"{t} (from {layer}) missing from TICKER_NAMES"


def test_all_layers_have_colors():
    for layer in TICKERS_BY_LAYER:
        assert layer in LAYER_COLORS, f"Layer '{layer}' missing from LAYER_COLORS"


# ── FLAG_THRESHOLDS structure ─────────────────────────────────────────────────

def test_flag_thresholds_has_proxy_section():
    prx = FLAG_THRESHOLDS["_proxy"]
    for key in ("drop_pct_watch", "drop_pct_trigger",
                "sell_frac_watch", "sell_frac_trigger",
                "downgrade_watch", "downgrade_trigger"):
        assert key in prx, f"_proxy missing key '{key}'"


def test_flag_thresholds_has_portfolio_section():
    ptf = FLAG_THRESHOLDS["_portfolio"]
    for key in ("voo_min_pct_warn", "voo_min_pct_trigger",
                "major_sell_warn", "major_sell_trigger"):
        assert key in ptf, f"_portfolio missing key '{key}'"


def test_flag_thresholds_ticker_entries():
    for ticker, expected_keys in [
        ("VOO",  ["drop_pct_warn", "drop_pct_trigger"]),
        ("CCJ",  ["uranium_warn", "uranium_trigger"]),
        ("FCX",  ["copper_warn", "copper_trigger"]),
        ("TEVA", ["price_warn", "price_trigger"]),
        ("EQX",  ["gold_warn", "gold_trigger"]),
    ]:
        assert ticker in FLAG_THRESHOLDS, f"{ticker} missing from FLAG_THRESHOLDS"
        for k in expected_keys:
            assert k in FLAG_THRESHOLDS[ticker], f"{ticker}.{k} missing"


def test_flag_threshold_trigger_gt_warn_for_drop():
    """Trigger threshold must be stricter (higher) than warn for drops."""
    assert FLAG_THRESHOLDS["VOO"]["drop_pct_trigger"] > FLAG_THRESHOLDS["VOO"]["drop_pct_warn"]


def test_proxy_trigger_stricter_than_watch():
    prx = FLAG_THRESHOLDS["_proxy"]
    assert prx["drop_pct_trigger"] > prx["drop_pct_watch"]
    assert prx["sell_frac_trigger"] > prx["sell_frac_watch"]
    assert prx["downgrade_trigger"] > prx["downgrade_watch"]


# ── COLOR palette ─────────────────────────────────────────────────────────────

def test_color_has_required_keys():
    required = ["primary", "positive", "negative", "warning", "neutral",
                "dim", "bg_red", "bg_dark", "text_dim"]
    for k in required:
        assert k in COLOR, f"COLOR missing key '{k}'"


def test_color_values_are_hex_strings():
    for k, v in COLOR.items():
        assert isinstance(v, str), f"COLOR['{k}'] is not a string"
        assert v.startswith("#"), f"COLOR['{k}'] = '{v}' is not a hex color"


# ── SUGGESTIONS structure ─────────────────────────────────────────────────────

def test_suggestions_required_fields():
    required = ["ticker", "name", "theme", "rationale", "complements"]
    for s in SUGGESTIONS:
        for field in required:
            assert field in s, f"Suggestion missing field '{field}': {s}"


def test_suggestions_tickers_are_uppercase():
    for s in SUGGESTIONS:
        assert s["ticker"] == s["ticker"].upper(), \
            f"Suggestion ticker '{s['ticker']}' is not uppercase"


def test_suggestions_complements_are_portfolio_tickers():
    portfolio_tickers = {t for tickers in TICKERS_BY_LAYER.values() for t in tickers}
    for s in SUGGESTIONS:
        for c in s["complements"]:
            assert c in portfolio_tickers, \
                f"Complement '{c}' in {s['ticker']} not in portfolio"


# ── COMMODITY_SYMBOLS ─────────────────────────────────────────────────────────

def test_commodity_symbols_has_required_commodities():
    for commodity in ("gold", "copper", "uranium"):
        assert commodity in COMMODITY_SYMBOLS, f"COMMODITY_SYMBOLS missing '{commodity}'"


def test_commodity_symbols_have_ticker():
    for name, (symbol, scale) in COMMODITY_SYMBOLS.items():
        assert isinstance(symbol, str) and len(symbol) > 0, \
            f"COMMODITY_SYMBOLS['{name}'] has empty ticker"
