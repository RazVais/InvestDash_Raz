# Raz Investment Dashboard — Claude Instructions

## Project Overview
Personal investment dashboard for Raz's portfolio. Built with Streamlit + Python.

- **Run**: `streamlit run dashboard.py` (always from the `RazDashboard/` directory)
- **Stack**: Streamlit, yfinance, Plotly, finnhub-python, finvizfinance, exchange-calendars
- **Data file**: `portfolio.json` (auto-created on first run, gitignored)
- **Secrets**: `.streamlit/secrets.toml` — add `FINNHUB_API_KEY = "..."` (gitignored)

## Architecture & Design Decisions

| Decision | Reason |
|---|---|
| `src/yf_patch.py` FIRST import | Patches yfinance SQLite caches before any import triggers them; must never be moved |
| One fetch per trading day | Analyst data doesn't change intra-day; `trading_day` date string passed as cache key |
| No fetch when market closed | Weekend/holiday = Refresh button disabled; existing `@st.cache_data` served |
| `portfolio.json` for persistence | Single-user local app; JSON is human-readable and editable |
| Per-ticker try/except in all fetchers | One bad ticker (e.g. ESLT) must never block the rest |
| finvizfinance 0.3s sleep | Rate limiting — Finviz silently 429s if hammered |
| yfinance batch download | `yf.download(all_tickers, group_by="ticker")` — single auth, no per-ticker rate limit |
| plotly < 6 pinned | plotly 6.x causes segfault on Windows Streamlit; pinned `>=5.18,<6` |
| numpy < 2 pinned | numpy 2.x breaks pyarrow/numexpr ABI; pinned `<2` |
| Python 3.9 syntax only | Anaconda ships 3.9 — no `float \| None`, no `list[str]`, use `typing.Optional` |
| All flag logic in red_flags.py | Never evaluate flag status outside `src/tabs/red_flags.py` |
| All Hebrew strings in config.py | Centralise so translation is a single-file edit |

## File Structure

```
RazDashboard/
├── dashboard.py                 ← thin entry point (imports only)
├── ver_1/
│   └── dashboard.py             ← archived v1
├── src/
│   ├── __init__.py
│   ├── yf_patch.py              ← Windows SQLite fix — MUST be first import
│   ├── config.py                ← all constants, Hebrew strings, thresholds
│   ├── market.py                ← get_market_state(), market_badge()
│   ├── portfolio.py             ← load/save/add/remove/update lots
│   ├── data/
│   │   ├── __init__.py
│   │   ├── prices.py            ← get_stock_data() — 1yr OHLCV + beta + div_yield
│   │   ├── analysts.py          ← targets, upgrades, consensus, EPS trend
│   │   ├── fundamentals.py      ← finviz fundamentals (21 fields)
│   │   ├── technicals.py        ← RSI, SMA, EMA, Bollinger, correlation — pure pandas
│   │   ├── macro.py             ← VIX, 10Y yield, DXY, commodities
│   │   ├── news.py              ← get_news() — 5 articles per ticker
│   │   └── loader.py            ← load_all_data() orchestrator
│   └── tabs/
│       ├── __init__.py
│       ├── overview.py          ← סקירה: macro strip, performance table, donut, correlation
│       ├── portfolio_tab.py     ← תיק שלי: multi-lot P&L table, add/edit/remove forms
│       ├── charts.py            ← גרפים: 1yr candlestick + RSI/MAs/Bollinger
│       ├── analysts_tab.py      ← אנליסטים: consensus, price targets, upgrades
│       ├── fundamentals_tab.py  ← פונדמנטלס: valuation, earnings dates, dividends
│       ├── red_flags.py         ← דגלים אדומים: all flags automated, NO "ידני"
│       └── news_tab.py          ← חדשות: latest articles per ticker
├── portfolio.json               ← gitignored, auto-created
├── requirements.txt
├── CLAUDE.md                    ← this file
├── README.md
├── .gitignore
└── .streamlit/
    ├── config.toml              ← dark theme, primaryColor #00cf8d
    └── secrets.toml             ← gitignored, FINNHUB_API_KEY
```

## Portfolio Structure (update when user adds/removes stocks)

| Layer | Tickers |
|---|---|
| Core (50%) | VOO |
| Physical Infrastructure | CCJ, FCX, ETN, VRT |
| Compute & Platform | AMD, AMZN, GOOGL |
| Security & Stability | CRWD, ESLT, TEVA, EQX |

**ESLT note**: Israeli stock listed on TASE. Minimal US analyst coverage expected — empty consensus, no upgrades/downgrades, may fail Finviz. This is normal, not a bug.

## Portfolio Data Model — Multi-Lot

```json
{
  "layers": {
    "Compute & Platform": [
      {"ticker": "AMD", "shares": 5.0, "buy_date": "2025-01-15"},
      {"ticker": "AMD", "shares": 3.0, "buy_date": "2025-03-01"}
    ]
  }
}
```

## Caching Strategy

| Fetcher | TTL | Notes |
|---------|-----|-------|
| `get_stock_data` | 1800s (30min) | key=(tickers_tuple, trading_day) |
| `get_macro_indicators` | 1800s | VIX, 10Y, DXY |
| `get_news` | 1800s | 5 articles per ticker |
| `get_analyst_targets` | 7d | Low churn |
| `get_upgrades_downgrades` | 7d | 180-day lookback |
| `get_consensus` | 7d | Finnhub first, yfinance fallback |
| `get_finviz_fundamentals` | 7d | 0.3s sleep between tickers |
| `get_eps_trend` | 7d | Lazy, on-demand |
| `get_commodity_prices` | 7d | GC=F, HG=F, UX1=F |
| `get_buy_price` | 30d | Historical cost basis |

## Red Flag Logic (all automated, NO "ידני")

| Ticker / Flag | Check | Thresholds |
|---|---|---|
| VOO | 6-month price drop from high | warn 7%, trigger 10% |
| CCJ | Uranium futures UX1=F | warn $85, trigger $80 |
| FCX | Copper futures HG=F | warn $4.50, trigger $4.20 |
| ETN | Analyst proxy | see below |
| VRT | Analyst proxy | see below |
| AMD | Analyst proxy | see below |
| AMZN | Analyst proxy | see below |
| GOOGL | Analyst proxy | see below |
| CRWD | Analyst proxy | see below |
| ESLT | Price drop + downgrade count | drop 12%/20%, downgrades 1/3 |
| TEVA | Stock price | warn $15, trigger $14 |
| EQX | Gold futures GC=F | warn $4,200, trigger $4,000 |
| 🗂 דירוג | 2+ major banks Sell/Underperform | — |
| 🗂 מבנה | VOO % of total portfolio value | warn 45%, trigger 40% |
| 🗂 תזה | Any non-VOO ticker consensus Sell or sell_fraction > 30% | — |

**Analyst proxy**: triggered if label==Sell OR sell_frac>30% OR downgrades≥3 OR drop≥20%; watch if label==Hold OR sell_frac>15% OR downgrades≥1 OR drop≥12%

Status rendering: 🔴 מופעל / 🟡 מעקב / 🟢 תקין / ⚫ אין נתונים — NO ⚪ ידני ever.

## Known Issues & Failures

| Date | Component | Description | Status |
|---|---|---|---|
| 2026-03-29 | Environment / numpy | Anaconda ships numpy 1.21.5; pandas 2.3.3 requires >=1.22.4. Upgrading to numpy 2.0.2 breaks pyarrow/numexpr/bottleneck (compiled against 1.x). | Fixed: `pip install "numpy<2"` — pins to latest 1.x (1.26.x) |
| 2026-03-29 | dashboard.py / type hints | `float \| None` and `list[str]` are Python 3.10+ syntax; Anaconda runs 3.9 → TypeError on startup | Fixed: use `typing.Optional`, no union type hints |
| 2026-03-29 | Environment / pyarrow segfault | Anaconda pyarrow compiled for numpy 1.21.5; after pip-upgrading numpy → segfault on startup | Fixed: `pip install --upgrade pyarrow` |
| 2026-03-29 | secrets / StreamlitSecretNotFoundError | `st.secrets.get()` throws when no secrets file exists | Fixed: wrapped in try/except in `main()` |
| 2026-03-29 | Environment / segfault (root cause) | Anaconda base env ABI mismatch after numpy upgrade | Fixed: use fresh venv — never run from Anaconda base env |
| 2026-03-29 | plotly 6 / segfault | plotly 6.x causes segfault when Streamlit renders charts | Fixed: pinned `plotly>=5.18,<6` |
| 2026-03-29 | yfinance / cookie cache crash | peewee SQLite access violation in Streamlit worker thread | Fixed: in-memory `_MemTzCache` + `_MemCookieCache` in `src/yf_patch.py` |
| 2026-03-29 | yfinance / rate limiting | Per-ticker `stock.history()` triggers separate Yahoo auth → Too Many Requests | Fixed: single `yf.download(all_tickers, group_by="ticker")` batch call |

**Rule for Claude**: Every time a bug is caught or a feature is added, update the table above AND the Changelog below before finishing the task.

## Changelog

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-03-28 | Initial release — 5-tab dashboard with live analyst data, portfolio tracking, market-aware caching |
| v1.1 | 2026-03-29 | Full Hebrew RTL UI — all labels, tabs, buttons translated; CSS direction:rtl injected globally |
| v1.2 | 2026-03-29 | Dynamic sidebar expanders — live betas, dividend yields, analyst actions from major firms |
| v2.0 | 2026-03-29 | Full rewrite — multi-file package, 7 tabs, multi-lot portfolio model, 1yr candlestick charts, RSI/MAs/Bollinger, macro strip (VIX/10Y/DXY), correlation matrix, all flags automated (no ידני) |
