"""Tests for src/data/batch.py — per-ticker fan-out, failure back-off."""

import pandas as pd
import pytest

from src.data import batch


@pytest.fixture(autouse=True)
def _clean_backoff():
    batch.reset_backoff()
    yield
    batch.reset_backoff()


def test_maps_every_ticker():
    out = batch.map_cached(lambda t, k: f"{t}:{k}", ["A", "B", "C"], "x")
    assert out == {"A": "A:x", "B": "B:x", "C": "C:x"}


def test_failure_returns_default_and_backs_off():
    calls = []

    def flaky(t):
        calls.append(t)
        if t == "BAD":
            raise RuntimeError("429")
        return 1

    out = batch.map_cached(flaky, ["OK", "BAD"], default=0)
    assert out == {"OK": 1, "BAD": 0}
    calls.clear()
    out = batch.map_cached(flaky, ["OK", "BAD"], default=0)
    assert out == {"OK": 1, "BAD": 0}
    assert "BAD" not in calls       # skipped during back-off window
    assert "OK" in calls


def test_backoff_expires(monkeypatch):
    def bad(t):
        raise RuntimeError("boom")

    batch.map_cached(bad, ["X"], default=None)
    monkeypatch.setattr(batch, "BACKOFF_SECONDS", -1)
    calls = []

    def good(t):
        calls.append(t)
        return 5

    good.__name__ = bad.__name__  # same fetcher identity as the failed call
    assert batch.map_cached(good, ["X"]) == {"X": 5}
    assert calls == ["X"]


def test_default_is_copied_per_ticker():
    def bad(t):
        raise RuntimeError("x")

    out = batch.map_cached(bad, ["A", "B"], default=pd.DataFrame(columns=["c"]))
    assert out["A"] is not out["B"]


def test_sequential_mode():
    order = []
    batch.map_cached(lambda t: order.append(t), ["A", "B", "C"], workers=1)
    assert order == ["A", "B", "C"]


def test_empty_input():
    assert batch.map_cached(lambda t: 1, []) == {}
