"""Overview tab — macro strip, performance table, P&L summary, donut chart, correlation matrix."""

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config import COLOR, HE, LAYER_COLORS, SECTOR_ETFS, TICKER_NAMES, is_tase_numeric
from src.data.prices import lookup_buy_price
from src.data.technicals import compute_correlation_matrix
from src.portfolio import add_lot, all_tickers, get_layer_for_ticker, lots_for_ticker, remove_ticker
from src.ui_helpers import color_legend, portfolio_treemap, section_title, term_glossary


# ── Stress-test scenario definitions ─────────────────────────────────────────
# Per-ticker shock estimates for 6 macro scenarios.
# For tickers not listed in "overrides", fallback = beta × market_shock (capped at 2.5×).
_STRESS_SHOCKS = {
    "🐻 שוק דובי": {
        "desc": "S&P 500 יורד 25% — מיתון כלכלי טיפוסי",
        "market_shock": -0.25,
        "color": "#e53935",
        "overrides": {
            "VOO": -0.25, "XAR": -0.20,
            "CCJ": -0.35, "FCX": -0.40, "ETN": -0.28, "VRT": -0.45, "EQX": +0.05,
            "AMD": -0.40, "AMZN": -0.28, "GOOGL": -0.30,
            "CRWD": -0.40, "ESLT": -0.15, "TEVA": -0.20,
        },
    },
    "💥 קריסת 2008": {
        "desc": "S&P 500 מאבד 50% — משבר פיננסי מערכתי",
        "market_shock": -0.50,
        "color": "#b71c1c",
        "overrides": {
            "VOO": -0.50, "XAR": -0.38,
            "CCJ": -0.65, "FCX": -0.65, "ETN": -0.55, "VRT": -0.60, "EQX": +0.10,
            "AMD": -0.60, "AMZN": -0.48, "GOOGL": -0.55,
            "CRWD": -0.55, "ESLT": -0.28, "TEVA": -0.35,
        },
    },
    "📈 הלם ריבית": {
        "desc": "Fed מעלה ריבית ל-6%+, תשואת 10Y מאמירה",
        "market_shock": -0.15,
        "color": "#ef6c00",
        "overrides": {
            "VOO": -0.15, "XAR": -0.08,
            "CCJ": -0.20, "FCX": -0.12, "ETN": -0.15, "VRT": -0.38, "EQX": -0.22,
            "AMD": -0.38, "AMZN": -0.22, "GOOGL": -0.25,
            "CRWD": -0.42, "ESLT": -0.05, "TEVA": -0.10,
        },
    },
    "💻 בועת טק": {
        "desc": "מכפילי AI/טק קורסים 40%, רוטציה לביטחון וסחורות",
        "market_shock": -0.10,
        "color": "#7b1fa2",
        "overrides": {
            "VOO": -0.12, "XAR": +0.08,
            "CCJ": -0.08, "FCX": -0.05, "ETN": -0.05, "VRT": -0.45, "EQX": +0.10,
            "AMD": -0.45, "AMZN": -0.30, "GOOGL": -0.35,
            "CRWD": -0.42, "ESLT": +0.05, "TEVA": +0.05,
        },
    },
    "🌡 סטגפלציה": {
        "desc": "אינפלציה גבוהה + צמיחה איטית — כמו שנות ה-70",
        "market_shock": -0.20,
        "color": "#f57f17",
        "overrides": {
            "VOO": -0.20, "XAR": -0.12,
            "CCJ": +0.05, "FCX": +0.15, "ETN": -0.10, "VRT": -0.30, "EQX": +0.30,
            "AMD": -0.30, "AMZN": -0.22, "GOOGL": -0.22,
            "CRWD": -0.28, "ESLT": -0.05, "TEVA": 0.00,
        },
    },
    "⚔️ ריצה לביטחון": {
        "desc": "הסלמה גיאופוליטית — ביטחון, זהב ואנרגיה גרעינית מתחזקים",
        "market_shock": -0.05,
        "color": "#1565c0",
        "overrides": {
            "VOO": -0.05, "XAR": +0.25,
            "CCJ": +0.10, "FCX": +0.05, "ETN": +0.05, "VRT": -0.10, "EQX": +0.15,
            "AMD": -0.15, "AMZN": -0.08, "GOOGL": -0.12,
            "CRWD": +0.12, "ESLT": +0.30, "TEVA": +0.05,
        },
    },
}


def render_overview(portfolio, data, market_state, td_str):
    prices      = data["prices"]
    targets     = data["targets"]
    consensus   = data["consensus"]
    macro       = data["macro"]

    _render_macro_strip(macro)
    _render_manage_tickers(portfolio)
    st.divider()
    _render_performance_table(portfolio, prices, targets, consensus)
    st.divider()
    col1, col2 = st.columns([1, 1])
    with col1:
        _render_pnl_summary(portfolio, prices)
    with col2:
        _render_allocation_donut(portfolio, prices)
    st.divider()
    _render_portfolio_heatmap(portfolio, prices)
    st.divider()
    _render_correlation_matrix(prices)
    st.divider()
    _render_stress_test(portfolio, prices)


def _render_manage_tickers(portfolio):
    """Compact add / remove ticker form embedded in the overview tab."""
    with st.expander("➕ / 🗑 ניהול ניירות ערך", expanded=False):
        col_add, col_rm = st.columns(2)

        with col_add:
            st.markdown(f'<div style="color:{COLOR["primary"]};font-weight:700;font-size:13px">הוסף נייר ערך</div>',
                        unsafe_allow_html=True)
            layers = list(portfolio["layers"].keys())
            new_ticker = st.text_input("סימול (Ticker)", key="ov_add_ticker",
                                       placeholder="e.g. NVDA").upper().strip()
            new_layer  = st.selectbox("שכבה", layers + ["➕ שכבה חדשה..."], key="ov_add_layer")
            if new_layer == "➕ שכבה חדשה...":
                new_layer = st.text_input("שם שכבה חדשה", key="ov_add_layer_new").strip()
            new_shares = st.number_input("כמות מניות", min_value=0.001, step=0.001,
                                         format="%.3f", key="ov_add_shares")
            new_date   = st.date_input("תאריך קנייה", value=date.today(), key="ov_add_date")

            if st.button("הוסף לתיק", key="ov_add_btn", use_container_width=True):
                if not new_ticker:
                    st.error("הכנס סימול.")
                elif not new_layer:
                    st.error("הכנס שם שכבה.")
                else:
                    add_lot(portfolio, new_layer, new_ticker, new_shares, new_date)
                    st.cache_data.clear()
                    st.success(f"נוסף {new_ticker} — רענון נתונים...")
                    st.rerun()

        with col_rm:
            st.markdown(f'<div style="color:{COLOR["negative"]};font-weight:700;font-size:13px">הסר נייר ערך</div>',
                        unsafe_allow_html=True)
            tickers_list = sorted(all_tickers(portfolio))
            if not tickers_list:
                st.caption("אין ניירות ערך בתיק.")
            else:
                rm_ticker = st.selectbox("בחר סימול להסרה", tickers_list, key="ov_rm_ticker")
                st.warning(f"יסיר את כל הלוטים של {rm_ticker}", icon="⚠️")
                if st.button(f"הסר {rm_ticker}", key="ov_rm_btn", use_container_width=True):
                    remove_ticker(portfolio, rm_ticker)
                    st.cache_data.clear()
                    st.success(f"{rm_ticker} הוסר מהתיק.")
                    st.rerun()


def _render_macro_strip(macro):
    vix  = macro.get("vix")
    y10  = macro.get("yield_10y")
    dxy  = macro.get("dxy")

    c1, c2, c3, _ = st.columns([1, 1, 1, 3])
    with c1:
        if vix is not None:
            color = COLOR["negative"] if vix >= 30 else (COLOR["warning"] if vix >= 20 else COLOR["positive"])
            st.markdown(
                f'<div style="text-align:right">'
                f'<div style="font-size:11px;color:{COLOR["text_dim"]}">{HE["vix"]}</div>'
                f'<div style="font-size:18px;font-weight:700;color:{color}">{vix:.1f}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    with c2:
        if y10 is not None:
            color = COLOR["negative"] if y10 >= 4.5 else (COLOR["warning"] if y10 >= 4.0 else COLOR["positive"])
            st.markdown(
                f'<div style="text-align:right">'
                f'<div style="font-size:11px;color:{COLOR["text_dim"]}">{HE["yield_10y"]}</div>'
                f'<div style="font-size:18px;font-weight:700;color:{color}">{y10:.2f}%</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    with c3:
        if dxy is not None:
            st.markdown(
                f'<div style="text-align:right">'
                f'<div style="font-size:11px;color:{COLOR["text_dim"]}">{HE["dxy"]}</div>'
                f'<div style="font-size:18px;font-weight:700">{dxy:.1f}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def _render_performance_table(portfolio, prices, targets, consensus):
    section_title("ביצועי תיק", "מחיר נוכחי, ביצוע שנתי מול VOO ויעדי אנליסטים לכל נייר")

    # Pre-compute 1Y return for each layer's benchmark ETF (fallback: VOO)
    def _bench_1y(layer_name):
        bench = SECTOR_ETFS.get(layer_name, "VOO")
        p = prices.get(bench)
        if p and p.get("history") is not None:
            h = p["history"]
            if len(h) > 1:
                return ((h.iloc[-1] / h.iloc[0]) - 1) * 100, bench
        # fallback to VOO
        voo_p = prices.get("VOO")
        if voo_p and voo_p.get("history") is not None:
            h = voo_p["history"]
            if len(h) > 1:
                return ((h.iloc[-1] / h.iloc[0]) - 1) * 100, "VOO"
        return 0.0, "VOO"

    rows = []
    for t in all_tickers(portfolio):
        layer    = get_layer_for_ticker(portfolio, t) or "אחר"
        is_watch = all(lot.get("shares", 0) == 0 for _l, lot in lots_for_ticker(portfolio, t))
        p   = prices.get(t)
        tgt = targets.get(t)
        con = consensus.get(t, {})

        is_tase = is_tase_numeric(t) or (p.get("currency") == "ILS" if p else False)
        cur_sym = "₪" if is_tase else "$"
        price_str  = f"{cur_sym}{p['price']:.2f}" if p else "—"
        change_val = p["change"] if p else None
        change_str = (
            f'<span style="color:{COLOR["positive"] if change_val >= 0 else COLOR["negative"]}">'
            f'{change_val:+.2f}%</span>'
            if change_val is not None else "—"
        )

        upside_str = "—"
        if not is_tase and p and tgt and tgt.get("mean"):
            up = ((tgt["mean"] - p["price"]) / p["price"]) * 100
            uc = COLOR["positive"] if up >= 0 else COLOR["negative"]
            upside_str = f'<span style="color:{uc}">{up:+.1f}%</span>'

        alpha_str = "—"
        if not is_tase and p and p.get("history") is not None and len(p["history"]) > 1:
            t_1y = ((p["history"].iloc[-1] / p["history"].iloc[0]) - 1) * 100
            bench_return, bench_ticker = _bench_1y(layer)
            alpha = t_1y - bench_return
            ac    = COLOR["positive"] if alpha >= 0 else COLOR["negative"]
            alpha_str = (
                f'<span style="color:{ac}">{alpha:+.1f}%</span>'
                f'<span style="font-size:9px;color:{COLOR["dim"]}"> vs {bench_ticker}</span>'
            )

        label = "TASE" if is_tase else con.get("label", "N/A")
        lc    = "#7c9fbf" if is_tase else (COLOR["positive"] if "Buy" in label else (COLOR["negative"] if "Sell" in label else COLOR["neutral"]))
        cons_str = f'<span style="color:{lc}">{label}</span>'

        if is_watch:
            row_bg      = "background:#12121e"
            ticker_html = (
                f'<span style="color:#888;font-weight:500">👁 {t}</span>'
                f'<span style="font-size:9px;color:#555;margin-right:4px"> מעקב</span>'
            )
        elif is_tase:
            row_bg      = "background:#0d0d1a"
            tase_tag    = (
                '<span style="font-size:9px;color:#7c9fbf;border:1px solid #334;'
                'border-radius:3px;padding:0 3px;margin-right:4px">₪</span>'
            )
            ticker_html = (
                f'{tase_tag}'
                f'<span style="color:{LAYER_COLORS.get(layer, COLOR["primary"])};font-weight:600">{t}</span>'
            )
        else:
            row_bg      = ""
            ticker_html = f'<span style="color:{LAYER_COLORS.get(layer, COLOR["primary"])};font-weight:600">{t}</span>'

        rows.append(
            f'<tr style="{row_bg}">'
            f'<td style="padding:4px 8px">{ticker_html}</td>'
            f'<td style="padding:4px 8px;font-size:11px;color:{COLOR["text_dim"]}">{TICKER_NAMES.get(t, t)}</td>'
            f'<td style="padding:4px 8px">{price_str}</td>'
            f'<td style="padding:4px 8px">{change_str}</td>'
            f'<td style="padding:4px 8px">{upside_str}</td>'
            f'<td style="padding:4px 8px">{"—" if is_watch else alpha_str}</td>'
            f'<td style="padding:4px 8px">{cons_str}</td>'
            f'</tr>'
        )

    th = "padding:6px 8px;color:{c};border-bottom:1px solid #444;text-align:right".format(c=COLOR["primary"])
    header = (
        f'<tr>'
        f'<th style="{th}">Ticker</th>'
        f'<th style="{th}">שם</th>'
        f'<th style="{th}">מחיר</th>'
        f'<th style="{th}">שינוי</th>'
        f'<th style="{th}">אפסייד</th>'
        f'<th style="{th}">Alpha 1Y</th>'
        f'<th style="{th}">קונצנזוס</th>'
        f'</tr>'
    )
    html = (
        '<div role="region" aria-label="ביצועי תיק" dir="rtl" style="font-size:12px">'
        '<table style="width:100%;border-collapse:collapse">'
        f'<thead>{header}</thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)
    color_legend([
        (COLOR["positive"],  "חיובי / עלייה"),
        (COLOR["negative"],  "שלילי / ירידה"),
        (COLOR["primary"],   "טיקר / לינק"),
        ("#9E9E9E",          "Hold / ניטרלי"),
    ])
    term_glossary([
        ("שינוי %",      "שינוי אחוזי ביחס למחיר הסגירה של יום המסחר הקודם."),
        ("אפסייד %",     "פוטנציאל עלייה לפי יעד המחיר הממוצע של האנליסטים: (יעד − מחיר) / מחיר × 100."),
        ("Alpha 1Y",     "תשואת הנייר ב-12 חודשים האחרונים פחות תשואת ה-ETF של השכבה (למשל XAR לביטחון, VOO לליבה). ערך חיובי = ביצועי יתר."),
        ("Strong Buy",   "לפחות 70% מהאנליסטים ממליצים קנייה או קנייה חזקה."),
        ("Buy",          "50%–70% מהאנליסטים ממליצים קנייה."),
        ("Hold",         "קונצנזוס ניטרלי — המתן, אל תוסיף ואל תמכור."),
        ("Sell",         "40%+ מהאנליסטים ממליצים מכירה."),
        ("N/A",          "אין נתוני אנליסטים זמינים עבור נייר זה (למשל ESLT)."),
    ])


def _render_pnl_summary(portfolio, prices):
    section_title("סיכום תיק", "עלות, שווי נוכחי ורווח/הפסד כולל לכל הלוטים")
    total_cost = total_value = 0.0
    tase_cost  = tase_value  = 0.0
    for t in all_tickers(portfolio):
        p = prices.get(t)
        if not p:
            continue
        is_tase = is_tase_numeric(t) or p.get("currency") == "ILS"
        for _layer, lot in lots_for_ticker(portfolio, t):
            if lot["shares"] <= 0:
                continue
            bp = lookup_buy_price(t, lot["buy_date"], prices)
            if bp:
                if is_tase:
                    tase_cost  += lot["shares"] * bp
                    tase_value += lot["shares"] * p["price"]
                else:
                    total_cost  += lot["shares"] * bp
                    total_value += lot["shares"] * p["price"]

    pnl     = total_value - total_cost
    pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0.0
    pnl_c   = COLOR["positive"] if pnl >= 0 else COLOR["negative"]

    rows = [
        ("עלות כוללת (USD)",   f"${total_cost:,.0f}",  ""),
        ("שווי נוכחי (USD)",   f"${total_value:,.0f}", ""),
        ("רווח/הפסד $",        f"${pnl:+,.0f}",        pnl_c),
        ("רווח/הפסד %",        f"{pnl_pct:+.2f}%",     pnl_c),
    ]
    html = '<div role="region" aria-label="סיכום תיק" dir="rtl" style="font-size:13px">'
    for label, val, color in rows:
        style = f"color:{color};font-weight:700" if color else ""
        html += (
            f'<div style="display:flex;justify-content:space-between;padding:4px 0">'
            f'<span style="color:{COLOR["text_dim"]}">{label}</span>'
            f'<span style="{style}">{val}</span>'
            f'</div>'
        )

    if tase_cost > 0 or tase_value > 0:
        tase_pnl     = tase_value - tase_cost
        tase_pnl_pct = (tase_pnl / tase_cost * 100) if tase_cost > 0 else 0.0
        tase_pnl_c   = COLOR["positive"] if tase_pnl >= 0 else COLOR["negative"]
        html += (
            f'<div style="margin-top:8px;padding-top:8px;border-top:1px solid #334">'
            f'<div style="font-size:10px;color:#7c9fbf;font-weight:600;margin-bottom:4px">TASE — בורסת תל אביב (₪)</div>'
        )
        for label, val, color in [
            ("עלות כוללת (₪)",  f"₪{tase_cost:,.0f}",  ""),
            ("שווי נוכחי (₪)",  f"₪{tase_value:,.0f}", ""),
            ("רווח/הפסד ₪",     f"₪{tase_pnl:+,.0f}",  tase_pnl_c),
            ("רווח/הפסד %",     f"{tase_pnl_pct:+.2f}%", tase_pnl_c),
        ]:
            style = f"color:{color};font-weight:700" if color else ""
            html += (
                f'<div style="display:flex;justify-content:space-between;padding:3px 0">'
                f'<span style="color:{COLOR["text_dim"]}">{label}</span>'
                f'<span style="{style}">{val}</span>'
                f'</div>'
            )
        html += "</div>"

    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def _render_allocation_donut(portfolio, prices):
    from src.data.macro import get_ils_usd_rate
    ils_usd = get_ils_usd_rate()  # 1 NIS → USD, cached weekly

    labels, values, colors = [], [], []
    for layer, lots in portfolio["layers"].items():
        layer_val = 0.0
        for lot in lots:
            t = lot["ticker"]
            p = prices.get(t)
            if not p:
                continue
            shares = max(lot.get("shares", 0), 0)
            price  = p["price"]
            if is_tase_numeric(t) or p.get("currency") == "ILS":
                layer_val += shares * price * ils_usd  # convert NIS → USD
            else:
                layer_val += shares * price
        if layer_val > 0:
            labels.append(layer)
            values.append(layer_val)
            colors.append(LAYER_COLORS.get(layer, COLOR["primary"]))

    if not values:
        st.caption("הזן מניות כדי לראות הקצאה")
        return

    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.55,
        marker_colors=colors,
        textinfo="percent+label",
        textfont_size=11,
        direction="clockwise",
    ))
    fig.update_layout(
        showlegend=False,
        margin={"t": 10, "b": 10, "l": 10, "r": 10},
        height=220,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#ffffff",
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_portfolio_heatmap(portfolio, prices):
    """Finviz-style portfolio heatmap: ticker boxes sized by value, colored by daily change."""
    section_title("מפת חום תיק", "גודל הריבוע = שווי ההחזקה | צבע = שינוי יומי | 👁 = ווצ'ליסט")

    col_heat, col_legend = st.columns([5, 1])
    with col_heat:
        portfolio_treemap(portfolio, prices, height=280)
    with col_legend:
        # Manual color scale legend
        scale = [
            ("#1b5e20", "+3%+"),
            ("#2e7d32", "+1.5%"),
            ("#388e3c", "+0.3%"),
            ("#2d3748", "  0%"),
            ("#c62828", "−0.3%"),
            ("#b71c1c", "−1.5%"),
            ("#7f0000", "−3%−"),
        ]
        items_html = "".join(
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:5px">'
            f'<div style="width:14px;height:14px;border-radius:2px;background:{c};flex-shrink:0"></div>'
            f'<span style="font-size:10px;color:#888">{lbl}</span></div>'
            for c, lbl in scale
        )
        st.markdown(
            f'<div style="padding-top:40px">{items_html}</div>',
            unsafe_allow_html=True,
        )


def _render_correlation_matrix(prices):
    section_title("מטריצת קורלציה (1 שנה)", "קשר בין תנועות המחיר של הניירות בשנה האחרונה")

    close_map = {}
    for t, p in prices.items():
        if t == "__errors__" or not isinstance(p, dict):
            continue
        if p and p.get("history") is not None:
            close_map[t] = p["history"]

    corr = compute_correlation_matrix(close_map)
    if corr.empty or corr.shape[0] < 2:
        st.caption("אין מספיק נתונים לחישוב קורלציה")
        return

    tickers_sorted = sorted(corr.columns.tolist())
    corr = corr.loc[tickers_sorted, tickers_sorted]
    labels_sorted = [TICKER_NAMES.get(t, t) for t in tickers_sorted]

    z    = corr.values.tolist()
    text = [[f"{v:.2f}" if not pd.isna(v) else "" for v in row] for row in corr.values]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=labels_sorted,
        y=labels_sorted,
        text=text,
        texttemplate="%{text}",
        colorscale="RdYlGn",
        zmin=-1, zmax=1,
        showscale=True,
        colorbar={"thickness": 12, "len": 0.8},
    ))
    fig.update_layout(
        height=350,
        margin={"t": 10, "b": 10, "l": 10, "r": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#ffffff", "size": 10},
        xaxis={"side": "bottom"},
    )
    st.plotly_chart(fig, use_container_width=True)
    color_legend([
        ("#1a9850", "+1.0 — תנועה זהה לחלוטין"),
        ("#ffffbf", " 0.0 — אין קשר"),
        ("#d73027", "−1.0 — תנועה הפוכה לחלוטין"),
        ("#555555", "NaN — פחות מ-30 ימי חפיפה"),
    ])
    term_glossary([
        ("קורלציה",          "מדד סטטיסטי בין −1 ל-+1 המתאר את מידת הקשר בין תנועות שני ניירות ערך."),
        ("+1.0",             "הניירות נעים יחד בכיוון זהה תמיד — הגנה גרועה, ריכוז סיכון."),
        ("−1.0",             "הניירות נעים בכיוון הפוך — הגנה מצוינת, גיוון מקסימלי."),
        ("0.0",              "אין קשר בין הניירות — גיוון טוב."),
        ("NaN (אפור)",       "פחות מ-30 ימי מסחר משותפים — אין מספיק נתונים לחישוב אמין."),
        ("min_periods=30",   "ספריית pandas: חישוב קורלציה רק אם קיימים לפחות 30 ימים חופפים."),
    ])


# ── Stress-test helpers ───────────────────────────────────────────────────────

def _ticker_shock(ticker, scenario, prices):
    """Return estimated shock fraction for ticker in scenario. Falls back to beta × market_shock."""
    overrides = scenario.get("overrides", {})
    if ticker in overrides:
        return overrides[ticker]
    p = prices.get(ticker) or {}
    beta = p.get("beta")
    if beta is not None:
        try:
            b = float(beta)
            if 0 < b < 5:
                return scenario["market_shock"] * min(b, 2.5)
        except (ValueError, TypeError):
            pass
    return scenario["market_shock"]


def _compute_portfolio_impacts(portfolio, prices):
    """Return (ticker_values, total_value, impacts).

    ticker_values : {ticker: current_dollar_value}
    impacts       : {scenario_name: {ticker: shock_fraction, "_portfolio": weighted_avg_shock}}
    """
    ticker_values = {}
    for t in all_tickers(portfolio):
        p = prices.get(t)
        if not p:
            continue
        shares = sum(lot.get("shares", 0) for _, lot in lots_for_ticker(portfolio, t))
        if shares > 0:
            ticker_values[t] = shares * p["price"]

    total_value = sum(ticker_values.values())
    if total_value == 0:
        return {}, 0.0, {}

    impacts = {}
    for name, scenario in _STRESS_SHOCKS.items():
        ticker_shocks = {}
        portfolio_dollar = 0.0
        for ticker, value in ticker_values.items():
            shock = _ticker_shock(ticker, scenario, prices)
            ticker_shocks[ticker] = shock
            portfolio_dollar += value * shock
        ticker_shocks["_portfolio"] = portfolio_dollar / total_value
        impacts[name] = ticker_shocks

    return ticker_values, total_value, impacts


def _stress_card(col, label, value, color="#ffffff", sub=""):
    sub_html = f"<div style='font-size:10px;color:#666;margin-top:2px'>{sub}</div>" if sub else ""
    col.markdown(
        f'<div style="background:#1a1a2e;border:1px solid #333;border-radius:8px;padding:10px 8px;text-align:center">'
        f'<div style="font-size:11px;color:#888;margin-bottom:3px">{label}</div>'
        f'<div style="font-size:18px;font-weight:700;color:{color}">{value}</div>'
        f'{sub_html}</div>',
        unsafe_allow_html=True,
    )


def _render_stress_test(portfolio, prices):
    section_title(
        "בדיקת עמידות תיק",
        "הערכת השפעת תרחישי קיצון על התיק — בהתבסס על חשיפות סקטוריאליות ובטא היסטורית",
    )

    ticker_values, total_value, impacts = _compute_portfolio_impacts(portfolio, prices)

    if not ticker_values or total_value == 0:
        st.caption("הזן מניות (כמות > 0) כדי לראות ניתוח תרחישים")
        return

    tickers = sorted(ticker_values.keys())
    ticker_labels = [TICKER_NAMES.get(t, t) for t in tickers]
    scenario_names = list(_STRESS_SHOCKS.keys())

    # ── Heatmap: scenarios × tickers ─────────────────────────────────────────
    z    = []
    text = []
    for name in scenario_names:
        row_z = []
        row_t = []
        for t in tickers:
            shock = impacts[name].get(t, 0)
            row_z.append(shock * 100)
            row_t.append(f"{shock*100:+.0f}%")
        z.append(row_z)
        text.append(row_t)

    colorscale = [
        [0.00, "#7f0000"],
        [0.20, "#c62828"],
        [0.38, "#ef5350"],
        [0.47, "#ffcdd2"],
        [0.50, "#2d3748"],
        [0.53, "#c8e6c9"],
        [0.62, "#66bb6a"],
        [0.80, "#2e7d32"],
        [1.00, "#1b5e20"],
    ]

    fig_heat = go.Figure(go.Heatmap(
        z=z,
        x=ticker_labels,
        y=scenario_names,
        text=text,
        texttemplate="%{text}",
        colorscale=colorscale,
        zmid=0,
        zmin=-65,
        zmax=35,
        showscale=True,
        colorbar={"title": "% שינוי", "thickness": 12, "len": 0.85},
    ))
    fig_heat.update_layout(
        height=270,
        margin={"t": 10, "b": 10, "l": 10, "r": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#ffffff", "size": 11},
        xaxis={"side": "bottom"},
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    # ── Portfolio-level bar chart ─────────────────────────────────────────────
    port_pcts  = [impacts[n]["_portfolio"] * 100 for n in scenario_names]
    bar_colors = [_STRESS_SHOCKS[n]["color"] for n in scenario_names]

    fig_bar = go.Figure(go.Bar(
        x=scenario_names,
        y=port_pcts,
        marker_color=bar_colors,
        text=[f"{v:+.1f}%" for v in port_pcts],
        textposition="outside",
        textfont={"size": 12},
    ))
    fig_bar.add_hline(y=0, line_color="#555", line_width=1)
    fig_bar.update_layout(
        height=250,
        margin={"t": 35, "b": 10, "l": 10, "r": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#ffffff", "size": 11},
        yaxis={"title": "שינוי (%)", "ticksuffix": "%", "gridcolor": "#333"},
        title={"text": "השפעה כוללת על שווי התיק לפי תרחיש", "font": {"size": 13}, "x": 0.5},
        showlegend=False,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # ── Scenario detail ───────────────────────────────────────────────────────
    sel = st.selectbox("בחר תרחיש לפירוט", scenario_names, key="stress_sel_scenario")
    scen             = _STRESS_SHOCKS[sel]
    port_pct         = impacts[sel]["_portfolio"]
    port_loss_dollar = total_value * port_pct
    retained         = total_value + port_loss_dollar
    survival_pct     = (1 + port_pct) * 100

    pnl_color    = COLOR["negative"] if port_loss_dollar < 0 else COLOR["positive"]
    pnl_str      = f"${abs(port_loss_dollar):,.0f}" if port_loss_dollar < 0 else f"+${port_loss_dollar:,.0f}"
    retain_color = COLOR["positive"] if survival_pct >= 80 else (COLOR["warning"] if survival_pct >= 65 else COLOR["negative"])

    cols = st.columns(4)
    _stress_card(cols[0], "השפעה על התיק", f"{port_pct*100:+.1f}%",
                 COLOR["negative"] if port_pct < 0 else COLOR["positive"])
    _stress_card(cols[1], "שווי תיק צפוי", f"${retained:,.0f}",
                 COLOR["negative"] if port_pct < -0.25 else (COLOR["warning"] if port_pct < -0.10 else COLOR["positive"]))
    _stress_card(cols[2], "הפסד / רווח $", pnl_str, pnl_color)
    _stress_card(cols[3], "% תיק נשמר", f"{survival_pct:.0f}%", retain_color)

    st.caption(f"📌 {scen['desc']}")

    # ── Worst / best performers ───────────────────────────────────────────────
    sorted_impacts = sorted(
        [(t, impacts[sel][t]) for t in tickers],
        key=lambda x: x[1],
    )
    col_worst, col_best = st.columns(2)
    with col_worst:
        st.markdown(
            f'<div style="color:{COLOR["negative"]};font-size:12px;font-weight:600;margin-bottom:4px">הכי פגועים</div>',
            unsafe_allow_html=True,
        )
        for t, shock in sorted_impacts[:3]:
            loss = ticker_values.get(t, 0) * shock
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;font-size:12px;padding:2px 0">'
                f'<span style="color:#ccc">{t}</span>'
                f'<span style="color:{COLOR["negative"]}">{shock*100:+.0f}% &nbsp; ${loss:,.0f}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
    with col_best:
        st.markdown(
            f'<div style="color:{COLOR["positive"]};font-size:12px;font-weight:600;margin-bottom:4px">הכי עמידים / מרוויחים</div>',
            unsafe_allow_html=True,
        )
        for t, shock in reversed(sorted_impacts[-3:]):
            gain = ticker_values.get(t, 0) * shock
            c    = COLOR["positive"] if shock >= 0 else COLOR["neutral"]
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;font-size:12px;padding:2px 0">'
                f'<span style="color:#ccc">{t}</span>'
                f'<span style="color:{c}">{shock*100:+.0f}% &nbsp; ${gain:+,.0f}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    term_glossary([
        ("בטא",            "מדד לתנודתיות הנייר ביחס לשוק הרחב. בטא=1.5 → הנייר נע 1.5× השוק (למעלה ולמטה)."),
        ("הלם ריבית",      "ריביות גבוהות פוגעות בחברות בעלות מכפילים גבוהים (P/E גבוה, Growth) יותר מחברות ערך."),
        ("סטגפלציה",       "אינפלציה גבוהה + צמיחה נמוכה. פוגע בצרכנים אך מיטיב עם סחורות (נחושת, זהב) ואנרגיה."),
        ("ריצה לביטחון",   "הסלמה גיאופוליטית מעלה ביקוש לביטחון, זהב ואנרגיה גרעינית, ופוגעת בנכסי סיכון."),
        ("% תיק נשמר",     "אחוז שווי התיק הנותר לאחר ההלם. 75% = איבדת 25% מהתיק. מתחת ל-65% = אדום."),
        ("אומדן",          "ההשפעות הן הערכות מבוססות-מחקר, לא ערכים מדויקים — המציאות תלויה בתזמון ובמהות האירוע."),
    ])
