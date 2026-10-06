"""Analysts tab — daily analysis (merged יומי) + buy timing + consensus table + price targets + upgrades."""

from concurrent.futures import ThreadPoolExecutor as _ThreadPool

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import ai
from src.config import COLOR, HE, MAJOR_FIRMS, PORTFOLIO_ETFS, TICKER_NAMES
from src.data.damodaran import get_damodaran_sector_data, get_sector_benchmarks
from src.data.technicals import bollinger, compute_rsi
from src.data.technicals import sma as _sma
from src.portfolio import active_tickers, all_tickers
from src.tabs.red_flags import get_all_flag_statuses
from src.ui_helpers import color_legend, esc, fmt_api_error, section_title, term_glossary


def warm_buy_timing_evals(tickers, data, all_flags, td_str, claude_api_key):
    """Pre-warm @st.cache_data buy-timing Claude evals for all portfolio tickers.

    Called from a background daemon thread in dashboard.py so that by the time
    the user opens the Analysts or Charts tab the evals are already cached.
    """
    if not claude_api_key:
        return

    non_etf = [t for t in tickers if t not in PORTFOLIO_ETFS]
    if not non_etf:
        return

    def _warm_one(ticker):
        try:
            sig = _compute_buy_signal(ticker, data, all_flags)
            signal_str = _build_timing_data_str(ticker, sig)
            _run_buy_timing_eval(ticker, signal_str, td_str, claude_api_key)
        except Exception:
            pass

    with _ThreadPool(max_workers=min(len(non_etf), 5)) as ex:
        list(ex.map(_warm_one, non_etf))


def render_analyst_views(portfolio, data, td_str="", claude_api_key=""):
    """תיק → אנליסטים ותזמון: buy-timing ranking + consensus / targets / upgrades."""
    prices    = data["prices"]
    targets   = data["targets"]
    consensus = data["consensus"]
    upgrades  = data["upgrades"]
    tickers   = active_tickers(portfolio)

    tab_timing, tab_consensus = st.tabs(["⏰ תזמון קנייה", "👥 קונצנזוס ואנליסטים"])
    with tab_timing:
        _render_buy_timing_tab(portfolio, data, td_str, claude_api_key)
    with tab_consensus:
        _render_consensus_table(tickers, consensus, prices)
        st.divider()
        _render_target_chart(tickers, prices, targets)
        st.divider()
        _render_upgrades_section(tickers, upgrades)


# ── Daily Analysis ────────────────────────────────────────────────────────────

def _render_daily_analysis(portfolio, prices, consensus, targets):
    """Daily dashboard: market pulse KPIs + per-ticker brief."""
    section_title("ניתוח יומי", "מצב התיק היום — מוסיפים, מפסידים, סיכום אנליסטים")
    tickers = sorted(all_tickers(portfolio))

    _render_market_pulse(tickers, prices, consensus, targets)


def _render_market_pulse(tickers, prices, consensus, targets):
    """4 KPI tiles: best mover, worst mover, avg analyst upside, portfolio beta."""
    # Gather data
    movers, upsides, betas = [], [], []
    for t in tickers:
        p = prices.get(t)
        if not p:
            continue
        change = p.get("change") or 0.0
        movers.append((t, change))
        beta = p.get("beta") or 1.0
        betas.append(beta)
        tgt = targets.get(t)
        if tgt and tgt.get("mean") and p.get("price") and p["price"] > 0:
            upsides.append((tgt["mean"] - p["price"]) / p["price"] * 100)

    best  = max(movers, key=lambda x: x[1], default=("—", 0.0))
    worst = min(movers, key=lambda x: x[1], default=("—", 0.0))
    avg_upside = sum(upsides) / len(upsides) if upsides else None
    avg_beta   = sum(betas)   / len(betas)   if betas   else None

    def _kpi(label, value_html, sub=""):
        return (
            f'<div style="background:#1a1f2e;border:1px solid #1f2937;border-radius:8px;'
            f'padding:12px 14px;text-align:right;direction:rtl">'
            f'<div style="font-size:10px;color:{COLOR["text_dim"]};margin-bottom:3px">{label}</div>'
            f'<div style="font-size:18px;font-weight:800;line-height:1.1">{value_html}</div>'
            f'<div style="font-size:10px;color:{COLOR["text_dim"]};margin-top:2px">{sub}</div>'
            f'</div>'
        )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        bc = COLOR["positive"]
        v = f'<span style="color:{bc}">{best[0]} {best[1]:+.2f}%</span>'
        st.markdown(_kpi("📈 מוביל היום", v), unsafe_allow_html=True)

    with c2:
        wc = COLOR["negative"]
        v = f'<span style="color:{wc}">{worst[0]} {worst[1]:+.2f}%</span>'
        st.markdown(_kpi("📉 מפסיד היום", v), unsafe_allow_html=True)

    with c3:
        if avg_upside is not None:
            uc = COLOR["positive"] if avg_upside >= 0 else COLOR["negative"]
            v = f'<span style="color:{uc}">{avg_upside:+.1f}%</span>'
            sub = f"{len(upsides)} ניירות עם יעד אנליסטים"
        else:
            v, sub = '<span style="color:#888">—</span>', ""
        st.markdown(_kpi("🎯 אפסייד ממוצע", v, sub), unsafe_allow_html=True)

    with c4:
        if avg_beta is not None:
            bc2 = (COLOR["negative"] if avg_beta > 1.3
                   else COLOR["warning"] if avg_beta > 1.0
                   else COLOR["positive"])
            v = f'<span style="color:{bc2}">{avg_beta:.2f}</span>'
            sub = "מעל 1.0 = תנודתי יותר מהשוק"
        else:
            v, sub = '<span style="color:#888">—</span>', ""
        st.markdown(_kpi("⚖️ בטא ממוצע תיק", v, sub), unsafe_allow_html=True)


# ── Today's Session Analysis ──────────────────────────────────────────────────

def _build_session_prompt(tickers, data):
    """
    Build a per-ticker data block used as the Claude prompt body and cache key.
    Uses only already-loaded data — zero extra network calls.
    """
    prices    = data.get("prices") or {}
    targets   = data.get("targets") or {}
    consensus = data.get("consensus") or {}
    news_dict = data.get("news") or {}
    macro     = data.get("macro") or {}

    vix      = macro.get("vix")
    yield10y = macro.get("yield_10y")

    lines = []

    # Macro header
    macro_line = "MACRO: "
    if vix is not None:
        macro_line += f"VIX={vix:.1f} "
    if yield10y is not None:
        macro_line += f"10Y_Yield={yield10y:.2f}% "
    lines.append(macro_line.strip())
    lines.append("")

    for t in tickers:
        p   = prices.get(t) or {}
        tgt = targets.get(t) or {}
        con = consensus.get(t) or {}

        price    = p.get("price") or 0.0
        change   = p.get("change") or 0.0
        high_52w = p.get("high_52w")
        low_52w  = p.get("low_52w")
        history  = p.get("history")

        parts = [f"TICKER: {t}"]
        if price:
            parts.append(f"price=${price:.2f} change={change:+.2f}%")
        if high_52w and low_52w:
            parts.append(f"52W_high=${high_52w:.2f} 52W_low=${low_52w:.2f}")

        # RSI
        try:
            if history is not None and len(history) >= 15:
                rsi_s = compute_rsi(history)
                if not rsi_s.empty:
                    parts.append(f"RSI={rsi_s.iloc[-1]:.1f}")
        except Exception:
            pass

        # SMA50 / SMA200
        try:
            if history is not None and price > 0:
                if len(history) >= 50:
                    s50 = _sma(history, 50)
                    if not s50.empty:
                        v50 = float(s50.iloc[-1])
                        rel = "above" if price >= v50 else "below"
                        parts.append(f"SMA50=${v50:.2f}({rel})")
                if len(history) >= 200:
                    s200 = _sma(history, 200)
                    if not s200.empty:
                        v200 = float(s200.iloc[-1])
                        rel = "above" if price >= v200 else "below"
                        parts.append(f"SMA200=${v200:.2f}({rel})")
        except Exception:
            pass

        # Bollinger
        try:
            if history is not None and len(history) >= 20 and price > 0:
                _mid, upper_b, lower_b = bollinger(history, 20, 2)
                if not _mid.empty:
                    parts.append(
                        f"BB_upper=${float(upper_b.iloc[-1]):.2f}"
                        f" BB_lower=${float(lower_b.iloc[-1]):.2f}"
                    )
        except Exception:
            pass

        # Analyst upside + consensus
        if tgt.get("mean") and price > 0:
            upside = (tgt["mean"] - price) / price * 100
            parts.append(f"analyst_target=${tgt['mean']:.2f}(upside={upside:+.1f}%)")
        if con.get("label"):
            parts.append(f"consensus={con['label']}")

        # Latest 2 news headlines
        headlines = (news_dict.get(t) or [])[:2]
        for art in headlines:
            title = (art.get("title") or "").strip()
            if title:
                parts.append(f"news: {title[:80]}")

        lines.append(" | ".join(parts))

    return "\n".join(lines)


@st.cache_data(ttl=43200, show_spinner=False)
def _session_cached(tickers_key: str, td_str: str, _prompt_body: str, _claude_api_key: str) -> dict:
    """One Claude call per (ticker set, trading day). Raises on failure (never cached)."""
    prompt_body = _prompt_body
    prompt = (
        "You are a professional equity trader generating a morning session briefing "
        "for a personal US stock portfolio.\n\n"
        f"Date: {td_str}\n\n"
        f"{prompt_body}\n\n"
        "Analyze each ticker for TODAY's US equity session and provide:\n"
        "1. catalyst: Key news or technical driver (or 'No catalyst' if none)\n"
        "2. premarket: Price action tone — strength/weakness and why (use change% + momentum)\n"
        "3. levels: Most relevant support and resistance as 'R:$X S:$Y' "
        "(derive from SMA50, SMA200, Bollinger bands, 52W high/low, analyst target)\n"
        "4. setup: Most likely intraday setup — choose from: "
        "ORB breakout / VWAP bounce / momentum continuation / mean reversion / "
        "pullback entry / wait for signal\n"
        "5. priority: High (strong catalyst + clear setup) / "
        "Medium (some signal, unclear edge) / Low (no edge today)\n\n"
        "CRITICAL RULES:\n"
        "- Return ONLY a raw JSON object. No code fences, no backticks, no markdown.\n"
        "- Max 12 words per field. English only.\n"
        "- Sort stocks array: High priority first, then Medium, then Low.\n"
        "- market_context: 2-3 sentences on today's overall session tone given macro data "
        "and portfolio composition.\n\n"
        'JSON: {"stocks":[{"ticker":"...","priority":"High|Medium|Low","catalyst":"...",'
        '"premarket":"...","levels":"R:$X S:$Y","setup":"..."},...], '
        '"market_context":"..."}'
    )
    text   = ai.ask(_claude_api_key, 4096, prompt, purpose="session")
    parsed = ai.parse_json(text)
    if parsed is None:
        raise ai.AIError(f"JSON לא תקין: {text[:120]}")
    if "stocks" not in parsed:
        raise ai.AIError("Response missing 'stocks' key")
    ai.mark_done("session", tickers_key, td_str)
    return parsed


def _run_session_analysis(tickers_key: str, prompt_body: str, td_str: str, claude_api_key: str) -> dict:
    """Morning session briefing for the active tickers.
    Returns {"stocks": [...], "market_context": "..."} or {"_error": "..."}."""
    try:
        with ai.key_lock("session", tickers_key, td_str):
            return _session_cached(tickers_key, td_str, prompt_body, claude_api_key)
    except Exception as exc:
        return {"_error": fmt_api_error(exc)}


def _render_session_analysis(portfolio, data, td_str, claude_api_key, wait_for_ai=True):
    """Render Today's Session Analysis table.

    wait_for_ai=False (היום tab): if the background warmup hasn't produced today's
    briefing yet, show a note instead of blocking the page on the Claude call.
    """
    section_title(
        "📊 ניתוח סשן היום",
        "סיכום מוקדם — קטליזטורים, מפתחות, סטאפ פוטנציאלי ועדיפות לפי איכות ההזדמנות",
    )

    if not claude_api_key:
        st.caption("🤖 הוסף ANTHROPIC_API_KEY לקובץ secrets.toml לקבלת ניתוח סשן AI")
        return

    tickers     = active_tickers(portfolio)  # held + starred — keeps the prompt small
    prompt_body = _build_session_prompt(tickers, data)
    tickers_key = ",".join(tickers)

    if not wait_for_ai and not ai.is_done("session", tickers_key, td_str):
        st.caption(HE["ai_preparing"])
        if st.button(HE["ai_check_again"], key="_session_refresh"):
            st.rerun()
        return

    with st.spinner("🤖 AI מנתח את הסשן..."):
        result = _run_session_analysis(tickers_key, prompt_body, td_str, claude_api_key)

    if "_error" in result:
        st.warning(f"⚠️ {result['_error']}")
        if st.button("🔄 נסה שוב", key="_retry_session"):
            st.rerun()  # failures are never cached — a rerun retries
        return

    stocks = result.get("stocks") or []
    if not stocks:
        st.caption("לא התקבלו נתוני סשן מה-AI.")
        return

    PRIORITY_COLOR = {
        "High":   COLOR["positive"],
        "Medium": COLOR["warning"],
        "Low":    COLOR["text_dim"],
    }
    PRIORITY_HE = {"High": "גבוהה", "Medium": "בינונית", "Low": "נמוכה"}

    _TH = (
        f"padding:5px 10px;color:{COLOR['primary']};"
        f"border-bottom:1px solid #333;font-size:11px;text-align:right"
    )
    _TD = "padding:6px 10px;font-size:11px;vertical-align:top"

    rows = ""
    for s in stocks:
        ticker   = esc(s.get("ticker", ""))
        priority = s.get("priority", "Low")
        pc       = PRIORITY_COLOR.get(priority, COLOR["text_dim"])
        ph       = esc(PRIORITY_HE.get(priority, priority))
        rows += (
            f'<tr>'
            f'<td style="{_TD};font-weight:700;color:{COLOR["primary"]}">{ticker}</td>'
            f'<td style="{_TD};color:{pc};font-weight:700">{ph}</td>'
            f'<td style="{_TD}">{esc(s.get("catalyst", "—"))}</td>'
            f'<td style="{_TD}">{esc(s.get("premarket", "—"))}</td>'
            f'<td style="{_TD};font-family:monospace;font-size:10px">{esc(s.get("levels", "—"))}</td>'
            f'<td style="{_TD};color:#aaa">{esc(s.get("setup", "—"))}</td>'
            f'</tr>'
        )

    html = (
        f'<div dir="rtl" style="overflow-x:auto">'
        f'<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f'<thead><tr>'
        f'<th style="{_TH}">Ticker</th>'
        f'<th style="{_TH}">עדיפות</th>'
        f'<th style="{_TH}">קטליזטור</th>'
        f'<th style="{_TH}">תנועת מחיר</th>'
        f'<th style="{_TH}">מפתחות (R/S)</th>'
        f'<th style="{_TH}">סטאפ</th>'
        f'</tr></thead><tbody>{rows}</tbody></table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)

    ctx = esc(result.get("market_context", ""))
    if ctx:
        st.markdown(
            f'<div dir="rtl" style="margin-top:12px;padding:10px 14px;'
            f'background:#0d1117;border-left:3px solid {COLOR["primary"]};'
            f'border-radius:4px;font-size:12px;color:#ccc;line-height:1.7">'
            f'<b style="color:{COLOR["primary"]}">🌍 הקשר שוק:</b> {ctx}</div>',
            unsafe_allow_html=True,
        )

    color_legend([
        (COLOR["positive"], "עדיפות גבוהה — קטליזטור חזק + סטאפ ברור"),
        (COLOR["warning"],  "עדיפות בינונית — אות חלש או אי-ודאות"),
        (COLOR["text_dim"], "עדיפות נמוכה — אין יתרון ברור להיום"),
    ])


# ── Buy Timing Tab ────────────────────────────────────────────────────────────

def _safe_pe(val):
    """Convert a value to a positive float PE ratio, or None."""
    if val is None:
        return None
    try:
        f = float(str(val).replace(",", "").strip())
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _compute_buy_signal(ticker, data, all_flags):
    """Compute 0-100 buy timing score for one ticker from technical + fundamental signals."""
    prices       = data.get("prices", {})
    consensus    = data.get("consensus", {})
    targets      = data.get("targets", {})
    macro        = data.get("macro", {})
    fundamentals = data.get("fundamentals", {})

    p        = prices.get(ticker) or {}
    con      = consensus.get(ticker) or {}
    tgt      = targets.get(ticker) or {}
    vix      = macro.get("vix")
    funda    = fundamentals.get(ticker) or {}
    history  = p.get("history")
    price_now = float(p.get("price") or 0.0)

    # ── RSI (max 20 pts) ──────────────────────────────────────────────────────
    rsi_val = None
    rsi_pts = 0
    if history is not None and len(history) >= 15:
        try:
            rsi_s = compute_rsi(history)
            if not rsi_s.empty:
                rsi_val = float(rsi_s.iloc[-1])
                if rsi_val < 30:
                    rsi_pts = 20
                elif rsi_val < 45:
                    rsi_pts = 12
                elif rsi_val < 55:
                    rsi_pts = 6
                elif rsi_val < 65:
                    rsi_pts = 2
        except Exception:
            pass

    # ── SMA 50 / 200 position (max 20 pts) ───────────────────────────────────
    sma50_val = sma200_val = None
    sma_pts = 0
    if history is not None and price_now > 0:
        try:
            if len(history) >= 50:
                s50 = _sma(history, 50)
                sma50_val = float(s50.iloc[-1]) if not s50.empty else None
            if len(history) >= 200:
                s200 = _sma(history, 200)
                sma200_val = float(s200.iloc[-1]) if not s200.empty else None
            below_50  = sma50_val  is not None and price_now < sma50_val
            below_200 = sma200_val is not None and price_now < sma200_val
            if below_50 and below_200:
                sma_pts = 20
            elif below_200:
                sma_pts = 12
            elif below_50:
                sma_pts = 5
        except Exception:
            pass

    # ── Bollinger band position (max 10 pts) ──────────────────────────────────
    bb_pos = None
    bb_pts = 0
    if history is not None and len(history) >= 20 and price_now > 0:
        try:
            mid_b, upper_b, lower_b = bollinger(history, 20, 2)
            if not mid_b.empty:
                u    = float(upper_b.iloc[-1])
                lb   = float(lower_b.iloc[-1])
                m    = float(mid_b.iloc[-1])
                span = (u - lb) or 1.0
                bb_pos = (price_now - lb) / span   # 0.0 = lower band, 1.0 = upper band
                if price_now <= lb:
                    bb_pts = 10
                elif price_now < m:
                    bb_pts = 5
                elif price_now < u:
                    bb_pts = 2
        except Exception:
            pass

    # ── Analyst upside (max 15 pts, skipped for ETFs) ────────────────────────
    upside_pct = None
    upside_pts = 0
    if ticker not in PORTFOLIO_ETFS and tgt.get("mean") and price_now > 0:
        upside_pct = (tgt["mean"] - price_now) / price_now * 100
        if upside_pct > 30:
            upside_pts = 15
        elif upside_pct > 20:
            upside_pts = 10
        elif upside_pct > 10:
            upside_pts = 5

    # ── VIX fear index (max 10 pts) ───────────────────────────────────────────
    vix_pts = 0
    if vix is not None:
        if vix > 25:
            vix_pts = 10
        elif vix > 20:
            vix_pts = 7
        elif vix > 15:
            vix_pts = 3

    # ── Damodaran P/E vs sector (max 15 pts, skipped for ETFs) ───────────────
    dama      = get_sector_benchmarks(ticker)
    sector_pe = dama.get("pe")
    sector_ev = dama.get("ev_ebitda")
    pe_pts    = 0
    if ticker not in PORTFOLIO_ETFS and sector_pe is not None:
        stock_pe = _safe_pe(funda.get("pe") or funda.get("forward_pe"))
        if stock_pe is not None:
            ratio = stock_pe / sector_pe
            if ratio < 0.70:
                pe_pts = 15
            elif ratio < 0.90:
                pe_pts = 9
            elif ratio < 1.10:
                pe_pts = 4

    # ── Flag penalty (max 25 pts deducted) ────────────────────────────────────
    flag_penalty = 0
    for f in all_flags:
        if f.get("ticker") == ticker:
            if f["status"] == "triggered":
                flag_penalty += 8
            elif f["status"] == "watch":
                flag_penalty += 3
    flag_penalty = min(flag_penalty, 25)

    # ── Final score ───────────────────────────────────────────────────────────
    raw   = rsi_pts + sma_pts + bb_pts + upside_pts + vix_pts + pe_pts
    score = max(0, min(100, raw - flag_penalty))

    if score >= 70:
        label = "חלון קנייה 🌟"
    elif score >= 50:
        label = "הזדמנות 🟢"
    elif score >= 25:
        label = "המתן 🟡"
    else:
        label = "לא עכשיו 🔴"

    return {
        "score":           score,
        "label":           label,
        "price":           price_now,
        "rsi_val":         rsi_val,
        "rsi_pts":         rsi_pts,
        "sma50_val":       sma50_val,
        "sma200_val":      sma200_val,
        "sma_pts":         sma_pts,
        "bb_pos":          bb_pos,
        "bb_pts":          bb_pts,
        "upside_pct":      upside_pct,
        "upside_pts":      upside_pts,
        "vix":             vix,
        "vix_pts":         vix_pts,
        "sector_pe":       sector_pe,
        "sector_ev":       sector_ev,
        "pe_pts":          pe_pts,
        "flag_penalty":    flag_penalty,
        "consensus_label": con.get("label", ""),
    }


def _build_timing_data_str(ticker, sig):
    """Format signal dict into a human-readable string used as the AI prompt + cache key."""
    p = sig
    parts = [
        f"Ticker: {ticker}",
        f"Score: {p['score']}/100 ({p['label']})",
    ]
    if p["price"]:
        parts.append(f"Current price: ${p['price']:.2f}")
    if p["rsi_val"] is not None:
        parts.append(f"RSI(14): {p['rsi_val']:.1f}")
    if p["sma50_val"]:
        pos = "below" if p["price"] < p["sma50_val"] else "above"
        parts.append(f"SMA50: ${p['sma50_val']:.2f} (price {pos})")
    if p["sma200_val"]:
        pos = "below" if p["price"] < p["sma200_val"] else "above"
        parts.append(f"SMA200: ${p['sma200_val']:.2f} (price {pos})")
    if p["bb_pos"] is not None:
        if p["bb_pos"] <= 0:
            bb_desc = "at or below lower Bollinger band"
        elif p["bb_pos"] < 0.5:
            bb_desc = "lower half of Bollinger range"
        elif p["bb_pos"] < 1.0:
            bb_desc = "upper half of Bollinger range"
        else:
            bb_desc = "above upper Bollinger band"
        parts.append(f"Bollinger: {bb_desc}")
    if p["upside_pct"] is not None:
        parts.append(f"Analyst upside to mean target: {p['upside_pct']:+.1f}%")
    if p["vix"] is not None:
        parts.append(f"VIX: {p['vix']:.1f}")
    if p["consensus_label"]:
        parts.append(f"Analyst consensus: {p['consensus_label']}")
    if p["sector_pe"] is not None:
        parts.append(f"Damodaran sector P/E benchmark: {p['sector_pe']:.1f}")
    if p["sector_ev"] is not None:
        parts.append(f"Damodaran sector EV/EBITDA benchmark: {p['sector_ev']:.1f}")
    if p["flag_penalty"] > 0:
        parts.append(f"Active red flag penalty: {p['flag_penalty']} pts")
    return " | ".join(parts)


@st.cache_data(ttl=43200, show_spinner=False)
def _buy_timing_cached(ticker: str, td_str: str, _signal_str: str, _claude_api_key: str) -> dict:
    """One Claude verdict per (ticker, trading day). Raises on failure (never cached)."""
    signal_str = _signal_str
    prompt = (
        f"Analyze the buy timing for stock {ticker} using this market data:\n"
        f"{signal_str}\n\n"
        "CRITICAL FORMATTING RULES:\n"
        "1. Return ONLY a raw JSON object. Do NOT wrap it in markdown code fences "
        "or backticks. No ``` before or after. No 'json' language tag.\n"
        "2. ALL explanation values MUST be written in Hebrew (עברית).\n"
        "3. Do not use quotation marks inside explanation values — "
        "use dashes or parentheses instead.\n\n"
        'Format: {"verdict":"...","catalyst":"...","entry_conditions":"...","time_horizon":"...",'
        '"damodaran_view":"...","breitstein_view":"..."}\n\n'
        "Rules:\n"
        "- verdict: one of exactly: לא עכשיו / המתן / הזדמנות / חלון קנייה\n"
        "- catalyst: 2 Hebrew sentences — what technical/fundamental signal creates the "
        "opportunity now (Buffett/Lynch margin of safety perspective)\n"
        "- entry_conditions: 2 Hebrew sentences — specific price level or trigger to watch "
        "(RSI threshold, SMA crossover, price target level)\n"
        "- time_horizon: one of exactly: קצר טווח (שבועות) / בינוני (1-3 חודשים) / "
        "ארוך טווח (6+ חודשים)\n"
        "- damodaran_view: 1 Hebrew sentence — is the stock cheap or expensive vs its "
        "Damodaran sector P/E and EV/EBITDA benchmarks? Apply intrinsic value framework\n"
        "- breitstein_view: 1 Hebrew sentence — technical trend: is this stock a leader or "
        "laggard in its sector? Assess price vs moving averages, RSI momentum, relative "
        "strength vs market. Apply Breitstein trend-following methodology"
    )
    text   = ai.ask(_claude_api_key, 900, prompt, purpose="buy_timing")
    parsed = ai.parse_json(text)
    if parsed is None:
        raise ai.AIError(f"JSON לא תקין: {text[:120]}")
    required = ("verdict", "catalyst", "entry_conditions", "time_horizon",
                "damodaran_view", "breitstein_view")
    missing = [k for k in required if k not in parsed]
    if missing:
        raise ai.AIError(f"חסרים שדות: {missing}")
    ai.mark_done("buy_timing", ticker, td_str)
    return parsed


def _run_buy_timing_eval(ticker: str, signal_str: str, td_str: str, claude_api_key: str) -> dict:
    """Buy timing verdict for ticker (cached per trading day). Returns dict or {"_error": msg}."""
    try:
        with ai.key_lock("buy_timing", ticker, td_str):
            return _buy_timing_cached(ticker, td_str, signal_str, claude_api_key)
    except Exception as exc:
        return {"_error": fmt_api_error(exc)}


def _render_score_bar(score, label):
    """Colored HTML progress bar for the buy timing score."""
    if score >= 70:
        color = "#00cf8d"
    elif score >= 50:
        color = "#4CAF50"
    elif score >= 25:
        color = "#FF9800"
    else:
        color = "#F44336"
    st.markdown(
        f'<div style="margin:6px 0 4px 0">'
        f'<div style="background:#1a1a2e;border-radius:4px;height:8px;overflow:hidden">'
        f'<div style="background:{color};width:{score}%;height:100%;border-radius:4px"></div>'
        f'</div>'
        f'<div style="display:flex;justify-content:space-between;margin-top:3px">'
        f'<span style="font-size:10px;color:#555">0</span>'
        f'<span style="font-size:12px;font-weight:700;color:{color}">{score}/100 — {label}</span>'
        f'<span style="font-size:10px;color:#555">100</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def _render_signal_chips(sig):
    """Inline HTML signal chips for RSI / SMA / Bollinger / Upside / VIX / Damodaran."""

    def _chip(label, pts, max_pts):
        ratio = pts / max_pts if max_pts > 0 else 0
        if ratio >= 0.7:
            bg, fg = "#1b3a1a", "#4CAF50"
        elif ratio >= 0.3:
            bg, fg = "#3a2a00", "#FF9800"
        else:
            bg, fg = "#1e1e2e", "#888888"
        return (
            f'<span style="display:inline-block;background:{bg};color:{fg};'
            f'border:1px solid {fg}44;border-radius:12px;padding:2px 9px;'
            f'font-size:10px;margin:2px 3px 2px 0;font-family:monospace">{label}</span>'
        )

    chips = ""

    if sig["rsi_val"] is not None:
        prefix = "🔥 " if sig["rsi_val"] < 30 else ""
        chips += _chip(f"{prefix}RSI {sig['rsi_val']:.0f}", sig["rsi_pts"], 20)

    if sig["sma200_val"] and sig["price"]:
        pos = "מתחת SMA200" if sig["price"] < sig["sma200_val"] else "מעל SMA200"
        chips += _chip(f"{pos} ${sig['sma200_val']:.0f}", sig["sma_pts"], 20)
    elif sig["sma50_val"] and sig["price"]:
        pos = "מתחת SMA50" if sig["price"] < sig["sma50_val"] else "מעל SMA50"
        chips += _chip(f"{pos} ${sig['sma50_val']:.0f}", sig["sma_pts"], 20)

    if sig["bb_pos"] is not None:
        if sig["bb_pos"] <= 0.2:
            bb_lbl = "🎯 BB תחתון"
        elif sig["bb_pos"] < 0.5:
            bb_lbl = "BB חצי תחתון"
        else:
            bb_lbl = "BB חצי עליון"
        chips += _chip(bb_lbl, sig["bb_pts"], 10)

    if sig["upside_pct"] is not None:
        chips += _chip(f"אפסייד {sig['upside_pct']:+.0f}%", sig["upside_pts"], 15)

    if sig["vix"] is not None:
        chips += _chip(f"VIX {sig['vix']:.1f}", sig["vix_pts"], 10)

    if sig["sector_pe"] is not None:
        chips += _chip(f"P/E sector {sig['sector_pe']:.1f}", sig["pe_pts"], 15)

    if sig["flag_penalty"] > 0:
        chips += (
            f'<span style="display:inline-block;background:#2d0a0a;color:#F44336;'
            f'border:1px solid #F4433644;border-radius:12px;padding:2px 9px;'
            f'font-size:10px;margin:2px 3px 2px 0">⚑ דגלים −{sig["flag_penalty"]}</span>'
        )

    st.markdown(
        f'<div dir="rtl" style="margin:4px 0 8px 0;line-height:2.0">{chips}</div>',
        unsafe_allow_html=True,
    )


def _render_timing_ai_card(verdict_dict, ticker, data_str, td_str, claude_api_key):
    """Render the 6-field AI verdict card. Shows retry button on error."""
    if "_error" in verdict_dict:
        st.warning(f"⚠️ {verdict_dict['_error']}")
        if st.button("🔄 נסה שוב", key=f"_retry_timing_{ticker}"):
            st.rerun()  # failures are never cached — a rerun retries
        return

    # Claude output — escape before it reaches unsafe_allow_html
    v    = esc(verdict_dict.get("verdict", ""))
    cat  = esc(verdict_dict.get("catalyst", ""))
    ent  = esc(verdict_dict.get("entry_conditions", ""))
    th   = esc(verdict_dict.get("time_horizon", ""))
    dama = esc(verdict_dict.get("damodaran_view", ""))
    brei = esc(verdict_dict.get("breitstein_view", ""))

    rows = ""
    if cat:
        rows += (
            f'<div style="margin-bottom:5px">'
            f'<span style="color:#888;font-size:10px">💡 קטליזטור:&nbsp;</span>{cat}</div>'
        )
    if ent:
        rows += (
            f'<div style="margin-bottom:5px">'
            f'<span style="color:#888;font-size:10px">🎯 כניסה:&nbsp;</span>{ent}</div>'
        )
    if dama:
        rows += (
            f'<div style="margin-bottom:4px">'
            f'<span style="color:#888;font-size:10px">📊 Damodaran:&nbsp;</span>'
            f'<span style="color:#aaa">{dama}</span></div>'
        )
    if brei:
        rows += (
            f'<div>'
            f'<span style="color:#888;font-size:10px">📈 Breitstein:&nbsp;</span>'
            f'<span style="color:#aaa">{brei}</span></div>'
        )

    st.markdown(
        f'<div dir="rtl" style="background:#0d1117;border:1px solid #1f2937;'
        f'border-radius:8px;padding:12px 14px;margin-top:6px;font-size:11px;line-height:1.65">'
        f'<div style="font-size:12px;font-weight:700;color:{COLOR["primary"]};margin-bottom:8px">'
        f'🤖 AI — {v}&nbsp;&nbsp;'
        f'<span style="font-size:10px;color:{COLOR["text_dim"]};font-weight:400">⏱ {th}</span>'
        f'</div>{rows}</div>',
        unsafe_allow_html=True,
    )


def _render_buy_timing_tab(portfolio, data, td_str, claude_api_key):
    """⏰ Buy Timing tab — score all tickers and show AI verdict cards."""
    section_title(
        "תזמון קנייה",
        "ניתוח טכני, Damodaran ו-AI לזיהוי חלון הכניסה האופטימלי",
    )

    with st.expander("📖 מתודולוגיה — 3 Frameworks", expanded=False):
        st.markdown(
            '<div dir="rtl" style="font-size:11px;color:#aaa;line-height:1.8">'
            '<b style="color:#00cf8d">Buffett / Lynch:</b> '
            'RSI מתחת ל-30 = אזור קנייה היסטורי | מחיר מתחת ל-SMA50/200 = תמיכה טכנית | '
            'Bollinger Band תחתון = מחיר קיצוני יחסית | אפסייד לפי יעד אנליסטים כמרווח ביטחון.'
            '<br><b style="color:#00cf8d">Damodaran (NYU):</b> '
            'P/E ו-EV/EBITDA של המניה מול ממוצע הסקטור לפי מסד הנתונים השנתי של '
            'Prof. Aswath Damodaran. מניה בהנחה לסקטור = נקודה חיובית.'
            '<br><b style="color:#00cf8d">Breitstein (Trend-Following):</b> '
            'האם המניה מובילה את הסקטור שלה? עוצמה יחסית, מיקום ביחס לממוצעים, '
            'ומומנטום RSI. גישה: אל תילחם במגמה — בקש ממנה שתעבוד בשבילך.'
            '</div>',
            unsafe_allow_html=True,
        )

    tickers = active_tickers(portfolio)

    # Pre-warm Damodaran cache (1 fetch per 7 days)
    get_damodaran_sector_data()

    # Compute flags + signals for all tickers
    all_flags = data.get("_flags") or get_all_flag_statuses(portfolio, data)
    signals   = {t: _compute_buy_signal(t, data, all_flags) for t in tickers}

    # Sort by score descending
    ranked = sorted(tickers, key=lambda t: signals[t]["score"], reverse=True)

    st.markdown(
        f'<div dir="rtl" style="font-size:11px;color:{COLOR["text_dim"]};margin:8px 0 12px 0">'
        f'ממוין לפי ציון הזדמנות — גבוה יותר = חלון קנייה טוב יותר</div>',
        unsafe_allow_html=True,
    )

    for t in ranked:
        sig   = signals[t]
        score = sig["score"]
        label = sig["label"]
        name  = TICKER_NAMES.get(t, t)

        with st.expander(f"{t} — {name}  |  {score}/100  {label}", expanded=score >= 50):
            _render_score_bar(score, label)
            _render_signal_chips(sig)

            if claude_api_key:
                data_str = _build_timing_data_str(t, sig)
                # Only call Claude for verdicts already computed today (cache hit) or on click
                if ai.is_done("buy_timing", t, td_str) or st.button(
                        HE["ai_run"], key=f"_ai_timing_{t}"):
                    with st.spinner("🤖 AI מנתח..."):
                        verdict = _run_buy_timing_eval(t, data_str, td_str, claude_api_key)
                    _render_timing_ai_card(verdict, t, data_str, td_str, claude_api_key)
            else:
                st.caption("🤖 הוסף ANTHROPIC_API_KEY לקובץ secrets.toml לקבלת ניתוח AI")


# ── Consensus Table ───────────────────────────────────────────────────────────

def _render_consensus_table(tickers, consensus, prices):
    section_title("קונצנזוס אנליסטים", "ממוצע המלצות אנליסטים ממוסדות פיננסיים מובילים")

    _TH = f"padding:5px 8px;color:{COLOR['primary']};border-bottom:1px solid #333;font-size:11px;text-align:right"
    _TD = "padding:5px 8px;font-size:12px"

    rows = ""
    for t in tickers:
        c   = consensus.get(t, {})
        p   = prices.get(t)
        lbl = c.get("label", "N/A")
        tot = c.get("total", 0)

        # Color by label
        lc = (COLOR["positive"] if "Buy" in lbl
              else COLOR["negative"] if "Sell" in lbl
              else COLOR["neutral"])

        price_str = f"${p['price']:.2f}" if p else "—"

        # Mini bar widths (% of total analysts) — capture tot in default arg to avoid B023
        def _w(n, _tot=tot):
            return int(n / _tot * 60) if _tot > 0 else 0

        sb, b, h, s, ss = (c.get(k, 0) for k in ("strong_buy","buy","hold","sell","strong_sell"))
        bar = (
            f'<div style="display:flex;gap:1px;align-items:center;height:10px">'
            f'<div style="width:{_w(sb)}px;background:#1b5e20;height:100%" title="Strong Buy: {sb}"></div>'
            f'<div style="width:{_w(b)}px;background:{COLOR["positive"]};height:100%" title="Buy: {b}"></div>'
            f'<div style="width:{_w(h)}px;background:{COLOR["neutral"]};height:100%" title="Hold: {h}"></div>'
            f'<div style="width:{_w(s)}px;background:{COLOR["negative"]};height:100%" title="Sell: {s}"></div>'
            f'<div style="width:{_w(ss)}px;background:#b71c1c;height:100%" title="Strong Sell: {ss}"></div>'
            f'</div>'
        )

        rows += (
            f'<tr>'
            f'<td style="{_TD};font-weight:700;color:{COLOR["primary"]}">{t}</td>'
            f'<td style="{_TD};font-size:10px;color:{COLOR["text_dim"]}">{TICKER_NAMES.get(t,"")}</td>'
            f'<td style="{_TD}">{price_str}</td>'
            f'<td style="{_TD};color:{lc};font-weight:700">{lbl}</td>'
            f'<td style="{_TD}">{bar} <span style="font-size:10px;color:{COLOR["text_dim"]}">({tot})</span></td>'
            f'<td style="{_TD};font-size:10px">{sb} / {b} / {h} / {s} / {ss}</td>'
            f'</tr>'
        )

    html = (
        f'<div dir="rtl" style="font-size:12px">'
        f'<table style="width:100%;border-collapse:collapse">'
        f'<thead><tr>'
        f'<th style="{_TH}">Ticker</th>'
        f'<th style="{_TH}">שם</th>'
        f'<th style="{_TH}">מחיר</th>'
        f'<th style="{_TH}">קונצנזוס</th>'
        f'<th style="{_TH}">פיזור</th>'
        f'<th style="{_TH}">SB/B/H/S/SS</th>'
        f'</tr></thead><tbody>{rows}</tbody></table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)
    color_legend([
        ("#4CAF50",  "Buy / Strong Buy — קנייה"),
        ("#9E9E9E",  "Hold — החזק"),
        ("#F44336",  "Sell / Strong Sell — מכירה"),
        ("#1b5e20",  "Strong Buy (כהה)"),
        ("#b71c1c",  "Strong Sell (כהה)"),
    ])
    term_glossary([
        ("Strong Buy",   "המלצה חזקה לקנייה — מעל 70% מהאנליסטים ממליצים קנייה."),
        ("Buy",          "המלצה לקנייה — 50%–70% מהאנליסטים."),
        ("Hold",         "המלצה להחזיק — אל תוסיף ואל תמכור, המתן לאותות חדשים."),
        ("Sell",         "המלצת מכירה — מעל 40% מהאנליסטים ממליצים מכירה."),
        ("Strong Sell",  "המלצת מכירה חזקה — רמת אזהרה גבוהה."),
        ("SB/B/H/S/SS",  "קיצור: Strong Buy / Buy / Hold / Sell / Strong Sell — מספר האנליסטים בכל קטגוריה."),
        ("פיזור (בר)",   "הפס הצבעוני מציג את יחס ההמלצות — ירוק=קנייה, אפור=החזק, אדום=מכירה."),
        ("N/A",          "אין נתוני אנליסטים — כיסוי מוגבל (למשל ESLT הנסחרת בבורסת ת\"א)."),
    ])


def _render_target_chart(tickers, prices, targets):
    section_title("יעדי מחיר אנליסטים", "יעד ממוצע, נמוך וגבוה לפי הערכות האנליסטים")

    t_list, lows, means, highs, currents, upsides = [], [], [], [], [], []
    for t in tickers:
        tgt = targets.get(t)
        p   = prices.get(t)
        if not tgt or not tgt.get("mean") or not p:
            continue
        t_list.append(t)
        lows.append(tgt["low"]  or tgt["mean"])
        means.append(tgt["mean"])
        highs.append(tgt["high"] or tgt["mean"])
        currents.append(p["price"])
        up = (tgt["mean"] - p["price"]) / p["price"] * 100
        upsides.append(up)

    if not t_list:
        st.caption("אין נתוני יעד זמינים.")
        return

    fig = go.Figure()
    # Error bars for low-high range
    fig.add_trace(go.Scatter(
        x=t_list, y=means,
        mode="markers",
        name="יעד ממוצע",
        marker={"color": COLOR["primary"], "size": 10, "symbol": "diamond"},
        error_y={
            "type": "data",
            "symmetric": False,
            "array": [h - m for h, m in zip(highs, means)],
            "arrayminus": [m - lo for m, lo in zip(means, lows)],
            "color": "#555",
            "thickness": 2,
        },
    ))
    # Current price
    fig.add_trace(go.Scatter(
        x=t_list, y=currents,
        mode="markers",
        name="מחיר נוכחי",
        marker={"color": COLOR["warning"], "size": 8, "symbol": "circle"},
    ))

    fig.update_layout(
        height=300,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#111111",
        font={"color": "#ffffff", "size": 11},
        legend={"orientation": "h", "y": 1.08},
        margin={"t": 20, "b": 20, "l": 20, "r": 20},
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="#222")
    fig.update_yaxes(gridcolor="#222", tickprefix="$")
    st.plotly_chart(fig, use_container_width=True)

    # Upside table below chart
    rows = ""
    for t, up in zip(t_list, upsides):
        uc = COLOR["positive"] if up >= 0 else COLOR["negative"]
        rows += (
            f'<span style="margin-left:16px">'
            f'<b>{t}</b>: <span style="color:{uc}">{up:+.1f}%</span>'
            f'</span>'
        )
    st.markdown(f'<div dir="rtl" style="font-size:12px">{rows}</div>', unsafe_allow_html=True)
    term_glossary([
        ("יעד ממוצע",  "ממוצע כל יעדי המחיר שפרסמו אנליסטים — מיוצג כיהלום ירוק בגרף."),
        ("טווח",       "הפסים בגרף מציינים את יעד המחיר הנמוך והגבוה ביותר שפרסמו האנליסטים."),
        ("מחיר נוכחי", "נקודה כתומה בגרף — מחיר הסגירה האחרון של הנייר."),
        ("אפסייד %",   "(יעד ממוצע − מחיר נוכחי) ÷ מחיר נוכחי × 100. ערך חיובי = פוטנציאל עלייה."),
        ("Coverage",   "מספר האנליסטים המכסים את הנייר — ככל שיותר, כך הנתון אמין יותר."),
    ])


def _render_upgrades_section(tickers, upgrades):
    section_title("שדרוגים / שינמוכים", "פעולות אנליסטים מ-180 הימים האחרונים — בנקים מובילים מודגשים")

    sel = st.selectbox("בחר סימול", tickers, key="ud_sel_v2",
                       format_func=lambda t: f"{t} — {TICKER_NAMES.get(t,'')}")
    df = upgrades.get(sel)

    if df is None or df.empty:
        st.caption("לא נמצאו פעולות אנליסט ב-180 הימים האחרונים.")
        return

    def _style(val):
        v = str(val).lower()
        if "up" in v or "init" in v or "buy" in v:
            return f"color:{COLOR['positive']};font-weight:600"
        if "down" in v or any(s in v for s in ("sell","reduce","underperform","underweight")):
            return f"color:{COLOR['negative']};font-weight:600"
        return ""

    # Highlight major firms
    rows = ""
    for _, row in df.iterrows():
        firm   = str(row.get("firm", ""))
        action = str(row.get("action", ""))
        fgrade = str(row.get("from_grade", ""))
        tgrade = str(row.get("to_grade", ""))
        dt     = row.get("date")
        ds     = dt.strftime("%d.%m.%y") if pd.notna(dt) else ""
        is_major = any(mf in firm.lower() for mf in MAJOR_FIRMS)
        firm_style = f"color:{COLOR['primary']};font-weight:700" if is_major else f"color:{COLOR['text_dim']}"
        rows += (
            f'<tr>'
            f'<td style="padding:4px 8px;font-size:11px">{ds}</td>'
            f'<td style="padding:4px 8px;font-size:11px;{firm_style}">{firm}</td>'
            f'<td style="padding:4px 8px;font-size:11px;{_style(action)}">{action}</td>'
            f'<td style="padding:4px 8px;font-size:11px;color:{COLOR["text_dim"]}">{fgrade}</td>'
            f'<td style="padding:4px 8px;font-size:11px;{_style(tgrade)}">{tgrade}</td>'
            f'</tr>'
        )

    _TH = f"padding:5px 8px;color:{COLOR['primary']};border-bottom:1px solid #333;font-size:11px"
    html = (
        f'<div dir="rtl" style="font-size:12px">'
        f'<table style="width:100%;border-collapse:collapse">'
        f'<thead><tr>'
        f'<th style="{_TH}">תאריך</th>'
        f'<th style="{_TH}">חברה</th>'
        f'<th style="{_TH}">פעולה</th>'
        f'<th style="{_TH}">מ-</th>'
        f'<th style="{_TH}">ל-</th>'
        f'</tr></thead><tbody>{rows}</tbody></table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)
    color_legend([
        ("#4CAF50",  "Upgrade / Initiation / Buy"),
        ("#F44336",  "Downgrade / Sell / Underperform"),
        ("#00cf8d",  "בנק/מוסד מוביל (JPM, GS, MS, BofA ועוד)"),
        ("#aaaaaa",  "אנליסט/בנק קטן"),
    ])
    term_glossary([
        ("Upgrade",       "שדרוג המלצה — האנליסט העלה את הדירוג (למשל מ-Hold ל-Buy)."),
        ("Downgrade",     "שינמוך המלצה — האנליסט הוריד את הדירוג (למשל מ-Buy ל-Hold)."),
        ("Initiated",     "כיסוי חדש — האנליסט מתחיל לכסות את הנייר בפעם הראשונה."),
        ("Reiterated",    "אישור דירוג קיים — האנליסט שמר על אותה המלצה."),
        ("Outperform",    "שקול ל-Buy — צפוי לבצע טוב יותר מהשוק."),
        ("Underperform",  "שקול ל-Sell — צפוי לבצע גרוע יותר מהשוק."),
        ("Overweight",    "שקול ל-Buy — משקל יתר בתיק מומלץ."),
        ("Underweight",   "שקול ל-Sell — משקל חסר בתיק מומלץ."),
        ("Neutral",       "שקול ל-Hold."),
        ("מ- / ל-",       "הדירוג הקודם (מ-) והחדש (ל-) — אפשר לזהות את כיוון השינוי."),
    ])
