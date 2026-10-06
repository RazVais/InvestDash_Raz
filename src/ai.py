"""Claude access layer — one model constant, one client per key, one JSON parser.

Caching convention for every AI feature (see CLAUDE.md "AI cache keys"):
  * The @st.cache_data function is keyed by (ticker, trading_day) only.
    Live inputs (prices, RSI, prompt text) and the API key are passed as
    parameters whose names start with "_" — Streamlit excludes those from the
    cache key, so intraday price ticks don't trigger new Claude calls.
  * Cached functions RAISE on failure. Streamlit never caches exceptions, so a
    transient error is retried on the next run instead of being served for hours.
  * mark_done()/is_done() let a tab show "run AI" buttons for results that
    haven't been computed yet instead of firing calls for every ticker.
"""

import json
import re
import threading
from typing import Dict, List, Optional, Set, Tuple

from src.config import CLAUDE_MODEL
from src.logger import get_logger

_log = get_logger(__name__)

_clients: Dict[str, object] = {}
_lock = threading.Lock()
_done: Set[Tuple] = set()
_calls = {"n": 0}


class AIError(Exception):
    """Claude returned an unusable response (truncated, unparseable, missing fields)."""


def _client(api_key: str):
    with _lock:
        client = _clients.get(api_key)
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, max_retries=2)
            _clients[api_key] = client
    return client


def ask(
    api_key: str,
    max_tokens: int,
    prompt: Optional[str] = None,
    system: Optional[str] = None,
    messages: Optional[List[Dict]] = None,
    purpose: str = "",
    allow_truncated: bool = False,
) -> str:
    """Send one request and return the text.

    Raises AIError on a truncated reply unless allow_truncated — use that for
    prose (a cut-off sentence is still useful); JSON callers must keep the raise,
    and the raise must not loop: a cached function that always raises is
    re-called on every rerun.
    """
    msgs = messages if messages is not None else [{"role": "user", "content": prompt or ""}]
    kwargs = {"model": CLAUDE_MODEL, "max_tokens": max_tokens, "messages": msgs}
    if system:
        kwargs["system"] = system
    with _lock:
        _calls["n"] += 1
        n = _calls["n"]
    _log.info("Claude call", extra={"purpose": purpose, "call_no": n})
    resp = _client(api_key).messages.create(**kwargs)
    if getattr(resp, "stop_reason", None) == "max_tokens":
        if not allow_truncated:
            raise AIError("תגובת AI קוצצה (max_tokens)")
        _log.warning("Claude reply truncated", extra={"purpose": purpose, "max_tokens": max_tokens})
    return resp.content[0].text.strip()


def call_count() -> int:
    """Number of Claude requests made by this process (for logs / verification)."""
    return _calls["n"]


def strip_fences(text: str) -> str:
    """Remove markdown code fences (```json / ``` with \\n or \\r\\n)."""
    text = re.sub(r"```[a-zA-Z]*[\r\n]*", "", text)
    return text.strip()


def parse_json(text: str) -> Optional[dict]:
    """Return the first JSON object in text, tolerating fences, prose around it,
    nested objects and trailing commas. None if nothing parses."""
    if not text:
        return None
    text = strip_fences(text)
    dec = json.JSONDecoder()
    i = text.find("{")
    while i != -1:
        try:
            obj, _ = dec.raw_decode(text, i)
            if isinstance(obj, dict):
                return obj
        except ValueError:
            pass
        i = text.find("{", i + 1)
    # Last resort: trailing commas (common LLM mistake) inside the outermost braces
    start, end = text.find("{"), text.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(re.sub(r",\s*([}\]])", r"\1", text[start:end]))
        return obj if isinstance(obj, dict) else None
    except ValueError:
        return None


def mark_done(kind: str, *key) -> None:
    """Record that an AI result exists in cache for (kind, *key)."""
    with _lock:
        _done.add((kind,) + tuple(key))


def is_done(kind: str, *key) -> bool:
    with _lock:
        return (kind,) + tuple(key) in _done


def claim_warmup(key) -> bool:
    """True exactly once per key per process — used to run the AI pre-warm once a day.

    Must live in an imported module: dashboard.py is re-executed on every rerun,
    so module-level state there resets each time.
    """
    with _lock:
        token = ("_warmup", key)
        if token in _done:
            return False
        _done.add(token)
        return True


_key_locks: Dict[Tuple, threading.Lock] = {}


def key_lock(*key) -> threading.Lock:
    """Per-result lock: concurrent callers (background warmup, tab pre-warm, card
    render) wait for the first one, then hit the cache instead of each calling Claude."""
    with _lock:
        lk = _key_locks.get(key)
        if lk is None:
            lk = _key_locks[key] = threading.Lock()
        return lk
