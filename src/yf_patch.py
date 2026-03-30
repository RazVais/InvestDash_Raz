# Fix: yfinance's SQLite caches (timezone + cookie, via peewee) crash on Windows
# when called from Streamlit's worker thread. Replace with in-memory caches that
# actually persist data — the built-in Dummies drop every value, forcing re-auth
# on every ticker call and triggering Yahoo rate limits.
# IMPORTANT: This module must be imported FIRST in dashboard.py before any yfinance import.

class _MemTzCache:
    def __init__(self):
        self._d = {}

    def lookup(self, tkr):
        return self._d.get(tkr)

    def store(self, tkr, tz):
        self._d[tkr] = tz


class _MemCookieCache:
    def __init__(self):
        self._d = {}

    def lookup(self, tkr):
        return self._d.get(tkr)

    def store(self, tkr, cookie):
        self._d[tkr] = cookie

    @property
    def Cookie_db(self):
        return None


def apply():
    """Patch yfinance's cache managers. Call once at import time."""
    from yfinance.cache import (
        _TzCacheManager as _YfTzMgr,
        _CookieCacheManager as _YfCookieMgr,
    )
    _YfTzMgr._tz_cache = _MemTzCache()
    _YfCookieMgr._Cookie_cache = _MemCookieCache()


apply()
