"""Analyst data: price targets, consensus, upgrades/downgrades."""

from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import streamlit as st
import yfinance as yf

from src.logger import get_logger

_log = get_logger(__name__)

try:
    import finnhub
    FINNHUB_AVAILABLE = True
except ImportError:
    FINNHUB_AVAILABLE = False



# ── Price targets ─────────────────────────────────────────────────────────────

def _fetch_one_target(t):
    try:
        tgt = yf.Ticker(t).analyst_price_targets
        if tgt and tgt.get("mean") is not None:
            return t, {
                "mean":   tgt.get("mean"),
                "low":    tgt.get("low"),
                "high":   tgt.get("high"),
                "median": tgt.get("median"),
                "count":  tgt.get("numberOfAnalysts", 0),
            }
        _log.warning("No analyst price targets for ticker", extra={"ticker": t})
    except Exception:
        _log.error("get_analyst_targets failed for ticker", exc_info=True, extra={"ticker": t})
    return t, None


@st.cache_data(ttl=86400 * 7)
def get_analyst_targets(tickers, trading_day):
    _log.info("get_analyst_targets entry", extra={"tickers": list(tickers), "trading_day": trading_day})
    with ThreadPoolExecutor(max_workers=min(len(tickers), 6)) as ex:
        return dict(ex.map(_fetch_one_target, tickers))


# ── Upgrades / Downgrades ─────────────────────────────────────────────────────
_COL_MAP = {
    "gradedate":  "date",      "date":       "date",
    "tograde":    "to_grade",  "to_grade":   "to_grade",
    "fromgrade":  "from_grade","from_grade": "from_grade",
    "firm":       "firm",      "company":    "firm",
    "action":     "action",
}


def _fetch_one_upgrades(args):
    t, cutoff = args
    empty = pd.DataFrame(columns=["date", "firm", "action", "from_grade", "to_grade"])
    try:
        df = yf.Ticker(t).upgrades_downgrades
        if df is None or df.empty:
            _log.warning("No upgrades/downgrades data for ticker", extra={"ticker": t})
            return t, empty.copy()

        df = df.reset_index()
        df.columns = [c.lower().replace(" ", "") for c in df.columns]
        df = df.rename(columns={c: _COL_MAP[c] for c in df.columns if c in _COL_MAP})

        if "date" not in df.columns:
            return t, empty.copy()

        df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
        df = df.dropna(subset=["date"])
        df = df[df["date"] >= cutoff].sort_values("date", ascending=False)

        for col in ("firm", "action", "from_grade", "to_grade"):
            if col not in df.columns:
                df[col] = ""

        return t, df[["date", "firm", "action", "from_grade", "to_grade"]].reset_index(drop=True)
    except Exception:
        _log.error("get_upgrades_downgrades failed for ticker", exc_info=True, extra={"ticker": t})
        return t, empty.copy()


@st.cache_data(ttl=86400 * 7)
def get_upgrades_downgrades(tickers, trading_day, lookback_days=180):
    _log.info("get_upgrades_downgrades entry", extra={"tickers": list(tickers), "trading_day": trading_day})
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=lookback_days)
    with ThreadPoolExecutor(max_workers=min(len(tickers), 6)) as ex:
        return dict(ex.map(_fetch_one_upgrades, [(t, cutoff) for t in tickers]))


# ── Consensus ─────────────────────────────────────────────────────────────────
@st.cache_resource
def _finnhub_client(api_key):
    return finnhub.Client(api_key=api_key)


def _fetch_consensus_worker(args):
    t, api_key = args
    return t, _fetch_consensus_one(t, api_key)


@st.cache_data(ttl=86400 * 7)
def get_consensus(tickers, trading_day, api_key=""):
    _log.info("get_consensus entry", extra={"tickers": list(tickers), "trading_day": trading_day})
    with ThreadPoolExecutor(max_workers=min(len(tickers), 6)) as ex:
        return dict(ex.map(_fetch_consensus_worker, [(t, api_key) for t in tickers]))


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
    """Fetch EPS trend. yfinance 0.2.54+ removed .eps_trend; falls back to earnings_estimate."""
    stock = yf.Ticker(ticker)
    # Try new attribute name first
    for attr in ("earnings_estimate", "eps_trend"):
        try:
            df = getattr(stock, attr, None)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass
    return None


# ── Earnings calendar ─────────────────────────────────────────────────────────

def _fetch_one_earnings(t):
    try:
        cal = yf.Ticker(t).calendar
        if isinstance(cal, pd.DataFrame):
            if "Earnings Date" in cal.index:
                dates = cal.loc["Earnings Date"].dropna().tolist()
                return t, pd.to_datetime(dates[0]) if dates else None
        elif isinstance(cal, dict):
            dates = cal.get("Earnings Date", [])
            return t, pd.to_datetime(dates[0]) if dates else None
    except Exception:
        pass
    return t, None


@st.cache_data(ttl=86400 * 7)
def get_earnings_dates(tickers, trading_day):
    """Return {ticker: next_earnings_date or None}."""
    with ThreadPoolExecutor(max_workers=min(len(tickers), 6)) as ex:
        return dict(ex.map(_fetch_one_earnings, tickers))
