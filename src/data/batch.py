"""Per-ticker fetch fan-out with a global concurrency cap and failure back-off.

Pattern for slow-changing data (analyst targets, consensus, upgrades, Finviz,
earnings dates):
  * a per-ticker @st.cache_data function does the network call and RAISES on
    failure (Streamlit never caches exceptions, so errors aren't served for 7 days);
  * the public batch function calls map_cached() over the tickers.
Adding one ticker then fetches only that ticker instead of the whole set.

_NET caps simultaneous network requests across every pool in the process —
the loader runs fetchers in parallel and each fetcher fans out again, which
previously put ~50 concurrent requests on Yahoo and triggered 429s.
"""

from concurrent.futures import ThreadPoolExecutor
import threading
import time
from typing import Callable, Dict, Iterable

from src.logger import get_logger

_log = get_logger(__name__)

MAX_CONCURRENT_REQUESTS = 8
BACKOFF_SECONDS = 15 * 60

_NET = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
_failed: Dict[tuple, float] = {}
_failed_lock = threading.Lock()


def _recently_failed(key) -> bool:
    with _failed_lock:
        ts = _failed.get(key)
        if ts is None:
            return False
        if time.monotonic() - ts > BACKOFF_SECONDS:
            del _failed[key]
            return False
        return True


def _record_failure(key) -> None:
    with _failed_lock:
        _failed[key] = time.monotonic()


def map_cached(
    fn: Callable,
    tickers: Iterable[str],
    *args,
    default=None,
    workers: int = 6,
) -> Dict[str, object]:
    """Return {ticker: fn(ticker, *args)} using up to `workers` threads.

    A raising call yields `default` for that ticker and is skipped (not retried)
    for BACKOFF_SECONDS. Each call holds one slot of the global request cap.
    """
    tickers = list(tickers)
    name = getattr(fn, "__name__", repr(fn))

    def _one(t):
        key = (name, t) + tuple(args)
        if _recently_failed(key):
            return t, _copy(default)
        try:
            with _NET:
                return t, fn(t, *args)
        except Exception:
            _record_failure(key)
            _log.warning("Per-ticker fetch failed — backing off",
                         extra={"fetcher": name, "ticker": t})
            return t, _copy(default)

    if not tickers:
        return {}
    if workers <= 1 or len(tickers) == 1:
        return dict(_one(t) for t in tickers)
    with ThreadPoolExecutor(max_workers=min(len(tickers), workers)) as ex:
        return dict(ex.map(_one, tickers))


def _copy(value):
    copier = getattr(value, "copy", None)
    return copier() if callable(copier) else value


def reset_backoff() -> None:
    """Forget recorded failures (tests / manual full refresh)."""
    with _failed_lock:
        _failed.clear()
