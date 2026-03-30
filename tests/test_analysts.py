"""Tests for src/data/analysts.py — _consensus_label (pure function)."""

from src.data.analysts import _consensus_label


def test_no_analysts_returns_na():
    assert _consensus_label(0, 0, 0, 0, 0, 0) == "N/A"


def test_strong_buy_at_70pct():
    # 7 strong_buy + 1 buy = 80% → Strong Buy
    assert _consensus_label(7, 1, 2, 0, 0, 10) == "Strong Buy"


def test_strong_buy_exactly_70pct():
    # 7 buy out of 10 = 70% → Strong Buy (>= 0.70)
    assert _consensus_label(0, 7, 3, 0, 0, 10) == "Strong Buy"


def test_buy_at_60pct():
    # 6 buy out of 10 = 60% → Buy (>= 0.50 but < 0.70)
    assert _consensus_label(0, 6, 4, 0, 0, 10) == "Buy"


def test_buy_exactly_50pct():
    # 5 buy out of 10 = 50% → Buy (>= 0.50)
    assert _consensus_label(0, 5, 5, 0, 0, 10) == "Buy"


def test_sell_at_40pct():
    # 4 sell out of 10 = 40% → Sell
    assert _consensus_label(0, 3, 3, 3, 1, 10) == "Sell"


def test_hold_when_no_dominant_view():
    # 3 buy, 3 hold, 2 sell out of 8 — none dominant
    assert _consensus_label(0, 3, 3, 2, 0, 8) == "Hold"


def test_strong_sell_counts_toward_sell_fraction():
    # 0 sell + 5 strong_sell = 50% → Sell
    assert _consensus_label(0, 0, 5, 0, 5, 10) == "Sell"


def test_buy_beats_sell_threshold():
    # 6 buy, 4 sell: buy_pct=60% >= 50%; sell takes precedence only if >=40%
    # sell_pct = 40% and buy_pct = 60% — buy wins (Strong Buy / Buy check first)
    result = _consensus_label(0, 6, 0, 4, 0, 10)
    assert result == "Buy"
