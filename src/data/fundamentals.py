"""Fundamental data via finvizfinance."""

import time

import streamlit as st

from src.config import is_tase_numeric
from src.data.batch import map_cached
from src.logger import get_logger

_log = get_logger(__name__)

try:
    from finvizfinance.quote import finvizfinance as fvf
    FINVIZ_AVAILABLE = True
except ImportError:
    FINVIZ_AVAILABLE = False

_FIELDS = {
    "P/E":          "pe",
    "Forward P/E":  "forward_pe",
    "PEG":          "peg",
    "EPS (ttm)":    "eps_ttm",
    "EPS next Y":   "eps_next_y",
    "EPS next Q":   "eps_next_q",
    "Short Float":  "short_float",
    "Inst Own":     "inst_own",
    "ROE":          "roe",
    "ROA":          "roa",
    "Market Cap":   "market_cap",
    "Sector":       "sector",
    "Industry":     "industry",
    "Dividend %":   "div_yield_fv",
    "Payout":       "payout",
    "P/B":          "pb",
    "P/S":          "ps",
    "Debt/Eq":      "debt_eq",
    "52W High":     "high_52w_fv",
    "52W Low":      "low_52w_fv",
    "Beta":         "beta_fv",
    "ATR":          "atr",
    "RSI (14)":     "rsi_fv",
}


@st.cache_data(ttl=86400 * 7, show_spinner=False)
def _finviz_one(t):
    """Finviz snapshot for one ticker. Raises on fetch errors (not cached)."""
    if is_tase_numeric(t):
        return {}
    try:
        raw = fvf(t).ticker_fundament()
    except Exception as exc:
        # Finviz answers 403 when it blocks scrapers — expected, no traceback spam
        _log.warning("Finviz fetch failed", extra={"ticker": t, "error": str(exc)[:120]})
        raise
    finally:
        time.sleep(0.3)  # Finviz rate-limit — do not remove
    mapped = {new: raw.get(orig, "-") for orig, new in _FIELDS.items()}
    if not any(v not in ("-", None, "") for v in mapped.values()):
        _log.warning("Finviz returned empty fundamentals for ticker", extra={"ticker": t})
    return mapped


def get_finviz_fundamentals(tickers, trading_day=None):
    """{ticker: fundamentals dict}. Cached per ticker for 7 days; sequential for Finviz."""
    if not FINVIZ_AVAILABLE:
        _log.warning("finvizfinance not available; skipping fundamentals fetch")
        return {t: {} for t in tickers}
    return map_cached(_finviz_one, tickers, default={}, workers=1)
