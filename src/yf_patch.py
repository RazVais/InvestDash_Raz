# Fix: yfinance's SQLite caches (timezone + cookie, via peewee) crash on Windows
# when called from Streamlit's worker thread. Replace with in-memory caches that
# actually persist data — the built-in Dummies drop every value, forcing re-auth
# on every ticker call and triggering Yahoo rate limits.
# IMPORTANT: This module must be imported FIRST in dashboard.py before any yfinance import.

import datetime as _dt


class _MemTzCache:
    def __init__(self):
        self._d = {}

    def lookup(self, tkr):
        return self._d.get(tkr)

    def store(self, tkr, tz):
        self._d[tkr] = tz


class _MemCookieCache:
    """Matches yfinance's _CookieCache contract: lookup() returns
    {'cookie': ..., 'age': timedelta} (yfinance checks 'age' to refresh daily).
    Returning the bare cookie raised TypeError on every load and forced re-auth.
    """

    def __init__(self):
        self._d = {}

    def lookup(self, strategy):
        entry = self._d.get(strategy)
        if entry is None:
            return None
        cookie, fetched = entry
        return {"cookie": cookie, "age": _dt.datetime.now() - fetched}

    def store(self, strategy, cookie):
        if cookie is None:
            self._d.pop(strategy, None)
        else:
            self._d[strategy] = (cookie, _dt.datetime.now())

    @property
    def Cookie_db(self):
        return None


def apply():
    """Patch yfinance's cache managers. Call once at import time."""
    from yfinance.cache import (
        _CookieCacheManager as _YfCookieMgr,
    )
    from yfinance.cache import (
        _TzCacheManager as _YfTzMgr,
    )
    _YfTzMgr._tz_cache = _MemTzCache()
    _YfCookieMgr._Cookie_cache = _MemCookieCache()


apply()
