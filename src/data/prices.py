"""Price data fetcher — 1-year OHLCV batch download via yfinance."""

import time
import pandas as pd
import yfinance as yf
import streamlit as st
from src.logger import get_logger

_log = get_logger(__name__)


@st.cache_data(ttl=1800)
def get_stock_data(tickers, trading_day):
    """
    Batch-download 1-year OHLCV for all tickers.
    Returns dict: {ticker: {price, change, beta, div_yield, ohlcv, high_52w, low_52w}}
    Uses trading_day as cache key so weekend/holiday hits serve cached data.
    """
    result = {}
    errors = {}

    _log.info("get_stock_data entry", extra={"tickers": list(tickers), "trading_day": trading_day})

    if not tickers:
        return result

    # Single batch download — one auth, one request
    try:
        raw = yf.download(
            list(tickers),
            period="1y",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    except Exception as e:
        _log.error("Batch yf.download failed", exc_info=True, extra={"tickers": list(tickers)})
        return {"__errors__": {t: str(e) for t in tickers}}

    for t in tickers:
        try:
            # Extract per-ticker OHLCV
            if len(tickers) == 1:
                df = raw.copy()
            else:
                df = raw[t].copy() if t in raw.columns.get_level_values(0) else pd.DataFrame()

            df = df.dropna(how="all")

            if df.empty:
                _log.warning("No OHLCV data for ticker", extra={"ticker": t})
                errors[t] = "no data"
                result[t] = None
                continue

            close  = df["Close"].dropna()
            open_  = df["Open"].dropna()
            high   = df["High"].dropna()
            low    = df["Low"].dropna()
            volume = df["Volume"].dropna() if "Volume" in df.columns else pd.Series(dtype=float)

            price = float(close.iloc[-1])
            prev  = float(close.iloc[-2]) if len(close) > 1 else price

            # Fetch per-ticker metadata (beta, div yield) — separate call, cached separately
            beta      = 1.0
            div_yield = 0.0
            try:
                info      = yf.Ticker(t).info
                beta      = float(info.get("beta") or 1.0)
                div_yield = float(info.get("dividendYield") or 0.0) * 100
            except Exception:
                _log.warning("Could not fetch ticker info (beta/div_yield)", extra={"ticker": t})

            ohlcv = pd.DataFrame({
                "Open":   open_,
                "High":   high,
                "Low":    low,
                "Close":  close,
                "Volume": volume,
            }).dropna(subset=["Close"])

            result[t] = {
                "price":     price,
                "change":    ((price - prev) / prev * 100) if prev else 0.0,
                "beta":      beta,
                "div_yield": div_yield,
                "ohlcv":     ohlcv,
                "high_52w":  float(close.max()),
                "low_52w":   float(close.min()),
                # Keep a plain close series for quick sparklines / correlation
                "history":   close,
            }
            time.sleep(0.1)

        except Exception as e:
            _log.error("Per-ticker processing failed", exc_info=True, extra={"ticker": t})
            errors[t] = str(e)
            result[t] = None

    _log.info("get_stock_data complete", extra={"ok": len([v for v in result.values() if v is not None]), "errors": len(errors)})
    result["__errors__"] = errors
    return result


def lookup_buy_price(ticker, buy_date, prices_dict):
    """
    Return the closing price on or just after buy_date.

    Strategy (fastest → slowest, avoids extra API calls):
      1. Find the date in the already-fetched 1yr OHLCV (no network call).
      2. Fall back to get_buy_price() only for dates older than ~1 year.
    """
    p = prices_dict.get(ticker) if prices_dict else None
    if p and p.get("ohlcv") is not None and not p["ohlcv"].empty:
        ohlcv = p["ohlcv"]
        bd    = pd.to_datetime(buy_date).tz_localize(None)
        # Normalise index timezone so comparison works
        idx = ohlcv.index
        if hasattr(idx, "tz") and idx.tz is not None:
            idx = idx.tz_localize(None)
        future = idx[idx >= bd]
        if len(future) > 0:
            return float(ohlcv["Close"].iloc[list(idx).index(future[0])])
    # Fallback: dedicated API call for dates outside the 1yr window
    return get_buy_price(ticker, buy_date)


@st.cache_data(ttl=3600)
def get_buy_price(ticker, buy_date):
    """
    Return closing price on or just after buy_date via yfinance.
    TTL=1h so transient failures retry soon (not cached for 30 days).
    """
    _log.info("get_buy_price entry", extra={"ticker": ticker, "buy_date": buy_date})
    try:
        d   = pd.to_datetime(buy_date)
        end = d + pd.Timedelta(days=10)
        dl  = yf.download(
            ticker,
            start=d.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if dl.empty:
            _log.warning("No price data found for buy_date", extra={"ticker": ticker, "buy_date": buy_date})
            return None
        # Handle both flat and MultiIndex columns
        if isinstance(dl.columns, pd.MultiIndex):
            close = dl["Close"].iloc[:, 0].dropna()
        else:
            close = dl["Close"].dropna() if "Close" in dl.columns else dl.iloc[:, 0].dropna()
        return float(close.iloc[0]) if not close.empty else None
    except Exception:
        _log.error("get_buy_price failed", exc_info=True, extra={"ticker": ticker, "buy_date": buy_date})
        return None
