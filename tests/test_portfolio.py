"""Tests for src/portfolio.py — mutations, helpers, persistence."""

from datetime import date
import json

import pytest

import src.portfolio as pm
from src.portfolio import (
    add_lot,
    all_tickers,
    get_layer_for_ticker,
    load_portfolio,
    lots_for_ticker,
    remove_lot,
    remove_ticker,
    save_portfolio,
    update_lot,
)

# ── Ticker helpers ─────────────────────────────────────────────────────────────

def test_all_tickers_unique_sorted(portfolio):
    tickers = all_tickers(portfolio)
    assert tickers == sorted(set(tickers))
    assert "VOO" in tickers
    assert "AMD" in tickers
    assert "AMZN" in tickers
    # AMD appears twice in layers but should only appear once
    assert tickers.count("AMD") == 1


def test_all_tickers_empty_portfolio():
    empty = {"layers": {}}
    assert all_tickers(empty) == []


def test_lots_for_ticker_multi_lot(portfolio):
    lots = lots_for_ticker(portfolio, "AMD")
    assert len(lots) == 2
    dates = [lot["buy_date"] for _, lot in lots]
    assert "2024-03-01" in dates
    assert "2024-06-01" in dates


def test_lots_for_ticker_single_lot(portfolio):
    lots = lots_for_ticker(portfolio, "VOO")
    assert len(lots) == 1
    layer, lot = lots[0]
    assert layer == "Core (50%)"
    assert lot["shares"] == 10.0


def test_lots_for_ticker_missing(portfolio):
    assert lots_for_ticker(portfolio, "NVDA") == []


def test_get_layer_for_ticker(portfolio):
    assert get_layer_for_ticker(portfolio, "VOO") == "Core (50%)"
    assert get_layer_for_ticker(portfolio, "AMD") == "Compute & Platform"


def test_get_layer_for_ticker_missing(portfolio):
    assert get_layer_for_ticker(portfolio, "NVDA") is None


# ── add_lot ───────────────────────────────────────────────────────────────────

def test_add_lot_appends(portfolio, nosave):
    add_lot(portfolio, "Core (50%)", "VOO", 5.0, "2024-09-01")
    lots = lots_for_ticker(portfolio, "VOO")
    assert len(lots) == 2
    shares = [lot["shares"] for _, lot in lots]
    assert 5.0 in shares


def test_add_lot_uppercases_ticker(portfolio, nosave):
    add_lot(portfolio, "Compute & Platform", "nvda", 2.0, "2024-08-01")
    tickers = all_tickers(portfolio)
    assert "NVDA" in tickers
    assert "nvda" not in tickers


def test_add_lot_creates_new_layer(portfolio, nosave):
    add_lot(portfolio, "New Layer", "TSLA", 1.0, "2024-07-01")
    assert "New Layer" in portfolio["layers"]
    assert any(lot["ticker"] == "TSLA" for lot in portfolio["layers"]["New Layer"])


def test_add_lot_new_ticker(portfolio, nosave):
    initial_count = len(all_tickers(portfolio))
    add_lot(portfolio, "Compute & Platform", "MSFT", 3.0, "2024-05-01")
    assert len(all_tickers(portfolio)) == initial_count + 1
    assert "MSFT" in all_tickers(portfolio)


def test_add_lot_stores_date_as_string(portfolio, nosave):
    add_lot(portfolio, "Core (50%)", "VOO", 2.0, date(2024, 10, 1))
    lots = lots_for_ticker(portfolio, "VOO")
    dates = [lot["buy_date"] for _, lot in lots]
    assert "2024-10-01" in dates


# ── update_lot ────────────────────────────────────────────────────────────────

def test_update_lot_changes_shares_and_date(portfolio, nosave):
    update_lot(portfolio, "Compute & Platform", "AMD", "2024-03-01", 9.0, "2024-03-15")
    lots = lots_for_ticker(portfolio, "AMD")
    dates_and_shares = {lot["buy_date"]: lot["shares"] for _, lot in lots}
    assert "2024-03-15" in dates_and_shares
    assert dates_and_shares["2024-03-15"] == 9.0
    # Other lot untouched
    assert "2024-06-01" in dates_and_shares
    assert dates_and_shares["2024-06-01"] == 3.0


def test_update_lot_nonexistent_date_no_crash(portfolio, nosave):
    # Should not raise — just does nothing
    update_lot(portfolio, "Compute & Platform", "AMD", "1999-01-01", 1.0, "1999-01-01")
    lots = lots_for_ticker(portfolio, "AMD")
    assert len(lots) == 2


# ── remove_lot ────────────────────────────────────────────────────────────────

def test_remove_lot_removes_one(portfolio, nosave):
    remove_lot(portfolio, "Compute & Platform", "AMD", "2024-03-01")
    lots = lots_for_ticker(portfolio, "AMD")
    assert len(lots) == 1
    assert lots[0][1]["buy_date"] == "2024-06-01"


def test_remove_lot_preserves_sibling_tickers(portfolio, nosave):
    remove_lot(portfolio, "Compute & Platform", "AMD", "2024-03-01")
    # AMZN should still be there
    assert "AMZN" in all_tickers(portfolio)


def test_remove_lot_cleans_empty_layer(portfolio, nosave):
    # Remove only VOO lot — Core layer should be deleted (>1 layer exists)
    remove_lot(portfolio, "Core (50%)", "VOO", "2024-01-15")
    assert "Core (50%)" not in portfolio["layers"]


def test_remove_lot_keeps_single_remaining_layer(nosave):
    """If only 1 layer left, it must be preserved even if empty."""
    p = {"layers": {"Only Layer": [{"ticker": "VOO", "shares": 1.0, "buy_date": "2024-01-01"}]}}
    remove_lot(p, "Only Layer", "VOO", "2024-01-01")
    assert "Only Layer" in p["layers"]
    assert p["layers"]["Only Layer"] == []


# ── remove_ticker ─────────────────────────────────────────────────────────────

def test_remove_ticker_removes_all_lots(portfolio, nosave):
    remove_ticker(portfolio, "AMD")
    assert "AMD" not in all_tickers(portfolio)


def test_remove_ticker_leaves_others(portfolio, nosave):
    remove_ticker(portfolio, "AMD")
    assert "VOO" in all_tickers(portfolio)
    assert "AMZN" in all_tickers(portfolio)


def test_remove_ticker_case_insensitive(portfolio, nosave):
    remove_ticker(portfolio, "amd")
    assert "AMD" not in all_tickers(portfolio)


# ── Persistence ───────────────────────────────────────────────────────────────

def test_save_load_roundtrip(portfolio, tmp_path, monkeypatch):
    monkeypatch.setattr(pm, "PORTFOLIO_FILE", tmp_path / "portfolio.json")
    save_portfolio(portfolio)
    loaded = load_portfolio()
    assert loaded["layers"] == portfolio["layers"]


def test_load_portfolio_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(pm, "PORTFOLIO_FILE", tmp_path / "missing.json")
    p = load_portfolio()
    assert "layers" in p
    assert len(p["layers"]) > 0


def test_load_portfolio_strips_empty_layers(tmp_path, monkeypatch):
    monkeypatch.setattr(pm, "PORTFOLIO_FILE", tmp_path / "portfolio.json")
    try:
        import streamlit as st
        st.session_state.pop("_portfolio_cache", None)
    except Exception:
        pass
    data = {"layers": {"Empty": [], "Has Data": [{"ticker": "VOO", "shares": 1.0, "buy_date": "2024-01-01"}]}}
    (tmp_path / "portfolio.json").write_text(json.dumps(data), encoding="utf-8")
    p = load_portfolio()
    assert "Empty" not in p["layers"]
    assert "Has Data" in p["layers"]


# ── Load-failure guard (never overwrite real data with defaults) ─────────────

@pytest.fixture
def fresh_session():
    """Clear the session-state keys load_portfolio/save_portfolio use."""
    import streamlit as st
    for k in ("_portfolio_cache", "_portfolio_load_failed", "_portfolio_save_error"):
        st.session_state.pop(k, None)
    yield
    for k in ("_portfolio_cache", "_portfolio_load_failed", "_portfolio_save_error"):
        st.session_state.pop(k, None)


def test_corrupt_file_blocks_save_and_keeps_original(tmp_path, monkeypatch, fresh_session):
    path = tmp_path / "portfolio.json"
    monkeypatch.setattr(pm, "PORTFOLIO_FILE", path)
    path.write_text("{not valid json", encoding="utf-8")

    p = load_portfolio()
    assert pm.portfolio_load_failed()
    assert (tmp_path / "portfolio.json.bak").read_text(encoding="utf-8") == "{not valid json"

    assert save_portfolio(p) is False
    assert path.read_text(encoding="utf-8") == "{not valid json"


def test_missing_file_is_not_a_failure(tmp_path, monkeypatch, fresh_session):
    monkeypatch.setattr(pm, "PORTFOLIO_FILE", tmp_path / "missing.json")
    p = load_portfolio()
    assert not pm.portfolio_load_failed()
    assert save_portfolio(p) is True


def test_gist_error_blocks_save(monkeypatch, tmp_path, fresh_session):
    monkeypatch.setattr(pm, "PORTFOLIO_FILE", tmp_path / "portfolio.json")
    monkeypatch.setattr(pm, "_get_gist_config", lambda: ("gid12345", "tok"))

    def _boom(*a, **k):
        raise RuntimeError("500 from GitHub")

    monkeypatch.setattr(pm.requests, "get", _boom)
    patched = []
    monkeypatch.setattr(pm.requests, "patch", lambda *a, **k: patched.append(1))

    p = load_portfolio()
    assert pm.portfolio_load_failed()
    assert save_portfolio(p) is False
    assert patched == []


def test_gist_save_failure_still_writes_local(monkeypatch, tmp_path, portfolio, fresh_session):
    import streamlit as st
    path = tmp_path / "portfolio.json"
    monkeypatch.setattr(pm, "PORTFOLIO_FILE", path)
    monkeypatch.setattr(pm, "_get_gist_config", lambda: ("gid12345", "tok"))

    class _Resp:
        status_code = 401

        def raise_for_status(self):
            raise RuntimeError("401")

    monkeypatch.setattr(pm.requests, "patch", lambda *a, **k: _Resp())
    assert save_portfolio(portfolio) is True
    assert st.session_state.get("_portfolio_save_error") == "gist"
    assert json.loads(path.read_text(encoding="utf-8"))["layers"] == portfolio["layers"]


def test_reload_clears_failure(tmp_path, monkeypatch, fresh_session):
    path = tmp_path / "portfolio.json"
    monkeypatch.setattr(pm, "PORTFOLIO_FILE", path)
    path.write_text("garbage", encoding="utf-8")
    load_portfolio()
    assert pm.portfolio_load_failed()

    path.write_text(json.dumps({"layers": {"Core": [{"ticker": "VOO", "shares": 1.0,
                                                     "buy_date": "2024-01-01"}]}}),
                    encoding="utf-8")
    pm.reload_portfolio()
    p = load_portfolio()
    assert not pm.portfolio_load_failed()
    assert "Core" in p["layers"]


# ── Star tier ────────────────────────────────────────────────────────────────

def test_active_tickers_is_held_plus_starred(nosave):
    p = {"layers": {
        "Core": [{"ticker": "VOO", "shares": 1.0, "buy_date": "2024-01-01"}],
        "Watch": [{"ticker": "NVDA", "shares": 0.0, "buy_date": "2024-01-01"},
                  {"ticker": "TSLA", "shares": 0.0, "buy_date": "2024-01-01"}],
    }}
    assert pm.held_tickers(p) == ["VOO"]
    assert pm.active_tickers(p) == ["VOO"]
    pm.set_starred(p, "NVDA", True)
    assert pm.active_tickers(p) == ["NVDA", "VOO"]
    pm.set_starred(p, "NVDA", False)
    assert pm.active_tickers(p) == ["VOO"]


def test_starred_ticker_removed_from_portfolio_is_not_active(nosave):
    p = {"layers": {"Core": [{"ticker": "VOO", "shares": 1.0, "buy_date": "2024-01-01"}]},
         "settings": {"starred": ["GONE"]}}
    assert pm.active_tickers(p) == ["VOO"]
