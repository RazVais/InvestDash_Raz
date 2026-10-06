"""Tests for src/ai.py — JSON parsing, done-tracking, and the warmup guard."""

import pytest

from src import ai


@pytest.mark.parametrize("text, expected", [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('```JSON\r\n{"a": 1}\r\n```', {"a": 1}),
    ('Sure! Here it is:\n{"a": {"b": [1, 2]}} hope that helps', {"a": {"b": [1, 2]}}),
    ('{"a": 1, "b": [1, 2,],}', {"a": 1, "b": [1, 2]}),   # trailing commas
    ('no json here', None),
    ('', None),
])
def test_parse_json(text, expected):
    assert ai.parse_json(text) == expected


def test_parse_json_skips_non_object_brace_noise():
    assert ai.parse_json('range {x} then {"ok": true}') == {"ok": True}


def test_mark_and_is_done():
    assert not ai.is_done("unit_test_kind", "AMD", "2026-01-02")
    ai.mark_done("unit_test_kind", "AMD", "2026-01-02")
    assert ai.is_done("unit_test_kind", "AMD", "2026-01-02")
    assert not ai.is_done("unit_test_kind", "AMD", "2026-01-03")


def test_claim_warmup_once_per_key():
    key = ("2026-01-02", ("AMD", "VOO"), "unit")
    assert ai.claim_warmup(key) is True
    assert ai.claim_warmup(key) is False
    assert ai.claim_warmup(("2026-01-05", ("AMD", "VOO"), "unit")) is True


def test_ask_raises_on_truncation(monkeypatch):
    class _Resp:
        stop_reason = "max_tokens"
        content = []

    class _Client:
        class messages:  # noqa: N801 — mimics the SDK attribute
            @staticmethod
            def create(**kwargs):
                return _Resp()

    monkeypatch.setattr(ai, "_client", lambda key: _Client())
    with pytest.raises(ai.AIError):
        ai.ask("k", 10, "hi")


def test_ask_counts_calls_and_passes_model(monkeypatch):
    seen = {}

    class _Block:
        text = "  ok  "

    class _Resp:
        stop_reason = "end_turn"
        content = [_Block()]

    class _Client:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                seen.update(kwargs)
                return _Resp()

    monkeypatch.setattr(ai, "_client", lambda key: _Client())
    n0 = ai.call_count()
    assert ai.ask("k", 10, "hi", system="sys") == "ok"
    assert ai.call_count() == n0 + 1
    assert seen["model"] == ai.CLAUDE_MODEL
    assert seen["system"] == "sys"
