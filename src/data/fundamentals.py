"""Fundamental data via finvizfinance."""

import time

import streamlit as st

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


@st.cache_data(ttl=86400 * 7)
def get_finviz_fundamentals(tickers, trading_day):
    _log.info("get_finviz_fundamentals entry", extra={"tickers": list(tickers), "trading_day": trading_day})
    if not FINVIZ_AVAILABLE:
        _log.warning("finvizfinance not available; skipping fundamentals fetch")
        return {t: {} for t in tickers}

    result = {}
    for t in tickers:
        try:
            raw = fvf(t).ticker_fundament()
            mapped = {new: raw.get(orig, "-") for orig, new in _FIELDS.items()}
            if not any(v not in ("-", None, "") for v in mapped.values()):
                _log.warning("Finviz returned empty fundamentals for ticker", extra={"ticker": t})
            result[t] = mapped
        except Exception:
            _log.error("get_finviz_fundamentals failed for ticker", exc_info=True, extra={"ticker": t})
            result[t] = {}
        time.sleep(0.3)  # Finviz rate-limit — do not remove
    return result
