# Fix: yfinance's SQLite caches (timezone + cookie, via peewee) crash on Windows
# when called from Streamlit's worker thread. Replace with proper in-memory caches
# that actually store data — using the built-in Dummies drops every value on store(),
# forcing Yahoo to be re-hit on every ticker call, causing rate-limits and failures.
class _MemTzCache:
    def __init__(self): self._d = {}
    def lookup(self, tkr): return self._d.get(tkr)
    def store(self, tkr, tz): self._d[tkr] = tz

class _MemCookieCache:
    def __init__(self): self._d = {}
    def lookup(self, tkr): return self._d.get(tkr)
    def store(self, tkr, cookie): self._d[tkr] = cookie
    @property
    def Cookie_db(self): return None

from yfinance.cache import (
    _TzCacheManager as _YfTzMgr,
    _CookieCacheManager as _YfCookieMgr,
)
_YfTzMgr._tz_cache = _MemTzCache()
_YfCookieMgr._Cookie_cache = _MemCookieCache()

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytz
import streamlit as st
import yfinance as yf

try:
    import exchange_calendars as xcals
    _nyse = xcals.get_calendar("XNYS")
    CALENDAR_AVAILABLE = True
except Exception:
    CALENDAR_AVAILABLE = False

try:
    import finnhub
    FINNHUB_AVAILABLE = True
except ImportError:
    FINNHUB_AVAILABLE = False

try:
    from finvizfinance.quote import finvizfinance as fvf
    FINVIZ_AVAILABLE = True
except ImportError:
    FINVIZ_AVAILABLE = False

# ── Constants ──────────────────────────────────────────────────────────────────

PORTFOLIO_FILE = Path(__file__).parent / "portfolio.json"
NYSE_TZ = pytz.timezone("America/New_York")
KNOWN_LIMITED_TICKERS = {"ESLT"}

# Display names for known tickers
TICKER_NAMES = {
    "VOO":   "Vanguard S&P 500 ETF",
    "CCJ":   "Cameco — אורניום",
    "FCX":   "Freeport-McMoRan — נחושת",
    "ETN":   "Eaton — תשתיות חשמל",
    "VRT":   "Vertiv — קירור מרכזי נתונים",
    "AMD":   "Advanced Micro Devices",
    "AMZN":  "Amazon",
    "GOOGL": "Alphabet (Google)",
    "CRWD":  "CrowdStrike — סייבר",
    "ESLT":  "אלביט מערכות",
    "TEVA":  "טבע תעשיות פרמצבטיות",
    "EQX":   "Equinox Gold — זהב",
}

# Default portfolio seeded from original code (shares=0 until user fills in)
DEFAULT_LAYERS = {
    "Core (50%)": [
        {"ticker": "VOO", "shares": 0, "buy_date": str(date.today())}
    ],
    "Physical Infrastructure": [
        {"ticker": "CCJ", "shares": 0, "buy_date": str(date.today())},
        {"ticker": "FCX", "shares": 0, "buy_date": str(date.today())},
        {"ticker": "ETN", "shares": 0, "buy_date": str(date.today())},
        {"ticker": "VRT", "shares": 0, "buy_date": str(date.today())},
    ],
    "Compute & Platform": [
        {"ticker": "AMD",  "shares": 0, "buy_date": str(date.today())},
        {"ticker": "AMZN", "shares": 0, "buy_date": str(date.today())},
        {"ticker": "GOOGL","shares": 0, "buy_date": str(date.today())},
    ],
    "Security & Stability": [
        {"ticker": "CRWD", "shares": 0, "buy_date": str(date.today())},
        {"ticker": "ESLT", "shares": 0, "buy_date": str(date.today())},
        {"ticker": "TEVA", "shares": 0, "buy_date": str(date.today())},
        {"ticker": "EQX",  "shares": 0, "buy_date": str(date.today())},
    ],
}

KPI_TOOLTIPS = {
    "מחיר":          "מחיר שוק נוכחי",
    "שינוי":         "שינוי מחיר לעומת סגירה קודמת",
    "בטא":           "תנודתיות יחסית למדד S&P 500 — מעל 1 פירושו תנודתי יותר מהשוק",
    "עלייה אפשרית":  "פער בין המחיר הנוכחי ליעד המחיר הממוצע של האנליסטים",
    "יעד מחיר":      "טווח יעד מחיר של האנליסטים: נמוך / ממוצע / גבוה",
    "עדיפות vs VOO": "תשואת מחיר ל-6 חודשים יחסית ל-VOO — חיובי = ביצועים עדיפים על המדד",
    "רווח/הפסד":     "רווח או הפסד לא ממומש מתאריך הרכישה",
    "תקופת אחזקה":   "מספר ימים מאז תאריך הרכישה שלך",
    "מניות":         "מספר המניות שברשותך",
    "שווי":          "שווי שוק נוכחי של הפוזיציה שלך (מניות × מחיר)",
}

# ── Portfolio persistence ──────────────────────────────────────────────────────

def load_portfolio() -> dict:
    if PORTFOLIO_FILE.exists():
        try:
            return json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    portfolio = {"layers": DEFAULT_LAYERS}
    save_portfolio(portfolio)
    return portfolio

def save_portfolio(portfolio: dict) -> None:
    PORTFOLIO_FILE.write_text(
        json.dumps(portfolio, indent=2, default=str), encoding="utf-8"
    )

def add_position(portfolio: dict, layer: str, ticker: str,
                 shares: float, buy_date_val: date) -> dict:
    ticker = ticker.upper().strip()
    if not ticker:
        return portfolio
    if layer not in portfolio["layers"]:
        portfolio["layers"][layer] = []
    existing = [p for p in portfolio["layers"][layer] if p["ticker"] != ticker]
    existing.append({"ticker": ticker, "shares": shares, "buy_date": str(buy_date_val)})
    portfolio["layers"][layer] = existing
    save_portfolio(portfolio)
    return portfolio

def remove_position(portfolio: dict, layer: str, ticker: str) -> dict:
    if layer in portfolio["layers"]:
        portfolio["layers"][layer] = [
            p for p in portfolio["layers"][layer] if p["ticker"] != ticker
        ]
        if not portfolio["layers"][layer]:
            del portfolio["layers"][layer]
    save_portfolio(portfolio)
    return portfolio

def all_tickers(portfolio: dict):
    return list({
        p["ticker"]
        for positions in portfolio["layers"].values()
        for p in positions
    })

# ── Market state ───────────────────────────────────────────────────────────────

def get_market_state() -> dict:
    now_et = datetime.now(NYSE_TZ)
    today = now_et.date()

    if CALENDAR_AVAILABLE:
        try:
            is_session = _nyse.is_session(str(today))
        except Exception:
            is_session = today.weekday() < 5
    else:
        is_session = today.weekday() < 5

    if not is_session:
        if CALENDAR_AVAILABLE:
            try:
                last_td = _nyse.previous_session(str(today)).date()
            except Exception:
                last_td = today
        else:
            # Walk back to the last weekday (Mon–Fri) as best approximation
            last_td = today - timedelta(days=1)
            while last_td.weekday() >= 5:
                last_td -= timedelta(days=1)
        label = "Weekend" if today.weekday() >= 5 else "Holiday"
        return {"is_trading_day": False, "is_open": False,
                "last_trading_day": last_td, "status_label": label}

    market_open  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)
    is_open = market_open <= now_et <= market_close
    if now_et < market_open:
        label = "Pre-Market"
    elif is_open:
        label = "Open"
    else:
        label = "After Hours"
    return {"is_trading_day": True, "is_open": is_open,
            "last_trading_day": today, "status_label": label}

# ── Data fetchers ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400 * 7)
def get_stock_data(tickers: tuple, trading_day: str) -> dict:
    """Per-ticker history fetch. In-memory cookie cache reuses auth after first call."""
    result = {}
    errors = {}
    for t in tickers:
        try:
            stock = yf.Ticker(t)
            hist  = stock.history(period="6mo")
            if hist.empty:
                errors[t] = "history empty"
                result[t] = None
                time.sleep(0.5)
                continue
            close = hist["Close"].dropna()
            price = float(close.iloc[-1])
            prev  = float(close.iloc[-2]) if len(close) > 1 else price
            beta      = 1.0
            div_yield = 0.0
            try:
                info      = stock.info
                beta      = float(info.get("beta") or 1.0)
                div_yield = float(info.get("dividendYield") or 0.0) * 100
            except Exception:
                pass
            result[t] = {
                "price":     price,
                "change":    ((price - prev) / prev) * 100 if prev else 0.0,
                "beta":      beta,
                "div_yield": div_yield,
                "history":   close,
            }
        except Exception as e:
            errors[t] = str(e)
            result[t] = None
        time.sleep(0.3)   # gentle pacing — cookie is reused, only data requests hit Yahoo
    result["__errors__"] = errors
    return result

@st.cache_data(ttl=86400 * 30)
def get_buy_price(ticker: str, buy_date: str):
    """Closing price on buy_date using batch-safe yf.download. Cached 30 days."""
    try:
        d = pd.to_datetime(buy_date)
        end = d + pd.Timedelta(days=7)
        dl = yf.download(ticker, start=d.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"),
                         progress=False, auto_adjust=True)
        if dl.empty:
            return None
        close = dl["Close"] if "Close" in dl.columns else dl.iloc[:, 0]
        close = close.dropna()
        return float(close.iloc[0]) if not close.empty else None
    except Exception:
        return None

@st.cache_data(ttl=86400 * 7)
def get_analyst_targets(tickers: tuple, trading_day: str) -> dict:
    result = {}
    for t in tickers:
        try:
            targets = yf.Ticker(t).analyst_price_targets
            if targets and targets.get("mean") is not None:
                result[t] = {
                    "mean":   targets.get("mean"),
                    "low":    targets.get("low"),
                    "high":   targets.get("high"),
                    "median": targets.get("median"),
                    "count":  targets.get("numberOfAnalysts", 0),
                }
            else:
                result[t] = None
        except Exception:
            result[t] = None
    return result

@st.cache_data(ttl=86400 * 7)
def get_upgrades_downgrades(tickers: tuple, trading_day: str, lookback_days: int = 180) -> dict:
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=lookback_days)
    result = {}
    empty  = pd.DataFrame(columns=["date", "firm", "action", "from_grade", "to_grade"])
    # yfinance column names have changed across versions — normalise defensively
    _COL_MAP = {
        "gradedate": "date", "date": "date",
        "tograde":   "to_grade",   "to_grade":   "to_grade",
        "fromgrade": "from_grade", "from_grade": "from_grade",
        "firm":      "firm",       "company":    "firm",
        "action":    "action",
    }
    for t in tickers:
        try:
            df = yf.Ticker(t).upgrades_downgrades
            if df is None or df.empty:
                result[t] = empty.copy()
                continue
            df = df.reset_index()
            df.columns = [c.lower().replace(" ", "") for c in df.columns]
            df = df.rename(columns={c: _COL_MAP[c] for c in df.columns if c in _COL_MAP})
            if "date" not in df.columns:
                result[t] = empty.copy()
                continue
            df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
            df = df.dropna(subset=["date"])
            df = df[df["date"] >= cutoff].sort_values("date", ascending=False)
            # keep only columns we have; fill missing with ""
            for col in ("firm", "action", "from_grade", "to_grade"):
                if col not in df.columns:
                    df[col] = ""
            result[t] = df[["date", "firm", "action", "from_grade", "to_grade"]].reset_index(drop=True)
        except Exception:
            result[t] = empty.copy()
    return result

@st.cache_resource
def _finnhub_client(api_key: str):
    return finnhub.Client(api_key=api_key)

@st.cache_data(ttl=86400 * 7)
def get_consensus(tickers: tuple, trading_day: str, api_key: str) -> dict:
    result = {}
    for t in tickers:
        entry = _fetch_consensus_one(t, api_key)
        result[t] = entry
    return result

def _fetch_consensus_one(ticker: str, api_key: str) -> dict:
    # Try Finnhub first, fall back to yfinance
    if FINNHUB_AVAILABLE and api_key and api_key != "your_key_here":
        try:
            trends = _finnhub_client(api_key).recommendation_trends(ticker)
            if trends:
                r = trends[0]
                sb = r.get("strongBuy", 0)
                b  = r.get("buy", 0)
                h  = r.get("hold", 0)
                s  = r.get("sell", 0)
                ss = r.get("strongSell", 0)
                total = sb + b + h + s + ss
                return {"strong_buy": sb, "buy": b, "hold": h, "sell": s,
                        "strong_sell": ss, "total": total,
                        "label": _consensus_label(sb, b, h, s, ss, total)}
        except Exception:
            pass
    # yfinance fallback
    try:
        df = yf.Ticker(ticker).recommendations_summary
        if df is not None and not df.empty:
            row = df[df["period"] == "0m"].iloc[0] if "0m" in df["period"].values else df.iloc[0]
            sb = int(row.get("strongBuy", 0))
            b  = int(row.get("buy", 0))
            h  = int(row.get("hold", 0))
            s  = int(row.get("sell", 0))
            ss = int(row.get("strongSell", 0))
            total = sb + b + h + s + ss
            return {"strong_buy": sb, "buy": b, "hold": h, "sell": s,
                    "strong_sell": ss, "total": total,
                    "label": _consensus_label(sb, b, h, s, ss, total)}
    except Exception:
        pass
    return {"strong_buy": 0, "buy": 0, "hold": 0, "sell": 0,
            "strong_sell": 0, "total": 0, "label": "N/A"}

def _consensus_label(sb, b, h, s, ss, total) -> str:
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

@st.cache_data(ttl=86400 * 7)
def get_finviz_fundamentals(tickers: tuple, trading_day: str) -> dict:
    if not FINVIZ_AVAILABLE:
        return {t: {} for t in tickers}
    FIELDS = {
        "P/E": "pe", "Forward P/E": "forward_pe", "EPS (ttm)": "eps_ttm",
        "Short Float": "short_float", "Inst Own": "inst_own",
        "ROE": "roe", "Market Cap": "market_cap", "Sector": "sector",
    }
    result = {}
    for t in tickers:
        try:
            raw = fvf(t).ticker_fundament()
            result[t] = {new: raw.get(orig, "-") for orig, new in FIELDS.items()}
        except Exception:
            result[t] = {}
        time.sleep(0.3)
    return result

@st.cache_data(ttl=1800)
def get_news(tickers: tuple, _trading_day: str, max_per: int = 5) -> dict:
    result = {}
    for t in tickers:
        try:
            raw = yf.Ticker(t).news or []
            items = []
            for article in raw[:max_per]:
                # yfinance 2024+ nests under 'content'
                c = article.get("content", article)
                provider = c.get("provider", {})
                if isinstance(provider, dict):
                    pub_name = provider.get("displayName", "Unknown")
                else:
                    pub_name = str(provider)
                url_obj = c.get("canonicalUrl", {})
                url = url_obj.get("url", "#") if isinstance(url_obj, dict) else str(url_obj)
                items.append({
                    "title":     c.get("title", article.get("title", "No title")),
                    "publisher": pub_name,
                    "link":      url,
                    "published": pd.to_datetime(
                        c.get("pubDate", article.get("providerPublishTime", "")),
                        utc=True, errors="coerce"
                    ),
                })
            result[t] = items
        except Exception:
            result[t] = []
    return result

@st.cache_data(ttl=86400 * 7)
def get_eps_trend(ticker: str, trading_day: str):
    try:
        df = yf.Ticker(ticker).eps_trend
        return df if df is not None and not df.empty else None
    except Exception as e:
        return str(e)

@st.cache_data(ttl=86400 * 7)
def get_commodity_prices(trading_day: str) -> dict:
    """Fetch gold (GC=F), copper (HG=F) and uranium (UX1=F) spot prices."""
    result = {}
    for sym, key, divisor_if_large in [
        ("GC=F",  "gold",    None),   # USD/oz
        ("HG=F",  "copper",  100.0),  # sometimes quoted in cents/lb
        ("UX1=F", "uranium", None),   # USD/lb
    ]:
        try:
            hist = yf.Ticker(sym).history(period="5d")
            if not hist.empty:
                price = float(hist["Close"].dropna().iloc[-1])
                if divisor_if_large and price > 20:
                    price /= divisor_if_large
                result[key] = price
        except Exception:
            pass
    return result

def load_all_data(portfolio: dict, market_state: dict, api_key: str) -> dict:
    tickers = tuple(sorted(all_tickers(portfolio)))
    td = str(market_state["last_trading_day"])
    with st.spinner("Loading prices & history..."):
        prices = get_stock_data(tickers, td)
    with st.spinner("Loading analyst targets..."):
        targets = get_analyst_targets(tickers, td)
    with st.spinner("Loading analyst consensus..."):
        consensus = get_consensus(tickers, td, api_key)
    with st.spinner("Loading upgrades & downgrades..."):
        upgrades = get_upgrades_downgrades(tickers, td)
    if FINVIZ_AVAILABLE:
        with st.spinner("Loading Finviz fundamentals (~5s)..."):
            fundamentals = get_finviz_fundamentals(tickers, td)
    else:
        fundamentals = {t: {} for t in tickers}
    with st.spinner("Loading news..."):
        news = get_news(tickers, td)
    with st.spinner("Loading commodity prices..."):
        commodities = get_commodity_prices(td)
    return {
        "prices": prices, "targets": targets, "consensus": consensus,
        "upgrades": upgrades, "fundamentals": fundamentals, "news": news,
        "commodities": commodities,
    }

# ── UI helpers ─────────────────────────────────────────────────────────────────

def kpi(label: str, value: str, tooltip: str, color: str = ""):
    style = f"color:{color};" if color else ""
    st.markdown(
        f'<div style="margin:2px 0"><span title="{tooltip}" style="font-size:12px;color:#aaa">'
        f'{label} <span style="font-size:10px">&#9432;</span></span>'
        f'<br><span style="font-size:14px;font-weight:600;{style}">{value}</span></div>',
        unsafe_allow_html=True,
    )

def color_pnl(val: float) -> str:
    return "#4CAF50" if val >= 0 else "#F44336"

HE_STATUS = {
    "Open":        "פתוח",
    "Pre-Market":  "טרום מסחר",
    "After Hours": "אחרי שעות",
    "Weekend":     "סוף שבוע",
    "Holiday":     "חג",
}

def market_badge(state: dict) -> str:
    label = HE_STATUS.get(state["status_label"], state["status_label"])
    colors = {
        "פתוח":        ("#4CAF50", "#1a3a1a"),
        "טרום מסחר":   ("#FF9800", "#3a2a00"),
        "אחרי שעות":  ("#9E9E9E", "#2a2a2a"),
        "סוף שבוע":   ("#9E9E9E", "#2a2a2a"),
        "חג":          ("#FF9800", "#3a2a00"),
    }
    fg, bg = colors.get(label, ("#9E9E9E", "#2a2a2a"))
    return (
        f'<span style="background:{bg};color:{fg};border:1px solid {fg};'
        f'border-radius:12px;padding:2px 10px;font-size:12px;font-weight:600">'
        f'&#9679; {label}</span>'
    )

# ── Tab renderers ──────────────────────────────────────────────────────────────

def render_overview(portfolio, data, market_state):
    prices  = data["prices"]
    targets = data["targets"]
    voo_hist = (prices.get("VOO") or {}).get("history")

    # Surface any data-fetch errors for debugging
    errs = prices.get("__errors__", {})
    if errs:
        with st.expander(f"⚠️ Data fetch issues ({len(errs)} tickers)", expanded=False):
            for tkr, msg in errs.items():
                st.caption(f"{tkr}: {msg}")

    # ── Performance summary table ─────────────────────────────────────────
    LAYER_SHORT = {
        "Core (50%)":            "CORE (50%)",
        "Physical Infrastructure": "Physical Infra",
        "Compute & Platform":    "Compute",
        "Security & Stability":  "Security",
    }
    voo_info = prices.get("VOO") or {}
    voo_h    = voo_info.get("history")
    voo_ret  = ((voo_h.iloc[-1] / voo_h.iloc[0]) - 1) if (voo_h is not None and len(voo_h) > 1) else None

    perf_rows = []
    for layer_name, positions in portfolio["layers"].items():
        if layer_name == "__errors__":
            continue
        layer_label = LAYER_SHORT.get(layer_name, layer_name)
        for pos in positions:
            t    = pos["ticker"]
            info = prices.get(t) or {}
            tgt  = targets.get(t) or {}
            price = info.get("price")
            if price is None:
                continue
            upside = None
            if tgt.get("mean"):
                upside = (tgt["mean"] - price) / price * 100
            alpha = None
            if t != "VOO" and voo_ret is not None:
                t_h = info.get("history")
                if t_h is not None and len(t_h) > 1:
                    t_ret = (t_h.iloc[-1] / t_h.iloc[0]) - 1
                    alpha = (t_ret - voo_ret) * 100
            # Status dot: green if upside > 0, orange if -10<upside<=0, red if <=-10
            if upside is None:
                dot = "⚪"
            elif upside > 0:
                dot = '<span style="color:#4CAF50;font-size:16px">●</span>'
            elif upside > -10:
                dot = '<span style="color:#FF9800;font-size:16px">●</span>'
            else:
                dot = '<span style="color:#F44336;font-size:16px">●</span>'

            perf_rows.append({
                "_layer": layer_label,
                "_ticker": t,
                "_price": f"${price:,.2f}",
                "_upside": f"{upside:+.1f}%" if upside is not None else "—",
                "_upside_val": upside or -999,
                "_alpha": f"{alpha:+.1f}%" if alpha is not None else "—",
                "_alpha_val": alpha or 0,
                "_dot": dot,
            })

    if perf_rows:
        _TH = ("direction:rtl;text-align:right;padding:6px 10px;"
               "color:#00cf8d;border-bottom:1px solid #333;font-size:12px")
        _TD = "padding:6px 10px;font-size:12px;white-space:nowrap"
        _UP_COLOR = lambda v: "#4CAF50" if v > 0 else ("#FF9800" if v > -10 else "#F44336")
        _AL_COLOR = lambda v: "#4CAF50" if v >= 0 else "#F44336"

        rows_html = ""
        for i, r in enumerate(perf_rows):
            bg = "background:#1a1a2a" if i % 2 else ""
            up_c = _UP_COLOR(r["_upside_val"]) if r["_upside"] != "—" else "#aaa"
            al_c = _AL_COLOR(r["_alpha_val"]) if r["_alpha"] != "—" else "#aaa"
            rows_html += (
                f'<tr style="{bg}">'
                f'<td style="{_TD};color:#aaa">{r["_layer"]}</td>'
                f'<td style="{_TD};font-weight:700;color:#00cf8d">{r["_ticker"]}</td>'
                f'<td style="{_TD};text-align:right">{r["_price"]}</td>'
                f'<td style="{_TD};text-align:right;color:{up_c};font-weight:600">{r["_upside"]}</td>'
                f'<td style="{_TD};text-align:right;color:{al_c};font-weight:600">{r["_alpha"]}</td>'
                f'<td style="{_TD};text-align:center">{r["_dot"]}</td>'
                f'</tr>'
            )

        st.markdown(
            f'<table style="width:100%;border-collapse:collapse;margin-bottom:8px">'
            f'<thead><tr>'
            f'<th style="{_TH}">שכבה אסטרטגית</th>'
            f'<th style="{_TH}">Ticker</th>'
            f'<th style="{_TH};text-align:right">מחיר</th>'
            f'<th style="{_TH};text-align:right">Upside %</th>'
            f'<th style="{_TH};text-align:right">Alpha (vs VOO)</th>'
            f'<th style="{_TH};text-align:center">סטטוס</th>'
            f'</tr></thead><tbody>{rows_html}</tbody></table>',
            unsafe_allow_html=True,
        )
        st.divider()

    # Portfolio summary bar
    total_invested = total_value = total_pnl = 0.0
    for positions in portfolio["layers"].values():
        for pos in positions:
            t      = pos["ticker"]
            shares = pos.get("shares", 0)
            if shares <= 0:
                continue
            price = (prices.get(t) or {}).get("price", 0)
            bp    = get_buy_price(t, pos["buy_date"]) or 0
            cost  = shares * bp
            val   = shares * price
            total_invested += cost
            total_value    += val
            total_pnl      += (val - cost)

    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0

    if total_invested > 0:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("סה״כ הושקע",   f"${total_invested:,.0f}")
        c2.metric("שווי נוכחי",    f"${total_value:,.0f}",
                  delta=f"${total_value - total_invested:+,.0f}")
        c3.metric("רווח/הפסד $",   f"${total_pnl:+,.0f}")
        c4.metric("רווח/הפסד %",   f"{total_pnl_pct:+.2f}%")
        st.divider()

    # Layer allocation pie
    layer_values = {}
    for layer_name, positions in portfolio["layers"].items():
        val = sum(
            pos["shares"] * ((prices.get(pos["ticker"]) or {}).get("price", 0))
            for pos in positions if pos["shares"] > 0
        )
        if val > 0:
            layer_values[layer_name] = val

    if layer_values:
        col_pie, _ = st.columns([1, 2])
        with col_pie:
            fig_pie = go.Figure(data=[go.Pie(
                labels=list(layer_values.keys()),
                values=list(layer_values.values()),
                hole=0.35,
                textinfo="label+percent",
                hovertemplate="%{label}<br>$%{value:,.0f}<br>%{percent}<extra></extra>",
            )])
            fig_pie.update_layout(
                title="הקצאת תיק לפי שכבה (שווי שוק)",
                height=320, margin=dict(t=40, b=0, l=0, r=0),
                showlegend=True,
            )
            st.plotly_chart(fig_pie, use_container_width=True,
                            config={"displayModeBar": False})
    else:
        st.info("הוסף מספר מניות בלשונית 'תיק שלי' כדי לראות את תרשים ההקצאה.")

    st.divider()

    # Layer sections
    for layer_name, positions in portfolio["layers"].items():
        if layer_name == "__errors__":
            continue
        st.markdown(f"### 📁 {layer_name}")
        if not positions:
            st.caption("אין פוזיציות בשכבה זו.")
            continue
        cols = st.columns(len(positions))
        for col, pos in zip(cols, positions):
            t      = pos["ticker"]
            shares = pos.get("shares", 0)
            info   = prices.get(t)
            tgt    = targets.get(t)

            with col:
                # Card background
                st.markdown(
                    f'<div style="background:#1e1e2e;border-radius:10px;padding:10px 12px 4px 12px;margin-bottom:4px">'
                    f'<span style="font-size:16px;font-weight:700;color:#00cf8d">{t}</span>'
                    + (f'<br><span style="font-size:10px;color:#FF9800">⚠️ כיסוי מוגבל בארה"ב</span>' if t in KNOWN_LIMITED_TICKERS else "")
                    + '</div>',
                    unsafe_allow_html=True,
                )

                if info is None:
                    st.warning("אין נתונים")
                    continue

                price  = info["price"]
                change = info["change"]

                st.metric("מחיר", f"${price:.2f}",
                          delta=f"{change:+.2f}%",
                          delta_color="normal")

                kpi("בטא", f"{info['beta']:.2f}", KPI_TOOLTIPS["בטא"])

                if tgt and tgt.get("mean"):
                    upside = (tgt["mean"] - price) / price * 100
                    kpi("עלייה אפשרית", f"{upside:+.1f}%",
                        KPI_TOOLTIPS["עלייה אפשרית"], color_pnl(upside))
                    n = tgt.get("count", "?")
                    kpi("יעד מחיר",
                        f"${tgt['low']:.0f} / ${tgt['mean']:.0f} / ${tgt['high']:.0f}",
                        f"{KPI_TOOLTIPS['יעד מחיר']} ({n} אנליסטים)")
                else:
                    kpi("עלייה אפשרית", "אין נתון", KPI_TOOLTIPS["עלייה אפשרית"])

                if t != "VOO" and voo_hist is not None:
                    t_hist = info.get("history")
                    if t_hist is not None and len(voo_hist) > 1 and len(t_hist) > 1:
                        alpha = (
                            (t_hist.iloc[-1] / t_hist.iloc[0] - 1) -
                            (voo_hist.iloc[-1] / voo_hist.iloc[0] - 1)
                        ) * 100
                        kpi("עדיפות vs VOO", f"{alpha:+.1f}%",
                            KPI_TOOLTIPS["עדיפות vs VOO"], color_pnl(alpha))

                if shares > 0:
                    bp  = get_buy_price(t, pos["buy_date"])
                    val = shares * price
                    kpi("מניות",  f"{shares:g}",   KPI_TOOLTIPS["מניות"])
                    kpi("שווי",   f"${val:,.0f}",  KPI_TOOLTIPS["שווי"])
                    if bp:
                        pnl     = val - shares * bp
                        pnl_pct = pnl / (shares * bp) * 100
                        kpi("רווח/הפסד", f"${pnl:+,.0f} ({pnl_pct:+.1f}%)",
                            KPI_TOOLTIPS["רווח/הפסד"], color_pnl(pnl))
                        days = (date.today() - date.fromisoformat(pos["buy_date"])).days
                        kpi("תקופת אחזקה", f"{days} ימים", KPI_TOOLTIPS["תקופת אחזקה"])
                else:
                    st.caption("_הזן מניות בלשונית 'תיק שלי'_")

                # Three sparklines: 30d / YTD / 6mo
                hist = info.get("history")
                if hist is not None and len(hist) > 1:
                    ytd_start = pd.Timestamp(
                        f"{date.today().year}-01-01", tz="UTC"
                    )
                    slices = [
                        ("30י׳", hist.iloc[-30:] if len(hist) >= 30 else hist),
                        ("YTD",  hist[hist.index >= ytd_start] if hasattr(hist.index, "tz") else hist.iloc[-63:]),
                        ("6M",   hist),
                    ]
                    sp_cols = st.columns(3)
                    for sp_col, (label, s) in zip(sp_cols, slices):
                        if s is None or len(s) < 2:
                            sp_col.caption(label)
                            continue
                        clr = "#4CAF50" if s.iloc[-1] >= s.iloc[0] else "#F44336"
                        chg = (s.iloc[-1] / s.iloc[0] - 1) * 100
                        fig_s = go.Figure()
                        fig_s.add_trace(go.Scatter(
                            y=s, mode="lines",
                            line=dict(color=clr, width=1.5)
                        ))
                        fig_s.update_layout(
                            height=65, margin=dict(l=0, r=0, t=14, b=0),
                            xaxis_visible=False, yaxis_visible=False,
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            title=dict(
                                text=f"<b>{label}</b> {chg:+.1f}%",
                                font=dict(size=10, color=clr),
                                x=0.5, xanchor="center", y=1, yanchor="top",
                            ),
                        )
                        sp_col.plotly_chart(fig_s, use_container_width=True,
                                            config={"displayModeBar": False})
        st.divider()


def render_portfolio_tab(portfolio, data):
    prices = data["prices"]
    st.subheader("כל הפוזיציות שלי")

    rows = []
    for layer_name, positions in portfolio["layers"].items():
        for pos in positions:
            t      = pos["ticker"]
            shares = pos.get("shares", 0)
            info   = prices.get(t) or {}
            price  = info.get("price", 0)
            bp     = get_buy_price(t, pos["buy_date"]) if shares > 0 else None
            cost   = shares * bp if bp else None
            val    = shares * price if price else None
            pnl    = (val - cost) if (val is not None and cost is not None) else None
            pnl_pct = (pnl / cost * 100) if (pnl is not None and cost and cost > 0) else None
            days   = (date.today() - date.fromisoformat(pos["buy_date"])).days
            rows.append({
                "Ticker":    t,
                "Layer":     layer_name,
                "Shares":    shares if shares > 0 else "—",
                "Buy Date":  pos["buy_date"],
                "Buy $":     f"${bp:.2f}" if bp else "—",
                "Cost":      f"${cost:,.0f}" if cost else "—",
                "Value":     f"${val:,.0f}" if val else "—",
                "P&L $":     f"${pnl:+,.0f}" if pnl is not None else "—",
                "P&L %":     f"{pnl_pct:+.1f}%" if pnl_pct is not None else "—",
                "Days":      days,
            })

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.markdown(
            '<div dir="rtl" style="font-size:12px;color:#aaa;line-height:1.8">'
            '<b>Ticker</b> — סימול הנייר. &nbsp;|&nbsp; '
            '<b>Buy $</b> — מחיר הסגירה ביום הרכישה (מ-yfinance). &nbsp;|&nbsp; '
            '<b>Cost</b> — עלות כוללת: מניות × מחיר רכישה. &nbsp;|&nbsp; '
            '<b>Value</b> — שווי נוכחי: מניות × מחיר היום. &nbsp;|&nbsp; '
            '<b>P&L $</b> — רווח/הפסד לא ממומש בדולרים. &nbsp;|&nbsp; '
            '<b>P&L %</b> — רווח/הפסד אחוזי מהעלות. &nbsp;|&nbsp; '
            '<b>Days</b> — ימי אחזקה מתאריך הרכישה.'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("אין פוזיציות עדיין. הוסף פוזיציה בטופס למטה.")

    st.divider()
    st.subheader("➕ הוסף / עדכן פוזיציה")

    # Build ticker→layer map from current portfolio
    ticker_layer_map = {
        p["ticker"]: layer_name
        for layer_name, positions in portfolio["layers"].items()
        for p in positions
    }

    # Dropdown list: known tickers with display names + manual entry option
    MANUAL = "➕ סימול חדש (הזן ידנית)"
    known_tickers = sorted(ticker_layer_map.keys())

    def _ticker_label(t):
        name = TICKER_NAMES.get(t, "")
        return f"{t} — {name}" if name else t

    ticker_options = [_ticker_label(t) for t in known_tickers] + [MANUAL]
    sel_label = st.selectbox("בחר חברה לעדכון", ticker_options, key="add_ticker_sel")

    if sel_label == MANUAL:
        ticker_in = st.text_input("סימול ידני", placeholder="לדוג׳ MSFT",
                                  key="manual_ticker").upper().strip()
        auto_layer = None
    else:
        ticker_in = sel_label.split(" — ")[0]
        auto_layer = ticker_layer_map.get(ticker_in)

    layer_options = list(portfolio["layers"].keys()) + ["+ שכבה חדשה"]
    default_idx = layer_options.index(auto_layer) if auto_layer in layer_options else 0

    with st.form("add_position", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        layer_sel = c1.selectbox("שכבה", layer_options, index=default_idx)
        shares_in = c2.number_input("מספר מניות", min_value=0.001, step=1.0,
                                    format="%.3f", value=1.0)
        date_in   = c3.date_input("תאריך רכישה", value=date.today())
        new_layer = st.text_input("שם שכבה חדשה (אם בחרת '+ שכבה חדשה')", "") \
                    if layer_sel == "+ שכבה חדשה" else ""
        submitted = st.form_submit_button("✅ הוסף / עדכן", type="primary")
        if submitted:
            if not ticker_in:
                st.error("נא לבחור סימול.")
            else:
                layer = new_layer.strip() if layer_sel == "+ שכבה חדשה" else layer_sel
                if not layer:
                    st.error("נא להזין שם שכבה.")
                else:
                    add_position(portfolio, layer, ticker_in, shares_in, date_in)
                    st.cache_data.clear()
                    st.success(f"✅ {ticker_in} נוסף לשכבה '{layer}'")
                    st.rerun()

    st.divider()
    st.subheader("🗑️ הסר פוזיציה")
    if portfolio["layers"]:
        rc1, rc2, rc3 = st.columns(3)
        del_layer = rc1.selectbox("שכבה", list(portfolio["layers"].keys()), key="del_l")
        del_opts  = [p["ticker"] for p in portfolio["layers"].get(del_layer, [])]
        if del_opts:
            del_ticker = rc2.selectbox("סימול", del_opts, key="del_t")
            if rc3.button("🗑️ הסר", type="secondary"):
                remove_position(portfolio, del_layer, del_ticker)
                st.rerun()
        else:
            rc2.caption("אין פוזיציות בשכבה זו.")


def render_analysts(portfolio, data):
    prices    = data["prices"]
    targets   = data["targets"]
    consensus = data["consensus"]
    upgrades  = data["upgrades"]
    tickers   = sorted(all_tickers(portfolio))

    st.subheader("קונצנזוס אנליסטים")

    CONSENSUS_HE = {
        "Strong Buy": "קנה חזק", "Buy": "קנה",
        "Hold": "החזק", "Sell": "מכור", "N/A": "אין נתון",
    }

    def _cstyle(val):
        c = {"קנה חזק": "#1a7a4a", "קנה": "#2d9e6b",
             "החזק": "#7a6a1a", "מכור": "#9e3a2d"}.get(str(val), "")
        return f"background-color:{c};color:white" if c else ""

    c_rows = []
    for t in tickers:
        c = consensus.get(t, {})
        c_rows.append({
            "Ticker":      t,
            "Strong Buy":  c.get("strong_buy", 0),
            "Buy":         c.get("buy", 0),
            "Hold":        c.get("hold", 0),
            "Sell":        c.get("sell", 0) + c.get("strong_sell", 0),
            "Total":       c.get("total", 0),
            "Consensus":   CONSENSUS_HE.get(c.get("label", "N/A"), c.get("label", "N/A")),
        })
    df_c = pd.DataFrame(c_rows)
    st.dataframe(
        df_c.style.applymap(_cstyle, subset=["Consensus"]),
        use_container_width=True, hide_index=True,
    )
    st.markdown(
        '<div dir="rtl" style="font-size:12px;color:#aaa;line-height:1.8">'
        '<b>Strong Buy / Buy / Hold / Sell</b> — מספר אנליסטים שממליצים על כל דירוג. '
        'המספרים מגיעים מ-Finnhub (עם גיבוי מ-yfinance). &nbsp;|&nbsp; '
        '<b>Total</b> — סך כל האנליסטים המכסים את המניה. &nbsp;|&nbsp; '
        '<b>Consensus</b> — המלצת הרוב: קנה חזק אם 70%+ ממליצים קנייה, '
        'קנה אם 50%+, מכור אם 40%+ ממליצים מכירה, אחרת החזק.'
        '</div>',
        unsafe_allow_html=True,
    )

    st.divider()
    st.subheader("טווחי יעד מחיר של אנליסטים")
    tickers_with = [t for t in tickers if targets.get(t) and targets[t].get("mean")]
    if tickers_with:
        fig = go.Figure()
        for t in tickers_with:
            tgt   = targets[t]
            price = (prices.get(t) or {}).get("price")
            fig.add_trace(go.Scatter(
                x=[tgt["low"], tgt["mean"], tgt["high"]],
                y=[t, t, t],
                mode="lines+markers",
                name=t,
                line=dict(color="#00cf8d", width=3),
                marker=dict(size=[8, 12, 8]),
                hovertemplate="%{x:.2f}<extra>%{y}</extra>",
            ))
            if price:
                fig.add_trace(go.Scatter(
                    x=[price], y=[t], mode="markers",
                    marker=dict(symbol="line-ns-open", size=16,
                                color="white", line=dict(width=2)),
                    showlegend=False,
                    hovertemplate=f"Current: ${price:.2f}<extra></extra>",
                ))
        fig.update_layout(
            height=max(300, len(tickers_with) * 40),
            margin=dict(l=60, r=20, t=20, b=20),
            xaxis_title="מחיר ($)", showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("אין נתוני יעד מחיר זמינים.")

    st.divider()
    st.subheader("שדרוגים/שינמוכים אחרונים (90 יום)")
    sel = st.selectbox("בחר סימול", tickers, key="ud_sel")
    if sel in KNOWN_LIMITED_TICKERS:
        st.info(f"כיסוי אנליסטים אמריקאי מוגבל עבור {sel} (מניה ישראלית).")
    df_ud = upgrades.get(sel, pd.DataFrame())
    if df_ud.empty:
        st.caption("לא נמצאו פעולות אנליסט ב-90 הימים האחרונים.")
    else:
        def _astyle(val):
            v = str(val).lower()
            if "up" in v or "init" in v:
                return "color:#4CAF50"
            if "down" in v:
                return "color:#F44336"
            return "color:#2196F3"
        df_show = df_ud.copy()
        df_show["date"] = df_show["date"].dt.strftime("%Y-%m-%d")
        df_show = df_show.rename(columns={
            "date": "Date", "firm": "Firm",
            "action": "Action", "from_grade": "From", "to_grade": "To",
        })
        st.dataframe(
            df_show.style.applymap(_astyle, subset=["Action"]),
            use_container_width=True, hide_index=True,
        )
        st.markdown(
            '<div dir="rtl" style="font-size:12px;color:#aaa;line-height:1.8">'
            '<b>Firm</b> — שם בית ההשקעות (Goldman Sachs, JPMorgan וכו׳). &nbsp;|&nbsp; '
            '<b>Action</b> — סוג הפעולה: <span style="color:#4CAF50">Upgrade = שדרוג</span>, '
            '<span style="color:#F44336">Downgrade = שינמוך</span>, '
            '<span style="color:#2196F3">Initiated = כיסוי חדש</span>. &nbsp;|&nbsp; '
            '<b>From / To</b> — הדירוג הקודם והחדש (Buy, Hold, Sell וכו׳).'
            '</div>',
            unsafe_allow_html=True,
        )


def render_fundamentals(portfolio, data):
    tickers = sorted(all_tickers(portfolio))
    if not FINVIZ_AVAILABLE:
        st.warning("נא להתקין finvizfinance לנתונים פונדמנטליים: `pip install finvizfinance`")
        return

    fund = data["fundamentals"]
    has_data = any(fund.get(t) for t in tickers)
    if not has_data:
        st.info("נתונים פונדמנטליים אינם זמינים (ייתכן שהסימולים אינם במסד הנתונים האמריקאי של Finviz).")
        return

    # ── Table 1: Valuation ────────────────────────────────────────────────
    st.subheader("📊 הערכת שווי")
    val_rows = []
    for t in tickers:
        f = fund.get(t) or {}
        val_rows.append({
            "Ticker": t,
            "P/E": f.get("pe", "—"),
            "Fwd P/E": f.get("forward_pe", "—"),
            "EPS (TTM)": f.get("eps_ttm", "—"),
            "ROE": f.get("roe", "—"),
        })
    st.dataframe(pd.DataFrame(val_rows), use_container_width=True, hide_index=True)
    st.markdown(
        '<div dir="rtl" style="font-size:12px;color:#aaa;line-height:1.8;margin-bottom:8px">'
        '<b>P/E</b> — מכפיל רווח: מחיר המניה חלקי הרווח השנתי למניה. '
        'ערך נמוך = זול יחסית לרווחים (לדוג׳ S&P 500 ממוצע ~20). &nbsp;|&nbsp; '
        '<b>Fwd P/E</b> — מכפיל רווח עתידי: מחושב לפי תחזיות אנליסטים לשנה הבאה — '
        'נמוך מ-P/E הנוכחי = צמיחת רווחים צפויה. &nbsp;|&nbsp; '
        '<b>EPS (TTM)</b> — רווח למניה ב-12 החודשים האחרונים (Trailing Twelve Months). &nbsp;|&nbsp; '
        '<b>ROE</b> — תשואה על ההון העצמי: כמה רווח נוצר על כל $1 של הון. מעל 15% = טוב.'
        '</div>',
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Table 2: Market & Ownership ───────────────────────────────────────
    st.subheader("🏦 שוק ובעלות")
    mkt_rows = []
    for t in tickers:
        f = fund.get(t) or {}
        mkt_rows.append({
            "Ticker": t,
            "Market Cap": f.get("market_cap", "—"),
            "Short Float": f.get("short_float", "—"),
            "Inst Own": f.get("inst_own", "—"),
            "Sector": f.get("sector", "—"),
        })
    st.dataframe(pd.DataFrame(mkt_rows), use_container_width=True, hide_index=True)
    st.markdown(
        '<div dir="rtl" style="font-size:12px;color:#aaa;line-height:1.8;margin-bottom:8px">'
        '<b>Market Cap</b> — שווי שוק כולל: מחיר × מספר מניות. B = מיליארד דולר. &nbsp;|&nbsp; '
        '<b>Short Float</b> — אחוז מניות מושאלות לצורך שורט. מעל 10% = לחץ שורטיסטים גבוה, '
        'סיכון ל-Short Squeeze. &nbsp;|&nbsp; '
        '<b>Inst Own</b> — אחזקה מוסדית: קרנות גידור, פנסיה, בנקים. מעל 70% = אמון מוסדי גבוה. &nbsp;|&nbsp; '
        '<b>Sector</b> — הענף הכלכלי של החברה.'
        '</div>',
        unsafe_allow_html=True,
    )

    st.divider()
    with st.expander("📈 מגמת EPS (טעינה לפי דרישה)"):
        sel = st.selectbox("סימול", tickers, key="eps_sel")
        if st.button("טען מגמת EPS"):
            td_key = next(
                (str(v["history"].index[-1].date()) for v in data["prices"].values()
                 if isinstance(v, dict) and v.get("history") is not None and len(v["history"]) > 0),
                str(date.today())
            )
            result = get_eps_trend(sel, td_key)
            if isinstance(result, str):
                st.error(result)
            elif result is not None:
                st.dataframe(result, use_container_width=True)
            else:
                st.info("אין נתוני מגמת EPS.")


def render_news(portfolio, data):
    tickers = sorted(all_tickers(portfolio))
    sel = st.multiselect("סנן לפי סימול", tickers, default=tickers, key="news_sel")
    articles = []
    for t in sel:
        for a in data["news"].get(t, []):
            articles.append({"ticker": t, **a})
    articles.sort(
        key=lambda x: x["published"] if pd.notna(x.get("published")) else pd.Timestamp.min,
        reverse=True,
    )
    if not articles:
        st.info("לא נמצאו חדשות אחרונות.")
        return
    for a in articles:
        c1, c2 = st.columns([0.07, 0.93])
        c1.markdown(f"**{a['ticker']}**")
        pub = a["published"].strftime("%b %d") if pd.notna(a.get("published")) else ""
        c2.markdown(f"[{a['title']}]({a['link']})  \n*{a['publisher']}* · {pub}")
        st.divider()


# ── App entry point ────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="דשבורד השקעות — רז", layout="wide",
                       initial_sidebar_state="expanded")

    # RTL — apply to the main content block only, not Streamlit's shell/flex wrappers
    st.markdown("""
    <style>
    /* Main content area: RTL */
    [data-testid="stMain"] { direction: rtl; }

    /* Sidebar: RTL */
    [data-testid="stSidebar"] { direction: rtl; }

    /* Metric labels */
    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
    [data-testid="stMetricDelta"] { direction: rtl; text-align: right; }

    /* Tabs: right-to-left order */
    [data-testid="stTabs"] [role="tablist"] { flex-direction: row-reverse; }

    /* Dataframes and charts: always LTR so numbers/axes display correctly */
    [data-testid="stDataFrame"],
    [data-testid="stDataFrame"] *,
    .dvn-scroller, .dvn-scroller *,
    .js-plotly-plot, .js-plotly-plot *,
    iframe { direction: ltr !important; text-align: left !important; }

    /* Input widgets: keep LTR internally for usability */
    input, textarea { direction: ltr; }
    </style>
    """, unsafe_allow_html=True)

    portfolio    = load_portfolio()
    market_state = get_market_state()
    try:
        api_key = st.secrets.get("FINNHUB_API_KEY", "")
    except Exception:
        api_key = ""

    td_str = (market_state["last_trading_day"].strftime("%a %d %b %Y")
              if hasattr(market_state["last_trading_day"], "strftime")
              else str(market_state["last_trading_day"]))

    st.markdown(
        f'<h1 style="margin-bottom:4px;direction:rtl">&#127963; דשבורד השקעות — רז &nbsp;'
        f'{market_badge(market_state)}</h1>'
        f'<p style="color:#aaa;margin-top:0;direction:rtl">נכון ל-{td_str} &nbsp;&middot;&nbsp; תיק עידן הבינה המלאכותית</p>',
        unsafe_allow_html=True,
    )

    data = load_all_data(portfolio, market_state, api_key)

    tab_ov, tab_pf, tab_an, tab_fu, tab_nw = st.tabs([
        "סקירה", "תיק שלי", "אנליסטים", "פונדמנטלס", "חדשות"
    ])

    with tab_ov:
        render_overview(portfolio, data, market_state)
    with tab_pf:
        render_portfolio_tab(portfolio, data)
    with tab_an:
        render_analysts(portfolio, data)
    with tab_fu:
        render_fundamentals(portfolio, data)
    with tab_nw:
        render_news(portfolio, data)

    with st.sidebar:
        st.header("📰 ניתוח יומי")
        st.markdown(
            f'<div dir="rtl"><b>סיכום סיכונים ({date.today().strftime("%d.%m.%Y")}):</b>'
            "<ul>"
            "<li><b>VOO:</b> השוק בוחן את רמות התמיכה.</li>"
            "<li><b>VRT &amp; ETN:</b> נהנות ממומנטום חיובי חזק.</li>"
            "<li><b>אלביט:</b> חוזי ענק ממשיכים לזרום.</li>"
            "</ul>"
            "<b>המלצת הקצאה:</b> נאש ממליץ על 40-50% ב-VOO. השאר בחברות השכבה."
            "</div>",
            unsafe_allow_html=True,
        )

        st.divider()
        with st.expander("🚩 דגלים אדומים למעקב"):
            _TH  = "text-align:right;padding:4px 6px;color:#00cf8d;border-bottom:1px solid #444;font-size:11px"
            _TD  = "padding:4px 6px;font-size:11px;vertical-align:top"

            _flags = [
                ("VOO",    "תיקון שוק משמעותי",        "ירידה של 10%+ משיא 6-חודש",                                                              "בחינת הגנות (Hedge)"),
                ("CCJ",    "ירידה במחירי האורניום",     "מתחת ל-$80",                                                                             "בחינת חוזי אספקה"),
                ("FCX",    "ירידה במחירי הנחושת",       "מתחת ל-$4.2/lb",                                                                         "הערכת כדאיות כריה"),
                ("ETN",    "האטה בתשתיות חשמל",         "צמצום השקעות בחוות שרתים (AI)",                                                          "בדיקת צבר הזמנות (Backlog)"),
                ("VRT",    "ירידה בביקוש לקירור",       "ירידה בצבר הזמנות רבעוני",                                                               "מעקב אחרי דוחות Nvidia"),
                ("AMD",    "אובדן נתח שוק ב-AI",        "הכנסות משבבי AI מתחת ל-$4.5B",                                                           "בחינת תחרות מול Nvidia"),
                ("AMZN",   "האטה בצמיחת הענן",          "צמיחה ב-AWS מתחת ל-17%",                                                                 "הערכת רווחיות מגזר הענן"),
                ("GOOGL",  "האטה בצמיחת הענן",          "צמיחה ב-GCP מתחת ל-20%",                                                                 "מעקב אחרי מנועי צמיחה ב-AI"),
                ("CRWD",   "האטה באימוץ הפלטפורמה",     "ירידה משמעותית ב-Net New ARR",                                                            "בדיקת אירועי פריצה/תקלות"),
                ("ESLT",   "ביטול חוזים מהותי",         "הודעה על ביטול חוזה מעל $100M",                                                          "מעקב תקציבי ביטחון"),
                ("RHM",    "קיצוץ תקציבי נאט״ו",        "ירידה בתקציב הביטחון הגרמני",                                                            "בחינת מומנטום גיאופוליטי"),
                ("TEVA",   "ירידה במחיר / רגולציה",     "מתחת ל-$14",                                                                             "בדיקת אישורי FDA חדשים"),
                ("EQX",    "קריסה במחיר הזהב",          "זהב מתחת ל-$4,000/oz",                                                                   "בחינת עלויות הפקה (AISC)"),
                ("🗂 תיק", "שינוי דירוג אנליסטים",      "2+ בנקים מובילים מורידים ל-Sell/Underperform",                                           "בחינת יציאה מהפוזיציה"),
                ("🗂 תיק", "שינוי במבנה התיק",          "VOO יורד מתחת ל-40% מהתיק",                                                              "איזון מחדש (Rebalancing)"),
                ("🗂 תיק", "סטייה מהתזה של נאש",        "חברה מפסיקה להיות 'צוואר בקבוק'",                                                        "בחינת החלפה באלטרנטיבה"),
            ]

            # ── Evaluate each flag against live data ──────────────────────
            _pr   = data["prices"]
            _upg  = data["upgrades"]
            _con  = data["consensus"]
            _comm = data.get("commodities", {})
            _SELL_GRADES = {"sell", "underperform", "underweight", "reduce"}
            _MAJOR_F = {"jpmorgan", "jp morgan", "goldman", "morgan stanley",
                        "bank of america", "bofa", "citi", "ubs", "rbc", "barclays"}

            def _drop_from_high(ticker):
                """Return (drop_pct, detail_str) using 6-month price history."""
                p = _pr.get(ticker)
                if p and p.get("history") is not None and len(p["history"]) > 0:
                    ath = float(p["history"].max())
                    drop = (ath - p["price"]) / ath * 100 if ath else 0
                    return drop, f"ירד {drop:.1f}% מהשיא"
                return None, ""

            def _downgrade_count(ticker):
                """Count recent Sell/Downgrade analyst actions for a ticker."""
                df = _upg.get(ticker)
                hits = []
                if df is not None and not df.empty:
                    for _, row in df.head(15).iterrows():
                        action = str(row.get("action", "")).lower()
                        grade  = str(row.get("to_grade", "")).lower()
                        firm   = str(row.get("firm", ""))
                        if "down" in action or any(s in grade for s in _SELL_GRADES):
                            hits.append(f'{firm}: {row.get("to_grade","")}')
                return hits

            def _consensus_status(ticker):
                """Return (label, sell_fraction, total)."""
                c = _con.get(ticker, {})
                total = c.get("total", 0)
                sells = c.get("sell", 0) + c.get("strong_sell", 0)
                return c.get("label", "N/A"), (sells / total if total else 0), total

            def _analyst_proxy(ticker):
                """Generic proxy: downgrades + consensus for earnings-metric flags."""
                hits   = _downgrade_count(ticker)
                label, sell_f, total = _consensus_status(ticker)
                drop, drop_str = _drop_from_high(ticker)
                detail = f"קונצנזוס: {label}"
                if hits:
                    detail += f" | {len(hits)} שינמוכים: {hits[0]}"
                if drop is not None:
                    detail += f" | {drop_str}"
                if label == "Sell" or sell_f > 0.3 or len(hits) >= 3:
                    return "triggered", detail
                if label == "Hold" or sell_f > 0.15 or len(hits) >= 1 or (drop is not None and drop >= 15):
                    return "watch", detail
                if total > 0 or drop is not None:
                    return "ok", detail
                return "manual", ""

            def _flag_status(ticker, flag):
                """Returns (status, detail). status: triggered|watch|ok|manual"""

                # ── Price-exact checks ────────────────────────────────────
                if ticker == "VOO":
                    p = _pr.get("VOO")
                    if p and p.get("history") is not None and len(p["history"]) > 0:
                        ath = float(p["history"].max())
                        drop = (ath - p["price"]) / ath * 100 if ath else 0
                        detail = f"ירד {drop:.1f}% מהשיא (${ath:.0f})"
                        if drop >= 10:
                            return "triggered", detail
                        if drop >= 7:
                            return "watch", detail
                        return "ok", detail

                elif ticker == "CCJ":
                    uranium = _comm.get("uranium")
                    if uranium:
                        detail = f"אורניום ${uranium:.0f}/lb"
                        if uranium < 80:
                            return "triggered", detail
                        if uranium < 85:
                            return "watch", detail
                        return "ok", detail
                    # fallback: CCJ price + analyst proxy
                    return _analyst_proxy("CCJ")

                elif ticker == "FCX":
                    copper = _comm.get("copper")
                    if copper:
                        detail = f"נחושת ${copper:.2f}/lb"
                        if copper < 4.2:
                            return "triggered", detail
                        if copper < 4.5:
                            return "watch", detail
                        return "ok", detail

                elif ticker == "TEVA":
                    p = _pr.get("TEVA")
                    if p:
                        detail = f"מחיר ${p['price']:.2f}"
                        if p["price"] < 14:
                            return "triggered", detail
                        if p["price"] < 15:
                            return "watch", detail
                        return "ok", detail

                elif ticker == "EQX":
                    gold = _comm.get("gold")
                    if gold:
                        detail = f"זהב ${gold:,.0f}/oz"
                        if gold < 4000:
                            return "triggered", detail
                        if gold < 4200:
                            return "watch", detail
                        return "ok", detail

                # ── Earnings-metric flags: analyst proxy ──────────────────
                elif ticker in ("ETN", "VRT", "AMD", "AMZN", "GOOGL", "CRWD"):
                    return _analyst_proxy(ticker)

                # ── News/qualitative: downgrades + price drop ─────────────
                elif ticker in ("ESLT", "RHM"):
                    hits = _downgrade_count(ticker)
                    label, _, _ = _consensus_status(ticker)
                    drop, drop_str = _drop_from_high(ticker)
                    detail = (f'{"; ".join(hits[:2])}' if hits
                              else f"קונצנזוס: {label}")
                    if drop is not None:
                        detail += f" | {drop_str}"
                    if len(hits) >= 2 or label == "Sell":
                        return "triggered", detail
                    if len(hits) >= 1 or (drop is not None and drop >= 15):
                        return "watch", detail
                    if label != "N/A" or drop is not None:
                        return "ok", detail

                # ── Portfolio-level checks ────────────────────────────────
                elif ticker == "🗂 תיק" and "דירוג" in flag:
                    hits = []
                    for t, df in _upg.items():
                        if df is None or df.empty:
                            continue
                        for _, row in df.iterrows():
                            firm  = str(row.get("firm", "")).lower()
                            grade = str(row.get("to_grade", "")).lower()
                            if any(mf in firm for mf in _MAJOR_F) and any(s in grade for s in _SELL_GRADES):
                                hits.append(f'{t}/{row["firm"]}')
                    n = len(hits)
                    detail = f'{n} הורדות: {", ".join(hits[:2])}' if hits else "אין הורדות ל-Sell מבנקים מובילים"
                    if n >= 2:
                        return "triggered", detail
                    if n == 1:
                        return "watch", detail
                    return "ok", detail

                elif ticker == "🗂 תיק" and "מבנה" in flag:
                    voo_val = total_val = 0.0
                    for layer_positions in portfolio["layers"].values():
                        for pos in layer_positions:
                            t, shares = pos["ticker"], pos.get("shares", 0)
                            p = _pr.get(t)
                            if p and shares > 0:
                                val = shares * p["price"]
                                total_val += val
                                if t == "VOO":
                                    voo_val += val
                    if total_val > 0:
                        pct = voo_val / total_val * 100
                        detail = f"VOO = {pct:.1f}% מהתיק"
                        if pct < 40:
                            return "triggered", detail
                        if pct < 45:
                            return "watch", detail
                        return "ok", detail

                elif ticker == "🗂 תיק" and "תזה" in flag:
                    problem = []
                    for t in all_tickers(portfolio):
                        if t == "VOO":
                            continue
                        label, sell_f, total = _consensus_status(t)
                        if total > 0 and (label == "Sell" or sell_f > 0.3):
                            problem.append(f"{t} ({label})")
                    detail = ", ".join(problem) if problem else "כל המניות עם קונצנזוס חיובי"
                    if len(problem) >= 2:
                        return "triggered", detail
                    if len(problem) == 1:
                        return "watch", detail
                    return "ok", detail

                return "manual", ""

            # ── Render table ──────────────────────────────────────────────
            _STATUS_CELL = {
                "triggered": ('<span style="color:#F44336;font-weight:700">🔴 מופעל</span>', "background:#2d0a0a"),
                "watch":     ('<span style="color:#FF9800;font-weight:700">🟡 מעקב</span>',  "background:#2a1800"),
                "ok":        ('<span style="color:#4CAF50">🟢 תקין</span>',                  ""),
                "manual":    ('<span style="color:#555">⚪ ידני</span>',                      ""),
            }

            rows_html = ""
            for i, (_tk, _fl, _thr, _act) in enumerate(_flags):
                _st, _det = _flag_status(_tk, _fl)
                _icon_html, _row_bg = _STATUS_CELL[_st]
                if not _row_bg:
                    _row_bg = "background:#1a1a2a" if i % 2 else ""
                _is_pf = _tk.startswith("🗂")
                _tk_style = f"{_TD};color:#FF9800;font-weight:700" if _is_pf else f"{_TD};font-weight:700;color:#00cf8d"
                _status_td = (f'{_icon_html}<br><span style="color:#888;font-size:10px">{_det}</span>'
                              if _det else _icon_html)
                rows_html += (
                    f'<tr style="{_row_bg}">'
                    f'<td style="{_TD}">{_status_td}</td>'
                    f'<td style="{_tk_style}">{_tk}</td>'
                    f'<td style="{_TD}">{_fl}</td>'
                    f'<td style="{_TD};color:#F44336">{_thr}</td>'
                    f'<td style="{_TD}">{_act}</td>'
                    f'</tr>'
                )

            st.markdown(
                f'<div dir="rtl" style="font-size:11px">'
                f'<table style="width:100%;border-collapse:collapse">'
                f'<thead><tr>'
                f'<th style="{_TH}">סטטוס</th>'
                f'<th style="{_TH}">Ticker</th>'
                f'<th style="{_TH}">דגל</th>'
                f'<th style="{_TH}">סף</th>'
                f'<th style="{_TH}">פעולה</th>'
                f'</tr></thead><tbody>{rows_html}</tbody></table></div>',
                unsafe_allow_html=True,
            )

        st.divider()
        with st.expander(f"⚖️ ניתוח סיכון ופעולות אנליסטים — {td_str}"):
            _pr  = data["prices"]
            _upg = data["upgrades"]
            _con = data["consensus"]
            _MAJOR = {
                "jpmorgan", "jp morgan", "goldman sachs", "goldman",
                "morgan stanley", "bank of america", "bofa", "merrill",
                "citi", "citigroup", "ubs", "rbc", "barclays",
                "wells fargo", "deutsche", "hsbc", "jefferies",
                "mizuho", "cowen", "td cowen", "oppenheimer",
                "bernstein", "piper sandler", "needham", "raymond james",
                "keybanc", "stifel", "wedbush",
            }
            # sort: tickers with live price by beta desc; no-price tickers at end
            def _beta_sort(t):
                p = _pr.get(t)
                return (0, -(p["beta"] if p else 0)) if p else (1, 0)

            _sorted_t = sorted(all_tickers(portfolio), key=_beta_sort)

            _bhtml = '<div dir="rtl" style="font-size:12px;line-height:1.7">'
            if not market_state.get("is_trading_day", True):
                _bhtml += (
                    f'<div style="color:#FF9800;font-size:11px;margin-bottom:8px">'
                    f'⚠️ שוק סגור — נתוני סגירה אחרונים ({td_str})</div>'
                )
            for _t in _sorted_t:
                _p  = _pr.get(_t)
                _c  = _con.get(_t, {})
                _cl = _c.get("label", "N/A")
                _ct = _c.get("total", 0)
                _cs = f'{_cl} ({_ct})' if _ct else _cl
                if _p:
                    _b  = _p["beta"]
                    _bc = "#F44336" if _b >= 1.3 else ("#FF9800" if _b >= 1.0 else "#4CAF50")
                    _bl = "גבוה" if _b >= 1.3 else ("בינוני" if _b >= 1.0 else "נמוך")
                    _header = (
                        f'<b>{_t}</b> — Beta <b style="color:{_bc}">{_b:.2f}</b>'
                        f' ({_bl}) &nbsp;|&nbsp; קונצנזוס: <b>{_cs}</b>'
                    )
                else:
                    _bc = "#555"
                    _header = f'<b>{_t}</b> — Beta N/A &nbsp;|&nbsp; קונצנזוס: <b>{_cs}</b>'
                _bhtml += (
                    f'<div style="margin:6px 0;padding:3px 0 3px 8px;'
                    f'border-right:3px solid {_bc}">{_header}'
                )
                _df = _upg.get(_t)
                if _df is not None and not _df.empty:
                    for _, _row in _df.head(3).iterrows():
                        _firm   = str(_row.get("firm", ""))
                        _action = str(_row.get("action", ""))
                        _grade  = str(_row.get("to_grade", ""))
                        _dt     = _row["date"]
                        _ds     = _dt.strftime("%d.%m.%y") if pd.notna(_dt) else ""
                        _fc     = "#00cf8d" if any(
                            _mf in _firm.lower() for _mf in _MAJOR
                        ) else "#999"
                        _bhtml += (
                            f'<br>&nbsp;&nbsp;→ <span style="color:{_fc}">{_firm}</span>:'
                            f' {_action} → <b>{_grade}</b>'
                            + (f' [{_ds}]' if _ds else "")
                        )
                _bhtml += '</div>'
            _bhtml += '</div>'
            st.markdown(_bhtml, unsafe_allow_html=True)

        with st.expander(f"💰 דיבידנדים ויעדי מחיר — {td_str}"):
            _pr  = data["prices"]
            _tgt = data["targets"]
            _con = data["consensus"]

            _dhtml = '<div dir="rtl" style="font-size:12px;line-height:1.8">'
            if not market_state.get("is_trading_day", True):
                _dhtml += (
                    f'<div style="color:#FF9800;font-size:11px;margin-bottom:8px">'
                    f'⚠️ שוק סגור — נתוני סגירה אחרונים ({td_str})</div>'
                )
            for _t in sorted(all_tickers(portfolio)):
                _p     = _pr.get(_t)
                _tg    = _tgt.get(_t)
                _c     = _con.get(_t, {})
                _cl    = _c.get("label", "N/A")
                _ct    = _c.get("total", 0)
                _name  = TICKER_NAMES.get(_t, _t)

                if _p:
                    _price  = _p["price"]
                    _dy     = _p.get("div_yield", 0.0)
                    _dy_str = (
                        f'דיב׳ <b style="color:#4CAF50">{_dy:.2f}%</b>'
                        if _dy and _dy > 0.05 else "ללא דיבידנד"
                    )
                else:
                    _price  = None
                    _dy_str = "מחיר N/A"

                _tg_str = ""
                if _tg and _tg.get("mean") and _price:
                    _mean  = _tg["mean"]
                    _up    = ((_mean - _price) / _price) * 100
                    _uc    = "#4CAF50" if _up >= 0 else "#F44336"
                    _cnt   = _tg.get("count", 0)
                    _cnt_s = f" ({_cnt})" if _cnt else ""
                    _tg_str = (
                        f' &nbsp;|&nbsp; יעד${_mean:.0f}{_cnt_s}'
                        f' <b style="color:{_uc}">({_up:+.1f}%)</b>'
                    )
                elif _tg and _tg.get("mean"):
                    _tg_str = f' &nbsp;|&nbsp; יעד${_tg["mean"]:.0f}'

                _cs_str = f' &nbsp;|&nbsp; {_cl}' + (f' ({_ct})' if _ct else '')
                _dhtml += (
                    f'<div style="margin:4px 0">'
                    f'<b>{_t}</b> &nbsp;|&nbsp; {_dy_str}{_tg_str}{_cs_str}'
                    f'<br><span style="color:#666;font-size:10px">{_name}</span>'
                    f'</div>'
                )
            _dhtml += '</div>'
            st.markdown(_dhtml, unsafe_allow_html=True)

        st.divider()
        st.caption(f"יום מסחר אחרון: {td_str}")
        st.caption(f"Finnhub: {'מחובר ✓' if FINNHUB_AVAILABLE else 'לא מותקן'}")
        st.caption(f"Finviz: {'מחובר ✓' if FINVIZ_AVAILABLE else 'לא מותקן'}")
        st.caption(f"לוח שנה: {'NYSE ✓' if CALENDAR_AVAILABLE else 'גיבוי (ימות שבוע)'}")

        he_status = HE_STATUS.get(market_state["status_label"], market_state["status_label"])
        is_closed = not market_state["is_trading_day"]
        if is_closed:
            st.caption(f"⚠️ השוק {he_status} — מציג נתונים אחרונים ידועים")
        if st.button("🔄 רענן נתונים", help="נקה מטמון וטען את כל הנתונים מחדש"):
            st.cache_data.clear()
            st.rerun()

        st.divider()
        with st.expander("💡 הסבר מדדי ה-KPI "):
            st.markdown(
                '<div dir="rtl" style="font-size:12px;line-height:1.8">'

                '<b>📈 Upside % (פלוס/מינוס):</b><br>'
                '<ul>'
                '<li><b>פלוס (+):</b> המניה נסחרת מתחת ליעד האנליסטים. זהו סימן חיובי — '
                'השוק חושב שיש למניה עוד לאן לעלות (למשל, לטבע יש אפסייד גבוה של 28.4%).</li>'
                '<li><b>מינוס (-):</b> המניה עקפה את יעד האנליסטים. זה עלול להעיד על '
                '"תמחור יתר" או שצורך האנליסטים לעדכן את התחזיות שלהם כלפי מעלה.</li>'
                '</ul>'

                '<b>📊 Alpha vs VOO (פלוס/מינוס):</b><br>'
                '<ul>'
                '<li><b>פלוס (+): אתה מנצח את השוק.</b> המניה עלתה יותר מה-S&P 500. '
                '(למשל אלביט ו-Vertiv הן ה"כוכבות" של התיק עם אלפא גבוהה מאוד.)</li>'
                '<li><b>מינוס (-):</b> המניה מפגרת אחרי המדד. במקרה של AMD וטבע, '
                'הן הניבו תשואה נמוכה יותר מה-VOO ברבעון האחרון. זה מצריך מעקב '
                'כדי לראות אם מדובר בתיקון זמני או בשינוי מגמה.</li>'
                '</ul>'

                '<b>🔵 Beta:</b><br>'
                '<ul>'
                '<li><b>מעל 1:</b> המניה תנודתית יותר מהשוק. בימי עלייה — עולה יותר. '
                'בימי ירידה — יורדת יותר. (AMD, VRT: Beta ~1.6-1.8)</li>'
                '<li><b>מתחת ל-1:</b> מניה יציבה יחסית. (VOO, TEVA: Beta ~0.5-0.7)</li>'
                '</ul>'

                '<b>🟢 סטטוס (נקודה צבעונית בטבלת הסקירה):</b><br>'
                '<ul>'
                '<li><b>ירוק:</b> Upside חיובי — המניה מתחת ליעד האנליסטים.</li>'
                '<li><b>כתום:</b> Upside שלילי קל (0% עד -10%) — המניה עקפה מעט את היעד.</li>'
                '<li><b>אדום:</b> Upside שלילי משמעותי (מתחת ל-10%-) — תמחור יתר ברור.</li>'
                '</ul>'

                '</div>',
                unsafe_allow_html=True,
            )


if __name__ == "__main__":
    main()
