"""Overview tab — macro strip, performance table, P&L summary, donut chart, correlation matrix."""

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config import COLOR, HE, LAYER_COLORS, SECTOR_ETFS, TICKER_NAMES
from src.data.prices import lookup_buy_price
from src.data.technicals import compute_correlation_matrix
from src.portfolio import add_lot, all_tickers, get_layer_for_ticker, lots_for_ticker, remove_ticker
from src.ui_helpers import color_legend, portfolio_treemap, section_title, term_glossary


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

        price_str  = f"${p['price']:.2f}" if p else "—"
        change_val = p["change"] if p else None
        change_str = (
            f'<span style="color:{COLOR["positive"] if change_val >= 0 else COLOR["negative"]}">'
            f'{change_val:+.2f}%</span>'
            if change_val is not None else "—"
        )

        upside_str = "—"
        if p and tgt and tgt.get("mean"):
            up = ((tgt["mean"] - p["price"]) / p["price"]) * 100
            uc = COLOR["positive"] if up >= 0 else COLOR["negative"]
            upside_str = f'<span style="color:{uc}">{up:+.1f}%</span>'

        alpha_str = "—"
        if p and p.get("history") is not None and len(p["history"]) > 1:
            t_1y = ((p["history"].iloc[-1] / p["history"].iloc[0]) - 1) * 100
            bench_return, bench_ticker = _bench_1y(layer)
            alpha = t_1y - bench_return
            ac    = COLOR["positive"] if alpha >= 0 else COLOR["negative"]
            alpha_str = (
                f'<span style="color:{ac}">{alpha:+.1f}%</span>'
                f'<span style="font-size:9px;color:{COLOR["dim"]}"> vs {bench_ticker}</span>'
            )

        label = con.get("label", "N/A")
        lc    = COLOR["positive"] if "Buy" in label else (COLOR["negative"] if "Sell" in label else COLOR["neutral"])
        cons_str = f'<span style="color:{lc}">{label}</span>'

        if is_watch:
            row_bg      = "background:#12121e"
            ticker_html = (
                f'<span style="color:#888;font-weight:500">👁 {t}</span>'
                f'<span style="font-size:9px;color:#555;margin-right:4px"> מעקב</span>'
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
    for t in all_tickers(portfolio):
        p = prices.get(t)
        if not p:
            continue
        for _layer, lot in lots_for_ticker(portfolio, t):
            if lot["shares"] <= 0:
                continue
            bp = lookup_buy_price(t, lot["buy_date"], prices)
            if bp:
                total_cost  += lot["shares"] * bp
                total_value += lot["shares"] * p["price"]

    pnl     = total_value - total_cost
    pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0.0
    pnl_c   = COLOR["positive"] if pnl >= 0 else COLOR["negative"]

    rows = [
        ("עלות כוללת",   f"${total_cost:,.0f}",  ""),
        ("שווי נוכחי",   f"${total_value:,.0f}", ""),
        ("רווח/הפסד $",  f"${pnl:+,.0f}",        pnl_c),
        ("רווח/הפסד %",  f"{pnl_pct:+.2f}%",     pnl_c),
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
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def _render_allocation_donut(portfolio, prices):
    labels, values, colors = [], [], []
    for layer, lots in portfolio["layers"].items():
        layer_val = 0.0
        for lot in lots:
            t = lot["ticker"]
            p = prices.get(t)
            if not p:
                continue
            layer_val += max(lot.get("shares", 0), 0) * p["price"]
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

    z    = corr.values.tolist()
    text = [[f"{v:.2f}" if not pd.isna(v) else "" for v in row] for row in corr.values]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=tickers_sorted,
        y=tickers_sorted,
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
