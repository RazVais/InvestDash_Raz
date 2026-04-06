"""Price data fetcher — multi-source with automatic fallback.

Source priority (per ticker):
  1. Yahoo Finance v8 REST API (requests, no library auth, different rate-limit pool)
  2. yfinance Ticker.history()  (fallback when v8 throttles)

Israeli stocks note (ESLT):
  ESLT is dual-listed on NASDAQ (USD) and TASE (ILS).
  The dashboard tracks USD value, so we always use the NASDAQ ticker (plain "ESLT").
  TASE's direct API (api.tase.co.il) is protected by an Imperva WAF that blocks
  non-browser HTTP clients — it cannot be called programmatically without a real browser.
  The TASE website (market.tase.co.il/en/market_data/index/148/major_data) is an
  Angular SPA that loads data via those same blocked XHR endpoints.
  Yahoo Finance v8 (query1.finance.yahoo.com) serves ESLT NASDAQ data reliably and
  is the most reliable programmatic source available.
"""

from concurrent.futures import ThreadPoolExecutor
import threading

import pandas as pd
import requests as _req
import streamlit as st
import yfinance as yf

from src.logger import get_logger

_log = get_logger(__name__)

# Limit concurrent yfinance .info calls — they share a rate-limit pool
_YF_INFO_SEM = threading.Semaphore(3)

_YF_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ── Source implementations ─────────────────────────────────────────────────────

def _fetch_yahoo_v8(ticker, period="1y"):
    """
    Direct Yahoo Finance v8/finance/chart REST call.
    Bypasses the yfinance library entirely — uses a separate HTTP session with
    its own rate-limit budget, no cookie/SQLite patches needed.
    Works for US tickers AND NASDAQ-listed Israeli tickers (e.g. ESLT).
    Returns (DataFrame, meta_dict) where meta_dict contains dividend/beta fields.
    """
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        r = _req.get(
            url,
            params={"interval": "1d", "range": period, "events": "div"},
            headers=_YF_HEADERS,
            timeout=15,
        )
        if r.status_code != 200:
            _log.warning("Yahoo v8 non-200", extra={"ticker": ticker, "status": r.status_code})
            return None, {}
        j = r.json()
        results = j.get("chart", {}).get("result")
        if not results:
            _log.warning("Yahoo v8 empty result", extra={"ticker": ticker})
            return None, {}
        res        = results[0]
        meta       = res.get("meta", {})
        # Attach dividend events to meta so caller can compute yield
        meta["_div_events"] = res.get("events", {}).get("dividends", {})
        timestamps = res.get("timestamp", [])
        if not timestamps:
            return None, meta
        q   = res["indicators"]["quote"][0]
        # Use adjusted close when available (accounts for splits/dividends)
        adj_list = res["indicators"].get("adjclose")
        closes   = adj_list[0].get("adjclose", q["close"]) if adj_list else q["close"]
        idx = pd.to_datetime(timestamps, unit="s").tz_localize(None)
        df  = pd.DataFrame({
            "Open":   q["open"],
            "High":   q["high"],
            "Low":    q["low"],
            "Close":  closes,
            "Volume": q["volume"],
        }, index=idx)
        df = df.dropna(subset=["Close"])
        return (df if not df.empty else None), meta
    except Exception:
        _log.error("Yahoo v8 fetch error", exc_info=True, extra={"ticker": ticker})
        return None, {}


def _fetch_yahoo_v8_range(ticker, start: str, end: str):
    """Yahoo v8 for a specific date range (used by get_buy_price)."""
    try:
        p1 = int(pd.Timestamp(start).timestamp())
        p2 = int(pd.Timestamp(end).timestamp())
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        r   = _req.get(
            url,
            params={"interval": "1d", "period1": p1, "period2": p2},
            headers=_YF_HEADERS,
            timeout=15,
        )
        if r.status_code != 200:
            return None
        j = r.json()
        results = j.get("chart", {}).get("result")
        if not results:
            return None
        res        = results[0]
        timestamps = res.get("timestamp", [])
        if not timestamps:
            return None
        q      = res["indicators"]["quote"][0]
        closes = q["close"]
        idx    = pd.to_datetime(timestamps, unit="s").tz_localize(None)
        s      = pd.Series(closes, index=idx).dropna()
        return s if not s.empty else None
    except Exception:
        _log.error("Yahoo v8 range fetch error", exc_info=True,
                   extra={"ticker": ticker, "start": start, "end": end})
        return None


def _fetch_yfinance_history(ticker):
    """Fallback: yfinance Ticker.history() — may hit rate limits under load."""
    try:
        df = yf.Ticker(ticker).history(period="1y", auto_adjust=True)
        if df is None or df.empty:
            return None
        # Strip timezone from index
        if hasattr(df.index, "tz") and df.index.tz is not None:
            df = df.copy()
            df.index = df.index.tz_localize(None)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
        return df if not df.empty else None
    except Exception:
        _log.warning("yfinance history fallback failed", exc_info=True,
                     extra={"ticker": ticker})
        return None


def _ohlcv_for_ticker(ticker):
    """
    Try sources in priority order and return (DataFrame, meta, source_name).

    Note on ESLT: We always use the plain NASDAQ ticker (USD). The TASE .TA
    suffix returns prices in ILA (Israeli Agorot, 1/100 of ILS) which would
    corrupt USD-denominated P&L calculations.
    """
    # 1. Yahoo Finance v8 REST (bypasses yfinance rate-limit budget)
    df, meta = _fetch_yahoo_v8(ticker)
    if df is not None:
        return df, meta, "yahoo_v8"

    # 2. yfinance Ticker.history() fallback — no meta dividend data available
    df = _fetch_yfinance_history(ticker)
    if df is not None:
        return df, {}, "yfinance"

    return None, {}, "none"


# ── Per-ticker worker (runs in thread pool) ───────────────────────────────────


def _process_one_ticker(t):
    """Fetch OHLCV + beta/div_yield/div_rate for a single ticker. Thread-safe."""
    try:
        df, meta, source = _ohlcv_for_ticker(t)
        if df is None or df.empty:
            _log.warning("All price sources failed", extra={"ticker": t})
            return t, None, "no data"

        close  = df["Close"].dropna()
        open_  = df["Open"].dropna()   if "Open"   in df.columns else close
        high   = df["High"].dropna()   if "High"   in df.columns else close
        low    = df["Low"].dropna()    if "Low"    in df.columns else close
        volume = df["Volume"].dropna() if "Volume" in df.columns else pd.Series(dtype=float)

        price = float(close.iloc[-1])
        prev  = float(close.iloc[-2]) if len(close) > 1 else price

        # Beta from yfinance .info (semaphore caps concurrent calls)
        beta = 1.0
        with _YF_INFO_SEM:
            try:
                info = yf.Ticker(t).info
                beta = float(info.get("beta") or 1.0)
            except Exception:
                _log.warning("ticker .info unavailable", extra={"ticker": t})

        # Dividend yield + annual rate — computed from v8 dividend events (zero extra requests)
        div_yield, div_rate = 0.0, 0.0
        try:
            div_events = meta.get("_div_events", {})
            if div_events and price > 0:
                import time as _time
                one_year_ago = _time.time() - 365 * 86400
                recent_amounts = [
                    float(v["amount"])
                    for v in div_events.values()
                    if float(v.get("date", 0)) >= one_year_ago
                ]
                if recent_amounts:
                    div_rate  = sum(recent_amounts)
                    div_yield = div_rate / price * 100
        except Exception:
            _log.warning("dividend events parse failed", extra={"ticker": t})

        ohlcv = pd.DataFrame({
            "Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume,
        }).dropna(subset=["Close"])

        _log.info("Fetched OHLCV", extra={"ticker": t, "source": source,
                                           "rows": len(ohlcv), "price": price})
        return t, {
            "price":     price,
            "change":    ((price - prev) / prev * 100) if prev else 0.0,
            "beta":      beta,
            "div_yield": div_yield,
            "div_rate":  div_rate,
            "ohlcv":     ohlcv,
            "high_52w":  float(close.max()),
            "low_52w":   float(close.min()),
            "history":   close,
        }, ""
    except Exception:
        _log.error("Ticker processing error", exc_info=True, extra={"ticker": t})
        return t, None, "error"


# ── Main cached fetcher ────────────────────────────────────────────────────────

@st.cache_data(ttl=1800)
def get_stock_data(tickers, trading_day):
    """
    Fetch 1-year OHLCV + metadata for all tickers in parallel.
    Uses Yahoo Finance v8 REST API as primary, yfinance as fallback.
    Returns dict: {ticker: {price, change, beta, div_yield, ohlcv, high_52w, low_52w, history}}
    """
    _log.info("get_stock_data start",
              extra={"tickers": list(tickers), "trading_day": trading_day})
    if not tickers:
        return {}

    result, errors = {}, {}
    with ThreadPoolExecutor(max_workers=min(len(tickers), 8)) as ex:
        for t, data, err in ex.map(_process_one_ticker, tickers):
            result[t] = data
            if err:
                errors[t] = err

    ok = sum(1 for v in result.values() if v is not None)
    _log.info("get_stock_data done", extra={"ok": ok, "errors": len(errors)})
    result["__errors__"] = errors
    return result


# ── Buy-price lookup ───────────────────────────────────────────────────────────

def lookup_buy_price(ticker, buy_date, prices_dict):
    """
    Return the closing price on or just after buy_date.
    1. Check already-fetched 1yr OHLCV (zero network cost).
    2. Fall back to get_buy_price() for older dates.
    """
    p = prices_dict.get(ticker) if prices_dict else None
    if p and p.get("ohlcv") is not None and not p["ohlcv"].empty:
        ohlcv = p["ohlcv"]
        bd    = pd.to_datetime(buy_date).tz_localize(None)
        idx   = ohlcv.index
        if hasattr(idx, "tz") and idx.tz is not None:
            idx = idx.tz_localize(None)
        future = idx[idx >= bd]
        if len(future) > 0:
            return float(ohlcv["Close"].iloc[list(idx).index(future[0])])
    return get_buy_price(ticker, buy_date)


@st.cache_data(ttl=3600)
def get_buy_price(ticker, buy_date):
    """
    Return closing price on or just after buy_date.
    Primary: Yahoo Finance v8 REST API.
    Fallback: yfinance Ticker.history() for specific range.
    """
    _log.info("get_buy_price", extra={"ticker": ticker, "buy_date": buy_date})
    try:
        d   = pd.to_datetime(buy_date)
        end = (d + pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        start = d.strftime("%Y-%m-%d")

        # Primary: Yahoo v8 range
        s = _fetch_yahoo_v8_range(ticker, start, end)
        if s is not None and not s.empty:
            return float(s.iloc[0])

        # Fallback: yfinance
        df = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
        if df is not None and not df.empty:
            close = df["Close"].dropna()
            if not close.empty:
                return float(close.iloc[0])

        _log.warning("No buy price found", extra={"ticker": ticker, "buy_date": buy_date})
        return None
    except Exception:
        _log.error("get_buy_price failed", exc_info=True,
                   extra={"ticker": ticker, "buy_date": buy_date})
        return None
