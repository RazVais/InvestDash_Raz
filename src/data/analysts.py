"""Analyst data: price targets, consensus, upgrades/downgrades."""

import time
import pandas as pd
import yfinance as yf
import streamlit as st
from src.logger import get_logger

_log = get_logger(__name__)

try:
    import finnhub
    FINNHUB_AVAILABLE = True
except ImportError:
    FINNHUB_AVAILABLE = False

from src.config import SELL_GRADES


# ── Price targets ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400 * 7)
def get_analyst_targets(tickers, trading_day):
    _log.info("get_analyst_targets entry", extra={"tickers": list(tickers), "trading_day": trading_day})
    result = {}
    for t in tickers:
        try:
            tgt = yf.Ticker(t).analyst_price_targets
            if tgt and tgt.get("mean") is not None:
                result[t] = {
                    "mean":   tgt.get("mean"),
                    "low":    tgt.get("low"),
                    "high":   tgt.get("high"),
                    "median": tgt.get("median"),
                    "count":  tgt.get("numberOfAnalysts", 0),
                }
            else:
                _log.warning("No analyst price targets for ticker", extra={"ticker": t})
                result[t] = None
        except Exception:
            _log.error("get_analyst_targets failed for ticker", exc_info=True, extra={"ticker": t})
            result[t] = None
    return result


# ── Upgrades / Downgrades ─────────────────────────────────────────────────────
_COL_MAP = {
    "gradedate":  "date",      "date":       "date",
    "tograde":    "to_grade",  "to_grade":   "to_grade",
    "fromgrade":  "from_grade","from_grade": "from_grade",
    "firm":       "firm",      "company":    "firm",
    "action":     "action",
}


@st.cache_data(ttl=86400 * 7)
def get_upgrades_downgrades(tickers, trading_day, lookback_days=180):
    _log.info("get_upgrades_downgrades entry", extra={"tickers": list(tickers), "trading_day": trading_day, "lookback_days": lookback_days})
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=lookback_days)
    empty  = pd.DataFrame(columns=["date", "firm", "action", "from_grade", "to_grade"])
    result = {}

    for t in tickers:
        try:
            df = yf.Ticker(t).upgrades_downgrades
            if df is None or df.empty:
                _log.warning("No upgrades/downgrades data for ticker", extra={"ticker": t})
                result[t] = empty.copy()
                continue

            df = df.reset_index()
            df.columns = [c.lower().replace(" ", "") for c in df.columns]
            df = df.rename(columns={c: _COL_MAP[c] for c in df.columns if c in _COL_MAP})

            if "date" not in df.columns:
                _log.warning("Upgrades/downgrades missing date column", extra={"ticker": t})
                result[t] = empty.copy()
                continue

            df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
            df = df.dropna(subset=["date"])
            df = df[df["date"] >= cutoff].sort_values("date", ascending=False)

            for col in ("firm", "action", "from_grade", "to_grade"):
                if col not in df.columns:
                    df[col] = ""

            result[t] = df[["date", "firm", "action", "from_grade", "to_grade"]].reset_index(drop=True)
        except Exception:
            _log.error("get_upgrades_downgrades failed for ticker", exc_info=True, extra={"ticker": t})
            result[t] = empty.copy()

    return result


# ── Consensus ─────────────────────────────────────────────────────────────────
@st.cache_resource
def _finnhub_client(api_key):
    return finnhub.Client(api_key=api_key)


@st.cache_data(ttl=86400 * 7)
def get_consensus(tickers, trading_day, api_key=""):
    _log.info("get_consensus entry", extra={"tickers": list(tickers), "trading_day": trading_day})
    result = {}
    for t in tickers:
        result[t] = _fetch_consensus_one(t, api_key)
    return result


def _fetch_consensus_one(ticker, api_key):
    # Try Finnhub first
    if FINNHUB_AVAILABLE and api_key and api_key not in ("", "your_key_here"):
        try:
            trends = _finnhub_client(api_key).recommendation_trends(ticker)
            if trends:
                r  = trends[0]
                sb = r.get("strongBuy", 0)
                b  = r.get("buy", 0)
                h  = r.get("hold", 0)
                s  = r.get("sell", 0)
                ss = r.get("strongSell", 0)
                total = sb + b + h + s + ss
                return {
                    "strong_buy": sb, "buy": b, "hold": h,
                    "sell": s, "strong_sell": ss, "total": total,
                    "label": _consensus_label(sb, b, h, s, ss, total),
                }
        except Exception:
            _log.error("Finnhub consensus fetch failed", exc_info=True, extra={"ticker": ticker})

    # yfinance fallback
    try:
        df = yf.Ticker(ticker).recommendations_summary
        if df is not None and not df.empty:
            row = (
                df[df["period"] == "0m"].iloc[0]
                if "0m" in df["period"].values
                else df.iloc[0]
            )
            sb = int(row.get("strongBuy", 0))
            b  = int(row.get("buy", 0))
            h  = int(row.get("hold", 0))
            s  = int(row.get("sell", 0))
            ss = int(row.get("strongSell", 0))
            total = sb + b + h + s + ss
            return {
                "strong_buy": sb, "buy": b, "hold": h,
                "sell": s, "strong_sell": ss, "total": total,
                "label": _consensus_label(sb, b, h, s, ss, total),
            }
    except Exception:
        _log.error("yfinance consensus fallback failed", exc_info=True, extra={"ticker": ticker})

    _log.warning("No consensus data available for ticker", extra={"ticker": ticker})
    return {"strong_buy": 0, "buy": 0, "hold": 0, "sell": 0,
            "strong_sell": 0, "total": 0, "label": "N/A"}


def _consensus_label(sb, b, h, s, ss, total):
    if total == 0:
        return "N/A"
    buy_pct  = (sb + b) / total
    sell_pct = (s + ss) / total
    if buy_pct >= 0.70:
        return "Strong Buy"
    if buy_pct >= 0.50:
        return "Buy"
    if sell_pct >= 0.40:
        return "Sell"
    return "Hold"


# ── EPS trend (on-demand) ─────────────────────────────────────────────────────
@st.cache_data(ttl=86400 * 7)
def get_eps_trend(ticker, trading_day):
    try:
        df = yf.Ticker(ticker).eps_trend
        return df if df is not None and not df.empty else None
    except Exception as e:
        return str(e)


# ── Earnings calendar ─────────────────────────────────────────────────────────
@st.cache_data(ttl=86400 * 7)
def get_earnings_dates(tickers, trading_day):
    """Return {ticker: next_earnings_date or None}."""
    result = {}
    for t in tickers:
        try:
            cal = yf.Ticker(t).calendar
            if isinstance(cal, pd.DataFrame):
                # Older yfinance: rows are fields, columns are date slots
                if "Earnings Date" in cal.index:
                    dates = cal.loc["Earnings Date"].dropna().tolist()
                    result[t] = pd.to_datetime(dates[0]) if dates else None
                else:
                    result[t] = None
            elif isinstance(cal, dict):
                dates = cal.get("Earnings Date", [])
                result[t] = pd.to_datetime(dates[0]) if dates else None
            else:
                result[t] = None
        except Exception:
            result[t] = None
        time.sleep(0.1)
    return result
