"""Analyst data: price targets, consensus, upgrades/downgrades."""


import pandas as pd
import streamlit as st
import yfinance as yf

from src.config import is_tase_numeric
from src.data.batch import map_cached
from src.logger import get_logger

_log = get_logger(__name__)

try:
    import finnhub
    FINNHUB_AVAILABLE = True
except ImportError:
    FINNHUB_AVAILABLE = False

try:
    from yfinance.exceptions import YFRateLimitError as _YFRateLimit
except ImportError:
    _YFRateLimit = None


def _yf_except(exc, msg, **kw):
    """Log rate-limit errors as WARNING, all others as ERROR with traceback."""
    if _YFRateLimit and isinstance(exc, _YFRateLimit):
        _log.warning(f"{msg} (rate limited)", **kw)
    else:
        _log.error(msg, exc_info=True, **kw)



# ── Price targets ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400 * 7, show_spinner=False)
def _target_one(t):
    """Analyst price targets for one ticker. Raises on fetch errors (not cached)."""
    if is_tase_numeric(t):
        return None
    try:
        tgt = yf.Ticker(t).analyst_price_targets
    except Exception as e:
        _yf_except(e, "get_analyst_targets failed for ticker", extra={"ticker": t})
        raise
    if tgt and tgt.get("mean") is not None:
        return {
            "mean":   tgt.get("mean"),
            "low":    tgt.get("low"),
            "high":   tgt.get("high"),
            "median": tgt.get("median"),
            "count":  tgt.get("numberOfAnalysts", 0),
        }
    _log.warning("No analyst price targets for ticker", extra={"ticker": t})
    return None


def get_analyst_targets(tickers, trading_day=None):
    """{ticker: targets or None}. Cached per ticker for 7 days (trading_day unused)."""
    return map_cached(_target_one, tickers)


# ── Upgrades / Downgrades ─────────────────────────────────────────────────────
_COL_MAP = {
    "gradedate":  "date",      "date":       "date",
    "tograde":    "to_grade",  "to_grade":   "to_grade",
    "fromgrade":  "from_grade","from_grade": "from_grade",
    "firm":       "firm",      "company":    "firm",
    "action":     "action",
}


_UPG_COLS = ["date", "firm", "action", "from_grade", "to_grade"]


@st.cache_data(ttl=86400 * 7, show_spinner=False)
def _upgrades_one(t, lookback_days):
    """Recent rating changes for one ticker. Raises on fetch errors (not cached)."""
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=lookback_days)
    empty = pd.DataFrame(columns=_UPG_COLS)
    if is_tase_numeric(t):
        return empty
    try:
        df = yf.Ticker(t).upgrades_downgrades
        if df is None or df.empty:
            _log.warning("No upgrades/downgrades data for ticker", extra={"ticker": t})
            return empty

        df = df.reset_index()
        df.columns = [c.lower().replace(" ", "") for c in df.columns]
        df = df.rename(columns={c: _COL_MAP[c] for c in df.columns if c in _COL_MAP})

        if "date" not in df.columns:
            return empty

        df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
        df = df.dropna(subset=["date"])
        df = df[df["date"] >= cutoff].sort_values("date", ascending=False)

        for col in ("firm", "action", "from_grade", "to_grade"):
            if col not in df.columns:
                df[col] = ""

        return df[_UPG_COLS].reset_index(drop=True)
    except Exception as e:
        _yf_except(e, "get_upgrades_downgrades failed for ticker", extra={"ticker": t})
        raise


def get_upgrades_downgrades(tickers, trading_day=None, lookback_days=180):
    """{ticker: DataFrame of rating changes}. Cached per ticker for 7 days."""
    return map_cached(_upgrades_one, tickers, lookback_days,
                      default=pd.DataFrame(columns=_UPG_COLS))


# ── Consensus ─────────────────────────────────────────────────────────────────
@st.cache_resource
def _finnhub_client(api_key):
    return finnhub.Client(api_key=api_key)


_NA_CONSENSUS = {"strong_buy": 0, "buy": 0, "hold": 0, "sell": 0,
                 "strong_sell": 0, "total": 0, "label": "N/A"}


def get_consensus(tickers, trading_day=None, api_key=""):
    """{ticker: consensus dict}. Cached per ticker for 7 days."""
    return map_cached(_consensus_one, tickers, api_key, default=dict(_NA_CONSENSUS))


@st.cache_data(ttl=86400 * 7, show_spinner=False)
def _consensus_one(ticker, api_key):
    return _fetch_consensus_one(ticker, api_key)


def _fetch_consensus_one(ticker, api_key):
    """Finnhub first, yfinance fallback. Raises if the fallback errored (not cached)."""
    if is_tase_numeric(ticker):
        return {"strong_buy": 0, "buy": 0, "hold": 0, "sell": 0,
                "strong_sell": 0, "total": 0, "label": "N/A"}
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
            _log.warning("Finnhub consensus fetch failed", extra={"ticker": ticker})

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
    except Exception as e:
        _yf_except(e, "yfinance consensus fallback failed", extra={"ticker": ticker})
        raise

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
    if is_tase_numeric(ticker):
        return None
    try:
        stock = yf.Ticker(ticker)
    except Exception:
        _log.warning("get_eps_trend: Ticker() failed", extra={"ticker": ticker})
        return None
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

@st.cache_data(ttl=86400 * 7, show_spinner=False)
def _earnings_one(t):
    """Next earnings date for one ticker. Raises on fetch errors (not cached)."""
    if is_tase_numeric(t):
        return None
    cal = yf.Ticker(t).calendar
    if isinstance(cal, pd.DataFrame):
        if "Earnings Date" in cal.index:
            dates = cal.loc["Earnings Date"].dropna().tolist()
            return pd.to_datetime(dates[0]) if dates else None
    elif isinstance(cal, dict):
        dates = cal.get("Earnings Date", [])
        return pd.to_datetime(dates[0]) if dates else None
    return None


def get_earnings_dates(tickers, trading_day=None):
    """Return {ticker: next_earnings_date or None}. Cached per ticker for 7 days."""
    return map_cached(_earnings_one, tickers)
