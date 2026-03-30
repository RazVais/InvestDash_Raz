# RazDashboard v2

Personal investment dashboard for the "Age of AI" portfolio. Tracks stocks across strategic layers with live data from Yahoo Finance, Finviz, and Finnhub. Built with Streamlit + Python, Hebrew RTL UI.

## Features

- **סקירה (Overview)** — macro strip (VIX, 10Y yield, DXY), performance table with upside % and alpha vs VOO, portfolio P&L summary, sector allocation donut chart, 1-year correlation matrix heatmap
- **תיק שלי (Portfolio)** — multi-lot model: track multiple buy events per ticker with individual dates, prices, and P&L; add/edit/remove individual lots or entire tickers
- **גרפים (Charts)** — 1-year candlestick chart per ticker with toggleable overlays: SMA 20/50/200, Bollinger Bands, RSI(14), volume bars, analyst price target line, 52W high/low, relative strength vs VOO
- **אנליסטים (Analysts)** — consensus table with mini distribution bar (Strong Buy/Buy/Hold/Sell/Strong Sell), price target range chart with error bars, recent upgrades/downgrades with major firm highlighting (JPM, GS, MS, BofA, etc.)
- **פונדמנטלס (Fundamentals)** — P/E, Fwd P/E, EPS, ROE, ROA, P/B, P/S, Debt/Equity, Market Cap, Short Float, Institutional Ownership, Sector, Industry via Finviz; next earnings countdown with urgency colors; dividend yield; EPS trend on-demand
- **דגלים אדומים (Red Flags)** — all flags 100% automated (no manual entries): commodity price checks (uranium, copper, gold), analyst proxy signals, portfolio structure checks, thesis checks. Status: 🔴/🟡/🟢/⚫
- **חדשות (News)** — latest headlines per ticker, filterable by ticker, date-sorted
- **Market-aware caching** — data fetched once per trading day; Refresh button disabled on weekends/holidays
- **Sidebar** — live market status badge, flag summary count, macro indicators, refresh button

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

### 3. Add your Finnhub key
Create (or edit) `.streamlit/secrets.toml`:
```toml
FINNHUB_API_KEY = "your_actual_key_here"
```
The app runs without a Finnhub key — it falls back to yfinance for consensus data.

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
src/yf_patch.py     ← Windows SQLite fix (MUST be first import)
src/config.py       ← all constants, thresholds, Hebrew strings
src/market.py       ← trading day detection and market status
src/portfolio.py    ← multi-lot JSON persistence
src/data/           ← individual data fetchers with @st.cache_data
src/tabs/           ← one module per tab
dashboard.py        ← thin entry point (page config + tab routing only)
```

## Notes

- **ESLT** (Elbit Systems) — Israeli stock, minimal US analyst coverage. Empty consensus and no upgrades/downgrades are expected, not errors.
- **plotly** is pinned `>=5.18,<6` — plotly 6.x causes a segfault on Windows Streamlit.
- **numpy** is pinned `<2` — numpy 2.x breaks pyarrow ABI compatibility.
- **yfinance** — do not upgrade past 0.2.54 without testing the `src/yf_patch.py` cache patch.

## Changelog

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-03-28 | Initial release — 5-tab dashboard, live analyst data, portfolio tracking, market-aware caching |
| v1.1 | 2026-03-29 | Full Hebrew RTL UI — all labels, tabs, buttons translated |
| v1.2 | 2026-03-29 | Dynamic sidebar — live betas, dividend yields, analyst actions from major firms |
| v2.0 | 2026-03-29 | Full rewrite — multi-file package, 7 tabs, multi-lot portfolio model, 1yr candlestick + technical overlays, macro strip, correlation matrix, all flags automated |
