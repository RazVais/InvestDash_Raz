"""Central data loader — orchestrates all fetchers and returns a single data dict."""

import streamlit as st

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


def load_all_data(portfolio, market_state, api_key=""):
    """
    Fetch all data sources and return a unified dict.
    trading_day is used as cache key — market-closed state serves cached data.

    Returns:
      data["prices"]       {ticker: {price, change, beta, div_yield, ohlcv, high_52w, low_52w, history}}
      data["targets"]      {ticker: {mean, low, high, median, count}}
      data["consensus"]    {ticker: {strong_buy, buy, hold, sell, strong_sell, total, label}}
      data["upgrades"]     {ticker: DataFrame}
      data["fundamentals"] {ticker: {pe, forward_pe, ...}}
      data["earnings"]     {ticker: next_earnings_date or None}
      data["macro"]        {vix, yield_10y, dxy}
      data["commodities"]  {gold, copper, uranium}
      data["news"]         {ticker: [articles]}
    """
    tickers = tuple(sorted(all_tickers(portfolio)))
    td      = str(market_state["last_trading_day"])
    _log.info("load_all_data start", extra={"ticker_count": len(tickers), "tickers": list(tickers), "trading_day": td})

    with st.spinner("טוען מחירים והיסטוריה..."):
        prices = get_stock_data(tickers, td)

    with st.spinner("טוען יעדי אנליסטים..."):
        targets = get_analyst_targets(tickers, td)

    with st.spinner("טוען קונצנזוס אנליסטים..."):
        consensus = get_consensus(tickers, td, api_key)

    with st.spinner("טוען שדרוגים/שינמוכים..."):
        upgrades = get_upgrades_downgrades(tickers, td)

    with st.spinner("טוען תאריכי דוחות..."):
        earnings = get_earnings_dates(tickers, td)

    if FINVIZ_AVAILABLE:
        with st.spinner("טוען פונדמנטלס (~10s)..."):
            fundamentals = get_finviz_fundamentals(tickers, td)
    else:
        fundamentals = {t: {} for t in tickers}

    with st.spinner("טוען מאקרו..."):
        macro = get_macro_indicators(td)

    with st.spinner("טוען סחורות..."):
        commodities = get_commodity_prices(td)

    with st.spinner("טוען חדשות..."):
        news = get_news(tickers, td)

    _log.info("load_all_data complete", extra={"ticker_count": len(tickers), "trading_day": td})
    return {
        "prices":        prices,
        "targets":       targets,
        "consensus":     consensus,
        "upgrades":      upgrades,
        "earnings":      earnings,
        "fundamentals":  fundamentals,
        "macro":         macro,
        "commodities":   commodities,
        "news":          news,
        "_market_open":  market_state.get("is_open", False),
    }
