"""Analysts tab — consensus table, price target chart, upgrades/downgrades."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config import COLOR, MAJOR_FIRMS, TICKER_NAMES
from src.portfolio import all_tickers
from src.ui_helpers import color_legend, section_title, term_glossary


def render_analysts(portfolio, data):
    prices    = data["prices"]
    targets   = data["targets"]
    consensus = data["consensus"]
    upgrades  = data["upgrades"]
    tickers   = sorted(all_tickers(portfolio))

    _render_consensus_table(tickers, consensus, prices)
    st.divider()
    _render_target_chart(tickers, prices, targets)
    st.divider()
    _render_upgrades_section(tickers, upgrades)


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
