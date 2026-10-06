# RazDashboard v4.3

Personal investment dashboard for the "Age of AI" portfolio. Tracks stocks across strategic layers with live data from Yahoo Finance, Finviz, and Finnhub. Built with Streamlit + Python, Hebrew RTL UI.

## Features

### Navigation (v4 — organised by what you're doing)
| Tab | For | Contents |
|---|---|---|
| **☀️ היום** | Daily check-in | Macro strip · change since yesterday (flow-adjusted) vs VOO · attention list (red flags, stops/alerts, earnings ≤ 7 days) · market pulse · AI session briefing · per-ticker AI briefs |
| **💼 תיק** | What you own | 📊 P&L + add/edit/remove lots · 📉 performance history vs VOO (time-weighted, drawdown) · ⚖️ rebalancing vs layer targets with new-cash allocation · 📋 securities + fundamentals · 👥 analysts & buy timing · 🗺 charts (donut, heatmap, correlation, stress test) · ⚠️ stops & alerts |
| **📈 מניה** | Buy/sell decisions on one ticker | Candlestick + indicators + relative strength · Monte Carlo · per-ticker AI (session, buy timing, consensus, 5 filters, news) · 📐 position-size calculator · 💡 ideas (suggestions + 5-filter screening) |
| **🎯 תרגול** | Trading practice | ORB intraday setup · trailing-stop backtester · trade journal analysis · AI trade journal |

The 🔔 bell in the header opens the full red-flags table.

### Watch list tiers
Held tickers and ⭐ starred watch names (תיק → 📍 מעקב) get analyst data, fundamentals, news and daily AI. Other watch-only tickers get prices only, and AI runs when you click 🤖.

### Red flags
All automated: commodity prices, analyst signals, portfolio structure, thesis checks — plus your own stop losses, trailing stops and price alerts. 🔴/🟡/🟢/⚫. Newly triggered flags can be emailed automatically.

### Infrastructure
- **Market-aware caching** — prices refresh every 30 min; analyst/fundamental data is cached per ticker for 7 days; AI results once per ticker per trading day. Refresh clears only live data. Failed fetches are retried, never cached
- **Two-tier parallel loading** — active tab data loaded immediately in ThreadPoolExecutor; remaining keys pre-warmed in background daemon thread
- **Macro sparklines** — 7-day SVG sparklines for VIX, 10Y yield, DXY in sidebar (green/red trend coloring)
- **Damodaran sector benchmarks** — annual P/E, EV/EBITDA, and beta data fetched from Prof. Aswath Damodaran's NYU public datasets (no auth required, cached 7 days)

## Setup

### 1. Create a virtual environment and install dependencies
```bash
cd C:/Users/razva/Python_Projects/RazDashboard
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

> **Important:** Always use the venv — do NOT run from the Anaconda base environment. Anaconda has pyarrow/numpy ABI conflicts that cause segfaults.

### 2. Get a free Finnhub API key
1. Sign up at [finnhub.io](https://finnhub.io) (free tier is sufficient)
2. Copy your API key

### 3. Add your keys
Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in what you use:
```toml
FINNHUB_API_KEY   = "your_finnhub_key_here"
ANTHROPIC_API_KEY = "your_claude_key_here"   # optional — enables AI briefs, buy timing, 5-filter analysis
```
Deploying anywhere public? Set `MODE = "cloud"` and `APP_PASSWORD` — see `SECURITY.md`.
The app runs without either key — Finnhub falls back to yfinance; Claude features show a prompt to add the key.

### 4. Run
```bash
cd C:/Users/razva/Python_Projects/RazDashboard
venv\Scripts\activate
streamlit run dashboard.py
```

**First-load time**: ~5–15 seconds (Finviz rate-limits to 0.3s per ticker, 1yr OHLCV fetch). Subsequent loads within the same trading day are instant (all data is cached).

## Portfolio Data

Positions are stored in `portfolio.json` (auto-created on first run, gitignored). Each ticker supports multiple buy lots with different dates — cost basis and P&L are calculated per lot from historical prices.

For cloud deployment, portfolio is persisted to a **GitHub Gist** (`GIST_ID` + `GITHUB_TOKEN` in secrets); the app falls back to the local file when not configured.

Manage positions through the **תיק שלי** tab: add a lot (ticker + shares + buy date), edit shares or date on existing lots, or remove lots/tickers entirely. Adding a new ticker automatically includes it in all analysis.

## Architecture

Multi-file Python package:
```
src/yf_patch.py       ← Windows SQLite fix (MUST be first import)
src/config.py         ← all constants, thresholds, Hebrew strings
src/market.py         ← trading day detection and market status
src/portfolio.py      ← multi-lot JSON persistence
src/data/             ← individual data fetchers with @st.cache_data
  damodaran.py        ← Damodaran NYU sector benchmarks (P/E, EV/EBITDA, beta) — 7d cache
src/tabs/             ← one module per tab
  analysts_tab.py     ← ניתוח יומי | ⏰ תזמון קנייה | קונצנזוס
  daily_brief_tab.py  ← 📋 יומי: per-ticker brief + Claude Haiku narrative
  analysis_tab.py     ← 🔬 ניתוח: 5-filter Claude Haiku evaluation
dashboard.py          ← thin entry point (page config, KPI header, routing)
```

## Notes

- **ESLT** (Elbit Systems) — Israeli stock, minimal US analyst coverage. Empty consensus and no upgrades/downgrades are expected, not errors.
- **plotly** is pinned `>=5.18,<6` — plotly 6.x causes a segfault on Windows Streamlit.
- **numpy** is pinned `<2` — numpy 2.x breaks pyarrow ABI compatibility.
- **yfinance** — do not upgrade past 0.2.54 without testing the `src/yf_patch.py` cache patch.
- **Streamlit address** — `address = "localhost"` in `config.toml` is required for `crypto.randomUUID` (secure context) in Streamlit 1.43+.

## Changelog

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-03-28 | Initial release — 5-tab dashboard, live analyst data, portfolio tracking, market-aware caching |
| v1.1 | 2026-03-29 | Full Hebrew RTL UI — all labels, tabs, buttons translated |
| v1.2 | 2026-03-29 | Dynamic sidebar — live betas, dividend yields, analyst actions from major firms |
| v2.0 | 2026-03-29 | Full rewrite — multi-file package, 7 tabs, multi-lot portfolio model, 1yr candlestick + technical overlays, macro strip, correlation matrix, all flags automated |
| v2.1 | 2026-04-02 | Two-tier parallel data loading with background cache warming |
| v2.2 | 2026-04-02 | 📋 יומי daily brief tab + 🔬 ניתוח 5-filter analysis tab with Claude Haiku AI |
| v3.0 | 2026-04-03 | Bloomberg-style UI: sidebar primary nav, KPI header (value/P&L/alpha/bell), secondary tab bar, macro sparklines |
| v3.1–v3.4 | 2026-03-29 – 2026-04-17 | Code quality refactor; AI daily briefs + 5-filter analysis; Damodaran benchmarks; ORB intraday chart; trading journal; buy timing AI; GitHub Gist cloud backend |
| v3.5 | 2026-04-19 | Monte Carlo GBM simulation; watch-only mode (0-share lots); Portfolio Stress Test; TASE numeric security support |
| v3.6 | 2026-05-01 | TASE live data via pymaya (api.tase.co.il); mutual fund support; YFRateLimitError handling |
| v3.7 | 2026-05-02 | Watch-only UI (toggle, 📍 section, 👁 overview indicator); MC max profit KPI card; MC chart crash fixes |
| v4.0 | 2026-10-06 | Safety: no more overwriting the portfolio/journal after a failed read; shekel holdings converted in every USD total; verified SMTP TLS; escaped news/AI HTML; password gate for cloud |
| v4.1 | 2026-10-06 | Speed: star tier, per-ticker caches, AI once per ticker per day (≈21 Claude calls/day instead of 124+ per refresh) |
| v4.2 | 2026-10-06 | Navigation: 4 job-based tabs (היום / תיק / מניה / תרגול) |
| v4.3 | 2026-10-06 | Decision tools: performance history vs VOO, rebalancing, position sizer, stops & price alerts as red flags |
