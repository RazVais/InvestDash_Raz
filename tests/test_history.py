"""Tests for src/history.py — snapshots, time-weighted returns, rebalancing, sizing."""

import pandas as pd
import pytest

from src import history as hx


def _row(date, value, shares, px, voo=100.0, **kw):
    return {"date": date, "value_usd": value, "cost_usd": None, "voo_close": voo,
            "shares": shares, "px": px, "by_layer": {}, "provisional": False, **kw}


# ── upsert ────────────────────────────────────────────────────────────────────

def test_upsert_appends_and_is_idempotent_for_final_rows():
    snaps = []
    assert hx.upsert_snapshot(snaps, _row("2026-01-02", 100, {}, {})) is True
    assert hx.upsert_snapshot(snaps, _row("2026-01-02", 999, {}, {})) is False
    assert snaps[0]["value_usd"] == 100


def test_provisional_row_replaced_by_final():
    snaps = [_row("2026-01-02", 100, {}, {}, provisional=True)]
    assert hx.upsert_snapshot(snaps, _row("2026-01-02", 101, {}, {})) is True
    assert snaps[0]["provisional"] is False and snaps[0]["value_usd"] == 101


def test_provisional_not_rewritten_for_tiny_moves():
    snaps = [_row("2026-01-02", 100, {}, {}, provisional=True)]
    assert hx.upsert_snapshot(snaps, _row("2026-01-02", 100.2, {}, {}, provisional=True)) is False


def test_rows_kept_sorted():
    snaps = [_row("2026-01-05", 1, {}, {})]
    hx.upsert_snapshot(snaps, _row("2026-01-02", 1, {}, {}))
    assert [r["date"] for r in snaps] == ["2026-01-02", "2026-01-05"]


# ── time-weighted returns ─────────────────────────────────────────────────────

def test_buying_more_is_a_flow_not_a_gain():
    snaps = [
        _row("2026-01-02", 1000, {"A": 10}, {"A": 100}),
        _row("2026-01-05", 2200, {"A": 20}, {"A": 110}),  # bought 10 @110, price +10%
    ]
    perf = hx.performance_frame(snaps)
    assert perf["flow"].iloc[-1] == pytest.approx(1100)
    assert perf["ret"].iloc[-1] == pytest.approx(0.10)     # not +120%


def test_selling_is_a_withdrawal_not_a_loss():
    snaps = [
        _row("2026-01-02", 2000, {"A": 20}, {"A": 100}),
        _row("2026-01-05", 1000, {"A": 10}, {"A": 100}),   # sold half, price flat
    ]
    perf = hx.performance_frame(snaps)
    assert perf["flow"].iloc[-1] == pytest.approx(-1000)
    assert perf["ret"].iloc[-1] == pytest.approx(0.0)


def test_drawdown_and_voo_index():
    snaps = [
        _row("2026-01-02", 100, {"A": 1}, {"A": 100}, voo=50),
        _row("2026-01-05", 120, {"A": 1}, {"A": 120}, voo=55),
        _row("2026-01-06", 90,  {"A": 1}, {"A": 90},  voo=50),
    ]
    perf = hx.performance_frame(snaps)
    assert perf["index"].iloc[-1] == pytest.approx(90)
    assert perf["drawdown"].min() == pytest.approx(90 / 120 - 1)
    assert perf["voo_index"].iloc[1] == pytest.approx(110)


def test_last_change_and_period_return():
    snaps = [
        _row("2026-01-02", 100, {"A": 1}, {"A": 100}, voo=100),
        _row("2026-02-02", 110, {"A": 1}, {"A": 110}, voo=105),
    ]
    perf = hx.performance_frame(snaps)
    lc = hx.last_change(perf)
    assert lc["pct"] == pytest.approx(10.0)
    assert lc["voo_pct"] == pytest.approx(5.0)
    assert hx.period_return(perf, "index", days=40) == pytest.approx(10.0)


def test_performance_frame_needs_two_rows():
    assert hx.performance_frame([_row("2026-01-02", 1, {}, {})]).empty


# ── snapshot_row / reconstruct ────────────────────────────────────────────────

def _entry(price, n=10, currency="USD"):
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    close = pd.Series([price] * n, index=idx, dtype=float)
    return {"price": price, "currency": currency, "history": close,
            "ohlcv": pd.DataFrame({"Close": close})}


def test_snapshot_row_converts_tase_and_skips_incomplete():
    pf = {"layers": {"Core (50%)": [
        {"ticker": "VOO", "shares": 2.0, "buy_date": "2026-01-01", "buy_price": 90.0},
        {"ticker": "1146356", "shares": 100.0, "buy_date": "2026-01-01", "buy_price": 20.0},
    ]}}
    data = {"prices": {"VOO": _entry(100.0), "1146356": _entry(30.0, currency="ILS")},
            "ils_usd": 0.25}
    row = hx.snapshot_row(pf, data, "2026-01-14", provisional=False)
    assert row["value_usd"] == pytest.approx(200 + 750)
    assert row["px"]["1146356"] == pytest.approx(7.5)
    del data["prices"]["1146356"]
    assert hx.snapshot_row(pf, data, "2026-01-14", provisional=False) is None


def test_reconstruct_counts_lots_from_buy_date():
    pf = {"layers": {"L": [
        {"ticker": "VOO", "shares": 1.0, "buy_date": "2026-01-01", "buy_price": 100.0},
        {"ticker": "VOO", "shares": 1.0, "buy_date": "2026-01-08", "buy_price": 100.0},
    ]}}
    rows = hx.reconstruct_history(pf, {"prices": {"VOO": _entry(100.0)}})
    by_date = {r["date"]: r["value_usd"] for r in rows}
    assert by_date["2026-01-01"] == 100 and by_date["2026-01-08"] == 200
    assert all(r["reconstructed"] for r in rows)
    perf = hx.performance_frame(rows)
    assert perf["ret"].abs().max() == pytest.approx(0.0)   # the 2nd buy is a flow


def test_merge_reconstructed_never_overwrites_real_rows():
    snaps = [_row("2026-01-02", 555, {}, {})]
    added = hx.merge_reconstructed(snaps, [_row("2026-01-02", 1, {}, {}, reconstructed=True),
                                           _row("2026-01-01", 1, {}, {}, reconstructed=True)])
    assert added == 1
    assert {r["date"]: r["value_usd"] for r in snaps}["2026-01-02"] == 555


# ── targets & rebalancing ─────────────────────────────────────────────────────

def test_default_targets_from_layer_names():
    t = hx.default_layer_targets(["Core (50%)", "Compute", "Security"])
    assert t == {"Core (50%)": 50.0, "Compute": 25.0, "Security": 25.0}


def test_rebalance_new_cash_goes_to_underweight_layers():
    plan = hx.rebalance_plan({"Core": 400.0, "Growth": 600.0},
                             {"Core": 50.0, "Growth": 50.0}, new_cash=200.0)
    by = plan.set_index("layer")
    # after deposit total 1200 → each target 600; Core short 200, Growth 0
    assert by.loc["Core", "buy_usd"] == pytest.approx(200.0)
    assert by.loc["Growth", "buy_usd"] == pytest.approx(0.0)
    assert by.loc["Core", "drift_pp"] == pytest.approx(-10.0)
    assert plan["buy_usd"].sum() == pytest.approx(200.0)


def test_rebalance_excess_cash_spread_by_target():
    plan = hx.rebalance_plan({"A": 500.0, "B": 500.0}, {"A": 50.0, "B": 50.0}, new_cash=100.0)
    assert plan["buy_usd"].sum() == pytest.approx(100.0)


# ── position sizing ───────────────────────────────────────────────────────────

def test_position_size_basic():
    r = hx.position_size(account_usd=20_000, risk_pct=1.0, entry=100.0, stop=95.0)
    assert r["shares"] == 40                 # $200 risk / $5 per share
    assert r["position_pct"] == pytest.approx(20.0)
    assert r["stop_pct"] == pytest.approx(5.0)


def test_position_size_converts_nis():
    r = hx.position_size(account_usd=20_000, risk_pct=1.0, entry=40.0, stop=38.0, fx=0.25)
    assert r["shares"] == 400                # $200 / (₪2 × 0.25)


@pytest.mark.parametrize("entry, stop", [(100, 100), (100, 120), (0, 5), (100, 0)])
def test_position_size_invalid(entry, stop):
    assert hx.position_size(20_000, 1.0, entry, stop) is None


# ── record_daily_snapshot timing ──────────────────────────────────────────────

@pytest.mark.parametrize("state, expect_rows, provisional", [
    ({"status_label": "Pre-Market", "is_open": False}, 0, None),
    ({"status_label": "Open", "is_open": True}, 1, True),
    ({"status_label": "After Hours", "is_open": False}, 1, False),
])
def test_record_snapshot_respects_market_state(monkeypatch, state, expect_rows, provisional):
    import src.tabs.planning_tab as pt
    saved = []
    monkeypatch.setattr(pt, "save_portfolio", lambda p: saved.append(1))
    pf = {"layers": {"L": [{"ticker": "VOO", "shares": 1.0, "buy_date": "2026-01-01",
                            "buy_price": 90.0}]}}
    pt.record_daily_snapshot(pf, {"prices": {"VOO": _entry(100.0)}}, "2026-01-14", state)
    snaps = pf.get("snapshots", [])
    assert len(snaps) == expect_rows
    assert len(saved) == expect_rows
    if expect_rows:
        assert snaps[0]["provisional"] is provisional
