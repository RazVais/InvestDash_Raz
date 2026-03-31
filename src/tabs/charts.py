"""Charts tab — 1-year candlestick with RSI, MAs, Bollinger, Volume, relative strength."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from src.config import COLOR, HE, TICKER_NAMES
from src.data.technicals import bollinger, compute_relative_strength, compute_rsi, sma
from src.portfolio import all_tickers
from src.ui_helpers import color_legend, term_glossary


def render_charts(portfolio, data):
    prices  = data["prices"]
    targets = data["targets"]

    tickers = sorted(all_tickers(portfolio))
    if not tickers:
        st.info("הוסף ניירות ערך לתיק כדי לראות גרפים.")
        return

    st.markdown('<div dir="rtl">', unsafe_allow_html=True)
    col1, col2 = st.columns([2, 5])
    with col1:
        sel = st.selectbox("בחר מניה", tickers, key="chart_sel",
                           format_func=lambda t: f"{t} — {TICKER_NAMES.get(t, '')}")
    with col2:
        c1, c2, c3, c4, c5 = st.columns(5)
        show_sma20   = c1.checkbox("SMA 20",    value=False, key="ch_sma20")
        show_sma50   = c2.checkbox("SMA 50",    value=True,  key="ch_sma50")
        show_sma200  = c3.checkbox("SMA 200",   value=True,  key="ch_sma200")
        show_boll    = c4.checkbox("Bollinger", value=False, key="ch_boll")
        show_rsi     = c5.checkbox("RSI",       value=True,  key="ch_rsi")
    st.markdown('</div>', unsafe_allow_html=True)

    p = prices.get(sel)
    if not p or p.get("ohlcv") is None or p["ohlcv"].empty:
        err = prices.get("__errors__", {}).get(sel, "")
        detail = f" — {err}" if err else ""
        st.warning(f"אין נתוני OHLCV עבור {sel}{detail}. נסה לרענן (כפתור בסרגל הצד).")
        return

    ohlcv = p["ohlcv"]
    close = ohlcv["Close"]

    # ── Build subplots ───────────────────────────────────────────────────────
    n_rows  = 2 + (1 if show_rsi else 0)
    row_h   = [0.65, 0.15] + ([0.20] if show_rsi else [])
    fig = make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        row_heights=row_h,
        vertical_spacing=0.03,
        subplot_titles=["", HE["volume_label"]] + ([HE["rsi_label"]] if show_rsi else []),
    )

    # ── Row 1: Candlestick ───────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=ohlcv.index,
        open=ohlcv["Open"], high=ohlcv["High"],
        low=ohlcv["Low"],   close=ohlcv["Close"],
        name=sel,
        increasing_line_color=COLOR["positive"],
        decreasing_line_color=COLOR["negative"],
        showlegend=False,
    ), row=1, col=1)

    # MAs
    if show_sma20:
        fig.add_trace(go.Scatter(x=ohlcv.index, y=sma(close, 20),
                                  name="SMA20", line={"color": "#AB47BC", "width": 1}),
                      row=1, col=1)
    if show_sma50:
        fig.add_trace(go.Scatter(x=ohlcv.index, y=sma(close, 50),
                                  name="SMA50", line={"color": "#42A5F5", "width": 1.2}),
                      row=1, col=1)
    if show_sma200:
        fig.add_trace(go.Scatter(x=ohlcv.index, y=sma(close, 200),
                                  name="SMA200", line={"color": "#FF7043", "width": 1.5}),
                      row=1, col=1)

    # Bollinger
    if show_boll:
        mid, upper, lower = bollinger(close)
        fig.add_trace(go.Scatter(x=ohlcv.index, y=upper, name="BB Upper",
                                  line={"color": "#78909C", "width": 1, "dash": "dot"}), row=1, col=1)
        fig.add_trace(go.Scatter(x=ohlcv.index, y=lower, name="BB Lower",
                                  line={"color": "#78909C", "width": 1, "dash": "dot"},
                                  fill="tonexty", fillcolor="rgba(120,144,156,0.05)"), row=1, col=1)

    # 52w high/low lines
    h52 = p["high_52w"]
    l52 = p["low_52w"]
    fig.add_hline(y=h52, line_dash="dash", line_color="#4CAF50", line_width=0.8,
                  annotation_text=f"52W High ${h52:.0f}", annotation_position="right",
                  row=1, col=1)
    fig.add_hline(y=l52, line_dash="dash", line_color="#F44336", line_width=0.8,
                  annotation_text=f"52W Low ${l52:.0f}", annotation_position="right",
                  row=1, col=1)

    # Analyst mean target line
    tgt = targets.get(sel)
    if tgt and tgt.get("mean"):
        fig.add_hline(y=tgt["mean"], line_dash="dot", line_color="#00cf8d", line_width=1.2,
                      annotation_text=f"יעד אנליסטים ${tgt['mean']:.0f}",
                      annotation_position="right",
                      row=1, col=1)

    # ── Row 2: Volume ────────────────────────────────────────────────────────
    if "Volume" in ohlcv.columns:
        vol_colors = [
            COLOR["positive"] if c >= o else COLOR["negative"]
            for c, o in zip(ohlcv["Close"], ohlcv["Open"])
        ]
        fig.add_trace(go.Bar(
            x=ohlcv.index, y=ohlcv["Volume"],
            name=HE["volume_label"],
            marker_color=vol_colors,
            showlegend=False,
        ), row=2, col=1)

    # ── Row 3: RSI ───────────────────────────────────────────────────────────
    if show_rsi:
        rsi_series = compute_rsi(close)
        fig.add_trace(go.Scatter(
            x=ohlcv.index, y=rsi_series,
            name="RSI", line={"color": "#FF9800", "width": 1.2},
        ), row=3, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="#F44336",
                      line_width=0.8, row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="#4CAF50",
                      line_width=0.8, row=3, col=1)
        fig.update_yaxes(range=[0, 100], row=3, col=1)

    # ── Layout ───────────────────────────────────────────────────────────────
    name_str = TICKER_NAMES.get(sel, sel)
    fig.update_layout(
        title={"text": f"{HE['chart_title']}{sel} — {name_str}", "font_color": COLOR["text_dim"], "font_size": 13, "x": 0.5},
        height=600 + (150 if show_rsi else 0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#111111",
        font={"color": "#ffffff", "size": 10},
        xaxis_rangeslider_visible=False,
        legend={"orientation": "h", "y": 1.02, "x": 0},
        margin={"t": 40, "b": 20, "l": 10, "r": 80},
        hovermode="x unified",
    )
    fig.update_xaxes(
        gridcolor="#222222",
        showgrid=True,
        zeroline=False,
    )
    fig.update_yaxes(
        gridcolor="#222222",
        showgrid=True,
        zeroline=False,
    )
    st.plotly_chart(fig, use_container_width=True)
    color_legend([
        (COLOR["positive"],  "נר ירוק — סגירה גבוהה מפתיחה (עלייה)"),
        (COLOR["negative"],  "נר אדום — סגירה נמוכה מפתיחה (ירידה)"),
        ("#AB47BC",          "SMA 20 — ממוצע נע 20 יום"),
        ("#42A5F5",          "SMA 50 — ממוצע נע 50 יום"),
        ("#FF7043",          "SMA 200 — ממוצע נע 200 יום"),
        ("#78909C",          "Bollinger Bands"),
        ("#4CAF50",          "שיא 52 שבוע (52W High)"),
        ("#F44336",          "שפל 52 שבוע (52W Low)"),
        (COLOR["primary"],   "יעד מחיר ממוצע (אנליסטים)"),
        ("#FF9800",          "RSI(14)"),
    ])
    term_glossary([
        ("נר יפני (Candlestick)",
         "כל נר מייצג יום מסחר: גוף = טווח פתיחה-סגירה, שפם = שיא ושפל יומי."),
        ("SMA 20",
         "Simple Moving Average — ממוצע מחירי הסגירה של 20 הימים האחרונים. מגיב מהר לשינויים."),
        ("SMA 50",
         "ממוצע נע 50 יום — קו תמיכה/התנגדות לטווח בינוני. פופולרי אצל טריידרים מוסדיים."),
        ("SMA 200",
         "ממוצע נע 200 יום — מגמה ארוכת טווח. מחיר מעל SMA200 = מגמת עלייה, מתחת = ירידה."),
        ("Bollinger Bands",
         "שני פסים הרחוקים 2 סטיות תקן מ-SMA20. רוחב פס גדול = תנודתיות גבוהה. מחיר בפס עליון = overbought."),
        ("RSI(14)",
         "Relative Strength Index — מדד תנע בין 0–100. מעל 70 = קנוי-יתר (ירידה אפשרית), מתחת 30 = מכור-יתר (עלייה אפשרית)."),
        ("52W High / Low",
         "שיא ושפל המחיר ב-52 השבועות האחרונים — נקודות מפתח פסיכולוגיות לתמיכה/התנגדות."),
        ("יעד אנליסטים",
         "ממוצע יעדי המחיר של כל האנליסטים המכסים את הנייר — קו ירוק מקווקו."),
        ("Volume (נפח)",
         "מספר המניות שנסחרו ביום. נפח גבוה + תנועת מחיר חזקה = אישור מגמה."),
    ])

    # ── Relative strength vs VOO ─────────────────────────────────────────────
    if sel != "VOO":
        voo_p = prices.get("VOO")
        if voo_p and voo_p.get("history") is not None and p.get("history") is not None:
            rs = compute_relative_strength(p["history"], voo_p["history"])
            if not rs.empty:
                rs_fig = go.Figure(go.Scatter(
                    x=rs.index, y=rs,
                    name=HE["rel_strength"],
                    line={"color": COLOR["primary"], "width": 1.5},
                    fill="tozeroy",
                    fillcolor="rgba(0,207,141,0.08)",
                ))
                rs_fig.add_hline(y=100, line_dash="dash", line_color="#555", line_width=0.8)
                rs_fig.update_layout(
                    title={"text": f"{HE['rel_strength']} — {sel} vs VOO",
                           "font_color": COLOR["text_dim"], "font_size": 12, "x": 0.5},
                    height=180,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="#111111",
                    font={"color": "#ffffff", "size": 10},
                    margin={"t": 30, "b": 10, "l": 10, "r": 10},
                    showlegend=False,
                    hovermode="x",
                )
                rs_fig.update_xaxes(gridcolor="#222222")
                rs_fig.update_yaxes(gridcolor="#222222")
                st.plotly_chart(rs_fig, use_container_width=True)
                term_glossary([
                    ("חוזק יחסי vs VOO",
                     "הנייר מחושב מחדש ל-100 ביום הראשון בגרף. ערך מעל 100 = ביצועי יתר מול ה-S&P 500. מתחת 100 = פיגור."),
                    ("VOO",
                     "Vanguard S&P 500 ETF — מדד הייחוס לתיק זה, עוקב אחרי 500 החברות הגדולות בארה\"ב."),
                ], label="📖 מקרא — חוזק יחסי")
