"""Macro indicators: VIX, US 10-year yield, DXY dollar index."""

from concurrent.futures import ThreadPoolExecutor

import streamlit as st
import yfinance as yf

from src.config import COMMODITY_SYMBOLS, MACRO_SYMBOLS
from src.logger import get_logger

_log = get_logger(__name__)


def _fetch_one_macro(args):
    key, sym = args
    try:
        hist = yf.Ticker(sym).history(period="7d")
        if not hist.empty:
            close = hist["Close"].dropna()
            if not close.empty:
                return key, float(close.iloc[-1]), close.tolist()[-7:]
        _log.warning("Macro indicator returned no data", extra={"key": key, "symbol": sym})
    except Exception:
        _log.error("Macro indicator fetch failed", exc_info=True, extra={"key": key, "symbol": sym})
    return key, None, []


@st.cache_data(ttl=1800)
def get_macro_indicators(trading_day):
    """Return {vix, yield_10y, dxy, vix_hist, yield_10y_hist, dxy_hist} — parallel fetch."""
    _log.info("get_macro_indicators entry", extra={"trading_day": trading_day})
    items = list(MACRO_SYMBOLS.items())
    result = {}
    with ThreadPoolExecutor(max_workers=len(items)) as ex:
        for key, val, hist_list in ex.map(_fetch_one_macro, items):
            result[key]             = val
            result[key + "_hist"]   = hist_list
    return result


def _fetch_one_commodity(args):
    key, sym, divisor = args
    try:
        hist = yf.Ticker(sym).history(period="5d")
        if not hist.empty:
            price = float(hist["Close"].dropna().iloc[-1])
            if divisor and price > 20:
                price /= divisor
            return key, price
        _log.warning("No price history for commodity", extra={"key": key, "symbol": sym})
    except Exception:
        _log.error("Commodity price fetch failed", exc_info=True, extra={"key": key, "symbol": sym})
    return key, None


@st.cache_data(ttl=86400 * 7)
def get_commodity_prices(trading_day):
    """Return {gold, copper, uranium} spot prices — parallel."""
    _log.info("get_commodity_prices entry", extra={"trading_day": trading_day})
    items = [(k, s, d) for k, (s, d) in COMMODITY_SYMBOLS.items()]
    with ThreadPoolExecutor(max_workers=len(items)) as ex:
        return dict(ex.map(_fetch_one_commodity, items))
