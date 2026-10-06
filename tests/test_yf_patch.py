"""src/yf_patch.py must honour yfinance's cookie-cache contract."""

import datetime as dt

import src.yf_patch as yp


def test_cookie_lookup_returns_dict_with_age():
    c = yp._MemCookieCache()
    assert c.lookup("basic") is None
    c.store("basic", "COOKIE")
    entry = c.lookup("basic")
    assert entry["cookie"] == "COOKIE"
    assert isinstance(entry["age"], dt.timedelta)
    assert entry["age"] < dt.timedelta(days=1)


def test_cookie_store_none_clears():
    c = yp._MemCookieCache()
    c.store("basic", "COOKIE")
    c.store("basic", None)
    assert c.lookup("basic") is None


def test_patch_is_installed():
    from yfinance.cache import _CookieCacheManager
    assert isinstance(_CookieCacheManager._Cookie_cache, yp._MemCookieCache)
