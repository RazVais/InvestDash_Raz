"""News fetcher — latest articles per ticker via yfinance."""

import pandas as pd
import yfinance as yf
import streamlit as st


@st.cache_data(ttl=1800)
def get_news(tickers, trading_day, max_per=5):
    result = {}
    for t in tickers:
        try:
            raw   = yf.Ticker(t).news or []
            items = []
            for article in raw[:max_per]:
                # yfinance 2024+ nests content under 'content' key
                c = article.get("content", article)
                provider = c.get("provider", {})
                pub_name = provider.get("displayName", "Unknown") if isinstance(provider, dict) else str(provider)
                url_obj  = c.get("canonicalUrl", {})
                url      = url_obj.get("url", "#") if isinstance(url_obj, dict) else str(url_obj)
                items.append({
                    "title":     c.get("title", article.get("title", "No title")),
                    "publisher": pub_name,
                    "link":      url,
                    "published": pd.to_datetime(
                        c.get("pubDate", article.get("providerPublishTime", "")),
                        utc=True, errors="coerce",
                    ),
                })
            result[t] = items
        except Exception:
            result[t] = []
    return result
