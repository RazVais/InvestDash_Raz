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
| yfinance per-symbol fetch in macro | `yf.download()` multi-ticker batch returns MultiIndex that silently fails; macro/commodity use per-symbol `Ticker().history()` in ThreadPoolExecutor instead |
| plotly < 6 pinned | plotly 6.x causes segfault on Windows Streamlit; pinned `>=5.18,<6` |
| numpy < 2 pinned | numpy 2.x breaks pyarrow/numexpr ABI; pinned `<2` |
| Python 3.9 syntax only | Anaconda ships 3.9 — no `float \| None`, no `list[str]`, use `typing.Optional` |
| All flag logic in red_flags.py | Never evaluate flag status outside `src/tabs/red_flags.py` |
| All Hebrew strings in config.py | Centralise so translation is a single-file edit |
| Sidebar primary nav + secondary tab bar | Bloomberg/TradingView layout: 5 main tabs in sidebar, 4 secondary tabs (News/Recs/Daily/Analysis) above content; red flags via KPI header bell |
| `address = "localhost"` in config.toml | Required for `crypto.randomUUID` secure context in Streamlit 1.43+ when running locally |
| Claude Haiku for AI briefs | `@st.cache_data(ttl=3600)` per ticker; graceful degradation if no `CLAUDE_API_KEY` in secrets |

## File Structure

```
RazDashboard/
├── dashboard.py                 ← entry point: page config, KPI header, sidebar nav, tab routing
├── ver_1/
│   └── dashboard.py             ← archived v1
├── src/
│   ├── __init__.py
│   ├── yf_patch.py              ← Windows SQLite fix — MUST be first import
│   ├── config.py                ← all constants, Hebrew strings, thresholds
│   ├── market.py                ← get_market_state(), market_badge()
│   ├── portfolio.py             ← load/save/add/remove/update lots
│   ├── ui_helpers.py            ← shared UI primitives (section_title, etc.)
│   ├── data/
│   │   ├── __init__.py
│   │   ├── prices.py            ← get_stock_data() — 1yr OHLCV + beta + div_yield; get_intraday_data() TTL=300s; get_current_price_or_daily_avg()
│   │   ├── analysts.py          ← targets, upgrades, consensus, EPS trend
│   │   ├── fundamentals.py      ← finviz fundamentals (21 fields)
│   │   ├── technicals.py        ← RSI, SMA, EMA, Bollinger, correlation — pure pandas
│   │   ├── macro.py             ← VIX, 10Y yield, DXY + 7-day history; commodities
│   │   ├── news.py              ← get_news() — 5 articles per ticker
│   │   ├── damodaran.py         ← Damodaran NYU sector benchmarks (P/E, EV/EBITDA, beta) — 7d cache
│   │   └── loader.py            ← load_all_data() two-tier parallel orchestrator
│   └── tabs/
│       ├── __init__.py
│       ├── overview.py          ← סקירה: macro strip, performance table, donut, correlation
│       ├── portfolio_tab.py     ← תיק שלי: multi-lot P&L table, add/edit/remove forms; 📈 יומן עסקאות sub-tab
│       ├── trading_journal_tab.py ← יומן עסקאות: retroactive P&L analysis from lots + optional CSV upload
│       ├── charts.py            ← גרפים: 1yr candlestick + RSI/MAs/Bollinger + ORB intraday chart
│       ├── analysts_tab.py      ← אנליסטים: ניתוח יומי (session AI) | ⏰ תזמון קנייה (score + trailing stop) | קונצנזוס
│       ├── fundamentals_tab.py  ← פונדמנטלס: valuation, earnings dates, dividends
│       ├── red_flags.py         ← דגלים אדומים: all flags automated, NO "ידני"
│       ├── news_tab.py          ← חדשות: latest articles per ticker
│       ├── daily_brief_tab.py   ← 📋 יומי: per-ticker brief + optional Claude Haiku narrative
│       └── analysis_tab.py      ← 🔬 ניתוח: 5-filter AI evaluation of non-portfolio tickers
├── portfolio.json               ← gitignored, auto-created
├── requirements.txt
├── CLAUDE.md                    ← this file
├── README.md
├── .gitignore
└── .streamlit/
    ├── config.toml              ← dark theme, primaryColor #00cf8d, address=localhost
    └── secrets.toml             ← gitignored, FINNHUB_API_KEY + CLAUDE_API_KEY
```

## Portfolio Structure (update when user adds/removes stocks)

| Layer | Tickers |
|---|---|
| Core (50%) | VOO, XAR |
| Physical Infrastructure | CCJ, FCX, ETN, VRT, EQX |
| Compute & Platform | AMD, AMZN, GOOGL |
| Security & Stability | CRWD, ESLT |
| Healthcare & Pharma | TEVA |

**XAR note**: SPDR S&P Aerospace & Defense ETF — now tracked under Core (50%) alongside VOO. Still used as the sector benchmark for Security & Stability in `SECTOR_ETFS`, so alpha for CRWD and ESLT continues to be measured vs XAR. It is in `PORTFOLIO_ETFS` so fundamentals/EPS tabs skip it.

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
| `get_macro_indicators` | 1800s | VIX, 10Y, DXY + 7-day history lists for sparklines |
| `get_news` | 1800s | 5 articles per ticker |
| `get_analyst_targets` | 7d | Low churn |
| `get_upgrades_downgrades` | 7d | 180-day lookback |
| `get_consensus` | 7d | Finnhub first, yfinance fallback |
| `get_finviz_fundamentals` | 7d | 0.3s sleep between tickers |
| `get_eps_trend` | 7d | Lazy, on-demand |
| `get_commodity_prices` | 7d | GC=F, HG=F, UX1=F |
| `get_buy_price` | 30d | Historical cost basis |
| `get_intraday_data` | 300s (5min) | Intraday OHLCV for ORB chart; converts to America/New_York tz |
| `_generate_ticker_brief` | 3600s (1h) | Claude Haiku per-ticker Hebrew narrative (daily_brief_tab) |
| `_run_five_filter_eval` | 3600s (1h) | Claude Haiku 5-filter JSON evaluation (analysis_tab) |
| `_run_buy_timing_eval` | 3600s (1h) | Claude Haiku buy timing verdict per ticker (analysts_tab) |
| `_run_session_analysis` | 3600s (1h) | Claude Haiku all-tickers morning session briefing (analysts_tab) |
| `get_damodaran_sector_data` | 7d | Damodaran NYU sector P/E, EV/EBITDA, beta benchmarks |

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
| 2026-04-03 | macro.py / empty macro data | `yf.download([symbols], ...)` for macro/commodity tickers returns MultiIndex columns that the parse logic silently fails on → VIX/10Y/DXY show "—" in sidebar | Fixed: rewrote `_fetch_one_macro` and `_fetch_one_commodity` to use per-symbol `yf.Ticker(sym).history()` in ThreadPoolExecutor |
| 2026-04-03 | browser / crypto.randomUUID | Streamlit 1.43+ uses `crypto.randomUUID()` which requires a secure context (HTTPS or localhost); accessing via IP → `crypto.randomUUID is not a function` | Fixed: added `address = "localhost"` to `.streamlit/config.toml` |
| 2026-04-03 | analysis_tab / anthropic missing | `anthropic` package listed in requirements.txt but not installed in venv → `No module named 'anthropic'` at runtime | Fixed: `pip install anthropic` in the venv |
| 2026-04-03 | analysis_tab / 5-filter silent errors | `except Exception: pass` swallowed all evaluation errors → empty stars with no feedback | Fixed: return `{"_error": str(exc)}` and display warning banner with retry button |
| 2026-04-03 | analysis_tab / JSON parse error | Claude Haiku embedded Hebrew quotation marks (`"`) inside JSON string values → `Expecting ',' delimiter` | Fixed: English-only prompt + `_safe_parse_json()` that strips trailing commas before retry |
| 2026-04-12 | analysts_tab / buy timing JSON | Claude Haiku returned ```json fences; `_safe_parse_json` regex `[a-z]*\n?` misses uppercase + Windows `\r\n` → parse fails | Fixed: `_strip_fences()` pre-processor with case-insensitive regex runs before `_safe_parse_json`; prompt updated with explicit "no code fences" instruction |
| 2026-04-12 | analysts.py / EPS trend | `yf.Ticker.eps_trend` removed in yfinance 0.2.54 → always returns None | Fixed: try `earnings_estimate` (new name) first, then `eps_trend` as fallback via `getattr()` |
| 2026-04-16 | analysts_tab / session analysis max_tokens | `_run_session_analysis` used `max_tokens=1200` for 13 tickers; response truncated mid-JSON → parse failure | Fixed: raised to `max_tokens=2500`; added `stop_reason=="max_tokens"` detection for clear error message |
| 2026-04-16 | trading_journal_tab / _compute_by_setup | First line of function filtered df by `setup_type` before the guard `if "setup_type" not in df.columns` → crash when column absent | Fixed: moved guard to top of function |

**Rule for Claude**: Every time a bug is caught or a feature is added, update the table above AND the Changelog below before finishing the task.

## Changelog

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-03-28 | Initial release — 5-tab dashboard with live analyst data, portfolio tracking, market-aware caching |
| v1.1 | 2026-03-29 | Full Hebrew RTL UI — all labels, tabs, buttons translated; CSS direction:rtl injected globally |
| v1.2 | 2026-03-29 | Dynamic sidebar expanders — live betas, dividend yields, analyst actions from major firms |
| v2.0 | 2026-03-29 | Full rewrite — multi-file package, 7 tabs, multi-lot portfolio model, 1yr candlestick charts, RSI/MAs/Bollinger, macro strip (VIX/10Y/DXY), correlation matrix, all flags automated (no ידני) |
| v2.1 | 2026-04-02 | Two-tier parallel data loading with background cache warming; email digest with alerts |
| v2.2 | 2026-04-02 | 📋 יומי daily brief tab; 🔬 ניתוח 5-filter analysis tab (both with Claude Haiku AI, TTL-cached) |
| v3.0 | 2026-04-03 | Bloomberg-style UI: sidebar primary nav (5 tabs), KPI header (value/P&L/alpha/bell), secondary tab bar (חדשות/המלצות/יומי/ניתוח), macro sparklines (7-day SVG); fixed macro data fetch + crypto.randomUUID |
| v3.1 | 2026-04-03 | Code quality: extracted 26+ large functions (>60 lines) into focused helpers across dashboard.py, charts.py, daily_brief_tab.py, analysis_tab.py; added SECURITY.md, .env.example, secrets.toml.example; fixed 5-filter silent errors + JSON parse errors |
| v3.2 | 2026-04-09 | XAR (SPDR Aerospace & Defense ETF) added as Security & Stability sector benchmark; per-layer alpha (XAR for defense, SPY for others); Finviz-style portfolio heatmap in overview + analysts tabs; conviction scatter matrix; 📋 יומי merged into אנליסטים as sub-tab |
| v3.3 | 2026-04-12 | ⏰ תזמון קנייה tab: AI buy timing scoring (RSI+SMA+Bollinger+upside+VIX+Damodaran P/E) 0-100 score; Damodaran NYU sector benchmark fetcher (P/E, EV/EBITDA, beta); Claude Haiku verdict card with Buffett/Lynch + Damodaran + Breitstein frameworks; fixed JSON fence parsing + EPS trend fallback |
| v3.4 | 2026-04-17 | ORB intraday chart (Python/Plotly, yfinance 5-min data, 5-condition signal, VWAP, episode state machine); buy price field in add/edit lot forms with auto-fill; Today's Session AI briefing (all-tickers Claude Haiku, priority table); 📈 יומן עסקאות sub-tab (retroactive P&L from portfolio lots + optional broker CSV, 6 analysis sections + pattern detection); 📏 Trailing Stop backtester in buy timing tab (n-bar trailing, MA cross entry, color-coded stop line); fixed session analysis max_tokens truncation |
