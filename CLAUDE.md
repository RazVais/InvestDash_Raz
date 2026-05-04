# Raz Investment Dashboard — Claude Instructions

## Project Overview
Personal investment dashboard for Raz's portfolio. Built with Streamlit + Python.

- **Run**: `streamlit run dashboard.py` (from `RazDashboard/` directory, venv active)
- **Stack**: Streamlit, yfinance, Plotly, finnhub-python, finvizfinance, exchange-calendars, pymaya
- **Secrets**: `.streamlit/secrets.toml` — `FINNHUB_API_KEY`, `CLAUDE_API_KEY`, `GIST_ID`, `GITHUB_TOKEN`

---

## Working Rules for Claude

1. **Python 3.9 syntax only** — no `float | None`, no `list[str]`; use `typing.Optional` and `List[str]`
2. **Read a file before editing it** — never edit blind
3. **Update CLAUDE.md on every change** — add a Changelog row and Known Pitfalls entry if a new bug/pattern was found
4. **`src/yf_patch.py` must be the first import** in any entry point — never move it
5. **All Hebrew strings in `src/config.py`** — never hardcode Hebrew elsewhere
6. **All red flag logic in `src/tabs/red_flags.py`** — never evaluate flag status in other files
7. **Per-ticker try/except in every fetcher** — one bad ticker must not crash the rest
8. **Never use `yf.download()` for macro/commodity tickers** — use per-symbol `Ticker().history()` in ThreadPoolExecutor
9. **Always guard TASE numeric tickers** — call `is_tase_numeric(t)` from `src/config.py` before passing to Finviz, yfinance analyst fetchers, or any US-market API
10. **After significant changes**, verify by running `streamlit run dashboard.py` — type errors surface immediately on startup

---

## Architecture & Design Decisions

| Decision | Reason |
|---|---|
| `src/yf_patch.py` FIRST import | Patches yfinance SQLite caches before any import triggers them |
| One fetch per trading day | Analyst data doesn't change intra-day; `trading_day` string is the cache key |
| No fetch when market closed | Weekend/holiday = Refresh button disabled; existing `@st.cache_data` served |
| `portfolio.json` + GitHub Gist | Local file for dev; Gist (`GIST_ID` + `GITHUB_TOKEN` in secrets) for Streamlit Cloud — falls back to file |
| plotly `>=5.18,<6` pinned | plotly 6.x causes segfault on Windows Streamlit |
| numpy `<2` pinned | numpy 2.x breaks pyarrow/numexpr ABI |
| Python 3.9 syntax only | Anaconda ships 3.9 — avoid 3.10+ type-hint syntax |
| finvizfinance 0.3s sleep | Finviz silently 429s if hammered |
| Claude Haiku for AI briefs | `@st.cache_data(ttl=3600)` per ticker; graceful degradation if no `CLAUDE_API_KEY` |
| Sidebar primary nav + secondary tab bar | Bloomberg/TradingView layout: 5 main tabs in sidebar, secondary tabs above content |

---

## File Structure

```
RazDashboard/
├── dashboard.py                   ← entry point: page config, KPI header, sidebar nav, tab routing
├── src/
│   ├── yf_patch.py                ← Windows SQLite fix — MUST be first import
│   ├── config.py                  ← all constants, Hebrew strings, thresholds, is_tase_numeric()
│   ├── market.py                  ← get_market_state(), market_badge()
│   ├── portfolio.py               ← load/save/add/remove lots; GitHub Gist backend
│   ├── ui_helpers.py              ← shared UI primitives
│   ├── data/
│   │   ├── prices.py              ← get_stock_data(); _process_tase_ticker() for TASE via pymaya
│   │   ├── analysts.py            ← targets, upgrades, consensus, EPS trend
│   │   ├── fundamentals.py        ← Finviz fundamentals (21 fields)
│   │   ├── technicals.py          ← RSI, SMA, EMA, Bollinger, correlation — pure pandas
│   │   ├── macro.py               ← VIX, 10Y yield, DXY + 7-day history; get_ils_usd_rate()
│   │   ├── news.py                ← get_news() — 5 articles per ticker
│   │   ├── damodaran.py           ← NYU sector P/E, EV/EBITDA, beta — 7d cache
│   │   ├── tase.py                ← pymaya wrapper: fetch_tase_current + fetch_tase_history; ETF vs mutual fund
│   │   └── loader.py              ← load_all_data() two-tier parallel orchestrator
│   └── tabs/
│       ├── overview.py            ← סקירה: macro strip, performance table, donut, correlation, stress test
│       ├── portfolio_tab.py       ← תיק שלי: P&L table, add/edit/remove forms, watch-only mode
│       ├── trading_journal_tab.py ← יומן עסקאות: retroactive P&L analysis + optional CSV
│       ├── charts.py              ← גרפים: candlestick, ORB, Monte Carlo, Trailing Stop backtester
│       ├── analysts_tab.py        ← אנליסטים: session AI | buy timing score | consensus
│       ├── fundamentals_tab.py    ← פונדמנטלס: valuation, earnings, dividends
│       ├── red_flags.py           ← דגלים אדומים: ALL flag logic lives here only
│       ├── news_tab.py            ← חדשות
│       ├── daily_brief_tab.py     ← 📋 יומי: Claude Haiku per-ticker brief
│       └── analysis_tab.py        ← 🔬 ניתוח: 5-filter Claude Haiku evaluation
```

---

## Portfolio Structure

| Layer | Tickers |
|---|---|
| Core (50%) | VOO, XAR, 1146356 (KSM TA-125 ETF) |
| Physical Infrastructure | CCJ, FCX, ETN, VRT, EQX |
| Compute & Platform | AMD, AMZN, GOOGL |
| Security & Stability | CRWD, ESLT |
| Healthcare & Pharma | TEVA |

- **XAR**: in Core (50%) for portfolio weight; still used as sector benchmark for CRWD/ESLT alpha; in `PORTFOLIO_ETFS` so fundamentals tabs skip it
- **ESLT**: Israeli TASE stock — empty consensus, no upgrades, may fail Finviz. Expected, not a bug
- **1146356**: KSM TA-125 ETF on TASE — numeric ID, routed via `tase.py`, prices in NIS
- **5124516**: KSM mutual fund (NAV-priced) — `SellPrice`/`PurchasePrice` fields, not `CloseRate`

---

## Caching Strategy

| Fetcher | TTL | Notes |
|---|---|---|
| `get_stock_data` | 1800s | key=(tickers_tuple, trading_day) |
| `get_macro_indicators` | 1800s | VIX, 10Y, DXY + 7-day sparkline history |
| `get_news` | 1800s | 5 articles per ticker |
| `get_analyst_targets` / `get_upgrades_downgrades` / `get_consensus` | 7d | Low churn |
| `get_finviz_fundamentals` / `get_eps_trend` / `get_commodity_prices` / `get_damodaran_sector_data` | 7d | |
| `get_buy_price` | 30d | Historical cost basis |
| `get_intraday_data` | 300s | ORB chart; converted to America/New_York tz |
| `get_ils_usd_rate` | 7d | USDILS=X; fallback 0.3397 |
| `_generate_ticker_brief` / `_run_five_filter_eval` / `_run_buy_timing_eval` / `_run_session_analysis` | 1h | Claude Haiku calls |

---

## Red Flag Logic

All flags are **100% automated** — NO "ידני" (manual) status ever. Source of truth: `src/tabs/red_flags.py`.

**Four flag categories** (read `red_flags.py` for current per-ticker thresholds):
- **Commodity price** — checks spot price of a linked commodity futures (uranium, copper, gold) against warn/trigger thresholds
- **Analyst proxy** — checks consensus label, sell fraction, recent downgrade count, and price drop vs highs
- **Portfolio structure** — VOO allocation % of total portfolio value
- **Thesis** — consensus Sell or high sell fraction on any non-VOO ticker

**Status rendering**: 🔴 מופעל / 🟡 מעקב / 🟢 תקין / ⚫ אין נתונים — never ⚪ or any manual label.

When adding a new ticker: check `red_flags.py` to decide which category it belongs to and add it there.

---

## Known Pitfalls (don't repeat these)

| Area | Pitfall |
|---|---|
| Environment | Never run from Anaconda base env — pyarrow/numpy ABI conflict causes segfault; always use venv |
| plotly | Don't upgrade past 5.x — 6.x segfaults on Windows Streamlit |
| numpy | Don't upgrade to 2.x — breaks pyarrow/numexpr ABI |
| yfinance | Don't upgrade past 0.2.54 without testing `src/yf_patch.py` cache patch |
| yf.download() | Multi-ticker batch returns MultiIndex that silently fails — use per-symbol fetch for macro/commodity |
| TASE tickers | Always call `is_tase_numeric(t)` before Finviz, analyst fetchers, or any US-market API |
| YFRateLimitError | Transient — demote to WARNING, not ERROR; import from `yfinance.exceptions` |
| plotly datetime axis | `add_vline(x=datetime)` triggers `_mean(str)` crash — use `add_shape` + `add_annotation` instead |
| Streamlit HTML blocks | Blank line between f-string continuation literals breaks HTML parser — extract variables instead |
| Python 3.9 | No `float \| None`, no `list[str]` — use `typing.Optional`, `List[str]` |
| TASE mutual fund | `SellPrice`/`PurchasePrice` for NAV (not `CloseRate`); dates in ISO format (not DD/MM/YYYY) |
| logging `name` field | `extra={"name": ...}` crashes Python logging — "name" is a reserved LogRecord field; use `"sec_name"` |
| Claude JSON output | Strip ```json fences before parsing; English-only prompts avoid Hebrew quote escaping issues |

---

## Changelog (recent — full history in `CLAUDE_old.md`)

| Version | Date | Change |
|---|---|---|
| v3.6 | 2026-05-01 | TASE live data via pymaya; mutual fund support; YFRateLimitError → WARNING; ILS→USD rate; TICKER_NAMES display names on Plotly axes |
| v3.7 | 2026-05-02 | Watch-only mode (👁 toggle, 📍 מעקב section, overview indicator); MC max profit KPI card; Trailing Stop moved to charts tab; Portfolio Stress Test committed; 1146356 added to Core (50%); GitHub Gist backend; MC crash fixes |
| v3.8 | 2026-05-02 | Charts: RS benchmark selector (SOXX/XLK/XAR/QQQ/GLD/XME; auto-defaults per ticker via `TICKER_BENCHMARK_DEFAULT`); dual-line RS view (sector bench + VOO context); MACD panel (12/26/9) with histogram; `compute_macd` added to `technicals.py` |
| v3.9 | 2026-05-03 | UI restructure: default tab → "תיק שלי"; visual charts (donut/heatmap/corr/stress) moved to new "🗺 תרשימי תיק" sub-tab in portfolio; "פונדמנטלס" merged into "סקירה"; charts tab: dropdown → left ticker button banner; per-ticker analyst panel (session AI / buy timing / consensus) below each chart |
