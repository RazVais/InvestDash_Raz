"""Charts tab — 1-year candlestick with RSI, MAs, Bollinger, Volume, relative strength."""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from src.config import COLOR, HE, TICKER_NAMES
from src.data.prices import get_intraday_data
from src.data.technicals import bollinger, compute_relative_strength, compute_rsi, sma
from src.portfolio import all_tickers
from src.ui_helpers import color_legend, section_title, term_glossary

# ── Chart-building helpers ────────────────────────────────────────────────────

def _build_main_figure(ohlcv, sel, show_rsi):
    """Create the subplot figure with correct row heights."""
    n_rows = 2 + (1 if show_rsi else 0)
    row_h  = [0.65, 0.15] + ([0.20] if show_rsi else [])
    return make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        row_heights=row_h,
        vertical_spacing=0.03,
        subplot_titles=["", HE["volume_label"]] + ([HE["rsi_label"]] if show_rsi else []),
    )


def _add_candlestick(fig, ohlcv, sel):
    fig.add_trace(go.Candlestick(
        x=ohlcv.index,
        open=ohlcv["Open"], high=ohlcv["High"],
        low=ohlcv["Low"],   close=ohlcv["Close"],
        name=sel,
        increasing_line_color=COLOR["positive"],
        decreasing_line_color=COLOR["negative"],
        showlegend=False,
    ), row=1, col=1)


def _add_moving_averages(fig, ohlcv, close, show_sma20, show_sma50, show_sma200):
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


def _add_bollinger(fig, ohlcv, close):
    mid, upper, lower = bollinger(close)
    fig.add_trace(go.Scatter(x=ohlcv.index, y=upper, name="BB Upper",
                             line={"color": "#78909C", "width": 1, "dash": "dot"}),
                  row=1, col=1)
    fig.add_trace(go.Scatter(x=ohlcv.index, y=lower, name="BB Lower",
                             line={"color": "#78909C", "width": 1, "dash": "dot"},
                             fill="tonexty", fillcolor="rgba(120,144,156,0.05)"),
                  row=1, col=1)


def _add_reference_lines(fig, p, tgt):
    """Add 52W high/low and analyst target horizontal lines."""
    h52, l52 = p["high_52w"], p["low_52w"]
    fig.add_hline(y=h52, line_dash="dash", line_color="#4CAF50", line_width=0.8,
                  annotation_text=f"52W High ${h52:.0f}", annotation_position="right",
                  row=1, col=1)
    fig.add_hline(y=l52, line_dash="dash", line_color="#F44336", line_width=0.8,
                  annotation_text=f"52W Low ${l52:.0f}", annotation_position="right",
                  row=1, col=1)
    if tgt and tgt.get("mean"):
        fig.add_hline(y=tgt["mean"], line_dash="dot", line_color="#00cf8d", line_width=1.2,
                      annotation_text=f"יעד אנליסטים ${tgt['mean']:.0f}",
                      annotation_position="right", row=1, col=1)


def _add_volume(fig, ohlcv):
    if "Volume" not in ohlcv.columns:
        return
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


def _add_rsi(fig, ohlcv, close):
    rsi_series = compute_rsi(close)
    fig.add_trace(go.Scatter(
        x=ohlcv.index, y=rsi_series,
        name="RSI", line={"color": "#FF9800", "width": 1.2},
    ), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#F44336", line_width=0.8, row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#4CAF50", line_width=0.8, row=3, col=1)
    fig.update_yaxes(range=[0, 100], row=3, col=1)


def _apply_chart_layout(fig, sel, show_rsi):
    name_str = TICKER_NAMES.get(sel, sel)
    fig.update_layout(
        title={"text": f"{HE['chart_title']}{sel} — {name_str}",
               "font_color": COLOR["text_dim"], "font_size": 13, "x": 0.5},
        height=600 + (150 if show_rsi else 0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#111111",
        font={"color": "#ffffff", "size": 10},
        xaxis_rangeslider_visible=False,
        legend={"orientation": "h", "y": 1.02, "x": 0},
        margin={"t": 40, "b": 20, "l": 10, "r": 80},
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="#222222", showgrid=True, zeroline=False)
    fig.update_yaxes(gridcolor="#222222", showgrid=True, zeroline=False)


def _render_relative_strength(sel, p, prices):
    """Render the relative strength vs VOO chart below the main chart."""
    if sel == "VOO":
        return
    voo_p = prices.get("VOO")
    if not (voo_p and voo_p.get("history") is not None and p.get("history") is not None):
        return
    rs = compute_relative_strength(p["history"], voo_p["history"])
    if rs.empty:
        return
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


# ── Public entry point ────────────────────────────────────────────────────────

def render_charts(portfolio, data):
    prices  = data["prices"]
    targets = data["targets"]

    tickers = sorted(all_tickers(portfolio))
    if not tickers:
        st.info("הוסף ניירות ערך לתיק כדי לראות גרפים.")
        return

    # ── Controls row ─────────────────────────────────────────────────────
    st.markdown('<div dir="rtl">', unsafe_allow_html=True)
    col1, col2 = st.columns([2, 5])
    with col1:
        sel = st.selectbox("בחר מניה", tickers, key="chart_sel",
                           format_func=lambda t: f"{t} — {TICKER_NAMES.get(t, '')}")
    with col2:
        c1, c2, c3, c4, c5 = st.columns(5)
        show_sma20  = c1.checkbox("SMA 20",    value=False, key="ch_sma20")
        show_sma50  = c2.checkbox("SMA 50",    value=True,  key="ch_sma50")
        show_sma200 = c3.checkbox("SMA 200",   value=True,  key="ch_sma200")
        show_boll   = c4.checkbox("Bollinger", value=False, key="ch_boll")
        show_rsi    = c5.checkbox("RSI",       value=True,  key="ch_rsi")
    st.markdown('</div>', unsafe_allow_html=True)

    p = prices.get(sel)
    if not p or p.get("ohlcv") is None or p["ohlcv"].empty:
        err    = prices.get("__errors__", {}).get(sel, "")
        detail = f" — {err}" if err else ""
        st.warning(f"אין נתוני OHLCV עבור {sel}{detail}. נסה לרענן (כפתור בסרגל הצד).")
        return

    ohlcv = p["ohlcv"]
    close = ohlcv["Close"]
    tgt   = targets.get(sel)

    # ── Build figure ─────────────────────────────────────────────────────
    fig = _build_main_figure(ohlcv, sel, show_rsi)
    _add_candlestick(fig, ohlcv, sel)
    _add_moving_averages(fig, ohlcv, close, show_sma20, show_sma50, show_sma200)
    if show_boll:
        _add_bollinger(fig, ohlcv, close)
    _add_reference_lines(fig, p, tgt)
    _add_volume(fig, ohlcv)
    if show_rsi:
        _add_rsi(fig, ohlcv, close)
    _apply_chart_layout(fig, sel, show_rsi)

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

    _render_relative_strength(sel, p, prices)
    _render_orb_chart(sel)


# ── ORB: Opening Range Breakout (Python / Plotly) ─────────────────────────────

def _compute_orb(df, vol_mult=1.5):
    """
    Compute ORB signals on an intraday DataFrame (America/New_York tz index).

    Opening range  = 09:30–10:00 ET
    Trade window   = 09:30–11:30 ET (first 2 hours)

    Five conditions must all be true (evaluated after the OR window closes):
      1. Close > OR high
      2. Volume >= vol_mult × average OR volume
      3. Close > session VWAP
      4. Bar is before 11:30 ET
      5. Close >= low + (high - low) * 0.5  (top 50% of bar range)

    Signal fires once per breakout episode; resets when close < OR high.

    Adds columns: vwap, entry_signal (bool), active_bg (bool).
    Returns (df_enriched, or_high, or_avg_vol) — or_high/or_avg_vol are None
    if the OR window has not yet closed.
    """
    from datetime import time as _dtime

    OR_START = _dtime(9, 30)
    OR_END   = _dtime(10, 0)
    TW_END   = _dtime(11, 30)

    df = df.copy()
    bar_times = df.index.time

    # ── Opening range ────────────────────────────────────────────────────────
    or_mask = (bar_times >= OR_START) & (bar_times < OR_END)
    or_bars = df[or_mask]

    if or_bars.empty:
        df["vwap"]         = float("nan")
        df["entry_signal"] = False
        df["active_bg"]    = False
        return df, None, None

    or_high    = float(or_bars["High"].max())
    or_avg_vol = float(or_bars["Volume"].mean())

    # ── Session VWAP (cumulative from first bar) ─────────────────────────────
    hlc3       = (df["High"] + df["Low"] + df["Close"]) / 3.0
    cum_vol    = df["Volume"].cumsum()
    cum_tp_vol = (hlc3 * df["Volume"]).cumsum()
    df["vwap"] = cum_tp_vol / cum_vol.replace(0, float("nan"))

    # ── Episode-based signal loop (stateful; intraday data is small ≤ 390 rows)
    entry_signal = [False] * len(df)
    active_bg    = [False] * len(df)
    in_episode   = False

    for i, (ts, row) in enumerate(df.iterrows()):
        t = ts.time()
        if t < OR_END:          # OR still forming — no signals yet
            continue

        # Reset episode when price retreats below OR high
        if row["Close"] < or_high:
            in_episode = False

        # Evaluate all five conditions
        bar_rng   = row["High"] - row["Low"]
        all_conds = (
            t < TW_END
            and row["Close"] > or_high                              # ① price break
            and row["Volume"] >= or_avg_vol * vol_mult              # ② volume surge
            and row["Close"] > row["vwap"]                          # ③ above VWAP
            and bar_rng > 0                                         # ④ non-doji guard
            and row["Close"] >= row["Low"] + bar_rng * 0.5         # ⑤ top-half close
        )

        if all_conds:
            active_bg[i] = True
            if not in_episode:
                entry_signal[i] = True     # one-shot entry
                in_episode = True

    df["entry_signal"] = entry_signal
    df["active_bg"]    = active_bg
    return df, or_high, or_avg_vol


def _build_orb_figure(df, or_high, or_avg_vol, sel, vol_mult):
    """Build intraday Plotly ORB chart: candlestick + OR high + VWAP + signals."""
    bar_td = (df.index[1] - df.index[0]) if len(df) > 1 else pd.Timedelta(minutes=5)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.72, 0.28],
        vertical_spacing=0.03,
    )

    # ── Candlestick ──────────────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name=sel, showlegend=False,
        increasing_line_color=COLOR["positive"],
        decreasing_line_color=COLOR["negative"],
        increasing_fillcolor=COLOR["positive"],
        decreasing_fillcolor=COLOR["negative"],
    ), row=1, col=1)

    # ── VWAP ─────────────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=df.index, y=df["vwap"],
        name="VWAP", mode="lines",
        line={"color": "cyan", "width": 1.5, "dash": "dot"},
    ), row=1, col=1)

    # ── OR high horizontal reference line ────────────────────────────────────
    if or_high is not None:
        fig.add_hline(
            y=or_high,
            line_color="orange", line_dash="dash", line_width=2,
            annotation_text=f"OR High  ${or_high:.2f}",
            annotation_font_color="orange",
            annotation_position="top right",
            row=1, col=1,
        )

    # ── Entry signal triangles (one per episode) ─────────────────────────────
    sig = df[df["entry_signal"]]
    if not sig.empty:
        fig.add_trace(go.Scatter(
            x=sig.index,
            y=sig["Low"] * 0.9975,          # slightly below bar low
            mode="markers+text",
            marker={"symbol": "triangle-up", "size": 14, "color": "lime"},
            text=["ORB"] * len(sig),
            textposition="bottom center",
            textfont={"color": "lime", "size": 10},
            name="ORB Entry",
        ), row=1, col=1)

    # ── Active-signal background (group consecutive active bars into vrects) ─
    in_bg    = False
    bg_start = None
    for i, active in enumerate(df["active_bg"].values):
        if active and not in_bg:
            bg_start = df.index[i]
            in_bg    = True
        elif not active and in_bg:
            fig.add_vrect(x0=bg_start, x1=df.index[i],
                          fillcolor="rgba(0,200,0,0.10)", layer="below", line_width=0)
            in_bg = False
    if in_bg and bg_start is not None:
        fig.add_vrect(x0=bg_start, x1=df.index[-1] + bar_td,
                      fillcolor="rgba(0,200,0,0.10)", layer="below", line_width=0)

    # ── Volume bars ──────────────────────────────────────────────────────────
    vol_colors = [
        COLOR["positive"] if c >= o else COLOR["negative"]
        for c, o in zip(df["Close"], df["Open"])
    ]
    fig.add_trace(go.Bar(
        x=df.index, y=df["Volume"],
        marker_color=vol_colors,
        name="Volume", showlegend=False,
    ), row=2, col=1)

    # OR average-volume threshold line in the volume panel
    if or_avg_vol is not None:
        fig.add_hline(
            y=or_avg_vol * vol_mult,
            line_color="rgba(255,165,0,0.7)", line_dash="dot", line_width=1,
            annotation_text=f"{vol_mult:.1f}× OR avg vol",
            annotation_font_color="orange",
            annotation_position="top right",
            row=2, col=1,
        )

    # ── Layout ───────────────────────────────────────────────────────────────
    day_str = df.index[-1].strftime("%Y-%m-%d") if len(df) > 0 else ""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        height=530,
        margin={"l": 0, "r": 0, "t": 36, "b": 0},
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        title={
            "text": f"{sel} — ORB Intraday ({day_str})",
            "font": {"color": COLOR["primary"], "size": 13},
            "x": 0,
        },
    )
    fig.update_xaxes(gridcolor="#2a2a2a", zeroline=False)
    fig.update_yaxes(gridcolor="#2a2a2a", zeroline=False)
    fig.update_yaxes(tickprefix="$", row=1, col=1)
    return fig


def _render_orb_chart(sel):
    """Render the ORB intraday chart section at the bottom of the charts tab."""
    st.divider()
    section_title(
        "⏱ ORB — Opening Range Breakout",
        "פריצת טווח פתיחה תוך-יומי | 09:30–10:00 ET | נתוני intraday בזמן אמת",
    )

    st.markdown(
        """
        <div dir="rtl" style="font-size:13px;color:#cccccc;margin-bottom:10px;line-height:1.7">
        האות מופיע כאשר <b>כל חמשת התנאים</b> מתקיימים יחד:<br>
        <span style="color:#aaa;font-size:12px">
        ① סגירה מעל OR High &nbsp;|&nbsp;
        ② נפח ≥ מכפיל × ממוצע OR &nbsp;|&nbsp;
        ③ מעל VWAP &nbsp;|&nbsp;
        ④ לפני 11:30 ET &nbsp;|&nbsp;
        ⑤ סגירה במחצית העליונה של הנר
        </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Controls ─────────────────────────────────────────────────────────────
    c1, c2 = st.columns([1, 3])
    with c1:
        interval = st.selectbox(
            "מסגרת זמן", ["1m", "2m", "5m", "15m"], index=2, key="orb_interval",
        )
    with c2:
        vol_mult = st.slider(
            "מכפיל נפח מינימלי (Volume Multiplier)",
            min_value=1.0, max_value=3.0, value=1.5, step=0.1, key="orb_vol_mult",
        )

    # ── Fetch intraday data ───────────────────────────────────────────────────
    df = get_intraday_data(sel, interval=interval)
    if df is None or df.empty:
        st.warning(
            f"אין נתוני intraday עבור {sel}. "
            "ייתכן שהשוק סגור, הסשן טרם התחיל, או שהנייר אינו נסחר בארה\"ב."
        )
        return

    # ── Compute signals ───────────────────────────────────────────────────────
    df_orb, or_high, or_avg_vol = _compute_orb(df, vol_mult=vol_mult)

    if or_high is None:
        st.info("טווח הפתיחה (09:30–10:00 ET) טרם הסתיים — הגרף יעודכן לאחר 10:00 ET.")

    # ── Chart ─────────────────────────────────────────────────────────────────
    fig = _build_orb_figure(df_orb, or_high, or_avg_vol, sel, vol_mult)
    st.plotly_chart(fig, use_container_width=True)

    # ── Signal summary ────────────────────────────────────────────────────────
    if or_high is not None:
        entries = df_orb[df_orb["entry_signal"]]
        if not entries.empty:
            st.success(f"✅ {len(entries)} אות ORB היום עבור {sel}")
            for ts, row in entries.iterrows():
                st.markdown(
                    f'<div dir="rtl" style="font-size:12px;color:#aaa;margin:2px 0">'
                    f'🟢 {ts.strftime("%H:%M ET")} — '
                    f'מחיר: <b>${row["Close"]:.2f}</b> | '
                    f'נפח: <b>{int(row["Volume"]):,}</b> '
                    f'({row["Volume"] / or_avg_vol:.1f}× OR avg)</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("אין אותות ORB עד כה היום.")

    color_legend([
        ("orange",  "OR High — גובה טווח הפתיחה (09:30–10:00 ET)"),
        ("cyan",    "VWAP — ממוצע משוקלל נפח (מצטבר מתחילת הסשן)"),
        ("#00FF00", "ORB ▲ — נקודת כניסה (כל 5 תנאים מתקיימים)"),
    ])
    term_glossary([
        ("Opening Range (OR)",
         "הטווח שנוצר בין 09:30 ל-10:00 ET — 30 דקות הפתיחה. ה-OR High הוא המחיר המקסימלי בחלון זה."),
        ("VWAP",
         "Volume-Weighted Average Price — מחיר ממוצע משוקלל בנפח המסחר. מחושב מצטבר מתחילת הסשן."),
        ("מכפיל נפח",
         "נפח נר הפריצה חייב לעלות על X פעמים ממוצע נפח נרות ה-OR. מאמת שהפריצה מלווה בביקוש אמיתי."),
        ("מחצית עליונה",
         "הסגירה גבוהה ממחצית הטווח של הנר (High-Low/2). מאשרת שלחץ הקנייה נשאר חזק עד סגירת הנר."),
        ("אות חד-פעמי",
         "פעם אחת לכל פריצה. מתאפס אוטומטית כשהמחיר סוגר מתחת ל-OR High, ומאפשר כניסה חוזרת."),
    ])
