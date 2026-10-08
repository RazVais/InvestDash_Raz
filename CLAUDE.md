# Raz Investment Dashboard — Claude Instructions

## Project Overview
Personal investment dashboard for Raz's portfolio. Built with Streamlit + Python.

- **Run**: `streamlit run dashboard.py` (from `RazDashboard/` directory, venv active)
- **Stack**: Streamlit, yfinance, Plotly, finnhub-python, finvizfinance, exchange-calendars, pymaya
- **Secrets**: `.streamlit/secrets.toml` — `FINNHUB_API_KEY`, `ANTHROPIC_API_KEY`, `SMTP_*`, `GIST_ID`, `GITHUB_TOKEN`, `MODE`, `APP_PASSWORD` (see `SECURITY.md`)
- **Repo is PUBLIC** — personal data files are gitignored; never `git add -A` blindly

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
11. **All money totals via `compute_holdings()`** in `src/valuation.py` — never sum `shares * price` by hand (TASE is NIS)
12. **Escape outside text** — RSS/Yahoo/Claude strings go through `esc()` / `safe_url()` before `unsafe_allow_html`
13. **Claude model ID only in `config.CLAUDE_MODEL`**

---

## Architecture & Design Decisions

| Decision | Reason |
|---|---|
| `src/yf_patch.py` FIRST import | Patches yfinance SQLite caches before any import triggers them |
| Ticker tiers | Held ∪ starred (`active_tickers()`) get analyst/Finviz/earnings/news fetches + AI; other watch-only tickers are price-only, AI on click. Star in תיק שלי → 📍 מעקב |
| Per-ticker caches | Slow data is cached per ticker (`map_cached()` in `src/data/batch.py`), so adding a ticker fetches only that ticker; global cap of 8 concurrent requests |
| One AI result per ticker per day | AI caches keyed `(ticker, trading_day)`; live inputs passed as `_`-prefixed args (excluded from the key); warmup runs once per day per process |
| No fetch when market closed | Weekend/holiday = Refresh button disabled; existing `@st.cache_data` served |
| `portfolio.json` + GitHub Gist | Local file for dev; Gist (`GIST_ID` + `GITHUB_TOKEN` in secrets) for Streamlit Cloud; local file is also written as a fallback. A failed read blocks saves for the session (never overwrite real data with defaults) |
| plotly `>=5.18,<6` pinned | plotly 6.x causes segfault on Windows Streamlit |
| numpy `<2` pinned | numpy 2.x breaks pyarrow/numexpr ABI |
| Python 3.9 syntax only | Anaconda ships 3.9 — avoid 3.10+ type-hint syntax |
| finvizfinance 0.3s sleep | Finviz silently 429s if hammered |
| Claude Haiku for AI briefs | `@st.cache_data(ttl=3600)` per ticker; graceful degradation if no `ANTHROPIC_API_KEY` |
| Cloud mode | `MODE="cloud"` requires `APP_PASSWORD` (hmac password gate) and hides the exit button (`os._exit`) |
| Job-based nav (4 tabs) | היום (daily check-in) / תיק (what I own) / מניה (one ticker + ideas) / תרגול (setups + journals). Organised by job, not data source. Red flags opens from the 🔔 bell / היום. Tab names live in `HE["tab_*"]` |
| היום never blocks on AI | `wait_for_ai=False`: uncached AI sections show a "preparing" note while the background warmup fills them |

---

## File Structure

```
RazDashboard/
├── dashboard.py                   ← entry point: page config, KPI header, sidebar nav, tab routing
├── src/
│   ├── yf_patch.py                ← Windows SQLite fix — MUST be first import
│   ├── config.py                  ← all constants, Hebrew strings, thresholds, is_tase_numeric()
│   ├── market.py                  ← get_market_state(), market_badge()
│   ├── portfolio.py               ← load/save/add/remove lots; GitHub Gist backend; save-blocking on load failure
│   ├── valuation.py               ← compute_holdings(): lots × prices → USD (NIS converted) — ALL totals
│   ├── journal.py                 ← only reader/writer of trading_journal_ai.json
│   ├── history.py                 ← snapshots, time-weighted returns, rebalance_plan(), position_size() — pure logic
│   ├── ai.py                      ← Claude: ask(), parse_json(), key_lock(), mark_done()/is_done()
│   ├── email_report.py            ← digest + alert emails (verified TLS)
│   ├── logger.py                  ← structured logging (never use extra={"name": ...})
│   ├── ui_helpers.py              ← shared UI primitives; esc() / safe_url()
│   ├── data/
│   │   ├── prices.py              ← get_stock_data(); _process_tase_ticker() for TASE via pymaya
│   │   ├── analysts.py            ← targets, upgrades, consensus, EPS trend
│   │   ├── fundamentals.py        ← Finviz fundamentals (21 fields)
│   │   ├── technicals.py          ← RSI, SMA, EMA, Bollinger, correlation — pure pandas
│   │   ├── macro.py               ← VIX, 10Y yield, DXY + 7-day history; get_ils_usd_rate()
│   │   ├── news.py                ← get_news() — up to 6 articles per ticker; get_company_profile()
│   │   ├── damodaran.py           ← NYU sector P/E, EV/EBITDA, beta — 7d cache
│   │   ├── tase.py                ← pymaya wrapper: fetch_tase_current + fetch_tase_history; ETF vs mutual fund
│   │   ├── batch.py               ← map_cached(): per-ticker fan-out, 8-request cap, failure back-off
│   │   └── loader.py              ← load_all_data() two-tier parallel orchestrator; refresh_live()
│   └── tabs/
│       ├── today_tab.py           ← היום: macro strip, attention list (flags + earnings ≤7d), market pulse, session AI, briefs
│       ├── portfolio_tab.py       ← תיק: P&L | ניירות ערך | אנליסטים ותזמון | תרשימים | עצירות; ⭐ star tier
│       ├── ticker_tab.py          ← מניה: 🔍 analyse any ticker (session-only, ⭐ to keep) + charts(sections=CHART_SECTIONS) + 💡 ideas
│       ├── practice_tab.py        ← תרגול: charts(sections=PRACTICE_SECTIONS) + both journals
│       ├── planning_tab.py        ← UI for history.py: 📉 ביצועים, ⚖️ איזון, 📐 position sizer, daily snapshot writer
│       ├── overview.py            ← render_securities() (manage/perf table/fundamentals), donut, correlation, stress test
│       ├── trading_journal_tab.py ← יומן עסקאות: retroactive P&L analysis + optional CSV; ➕ manual historic trade form; edit/delete history trades
│       ├── charts.py              ← render_charts(sections=…): candlestick, MC, analyst panel | ORB, trailing stop
│       ├── analysts_tab.py        ← render_analyst_views() (buy timing + consensus), session AI, market pulse
│       ├── fundamentals_tab.py    ← valuation, earnings, dividends (inside תיק → ניירות ערך)
│       ├── red_flags.py           ← דגלים אדומים: ALL flag logic lives here only
│       ├── news_tab.py            ← per-ticker news helpers (used by the מניה analyst panel)
│       ├── daily_brief_tab.py     ← per-ticker Claude Haiku brief (embedded in analysts tab)
│       ├── suggestions_tab.py     ← 💡 המלצות: curated complementary picks
│       ├── analysis_tab.py        ← 🔬 ניתוח: 5-filter Claude Haiku evaluation
│       └── trading_journal_ai_tab.py ← יומן AI: chat trade logging (Claude)
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

**portfolio.json keys**: `layers`, `trade_history`, `alerts`, `settings` (`email_recipients`, `auto_alert`, `starred`, `layer_targets`), `snapshots` (one row per trading day — see `src/history.py`; never written pre-market, provisional while open, final after close)

---

## Caching Strategy

**Rule: cached functions raise on failure** — Streamlit never caches exceptions, so errors are retried instead of served for days. Wrappers catch and return a default.

| Fetcher | TTL | Key / notes |
|---|---|---|
| `get_stock_data` | 1800s | (tickers_tuple, trading_day) — all tickers |
| `get_macro_indicators` | 1800s | VIX, 10Y, DXY + 7-day sparkline history |
| `get_news` | 1800s | active tickers; up to 6 articles each |
| `_target_one` / `_upgrades_one` / `_consensus_one` / `_earnings_one` / `_finviz_one` | 7d | **per ticker**, no trading_day; via `map_cached()`; failures back off 15 min |
| `get_commodity_prices` | 7d | keyed by trading_day (spot prices move daily) |
| `_damodaran_cached` / `_ils_usd_cached` | 7d | failures NOT cached (fallback returned uncached) |
| `get_buy_price` | 30d | historical close; `.TA` × 0.01 (agorot→NIS) |
| `get_intraday_data` | 300s | ORB chart; America/New_York tz; None for TASE |
| `_brief_cached` / `_buy_timing_cached` / `_five_filter_cached` / `_session_cached` | 12h | **(ticker, trading_day)**; `_inputs`/`_api_key` excluded from key; `ai.key_lock()` dedupes concurrent misses |
| `_summarize_titles` | 12h | (ticker, headline tuple, day) — re-runs only when headlines change |
| `_run_mc` | 1h | seeded (deterministic fan chart) |

**Refresh button** → `refresh_live()` clears only prices / intraday / macro / news. Portfolio edits clear nothing (the ticker tuple in the key changes by itself). Never call `st.cache_data.clear()`.

---

## Red Flag Logic

All flags are **100% automated** — NO "ידני" (manual) status ever. Source of truth: `src/tabs/red_flags.py`.

**Five flag categories** (read `red_flags.py` for current per-ticker thresholds):
- **Commodity price** — checks spot price of a linked commodity futures (uranium, copper, gold) against warn/trigger thresholds
- **Analyst proxy** — checks consensus label, sell fraction, recent downgrade count, and price drop vs highs
- **Portfolio structure** — VOO allocation % of total portfolio value
- **Thesis** — consensus Sell or high sell fraction on any non-VOO ticker
- **User stops & price alerts** — `portfolio["alerts"]` (stop loss, trailing stop % from the peak since buy, price above/below); 🟡 within `FLAG_THRESHOLDS["_alerts"]` %. These flow into the bell, היום and the auto-alert email

`get_all_flag_statuses()` is the single list every consumer reads; `dashboard.main()` stores it in `data["_flags"]`.

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
| Claude JSON output | Strip ```json fences before parsing; English-only prompts avoid Hebrew quote escaping issues; use `json.JSONDecoder.raw_decode`, not a non-greedy regex (breaks on nested objects) |
| NIS + USD totals | TASE prices are NIS — summing `shares * price` across tickers mixes currencies (header, stress test, VOO flag and email were all wrong). Use `compute_holdings()` |
| Yahoo `.TA` prices | Quoted in agorot (ILA), pymaya in NIS — multiply `.TA` closes by 0.01 |
| Load-failure fallback | Returning defaults on a failed read, then saving, wipes real data. Mark the session load-failed and block saves |
| Two writers, one file | Tabs caching a file in session state will overwrite each other's writes — route through one module (`journal.py`) |
| yf_patch cookie cache | yfinance's cookie `lookup()` must return `{'cookie', 'age'}`; returning the bare cookie raised TypeError on every load and forced re-auth (more 429s) |
| `.info` in the price cache | yfinance `.info` inside the 30-min `get_stock_data` cache re-fetched beta/P/E for all 66 tickers every refresh (~1 min cold under throttling). It is now `get_info_snapshot()` — 7d, active tickers only, merged by the loader |
| Equity curve flows | Cost-basis diffs as cash flows book a fake gain/loss on every sell. Flow = Σ Δshares × today's price (snapshots store `shares` + `px`) |
| AppTest harness on Windows | `AppTest.from_function` writes the script in cp1252 — no Hebrew or em-dashes in the function source; import `src.yf_patch` first inside it or yfinance's SQLite cache segfaults |
| Pre-market snapshot | `last_trading_day` is today before the open but prices are yesterday's close — a final row then locks the wrong value. Skip pre-market |
| Module state in dashboard.py | Streamlit re-executes `dashboard.py` on every rerun — module-level flags/Events there reset each time. Keep cross-rerun state in an imported module (`src/ai.py`, `loader._bg_done`) |
| Concurrent cache misses | Background warmup + tab pre-warm + render all missed the same `@st.cache_data` key and each called Claude (3× calls). Wrap AI cache calls in `ai.key_lock(...)` |
| Hebrew max_tokens | Hebrew is token-heavy: 200 tokens truncated every brief. Prose uses `allow_truncated=True`; a cached fn that always raises is re-called every rerun |
| Caching failures | Returning `{}` / a fallback from a 7d-cached fn serves the failure for a week — raise inside the cached fn, catch in a wrapper |
| smtplib TLS | `starttls()` / `SMTP_SSL` without `ssl.create_default_context()` skip cert verification on Python 3.9 |

---

## Changelog (recent — full history in `CLAUDE_old.md`)

| Version | Date | Change |
|---|---|---|
| v3.6 | 2026-05-01 | TASE live data via pymaya; mutual fund support; YFRateLimitError → WARNING; ILS→USD rate; TICKER_NAMES display names on Plotly axes |
| v3.7 | 2026-05-02 | Watch-only mode (👁 toggle, 📍 מעקב section, overview indicator); MC max profit KPI card; Trailing Stop moved to charts tab; Portfolio Stress Test committed; 1146356 added to Core (50%); GitHub Gist backend; MC crash fixes |
| v3.8 | 2026-05-02 | Charts: RS benchmark selector (SOXX/XLK/XAR/QQQ/GLD/XME; auto-defaults per ticker via `TICKER_BENCHMARK_DEFAULT`); dual-line RS view (sector bench + VOO context); MACD panel (12/26/9) with histogram; `compute_macd` added to `technicals.py` |
| v3.9 | 2026-05-03 | UI restructure: default tab → "תיק שלי"; visual charts (donut/heatmap/corr/stress) moved to new "🗺 תרשימי תיק" sub-tab in portfolio; "פונדמנטלס" merged into "סקירה"; charts tab: dropdown → left ticker button banner; per-ticker analyst panel (session AI / buy timing / consensus) below each chart |
| v4.0 | 2026-10-06 | Phase 0 safety: portfolio/journal saves blocked after a failed read (+`.bak`); loader `extra={"name"}` crash fixed + warm flag re-armed in `finally`; `src/valuation.py` currency-aware totals (header, P&L summary, donut, stress test, VOO flag, email); `.TA` buy-price agorot fix; TASE guards on earnings/EPS/profile; SMTP verified TLS + timeout; `esc()`/`safe_url()` on news + AI output; `src/journal.py` single writer; `CLAUDE_MODEL` constant; `MODE`/`APP_PASSWORD` cloud gate; gitignore personal files; `yf_patch` cookie cache returns yfinance's `{cookie, age}` contract |
| v4.1 | 2026-10-06 | Phase 1 speed + AI cost: star tier (`active_tickers()`, ⭐ multiselect) — analyst/Finviz/earnings/news + AI only for held ∪ starred; `src/ai.py` (shared client, `parse_json`, `key_lock`, call counter) — AI cached per (ticker, day), failures uncached, warmup once/day incl. session, buy-timing/5-filter AI on click (measured: 124+ calls/refresh → 21 calls/day; analysts tab 128s → 2.7s warm, 🔬 75s → 2s); per-ticker 7d caches via `src/data/batch.py` (8-request global cap, 15-min failure back-off); `refresh_live()` replaces all `st.cache_data.clear()`; Damodaran parallel + failures uncached; ILS fallback uncached; buy price 30d + searchsorted; Monte Carlo seeded + cached; flags computed once (`data["_flags"]`); TASE guard on intraday; prose AI no longer truncated (brief 600 tokens) |
| v4.2 | 2026-10-06 | Phase 2 navigation: 8 screens → 4 job tabs (היום / תיק / מניה / תרגול); secondary tab bar removed; 💡+🔬 merged into מניה → רעיונות; `render_charts(sections=…)` shared by מניה and תרגול; היום never blocks on AI; `.info` split into 7d per-ticker `get_info_snapshot()` for active tickers (cold load 51s → 25s under Yahoo throttling); removed unused `render_overview` / `render_analysts` / `render_news` |
| v4.3 | 2026-10-06 | Phase 3 decision tools: daily snapshots in `portfolio["snapshots"]` (provisional/final, pre-market skipped) + 🔁 one-year reconstruction; 📉 ביצועים (time-weighted index vs VOO, drawdown, 1M/3M/YTD/alpha); היום shows change since the last snapshot; ⚖️ איזון (editable layer targets, drift, new-cash allocation, buys only); 📐 position sizer under the chart (risk %, stop → shares, NIS-aware, layer weight after); stops/trailing/price alerts are now evaluated as red flags (bell + email) |
| v4.4 | 2026-10-06 | Trading journal: ➕ manual historic trade form (fees, setup type → by-setup stats, note; validates dates/duplicates) moved here from תיק; 🗑 delete history trades; edit recomputes P&L net of fees; `add_closed_trade(fees, setup_type, note)`, `remove_closed_trade`, `find_closed_trade`, `closed_trade_pnl` in portfolio.py; `SETUP_TYPES` shared by both journals |
| v4.5 | 2026-10-08 | מניה: 🔍 "נתח מניה חדשה" box — any ticker gets the full page (chart, MC, buy timing, consensus, 5 filters, news, sizer) for the session via `fetch_adhoc_data`/`merge_data`; ⭐ adds it as a starred watch-only lot; `render_charts(extra_tickers=…)`; ideas-tab custom 5-filter box replaced by a pointer |
