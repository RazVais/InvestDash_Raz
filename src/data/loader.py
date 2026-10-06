"""Central data loader — two-tier parallel loading with background cache warming.

Tier 1 (immediate, parallel):
  Keys required by the active tab + sidebar — fetched together in a ThreadPoolExecutor
  and returned before the tab renders.

Tier 2 (deferred, background):
  Remaining keys are warmed in a daemon thread so that when the user navigates to
  another tab the data is already in @st.cache_data and renders instantly.

Ticker tiers:
  * prices / macro / commodities — every ticker in the portfolio (incl. watch-only)
  * analyst, fundamentals, earnings, news — active tickers only (held ∪ starred);
    archive-tier watch names are price-only, which keeps fetch volume and
    Yahoo/Finviz rate limiting down.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import contextlib
import threading

import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx

from src.config import HE, ILS_USD_FALLBACK, is_tase_numeric
from src.data.analysts import (
    get_analyst_targets,
    get_consensus,
    get_earnings_dates,
    get_eps_trend,
    get_upgrades_downgrades,
)
from src.data.damodaran import get_damodaran_sector_data
from src.data.fundamentals import FINVIZ_AVAILABLE, get_finviz_fundamentals
from src.data.macro import get_commodity_prices, get_ils_usd_rate, get_macro_indicators
from src.data.news import get_company_profile, get_news
from src.data.prices import get_info_snapshot, get_intraday_data, get_stock_data, merge_info
from src.logger import get_logger
from src.portfolio import active_tickers, all_tickers

_log = get_logger(__name__)

# ── Tab → data dependency map ─────────────────────────────────────────────────
_TAB_NEEDS = {
    HE["tab_today"]:    frozenset(["prices", "consensus", "targets", "upgrades", "macro",
                                   "earnings", "commodities"]),
    HE["tab_holdings"]: frozenset(["prices", "targets", "consensus", "upgrades", "macro",
                                   "fundamentals", "earnings"]),
    HE["tab_ticker"]:   frozenset(["prices", "targets", "consensus", "fundamentals", "news"]),
    HE["tab_practice"]: frozenset(["prices"]),
    "דגלים אדומים":     frozenset(["prices", "consensus", "upgrades", "commodities"]),
}

# Fetchers that only run for active tickers (held ∪ starred)
_ACTIVE_ONLY = frozenset(["info", "targets", "consensus", "upgrades", "earnings", "fundamentals", "news"])

# Keys the sidebar always needs (flag summary + macro strip)
_SIDEBAR_NEEDS = frozenset(["prices", "info", "consensus", "upgrades", "commodities", "macro"])

_ALL_KEYS = frozenset([
    "prices", "info", "targets", "consensus", "upgrades",
    "earnings", "fundamentals", "macro", "commodities", "news",
])

# Empty defaults returned for keys not yet loaded
_EMPTY: dict = {
    "prices":       {},
    "info":         {},
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

def _call_fetcher(name, tickers, td, api_key, active=None):
    """Run one fetcher by name; returns (name, result).

    `active` (held ∪ starred) replaces `tickers` for the _ACTIVE_ONLY fetchers.
    """
    if name in _ACTIVE_ONLY and active is not None:
        tickers = active
    if not tickers:
        return name, _EMPTY.get(name, {})
    try:
        if name == "prices":
            return name, get_stock_data(tickers, td)
        if name == "info":
            return name, get_info_snapshot(tickers)
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
        _log.error("Fetcher error", exc_info=True, extra={"fetcher": name})
    return name, _EMPTY.get(name, {})


def _safe_warm(fn, *args):
    """Call fn(*args) silently — used in Tier 3 background warming."""
    with contextlib.suppress(Exception):
        fn(*args)


def _warm_lazy(tickers, td):
    """Tier 3: pre-warm per-tab lazy fetches not covered by the 9-key core dict.

    Covers:
      - Damodaran sector benchmarks (analysts / buy-timing tab)
      - EPS trend per non-TASE ticker (fundamentals tab)
      - Company profile per non-TASE ticker (news tab)
    """
    non_tase = [t for t in tickers if not is_tase_numeric(t)]
    tasks = [(get_damodaran_sector_data, ())]
    for t in non_tase:
        tasks.append((get_eps_trend, (t, td)))
        tasks.append((get_company_profile, (t, td)))
    with ThreadPoolExecutor(max_workers=min(len(tasks), 6)) as ex:
        for fn, args in tasks:
            ex.submit(_safe_warm, fn, *args)


def _warm_background(names, tickers, td, api_key, active):
    """Daemon thread: Tier 2 (core keys, parallel) then Tier 3 (per-tab lazy fetches)."""
    _log.info("Background warming started", extra={"keys": sorted(names)})
    try:
        with ThreadPoolExecutor(max_workers=min(len(names), 4) or 1) as ex:
            list(ex.map(lambda n: _call_fetcher(n, tickers, td, api_key, active), names))
        _warm_lazy(active, td)
        _log.info("Background warming complete")
    except Exception:
        _log.warning("Background warming aborted", exc_info=True)
    finally:
        _bg_done.set()  # always re-arm, or warming stops for the process lifetime


# ── Refresh ───────────────────────────────────────────────────────────────────

def refresh_live():
    """Drop only the intraday-sensitive caches (prices, intraday, macro, news).

    Analyst / Finviz / Damodaran / buy-price / FX caches (7-30d) and the
    per-day AI results survive — clearing them caused full re-fetches and
    re-ran every Claude call.
    """
    for fn in (get_stock_data, get_intraday_data, get_macro_indicators, get_news):
        with contextlib.suppress(Exception):
            fn.clear()
    _log.info("Live caches cleared")


# ── Public entry point ────────────────────────────────────────────────────────

def load_all_data(portfolio, market_state, api_key="", active_tab=HE["tab_today"]):
    """
    Fetch data for the active tab immediately (parallel), then warm the
    remaining keys in a background daemon thread.

    Returns a data dict with defaults for any deferred keys.
    data["_deferred"] = frozenset of keys not yet loaded this call.
    """
    tickers = tuple(sorted(all_tickers(portfolio)))
    active  = tuple(active_tickers(portfolio))
    td      = str(market_state["last_trading_day"])

    _log.info("load_all_data", extra={
        "n_tickers": len(tickers), "n_active": len(active), "trading_day": td, "tab": active_tab,
    })

    # Keys to load right now
    needed   = (_TAB_NEEDS.get(active_tab, frozenset()) | _SIDEBAR_NEEDS) & _ALL_KEYS
    deferred = _ALL_KEYS - needed

    data = dict(_EMPTY)

    if tickers:
        with st.spinner("טוען נתונים..."), ThreadPoolExecutor(max_workers=min(len(needed), 8)) as ex:
            futures = {
                ex.submit(_call_fetcher, name, tickers, td, api_key, active): name
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
                args=(list(deferred), tickers, td, api_key, active),
                daemon=True,
            )
            add_script_run_ctx(t)
            t.start()

    merge_info(data["prices"], data.get("info"))  # beta / P/E / sector for active tickers

    try:
        data["ils_usd"] = get_ils_usd_rate()  # 7d cache; every USD total needs it
    except Exception:
        data["ils_usd"] = ILS_USD_FALLBACK
    data["_market_open"] = market_state.get("is_open", False)
    data["_deferred"]    = deferred
    return data
