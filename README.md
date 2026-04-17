# RazDashboard v3.4

Personal investment dashboard for the "Age of AI" portfolio. Tracks stocks across strategic layers with live data from Yahoo Finance, Finviz, and Finnhub. Built with Streamlit + Python, Hebrew RTL UI.

## Features

### Sidebar navigation
Bloomberg/TradingView-style layout: sidebar is the primary navigation hub with 5 main tabs, macro watchlist with SVG sparklines, and tool buttons at the bottom.

### KPI Header
Live stats bar at the top of every page:
- **שווי תיק** — total portfolio value (all lots × current prices)
- **רווח/הפסד** — total P&L in $ and %
- **Alpha vs VOO** — 30-day portfolio return minus VOO 30-day return
- **🔔 Bell** — alert count badge; red if flags triggered, yellow if watches, click to open Red Flags

### Primary tabs (sidebar)
- **סקירה (Overview)** — macro strip (VIX, 10Y yield, DXY), performance table with upside % and alpha vs VOO, portfolio P&L summary, sector allocation donut chart, 1-year correlation matrix heatmap
- **תיק שלי (Portfolio)** — two sub-tabs: **📊 תיק שלי**: multi-lot model with individual dates, buy prices (auto-filled from live data if left blank), and P&L; add/edit/remove lots; **📈 יומן עסקאות**: retroactive trading performance analysis — auto-loads all portfolio lots from first buy date, optional broker CSV supplement for closed trades; 6 analysis sections: overall stats (win rate, expectancy, avg win/loss), by portfolio layer, by setup type, by time-of-day block (9:30–16:00), by day of week, and auto pattern detection with Hebrew recommendations
- **גרפים (Charts)** — 1-year candlestick chart per ticker with toggleable overlays: SMA 20/50/200, Bollinger Bands, RSI(14), volume bars, analyst price target line, 52W high/low, relative strength vs VOO; **ORB (Opening Range Breakout)** intraday chart: 5-condition signal (price break + volume surge + above VWAP + trade window + top-50% bar close), configurable interval (1m/2m/5m/15m) and volume multiplier, green background on active episodes
- **אנליסטים (Analysts)** — three sub-tabs:
  - **📋 ניתוח יומי** — Finviz-style heatmap, market pulse KPIs, analyst conviction scatter matrix; **📊 Today's Session AI briefing**: single Claude Haiku call covers all tickers, returns priority-sorted table (High/Medium/Low) with catalyst, price assessment, support/resistance levels (R:$X S:$Y), and likely intraday setup; overall market context paragraph; Claude Haiku per-ticker daily brief
  - **⏰ תזמון קנייה** — AI buy timing: 0-100 signal score (RSI, SMA50/200, Bollinger, analyst upside, VIX, Damodaran sector P/E) + Claude Haiku Hebrew verdict card using Buffett/Lynch, Damodaran, and Breitstein frameworks; tickers ranked best opportunity first; **📏 Trailing Stop backtester**: n-bar trailing stop on 1yr daily data, MA-cross entry, color-coded stop line (red=initial/green=trailing), entry/exit markers, configurable lookback + MA periods, win rate + P&L stats
  - **👥 קונצנזוס ואנליסטים** — consensus table with mini distribution bar, price target range chart with error bars, recent upgrades/downgrades with major firm highlighting
- **פונדמנטלס (Fundamentals)** — P/E, Fwd P/E, EPS, ROE, ROA, P/B, P/S, Debt/Equity, Market Cap, Short Float, Institutional Ownership, Sector, Industry via Finviz; next earnings countdown with urgency colors; dividend yield; EPS trend on-demand

### Red Flags (bell icon in header)
All flags 100% automated (no manual entries): commodity price checks (uranium, copper, gold), analyst proxy signals, portfolio structure checks, thesis checks. Status: 🔴/🟡/🟢/⚫

### Secondary tabs (above main content)
- **חדשות (News)** — latest headlines per ticker, filterable by ticker, date-sorted
- **💡 המלצות (Recommendations)** — AI + analyst-backed buy/hold/sell recommendations
- **📋 יומי (Daily Brief)** — per-ticker Hebrew daily brief: consensus + upside, recent upgrade/downgrade pills, red flag status, 1-month alpha vs VOO. Optional Claude Haiku AI narrative (2-3 Hebrew bullet points, cached 1h)
- **🔬 ניתוח (5-Filter Analysis)** — auto-analyzes all watch-list tickers not currently in portfolio using 5 investment filters via Claude Haiku: revenue growth, competitive position, leadership, market timing, risk. Scored 1–5 per filter with color coding. Custom ticker input for any stock

### Infrastructure
- **Market-aware caching** — data fetched once per trading day; Refresh button disabled on weekends/holidays
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

### 3. Add your Finnhub key (and optionally Claude key)
Create (or edit) `.streamlit/secrets.toml`:
```toml
FINNHUB_API_KEY  = "your_finnhub_key_here"
ANTHROPIC_API_KEY = "your_claude_key_here"   # optional — enables AI daily briefs + 5-filter analysis
```
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
