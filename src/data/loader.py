"""Central data loader — two-tier parallel loading with background cache warming.

Tier 1 (immediate, parallel):
  Keys required by the active tab + sidebar — fetched together in a ThreadPoolExecutor
  and returned before the tab renders.

Tier 2 (deferred, background):
  Remaining keys are warmed in a daemon thread so that when the user navigates to
  another tab the data is already in @st.cache_data and renders instantly.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx

from src.data.analysts import (
    get_analyst_targets,
    get_consensus,
    get_earnings_dates,
    get_upgrades_downgrades,
)
from src.data.fundamentals import FINVIZ_AVAILABLE, get_finviz_fundamentals
from src.data.macro import get_commodity_prices, get_macro_indicators
from src.data.news import get_news
from src.data.prices import get_stock_data
from src.logger import get_logger
from src.portfolio import all_tickers

_log = get_logger(__name__)

# ── Tab → data dependency map ─────────────────────────────────────────────────
_TAB_NEEDS = {
    "סקירה":        frozenset(["prices", "targets", "consensus", "macro"]),
    "תיק שלי":      frozenset(["prices"]),
    "גרפים":        frozenset(["prices", "targets"]),
    "אנליסטים":     frozenset(["prices", "consensus", "targets", "upgrades"]),
    "פונדמנטלס":   frozenset(["prices", "fundamentals", "earnings"]),
    "דגלים אדומים": frozenset(["prices", "consensus", "upgrades", "commodities"]),
    "חדשות":        frozenset(["news"]),
    "💡 המלצות":    frozenset(["prices", "targets", "consensus"]),
    "📋 יומי":      frozenset(["prices", "consensus", "targets", "upgrades"]),
    "🔬 ניתוח":     frozenset(["prices"]),
}

# Keys the sidebar always needs (flag summary + macro strip)
_SIDEBAR_NEEDS = frozenset(["prices", "consensus", "upgrades", "commodities", "macro"])

_ALL_KEYS = frozenset([
    "prices", "targets", "consensus", "upgrades",
    "earnings", "fundamentals", "macro", "commodities", "news",
])

# Empty defaults returned for keys not yet loaded
_EMPTY: dict = {
    "prices":       {},
    "targets":      {},
    "consensus":    {},
    "upgrades":     {},
    "fundamentals": {},
    "earnings":     {},
    "macro":        {"vix": None, "yield_10y": None, "dxy": None},
    "commodities":  {"gold": None, "copper": None, "uranium": None},
    "news":         {},
}

# Module-level event so background warming survives Streamlit reruns
_bg_done = threading.Event()
_bg_done.set()  # "idle" at startup


# ── Fetcher dispatcher ────────────────────────────────────────────────────────

def _call_fetcher(name, tickers, td, api_key):
    """Run one fetcher by name; returns (name, result)."""
    try:
        if name == "prices":
            return name, get_stock_data(tickers, td)
        if name == "targets":
            return name, get_analyst_targets(tickers, td)
        if name == "consensus":
            return name, get_consensus(tickers, td, api_key)
        if name == "upgrades":
            return name, get_upgrades_downgrades(tickers, td)
        if name == "earnings":
            return name, get_earnings_dates(tickers, td)
        if name == "fundamentals":
            res = get_finviz_fundamentals(tickers, td) if FINVIZ_AVAILABLE else {}
            return name, res
        if name == "macro":
            return name, get_macro_indicators(td)
        if name == "commodities":
            return name, get_commodity_prices(td)
        if name == "news":
            return name, get_news(tickers, td)
    except Exception:
        _log.error("Fetcher error", exc_info=True, extra={"name": name})
    return name, _EMPTY.get(name, {})


def _warm_background(names, tickers, td, api_key):
    """Daemon thread: pre-warm @st.cache_data for deferred keys."""
    _log.info("Background warming started", extra={"keys": sorted(names)})
    for name in names:
        _call_fetcher(name, tickers, td, api_key)
    _bg_done.set()
    _log.info("Background warming complete")


# ── Public entry point ────────────────────────────────────────────────────────

def load_all_data(portfolio, market_state, api_key="", active_tab="סקירה"):
    """
    Fetch data for the active tab immediately (parallel), then warm the
    remaining keys in a background daemon thread.

    Returns a data dict with defaults for any deferred keys.
    data["_deferred"] = frozenset of keys not yet loaded this call.
    """
    tickers = tuple(sorted(all_tickers(portfolio)))
    td      = str(market_state["last_trading_day"])

    _log.info("load_all_data", extra={
        "tickers": list(tickers), "trading_day": td, "tab": active_tab,
    })

    # Keys to load right now
    needed   = (_TAB_NEEDS.get(active_tab, frozenset()) | _SIDEBAR_NEEDS) & _ALL_KEYS
    deferred = _ALL_KEYS - needed

    data = dict(_EMPTY)

    if tickers:
        with st.spinner("טוען נתונים..."), ThreadPoolExecutor(max_workers=min(len(needed), 8)) as ex:
            futures = {
                ex.submit(_call_fetcher, name, tickers, td, api_key): name
                for name in needed
            }
            for fut in as_completed(futures):
                name, result = fut.result()
                data[name] = result

        # Start background warming only when idle (avoid stacking threads)
        if deferred and _bg_done.is_set():
            _bg_done.clear()
            t = threading.Thread(
                target=_warm_background,
                args=(list(deferred), tickers, td, api_key),
                daemon=True,
            )
            add_script_run_ctx(t)
            t.start()

    data["_market_open"] = market_state.get("is_open", False)
    data["_deferred"]    = deferred
    return data
