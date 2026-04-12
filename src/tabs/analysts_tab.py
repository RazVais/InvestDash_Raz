"""Analysts tab — daily analysis (merged יומי) + buy timing + consensus table + price targets + upgrades."""

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config import COLOR, MAJOR_FIRMS, PORTFOLIO_ETFS, TICKER_NAMES
from src.data.damodaran import get_damodaran_sector_data, get_sector_benchmarks
from src.data.technicals import bollinger, compute_rsi
from src.data.technicals import sma as _sma
from src.portfolio import all_tickers
from src.tabs.analysis_tab import _safe_parse_json
from src.tabs.daily_brief_tab import render_daily_brief
from src.tabs.red_flags import get_all_flag_statuses
from src.ui_helpers import color_legend, portfolio_treemap, section_title, term_glossary


def render_analysts(portfolio, data, td_str: str = "", claude_api_key: str = ""):
    prices    = data["prices"]
    targets   = data["targets"]
    consensus = data["consensus"]
    upgrades  = data["upgrades"]
    tickers   = sorted(all_tickers(portfolio))

    tab_daily, tab_timing, tab_consensus = st.tabs([
        "📋 ניתוח יומי", "⏰ תזמון קנייה", "👥 קונצנזוס ואנליסטים",
    ])

    with tab_daily:
        _render_daily_analysis(portfolio, prices, consensus, targets)
        st.divider()
        render_daily_brief(portfolio, data, td_str, claude_api_key)

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
    """Finviz-inspired daily dashboard: market pulse + heatmap + conviction scatter."""
    section_title("ניתוח יומי", "מצב התיק היום — מוסיפים, מפסידים, עוצמת אנליסטים ומפת חום")
    tickers = sorted(all_tickers(portfolio))

    _render_market_pulse(tickers, prices, consensus, targets)
    st.divider()

    # ── Heatmap row ───────────────────────────────────────────────
    col_heat, col_legend = st.columns([6, 1])
    with col_heat:
        st.markdown(
            f'<div dir="rtl" style="font-size:13px;font-weight:600;color:{COLOR["primary"]};'
            f'margin-bottom:4px">📊 מפת חום תיק</div>'
            f'<div dir="rtl" style="font-size:10px;color:{COLOR["text_dim"]};margin-bottom:6px">'
            f'גודל = שווי | צבע = שינוי יומי % | 👁 = ווצ\'ליסט</div>',
            unsafe_allow_html=True,
        )
        portfolio_treemap(portfolio, prices, height=260)
    with col_legend:
        scale = [("#1b5e20","+3%+"),("#388e3c","+0.5%"),("#2d3748","  0%"),
                 ("#c62828","−0.5%"),("#7f0000","−3%−")]
        items = "".join(
            f'<div style="display:flex;align-items:center;gap:5px;margin-bottom:4px">'
            f'<div style="width:12px;height:12px;border-radius:2px;background:{c}"></div>'
            f'<span style="font-size:9px;color:#666">{lbl}</span></div>'
            for c, lbl in scale
        )
        st.markdown(f'<div style="padding-top:36px">{items}</div>', unsafe_allow_html=True)

    st.divider()

    # ── Conviction scatter — full width, centred ──────────────────
    st.markdown(
        f'<div dir="rtl" style="font-size:13px;font-weight:600;color:{COLOR["primary"]};'
        f'margin-bottom:2px">🎯 מטריצת עוצמת אנליסטים</div>'
        f'<div dir="rtl" style="font-size:10px;color:{COLOR["text_dim"]};margin-bottom:10px">'
        f'ציר X = אפסייד לפי יעד אנליסטים&nbsp;|&nbsp;'
        f'ציר Y = % אנליסטים עם המלצת קנייה&nbsp;|&nbsp;'
        f'גודל נקודה = מספר אנליסטים&nbsp;|&nbsp;'
        f'צבע = שינוי יומי %</div>',
        unsafe_allow_html=True,
    )
    _render_conviction_scatter(tickers, prices, consensus, targets)

    # Quadrant explanation cards below the chart
    q_cards = [
        ("#4CAF5022", "#4CAF50", "🟢 הזדמנות — ימין עליון",
         "אפסייד גבוה + רוב האנליסטים ממליצים קנייה. "
         "המניה נסחרת מתחת ליעד ויש קונצנזוס חיובי — אזור המפגש האידיאלי."),
        ("#FF980022", "#FF9800", "🟡 פוטנציאל נסתר — ימין תחתון",
         "אפסייד גבוה אך האנליסטים זהירים. ייתכן שהשוק ראה סיכון שהאנליסטים מתעלמים ממנו, "
         "או הזדמנות קונטרריאנית."),
        ("#F4433622", "#F44336", "🔴 מומחים קנו כבר — שמאל עליון",
         "רוב האנליסטים אוהבים את המניה, אך המחיר כבר גבוה מהיעד. "
         "הציפיות כבר מגולמות — סיכון ל-Priced In."),
        ("#9E9E9E22", "#9E9E9E", "⚫ הימנע — שמאל תחתון",
         "אפסייד שלילי (מחיר מעל יעד) ומעט המלצות קנייה. "
         "אין קטליזטור מחירי נראה לעין — עדיף לחכות לנתונים חדשים."),
    ]
    cols = st.columns(4)
    for col, (bg, border, title, desc) in zip(cols, q_cards):
        with col:
            st.markdown(
                f'<div dir="rtl" style="background:{bg};border:1px solid {border}33;'
                f'border-radius:8px;padding:10px 12px;height:100%">'
                f'<div style="font-size:11px;font-weight:700;color:{border};margin-bottom:5px">'
                f'{title}</div>'
                f'<div style="font-size:10px;color:#aaaaaa;line-height:1.55">{desc}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


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


def _render_conviction_scatter(tickers, prices, consensus, targets):
    """
    Finviz-style analyst conviction matrix.
    X = analyst upside%, Y = % buy recommendations, dot size = sqrt(analyst count),
    dot color = daily % change.  Top-right = strongest opportunity signal.
    """
    xs, ys, sizes, colors, labels, hovers = [], [], [], [], [], []

    for t in tickers:
        p     = prices.get(t)
        con   = consensus.get(t, {})
        tgt   = targets.get(t)
        total = con.get("total", 0)
        if not p or total < 2 or not tgt or not tgt.get("mean") or p.get("price", 0) <= 0:
            continue

        upside   = (tgt["mean"] - p["price"]) / p["price"] * 100
        buy_frac = (con.get("strong_buy", 0) + con.get("buy", 0)) / total * 100
        change   = p.get("change", 0.0) or 0.0

        xs.append(upside)
        ys.append(buy_frac)
        # sqrt scaling: 5 analysts→10px, 25→20px, 76→28px — readable, never overwhelming
        sizes.append(max(int(math.sqrt(total) * 3.5), 8))
        colors.append(change)
        labels.append(t)
        hovers.append(
            f"<b>{t}</b><br>"
            f"אפסייד: {upside:+.1f}%<br>"
            f"Buy: {buy_frac:.0f}% ({total} אנליסטים)<br>"
            f"שינוי יומי: {change:+.2f}%"
        )

    if not xs:
        st.caption("אין נתוני אנליסטים זמינים.")
        return

    x_pad = max((max(xs) - min(xs)) * 0.15, 8)
    y_pad = 8
    x_min, x_max = min(xs) - x_pad, max(xs) + x_pad
    y_min, y_max = max(min(ys) - y_pad, -5), min(max(ys) + y_pad, 108)

    fig = go.Figure()

    # Subtle quadrant shading
    for x0, x1, y0, y1, col in [
        (x_min, 0,     50, y_max, "rgba(244,67,54,0.04)"),   # top-left: danger
        (0,     x_max, 50, y_max, "rgba(76,175,80,0.06)"),   # top-right: opportunity
        (x_min, 0,     y_min, 50, "rgba(244,67,54,0.02)"),   # bottom-left: avoid
        (0,     x_max, y_min, 50, "rgba(255,152,0,0.04)"),   # bottom-right: wait
    ]:
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                      fillcolor=col, line_width=0, layer="below")

    # Reference dividers
    fig.add_hline(y=50, line_dash="dot", line_color="#2a2a2a", line_width=1)
    fig.add_vline(x=0,  line_dash="dot", line_color="#2a2a2a", line_width=1)

    # Quadrant corner labels — midpoint of each quadrant
    mid_x_right = (0 + x_max) / 2
    mid_x_left  = (x_min + 0) / 2
    mid_y_top   = (50 + y_max) / 2
    mid_y_bot   = (y_min + 50) / 2
    for qx, qy, qtxt, qcol in [
        (mid_x_right, mid_y_top, "🟢 הזדמנות",  "rgba(76,175,80,0.35)"),
        (mid_x_left,  mid_y_top, "🔴 מסוכן",    "rgba(244,67,54,0.35)"),
        (mid_x_right, mid_y_bot, "🟡 פוטנציאל", "rgba(255,152,0,0.35)"),
        (mid_x_left,  mid_y_bot, "⚫ הימנע",    "rgba(158,158,158,0.35)"),
    ]:
        fig.add_annotation(
            x=qx, y=qy, text=qtxt, showarrow=False,
            font={"size": 11, "color": qcol}, xanchor="center", yanchor="middle",
        )

    fig.add_trace(go.Scatter(
        x=xs, y=ys,
        mode="markers+text",
        text=labels,
        textposition="top center",
        textfont={"size": 9, "color": "#e0e0e0", "family": "monospace"},
        marker={
            "size":  sizes,
            "color": colors,
            "colorscale": [
                [0.0,  "#b71c1c"],
                [0.35, "#e53935"],
                [0.48, "#37474f"],
                [0.52, "#37474f"],
                [0.65, "#43a047"],
                [1.0,  "#1b5e20"],
            ],
            "cmin": -2.5, "cmax": 2.5,
            "showscale": True,
            "colorbar": {
                "title": {"text": "שינוי%", "font": {"size": 9}},
                "thickness": 8, "len": 0.5,
                "tickfont": {"size": 8},
                "x": 1.01,
            },
            "line": {"color": "#1a1a1a", "width": 1},
            "opacity": 0.9,
        },
        customdata=hovers,
        hovertemplate="%{customdata}<extra></extra>",
    ))

    fig.update_layout(
        height=480,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0a0e17",
        font={"color": "#aaaaaa", "size": 10},
        margin={"t": 8, "b": 36, "l": 44, "r": 28},
        showlegend=False,
        xaxis={
            "title": {"text": "אפסייד אנליסטים %", "font": {"size": 10}},
            "gridcolor": "#161b22", "zeroline": False,
            "ticksuffix": "%", "range": [x_min, x_max],
            "tickfont": {"size": 9},
        },
        yaxis={
            "title": {"text": "% המלצות Buy", "font": {"size": 10}},
            "gridcolor": "#161b22", "zeroline": False,
            "ticksuffix": "%", "range": [y_min, y_max],
            "tickfont": {"size": 9},
        },
    )
    st.plotly_chart(fig, use_container_width=True)


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


def _strip_fences(text: str) -> str:
    """
    Remove markdown code fences from an LLM response.
    Handles: ```json / ```JSON / ``` with \n or \r\n line endings.
    Applied before _safe_parse_json as an extra safety layer.
    """
    import re as _re
    # Case-insensitive, strip language tag and any whitespace (including \r)
    text = _re.sub(r"```[a-zA-Z]*[\r\n]*", "", text)
    text = _re.sub(r"```[\r\n]*", "", text)
    return text.strip()


@st.cache_data(ttl=3600)
def _run_buy_timing_eval(
    ticker: str, signal_str: str, td_str: str, claude_api_key: str
) -> dict:
    """Call Claude Haiku for a buy timing verdict. Returns dict or {"_error": msg}."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=claude_api_key)
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
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        text   = _strip_fences(msg.content[0].text)
        parsed = _safe_parse_json(text)
        if parsed is None:
            return {"_error": f"JSON לא תקין: {text[:120]}"}
        required = ("verdict", "catalyst", "entry_conditions", "time_horizon",
                    "damodaran_view", "breitstein_view")
        missing = [k for k in required if k not in parsed]
        if missing:
            return {"_error": f"חסרים שדות: {missing}"}
        return parsed
    except Exception as exc:
        return {"_error": str(exc)[:200]}


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
            _run_buy_timing_eval.clear()
            st.rerun()
        return

    v    = verdict_dict.get("verdict", "")
    cat  = verdict_dict.get("catalyst", "")
    ent  = verdict_dict.get("entry_conditions", "")
    th   = verdict_dict.get("time_horizon", "")
    dama = verdict_dict.get("damodaran_view", "")
    brei = verdict_dict.get("breitstein_view", "")

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

    tickers = sorted(all_tickers(portfolio))

    # Pre-warm Damodaran cache (1 fetch per 7 days)
    get_damodaran_sector_data()

    # Compute flags + signals for all tickers
    all_flags = get_all_flag_statuses(portfolio, data)
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
                with st.spinner("🤖 AI מנתח..."):
                    verdict = _run_buy_timing_eval(t, data_str, td_str, claude_api_key)
                _render_timing_ai_card(verdict, t, data_str, td_str, claude_api_key)
            else:
                st.caption("🤖 הוסף CLAUDE_API_KEY לקובץ secrets.toml לקבלת ניתוח AI")


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
