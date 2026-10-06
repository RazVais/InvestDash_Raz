"""Tests for src/journal.py persistence and src/ui_helpers escaping."""

import json

import pytest

import src.journal as jr
from src.tabs.trading_journal_ai_tab import _parse
from src.ui_helpers import esc, safe_url


@pytest.fixture
def jfile(tmp_path, monkeypatch):
    path = tmp_path / "trading_journal_ai.json"
    monkeypatch.setattr(jr, "JOURNAL_FILE", path)
    return path


def test_prepend_creates_file(jfile):
    assert jr.prepend_entry({"ticker": "AMD"}) is True
    assert json.loads(jfile.read_text(encoding="utf-8")) == [{"ticker": "AMD"}]


def test_prepend_keeps_existing_entries(jfile):
    jfile.write_text(json.dumps([{"ticker": "OLD"}]), encoding="utf-8")
    jr.prepend_entry({"ticker": "NEW"})
    tickers = [e["ticker"] for e in json.loads(jfile.read_text(encoding="utf-8"))]
    assert tickers == ["NEW", "OLD"]


def test_corrupt_journal_is_never_overwritten(jfile):
    jfile.write_text("[{broken", encoding="utf-8")
    assert jr.prepend_entry({"ticker": "AMD"}) is False
    assert jfile.read_text(encoding="utf-8") == "[{broken"
    assert (jfile.parent / "trading_journal_ai.json.bak").exists()
    with pytest.raises(jr.JournalReadError):
        jr.load_journal()


def test_parse_handles_nested_json():
    reply = ('PART 1: Clean trade.\nPART 2:\n'
             '{"ticker":"NVDA","meta":{"src":"chat"},"result":"Win","actual_r":1.5}')
    p1, flagged, json_str, trade = _parse(reply)
    assert trade["ticker"] == "NVDA"
    assert trade["meta"] == {"src": "chat"}
    assert p1 == "Clean trade."
    assert flagged is False


def test_esc_neutralises_markup():
    assert esc('<script>alert(1)</script>') == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert esc('a"b') == "a&quot;b"
    assert esc(None) == ""


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "data:text/html,x", "", None, "vbscript:x"])
def test_safe_url_rejects_non_http(bad):
    assert safe_url(bad) == "#"


def test_safe_url_keeps_and_escapes_http():
    assert safe_url("https://x.com/a?b=1&c=2") == "https://x.com/a?b=1&amp;c=2"
