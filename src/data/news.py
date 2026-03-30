"""News fetcher — Yahoo Finance RSS (no auth, no rate-limit issues)."""

import email.utils
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests
import streamlit as st
from src.config import TICKER_BRIEFS
from src.logger import get_logger

_log = get_logger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _fetch_rss(ticker: str, n: int = 6) -> list:
    """
    Fetch news via Yahoo Finance RSS feed.
    No auth required — separate rate-limit budget from the chart/quote APIs.
    """
    try:
        r = requests.get(
            "https://feeds.finance.yahoo.com/rss/2.0/headline",
            params={"s": ticker, "region": "US", "lang": "en-US"},
            headers=_HEADERS,
            timeout=12,
        )
        if r.status_code != 200:
            _log.warning("RSS non-200", extra={"ticker": ticker, "status": r.status_code})
            return []

        root = ET.fromstring(r.content)
        items = []
        for item in root.findall(".//item")[:n]:
            title   = item.findtext("title", "")
            link    = item.findtext("link", "#")
            pubdate = item.findtext("pubDate", "")
            source  = item.findtext("source", "") or "Yahoo Finance"

            dt = None
            if pubdate:
                try:
                    parsed = email.utils.parsedate(pubdate)
                    if parsed:
                        dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            if title:
                items.append({
                    "title":     title,
                    "link":      link,
                    "published": dt,
                    "publisher": source,
                })
        return items
    except Exception:
        _log.error("RSS fetch failed", exc_info=True, extra={"ticker": ticker})
        return []


@st.cache_data(ttl=1800)
def get_news(tickers, trading_day, max_per=6):
    """Fetch up to max_per news articles per ticker via Yahoo RSS."""
    result = {}
    for t in tickers:
        _log.info("get_news", extra={"ticker": t})
        result[t] = _fetch_rss(t, n=max_per)
    return result


@st.cache_data(ttl=3600)
def get_company_profile(ticker: str, trading_day: str) -> dict:
    """
    Fetch company profile from Yahoo Finance v8 chart meta + quoteSummary.
    Returns: {name, sector, industry, description, website, employees}
    trading_day used as cache key only.
    """
    profile = {"name": ticker, "sector": "", "industry": "",
                "description": "", "website": "", "employees": None}
    try:
        # Chart meta gives longName, exchange, currency (always available)
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            params={"interval": "1d", "range": "5d"},
            headers=_HEADERS,
            timeout=12,
        )
        if r.status_code == 200:
            meta = (r.json().get("chart", {})
                    .get("result", [{}])[0].get("meta", {}))
            profile["name"] = meta.get("longName") or meta.get("shortName") or ticker

        # quoteSummary assetProfile gives sector, industry, description
        r2 = requests.get(
            f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}",
            params={"modules": "assetProfile"},
            headers=_HEADERS,
            timeout=12,
        )
        if r2.status_code == 200:
            res = r2.json().get("quoteSummary", {}).get("result") or []
            if res and res[0]:
                ap = res[0].get("assetProfile", {})
                profile["sector"]      = ap.get("sector", "")
                profile["industry"]    = ap.get("industry", "")
                profile["description"] = ap.get("longBusinessSummary", "")
                profile["website"]     = ap.get("website", "")
                profile["employees"]   = ap.get("fullTimeEmployees")

        # Fall back to curated static brief if live description unavailable
        if not profile["description"]:
            profile["description"] = TICKER_BRIEFS.get(ticker, "")

    except Exception:
        _log.error("get_company_profile failed", exc_info=True, extra={"ticker": ticker})

    return profile
