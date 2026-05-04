"""Charts tab — 1-year candlestick with RSI, MAs, Bollinger, Volume, relative strength."""


import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from src.config import (
    COLOR,
    HE,
    RS_BENCHMARK_LABELS,
    TICKER_BENCHMARK_DEFAULT,
    TICKER_NAMES,
    is_tase_numeric,
)
from src.data.prices import get_intraday_data
from src.data.technicals import bollinger, compute_macd, compute_relative_strength, compute_rsi, sma
from src.portfolio import all_tickers
from src.ui_helpers import color_legend, section_title, term_glossary

# ── Chart-building helpers ────────────────────────────────────────────────────

def _build_main_figure(ohlcv, sel, show_rsi, show_macd=False):
    """Create the subplot figure with correct row heights."""
    extra_h = ([0.20] if show_rsi else []) + ([0.20] if show_macd else [])
    extra_t = ([HE["rsi_label"]] if show_rsi else []) + (["MACD (12/26/9)"] if show_macd else [])
    n_rows  = 2 + len(extra_h)
    return make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        row_heights=[0.65, 0.15] + extra_h,
        vertical_spacing=0.03,
        subplot_titles=["", HE["volume_label"]] + extra_t,
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


def _add_rsi(fig, ohlcv, close, row=3):
    rsi_series = compute_rsi(close)
    fig.add_trace(go.Scatter(
        x=ohlcv.index, y=rsi_series,
        name="RSI", line={"color": "#FF9800", "width": 1.2},
    ), row=row, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#F44336", line_width=0.8, row=row, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#4CAF50", line_width=0.8, row=row, col=1)
    fig.update_yaxes(range=[0, 100], row=row, col=1)


def _add_macd(fig, ohlcv, close, row):
    """MACD panel: histogram (green/red) + MACD line + Signal line + zero reference."""
    macd_line, signal_line, histogram = compute_macd(close)
    bar_colors = [COLOR["positive"] if v >= 0 else COLOR["negative"] for v in histogram]
    fig.add_trace(go.Bar(
        x=ohlcv.index, y=histogram,
        name="MACD Histogram",
        marker_color=bar_colors,
        opacity=0.7,
        showlegend=True,
    ), row=row, col=1)
    fig.add_trace(go.Scatter(
        x=ohlcv.index, y=macd_line,
        name="MACD",
        line={"color": "#2196F3", "width": 1.2},
    ), row=row, col=1)
    fig.add_trace(go.Scatter(
        x=ohlcv.index, y=signal_line,
        name="Signal",
        line={"color": "#FF9800", "width": 1.2, "dash": "dot"},
    ), row=row, col=1)
    fig.add_hline(y=0, line_dash="solid", line_color="#444444", line_width=0.8, row=row, col=1)


def _apply_chart_layout(fig, sel, show_rsi, show_macd=False):
    name_str = TICKER_NAMES.get(sel, sel)
    n_extra  = (1 if show_rsi else 0) + (1 if show_macd else 0)
    fig.update_layout(
        title={"text": f"{HE['chart_title']}{sel} — {name_str}",
               "font_color": COLOR["text_dim"], "font_size": 13, "x": 0.5},
        height=600 + n_extra * 150,
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


@st.cache_data(ttl=1800)
def _fetch_benchmark_history(sym):
    # type: (str) -> Optional[pd.Series]
    """Fetch 1-year close for a benchmark ETF not in the portfolio (cached 30 min)."""
    import yfinance as yf
    try:
        df = yf.Ticker(sym).history(period="1y", auto_adjust=True)
        if df is not None and not df.empty:
            close = df["Close"].dropna()
            if hasattr(close.index, "tz") and close.index.tz is not None:
                close.index = close.index.tz_localize(None)
            return close if not close.empty else None
    except Exception:
        pass
    return None


def _render_relative_strength(sel, p, prices):
    """RS chart with benchmark selector and dual-line view (primary benchmark + VOO context)."""
    if sel == "VOO" or is_tase_numeric(sel):
        return
    if p.get("history") is None:
        return

    ticker_history = p["history"]

    # Benchmark selector — auto-defaults to the right sector ETF per ticker
    bench_options = list(RS_BENCHMARK_LABELS.keys())
    default_bench = TICKER_BENCHMARK_DEFAULT.get(sel, "VOO")
    default_idx   = bench_options.index(default_bench) if default_bench in bench_options else 0

    st.markdown('<div dir="rtl">', unsafe_allow_html=True)
    selected_bench = st.selectbox(
        HE["rs_benchmark_sel"],
        options=bench_options,
        index=default_idx,
        format_func=lambda s: RS_BENCHMARK_LABELS.get(s, s),
        key=f"rs_bench_{sel}",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # Fetch primary benchmark — prefer already-loaded prices dict (zero cost for VOO)
    bench_close = None
    if selected_bench in prices and prices[selected_bench]:
        bench_close = prices[selected_bench].get("history")
    if bench_close is None or (hasattr(bench_close, "empty") and bench_close.empty):
        bench_close = _fetch_benchmark_history(selected_bench)
    if bench_close is None:
        st.caption(f"לא ניתן לטעון נתונים עבור {selected_bench}.")
        return

    rs_primary = compute_relative_strength(ticker_history, bench_close)
    if rs_primary.empty:
        st.caption(f"אין מספיק נתונים להשוואה מול {selected_bench}.")
        return

    # VOO context line (skip when VOO is already the selected benchmark)
    rs_voo = None
    if selected_bench != "VOO":
        voo_h = None
        if "VOO" in prices and prices["VOO"]:
            voo_h = prices["VOO"].get("history")
        if voo_h is None:
            voo_h = _fetch_benchmark_history("VOO")
        if voo_h is not None:
            rs_tmp = compute_relative_strength(ticker_history, voo_h)
            rs_voo = rs_tmp if not rs_tmp.empty else None

    rs_fig = go.Figure()
    rs_fig.add_trace(go.Scatter(
        x=rs_primary.index, y=rs_primary,
        name=f"{sel} vs {selected_bench}",
        line={"color": COLOR["primary"], "width": 2},
        fill="tozeroy",
        fillcolor="rgba(0,207,141,0.08)",
    ))
    if rs_voo is not None:
        rs_fig.add_trace(go.Scatter(
            x=rs_voo.index, y=rs_voo,
            name=f"{sel} {HE['rs_vs_voo_ctx']}",
            line={"color": "#9E9E9E", "width": 1.2, "dash": "dot"},
        ))
    rs_fig.add_hline(y=100, line_dash="dash", line_color="#555", line_width=0.8)
    rs_fig.update_layout(
        title={"text": f"חוזק יחסי — {sel} vs {selected_bench}",
               "font_color": COLOR["text_dim"], "font_size": 12, "x": 0.5},
        height=200,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#111111",
        font={"color": "#ffffff", "size": 10},
        margin={"t": 30, "b": 10, "l": 10, "r": 10},
        showlegend=(rs_voo is not None),
        legend={"orientation": "h", "y": 1.08, "font": {"size": 9}},
        hovermode="x unified",
    )
    rs_fig.update_xaxes(gridcolor="#222222")
    rs_fig.update_yaxes(gridcolor="#222222")
    st.plotly_chart(rs_fig, use_container_width=True)

    glossary = [
        ("חוזק יחסי",
         "הנייר מחושב מחדש ל-100 ביום הראשון. ערך מעל 100 = ביצועי יתר מול הבנצ'מרק. מתחת 100 = פיגור."),
        (RS_BENCHMARK_LABELS.get(selected_bench, selected_bench),
         f"הבנצ'מרק הנבחר ({selected_bench})."),
    ]
    if rs_voo is not None:
        glossary.append(("VOO (הקשר)", "קו מקווקו אפור — השוואה נוספת מול S&P 500 הרחב."))
    term_glossary(glossary, label="📖 מקרא — חוזק יחסי")


# ── Per-ticker analyst panel (session / timing / consensus) ──────────────────

def _render_per_ticker_analyst(sel, portfolio, data, td_str, claude_api_key):
    from src.tabs.analysis_tab import _render_ticker_section
    from src.tabs.analysts_tab import (
        _build_session_prompt,
        _build_timing_data_str,
        _compute_buy_signal,
        _render_consensus_table,
        _render_score_bar,
        _render_signal_chips,
        _render_target_chart,
        _render_timing_ai_card,
        _run_buy_timing_eval,
        _run_session_analysis,
    )
    from src.tabs.news_tab import _render_articles, _render_company_brief, _render_today_summary
    from src.tabs.red_flags import get_all_flag_statuses

    prices       = data["prices"]
    targets      = data["targets"]
    consensus    = data["consensus"]
    fundamentals = data.get("fundamentals", {})
    news         = data.get("news", {})
    tickers      = sorted(all_tickers(portfolio))

    st.divider()
    st.markdown(
        f'<div dir="rtl" style="font-size:14px;font-weight:700;color:#00cf8d;margin-bottom:8px">'
        f'📊 ניתוח — {sel}</div>',
        unsafe_allow_html=True,
    )

    tab_session, tab_timing, tab_consensus, tab_analysis, tab_news = st.tabs([
        "📋 ניתוח יומי", "⏰ תזמון קנייה", "👥 קונצנזוס", "🔬 5 פילטרים", "📰 חדשות"
    ])

    with tab_session:
        if not claude_api_key:
            st.caption("🤖 הוסף CLAUDE_API_KEY לקובץ secrets.toml לקבלת ניתוח סשן AI")
        else:
            prompt_body = _build_session_prompt(tickers, data)
            tickers_key = ",".join(tickers)
            with st.spinner("🤖 AI מנתח את הסשן..."):
                result = _run_session_analysis(tickers_key, prompt_body, td_str, claude_api_key)
            if "_error" in result:
                st.warning(f"⚠️ {result['_error']}")
            else:
                stocks = result.get("stocks") or []
                entry  = next((s for s in stocks if s.get("ticker") == sel), None)
                if entry:
                    priority = entry.get("priority", "Low")
                    P_COLOR  = {"High": "#00cf8d", "Medium": "#ff9800", "Low": "#888888"}
                    P_HE     = {"High": "גבוהה", "Medium": "בינונית", "Low": "נמוכה"}
                    pc = P_COLOR.get(priority, "#888888")
                    st.markdown(
                        f'<div dir="rtl" style="background:#0d1117;border:1px solid #1f2937;'
                        f'border-radius:8px;padding:14px 16px;font-size:12px;line-height:2.0">'
                        f'<div style="font-size:13px;font-weight:700;color:#fff;margin-bottom:8px">'
                        f'{sel}&nbsp;<span style="color:{pc};font-size:11px">● עדיפות {P_HE.get(priority, priority)}</span></div>'
                        f'<div><span style="color:#888">קטליזטור:</span> {entry.get("catalyst", "—")}</div>'
                        f'<div><span style="color:#888">תנועת מחיר:</span> {entry.get("premarket", "—")}</div>'
                        f'<div style="font-family:monospace"><span style="color:#888">מפתחות:</span> {entry.get("levels", "—")}</div>'
                        f'<div><span style="color:#888">סטאפ:</span> {entry.get("setup", "—")}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    ctx = result.get("market_context", "")
                    if ctx:
                        st.caption(f"🌍 {ctx}")
                else:
                    st.caption(f"אין נתוני סשן עבור {sel}")

    with tab_timing:
        all_flags = get_all_flag_statuses(portfolio, data)
        sig = _compute_buy_signal(sel, data, all_flags)
        _render_score_bar(sig["score"], f"ציון תזמון קנייה — {sel}")
        _render_signal_chips(sig)
        if claude_api_key:
            data_str = _build_timing_data_str(sel, sig)
            with st.spinner("🤖 AI מעריך תזמון..."):
                verdict = _run_buy_timing_eval(sel, data_str, td_str, claude_api_key)
            _render_timing_ai_card(verdict, sel, data_str, td_str, claude_api_key)

    with tab_consensus:
        _render_consensus_table([sel], consensus, prices)
        _render_target_chart([sel], prices, targets)

    with tab_analysis:
        name = TICKER_NAMES.get(sel) or (prices.get(sel) or {}).get("name", sel)
        _render_ticker_section(
            ticker=sel,
            name=name,
            theme="",
            p=prices.get(sel),
            con=consensus.get(sel) or {},
            tgt=targets.get(sel),
            fun=fundamentals.get(sel) or None,
            td_str=td_str,
            claude_api_key=claude_api_key,
            expanded=True,
        )

    with tab_news:
        _render_today_summary(sel, news, td_str, claude_api_key)
        st.divider()
        _render_company_brief(sel, td_str)
        st.divider()
        _render_articles(sel, news)


# ── Public entry point ────────────────────────────────────────────────────────

def render_charts(portfolio, data, td_str="", claude_api_key=""):
    prices  = data["prices"]
    targets = data["targets"]

    tickers = sorted(all_tickers(portfolio))
    if not tickers:
        st.info("הוסף ניירות ערך לתיק כדי לראות גרפים.")
        return

    # ── Session state: persist ticker selection across reruns ─────────────
    if "chart_sel" not in st.session_state or st.session_state.chart_sel not in tickers:
        st.session_state.chart_sel = tickers[0]

    # Compact style for ticker nav buttons inside the scrollable container
    st.markdown(
        """<style>
        [data-testid="stVerticalBlockBorderWrapper"] button {
            font-size: 11px !important;
            padding: 2px 6px !important;
            min-height: 28px !important;
            height: auto !important;
            line-height: 1.3 !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"] button p {
            white-space: pre-line !important;
            font-size: 11px !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )

    nav_open = not st.session_state.get("chart_nav_collapsed", False)
    main_col, right_col = st.columns([4, 1]) if nav_open else st.columns([19, 1])

    sel = st.session_state.chart_sel

    with right_col:
        # ── Collapse / expand toggle ──────────────────────────────────────
        toggle_icon = "▶" if nav_open else "◀"
        if st.button(toggle_icon, key="chart_nav_toggle",
                     help="הסתר/הצג רשימת ניירות ערך", use_container_width=True):
            st.session_state.chart_nav_collapsed = nav_open
            st.rerun()

        if nav_open:
            sel_name = TICKER_NAMES.get(sel) or (prices.get(sel) or {}).get("name", "")
            st.markdown(
                f'<div style="font-size:10px;font-weight:700;color:#888;margin-bottom:2px">ניירות ערך</div>'
                f'<div style="font-size:10px;color:#00cf8d;margin-bottom:6px;line-height:1.4">'
                f'{sel_name or sel}</div>',
                unsafe_allow_html=True,
            )
            with st.container(height=840, border=False):
                for t in tickers:
                    btn_type = "primary" if st.session_state.chart_sel == t else "secondary"
                    name = TICKER_NAMES.get(t) or (prices.get(t) or {}).get("name", "")
                    if name and len(name) > 18:
                        name = name[:17] + "…"
                    label = f"{t}\n{name}" if name else t
                    if st.button(label, key=f"chart_btn_{t}", type=btn_type,
                                 use_container_width=True):
                        st.session_state.chart_sel = t
                        st.rerun()

    with main_col:
        # ── Indicator checkboxes ──────────────────────────────────────────
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        show_sma20  = c1.checkbox("SMA 20",    value=False, key="ch_sma20")
        show_sma50  = c2.checkbox("SMA 50",    value=True,  key="ch_sma50")
        show_sma200 = c3.checkbox("SMA 200",   value=True,  key="ch_sma200")
        show_boll   = c4.checkbox("Bollinger", value=False, key="ch_boll")
        show_rsi    = c5.checkbox("RSI",       value=True,  key="ch_rsi")
        show_macd   = c6.checkbox("MACD",      value=False, key="ch_macd")

        p = prices.get(sel)
        if not p or p.get("ohlcv") is None or p["ohlcv"].empty:
            err    = prices.get("__errors__", {}).get(sel, "")
            detail = f" — {err}" if err else ""
            st.warning(f"אין נתוני OHLCV עבור {sel}{detail}. נסה לרענן (כפתור בסרגל הצד).")
            return

        ohlcv = p["ohlcv"]
        close = ohlcv["Close"]
        tgt   = targets.get(sel)

        # ── Build figure ──────────────────────────────────────────────────
        fig = _build_main_figure(ohlcv, sel, show_rsi, show_macd)
        _add_candlestick(fig, ohlcv, sel)
        _add_moving_averages(fig, ohlcv, close, show_sma20, show_sma50, show_sma200)
        if show_boll:
            _add_bollinger(fig, ohlcv, close)
        _add_reference_lines(fig, p, tgt)
        _add_volume(fig, ohlcv)
        next_row = 3
        if show_rsi:
            _add_rsi(fig, ohlcv, close, row=next_row)
            next_row += 1
        if show_macd:
            _add_macd(fig, ohlcv, close, row=next_row)
        _apply_chart_layout(fig, sel, show_rsi, show_macd)

        st.plotly_chart(fig, use_container_width=True)
        legend_items = [
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
        ]
        if show_macd:
            legend_items += [
                ("#2196F3",         "MACD Line (EMA12 - EMA26)"),
                ("#FF9800",         "Signal Line (EMA9 של MACD)"),
                (COLOR["positive"], "MACD Histogram חיובי (מומנטום עולה)"),
                (COLOR["negative"], "MACD Histogram שלילי (מומנטום יורד)"),
            ]
        color_legend(legend_items)
        glossary_terms = [
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
        ]
        if show_macd:
            glossary_terms.append((
                "MACD (12/26/9)",
                "Moving Average Convergence Divergence — EMA12 פחות EMA26. "
                "חציית ה-Signal Line מלמטה = מומנטום חיובי (אות קנייה). "
                "היסטוגרם ירוק = תנע עולה, אדום = יורד.",
            ))
        term_glossary(glossary_terms)

        _render_relative_strength(sel, p, prices)
        _render_orb_chart(sel)
        st.divider()
        _render_monte_carlo_section(sel, prices, targets)
        st.divider()
        _render_trailing_stop_section(sel, prices)

        if not is_tase_numeric(sel):
            _render_per_ticker_analyst(sel, portfolio, data, td_str, claude_api_key)


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


# ── Monte Carlo simulation ────────────────────────────────────────────────────

def _run_mc(close_series, current_price, n_sims, n_days):
    """GBM Monte Carlo simulation. Returns (n_sims, n_days+1) price-path array."""
    log_ret = np.log(close_series / close_series.shift(1)).dropna()
    mu      = log_ret.mean()
    sigma   = log_ret.std()
    Z       = np.random.standard_normal((n_sims, n_days))
    paths   = np.empty((n_sims, n_days + 1))
    paths[:, 0] = current_price
    for t in range(1, n_days + 1):
        paths[:, t] = paths[:, t - 1] * np.exp(
            (mu - 0.5 * sigma ** 2) + sigma * Z[:, t - 1]
        )
    return paths


def _build_mc_figure(close_series, paths, ticker, n_days,
                     analyst_target=None, show_sample_paths=True):
    """Plotly fan chart: historical close + percentile bands + optional sample paths."""
    last_date    = close_series.index[-1]
    future_dates = pd.bdate_range(
        start=last_date + pd.Timedelta(days=1), periods=n_days
    )

    # Percentiles at each future step (columns 1..n_days)
    pcts = {p: np.percentile(paths[:, 1:], p, axis=0) for p in [5, 25, 50, 75, 95]}

    fig = go.Figure()

    # Historical close (grey)
    fig.add_trace(go.Scatter(
        x=close_series.index, y=close_series,
        name="היסטוריה",
        line={"color": "#888888", "width": 1.5},
        hovertemplate="%{y:.2f}<extra>היסטוריה</extra>",
    ))

    # Outer band: P5 (lower) → P95 (upper), fill="tonexty" fills P5→P95
    fig.add_trace(go.Scatter(
        x=future_dates, y=pcts[5],
        name="P5 (גרוע)",
        line={"color": "#4CAF50", "width": 0.5, "dash": "dot"},
        hovertemplate="%{y:.2f}<extra>5%</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=future_dates, y=pcts[95],
        name="P95 (מיטבי)",
        line={"color": "#4CAF50", "width": 0.5, "dash": "dot"},
        fill="tonexty",
        fillcolor="rgba(76,175,80,0.10)",
        hovertemplate="%{y:.2f}<extra>95%</extra>",
    ))

    # Inner band: P25 → P75
    fig.add_trace(go.Scatter(
        x=future_dates, y=pcts[25],
        name="P25",
        line={"color": "#4CAF50", "width": 0.8},
        hovertemplate="%{y:.2f}<extra>25%</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=future_dates, y=pcts[75],
        name="P75",
        line={"color": "#4CAF50", "width": 0.8},
        fill="tonexty",
        fillcolor="rgba(76,175,80,0.22)",
        hovertemplate="%{y:.2f}<extra>75%</extra>",
    ))

    # Median (P50)
    fig.add_trace(go.Scatter(
        x=future_dates, y=pcts[50],
        name="חציון (P50)",
        line={"color": "#00cf8d", "width": 2, "dash": "dash"},
        hovertemplate="%{y:.2f}<extra>חציון</extra>",
    ))

    # Sample paths (thin, semi-transparent)
    if show_sample_paths:
        sample_idx = np.random.choice(
            paths.shape[0], size=min(8, paths.shape[0]), replace=False
        )
        for i in sample_idx:
            fig.add_trace(go.Scatter(
                x=future_dates, y=paths[i, 1:],
                mode="lines",
                line={"color": "rgba(200,200,200,0.18)", "width": 0.8},
                showlegend=False,
                hoverinfo="skip",
            ))

    # Analyst target
    if analyst_target:
        fig.add_hline(
            y=analyst_target,
            line_color="#FF9800", line_dash="dot", line_width=1.5,
            annotation_text=f"יעד אנליסטים ${analyst_target:.0f}",
            annotation_font_color="#FF9800",
            annotation_position="top right",
        )

    # Today divider — add_shape avoids plotly's _mean(str) crash on datetime axes
    fig.add_shape(
        type="line",
        x0=last_date, x1=last_date,
        y0=0, y1=1,
        xref="x", yref="paper",
        line={"color": "#555555", "width": 1.5, "dash": "dash"},
    )
    fig.add_annotation(
        x=last_date, y=1, yref="paper",
        text="היום",
        showarrow=False,
        font={"color": "#888888", "size": 10},
        xanchor="right",
        yanchor="top",
    )

    name_str = TICKER_NAMES.get(ticker, ticker)
    fig.update_layout(
        title={
            "text": f"מונטה קארלו — {ticker} ({name_str})",
            "font": {"color": COLOR["text_dim"], "size": 13},
            "x": 0.5,
        },
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font={"color": "#ffffff", "size": 10},
        height=420,
        margin={"t": 40, "b": 20, "l": 10, "r": 80},
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.03, "x": 0},
    )
    fig.update_xaxes(gridcolor="#2a2a2a", zeroline=False)
    fig.update_yaxes(gridcolor="#2a2a2a", zeroline=False, tickprefix="$")
    return fig


def _render_mc_stats(paths, current_price):
    """5-card KPI strip: profit probability, median, P5, P95, VaR."""
    final      = paths[:, -1]
    p_profit   = float((final > current_price).mean() * 100)
    median     = float(np.median(final))
    p5         = float(np.percentile(final, 5))
    p95        = float(np.percentile(final, 95))
    max_price  = float(np.max(final))
    var5       = (p5 - current_price) / current_price * 100
    max_profit = (max_price - current_price) / current_price * 100

    def _card(col, label, value, color="#ffffff", sub=""):
        sub_html = f"<div style='font-size:10px;color:#666;margin-top:2px'>{sub}</div>" if sub else ""
        col.markdown(
            f'<div style="background:#1a1a2e;border:1px solid #333;border-radius:8px;padding:12px 10px;text-align:center">'
            f'<div style="font-size:11px;color:#888;margin-bottom:4px">{label}</div>'
            f'<div style="font-size:20px;font-weight:700;color:{color}">{value}</div>'
            f'{sub_html}</div>',
            unsafe_allow_html=True,
        )

    profit_color = (
        COLOR["positive"] if p_profit >= 55
        else COLOR["negative"] if p_profit <= 45
        else "#ffffff"
    )

    cols = st.columns(6)
    _card(cols[0], "P(רווח)", f"{p_profit:.0f}%", profit_color,
          sub="סימולציות שמסתיימות ברווח")
    _card(cols[1], "מחיר חציוני", f"${median:.2f}")
    _card(cols[2], "גרוע (P5)", f"${p5:.2f}", COLOR["negative"])
    _card(cols[3], "מיטבי (P95)", f"${p95:.2f}", COLOR["positive"])
    _card(cols[4], "VaR (5%)", f"{var5:.1f}%", COLOR["negative"] if var5 < 0 else COLOR["positive"],
          sub="הפסד מקסימלי ב-95% מהמקרים")
    _card(cols[5], "רווח מקסימלי", f"+{max_profit:.1f}%", COLOR["positive"],
          sub=f"${max_price:.2f} — הסימולציה האופטימית ביותר")


def _render_monte_carlo_section(ticker, prices, targets):
    """Monte Carlo price simulation section at the bottom of the charts tab."""
    section_title(
        "סימולציית מונטה קארלו",
        "חיזוי מסלולי מחיר לפי תנודתיות היסטורית — מודל Geometric Brownian Motion",
    )

    ohlcv     = (prices.get(ticker) or {}).get("ohlcv")
    cur_price = (prices.get(ticker) or {}).get("price")
    if ohlcv is None or cur_price is None or ohlcv.empty:
        st.info("אין נתוני OHLCV לסימולציה.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        horizon = st.selectbox(
            "אופק (ימי מסחר)", [30, 60, 90, 180, 252], index=2, key="mc_horizon"
        )
    with c2:
        n_sims = st.selectbox(
            "סימולציות", [500, 1000, 5000], index=1, key="mc_sims"
        )
    with c3:
        show_paths = st.toggle("הצג מסלולים", value=True, key="mc_show_paths")

    close  = ohlcv["Close"].dropna()
    target = (targets.get(ticker) or {}).get("mean")

    paths = _run_mc(close, float(cur_price), n_sims=int(n_sims), n_days=int(horizon))
    fig   = _build_mc_figure(
        close, paths, ticker, int(horizon),
        analyst_target=target, show_sample_paths=show_paths,
    )
    st.plotly_chart(fig, use_container_width=True)
    _render_mc_stats(paths, float(cur_price))

    term_glossary([
        ("Geometric Brownian Motion (GBM)",
         "מודל מתמטי לחיזוי מחירי מניות. מניח שינויים אקראיים לוגריתמיים עם סטיית תקן קבועה. "
         "הנחת יסוד: תנודתיות עבר מייצגת את תנודתיות העתיד."),
        ("VaR — Value at Risk (5%)",
         "ההפסד המקסימלי ברמת ביטחון 95% — רק 5% מהסימולציות מסתיימות בהפסד גדול יותר."),
        ("P(רווח)",
         "אחוז הסימולציות שמסתיימות במחיר גבוה מהמחיר הנוכחי — הסתברות גולמית לרווח לפי המודל."),
        ("P5 / P95",
         "אחוזון 5 ו-95 — טווח ה-90% המרכזי של כל התוצאות האפשריות."),
        ("חציון (P50)",
         "מחצית הסימולציות מסתיימות מעל לערך זה ומחצית מתחתיו."),
    ], label="📖 מקרא — מונטה קארלו")


# ── Trailing Stop Backtester ──────────────────────────────────────────────────

def _compute_trailing_stop(
    ohlcv: "pd.DataFrame",
    n_bars: int = 2,
    fast_ma: int = 20,
    slow_ma: int = 50,
) -> "pd.DataFrame":
    """
    Backtest a trailing stop strategy on 1-year daily OHLCV.

    Entry:    fast_ma crosses above slow_ma.
    Stop:     lowest Low of the previous n_bars at entry time.
    Trailing: whenever current bar's High > max(High of previous n_bars),
              raise stop to min(Low of previous n_bars) — never down.
    Exit:     Close < current stop level.

    Added columns (all prefixed with _ to mark as internal):
      _fast_ma, _slow_ma  — moving average values
      _stop               – stop level (None when not in trade)
      _stop_color         – "red" (initial) | "green" (has trailed) | None
      _entry, _exit       – bool flags
    """
    df = ohlcv[["Open", "High", "Low", "Close", "Volume"]].copy()
    n  = len(df)

    df["_fast_ma"] = df["Close"].rolling(fast_ma, min_periods=fast_ma).mean()
    df["_slow_ma"] = df["Close"].rolling(slow_ma, min_periods=slow_ma).mean()

    # Entry signal: fast MA crosses above slow MA on this bar
    df["_ma_cross"] = (
        (df["_fast_ma"] > df["_slow_ma"])
        & (df["_fast_ma"].shift(1) <= df["_slow_ma"].shift(1))
    )

    # State machine — iterate bar by bar
    stop_arr       = [None] * n
    stop_color_arr = [None] * n
    entry_arr      = [False] * n
    exit_arr       = [False] * n

    in_trade    = False
    stop        = 0.0
    stop_moved  = False
    entry_price = 0.0  # noqa: F841

    start_i = max(n_bars, slow_ma)

    for i in range(start_i, n):
        high_i  = float(df["High"].iat[i])
        close_i = float(df["Close"].iat[i])
        prev    = df.iloc[i - n_bars: i]
        n_high  = float(prev["High"].max())
        n_low   = float(prev["Low"].min())

        if not in_trade:
            if bool(df["_ma_cross"].iat[i]):
                in_trade    = True
                stop        = n_low
                stop_moved  = False
                entry_arr[i] = True
        else:
            if high_i > n_high:
                new_stop = n_low
                if new_stop > stop:
                    stop       = new_stop
                    stop_moved = True

            stop_arr[i]       = stop
            stop_color_arr[i] = "green" if stop_moved else "red"

            if close_i < stop:
                exit_arr[i] = True
                in_trade    = False
                stop_moved  = False

    df["_stop"]       = stop_arr
    df["_stop_color"] = stop_color_arr
    df["_entry"]      = entry_arr
    df["_exit"]       = exit_arr
    return df


def _trailing_stop_stats(df: "pd.DataFrame") -> dict:
    """Compute completed trade P&L statistics from trailing stop simulation."""
    entry_rows = df[df["_entry"]]
    exit_rows  = df[df["_exit"]]
    entry_idx  = entry_rows.index.tolist()
    exit_idx   = exit_rows.index.tolist()

    pnl_pcts: list = []
    for ei in exit_idx:
        prior = [e for e in entry_idx if e < ei]
        if not prior:
            continue
        ep = float(df.loc[prior[-1], "Close"])
        xp = float(df.loc[ei, "Close"])
        if ep > 0:
            pnl_pcts.append((xp - ep) / ep * 100)

    if not pnl_pcts:
        return {
            "n_trades": 0, "n_entries": len(entry_rows),
            "win_rate": None, "avg_win": None, "avg_loss": None, "total_pnl_pct": None,
        }

    wins   = [p for p in pnl_pcts if p > 0]
    losses = [p for p in pnl_pcts if p <= 0]
    return {
        "n_trades":      len(pnl_pcts),
        "n_entries":     len(entry_rows),
        "win_rate":      len(wins) / len(pnl_pcts),
        "avg_win":       sum(wins)   / len(wins)   if wins   else None,
        "avg_loss":      sum(losses) / len(losses) if losses else None,
        "total_pnl_pct": sum(pnl_pcts),
    }


def _build_trailing_stop_figure(
    df: "pd.DataFrame",
    ticker: str,
    n_bars: int,
    fast_ma: int,
    slow_ma: int,
    show_stop: bool,
) -> go.Figure:
    """
    Plotly candlestick chart with MA lines, color-coded trailing stop,
    and entry (triangle-up) / exit (square) markers.
    """
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name=ticker,
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
        showlegend=True,
    ))

    fig.add_trace(go.Scatter(
        x=df.index, y=df["_fast_ma"],
        mode="lines", name=f"SMA {fast_ma}",
        line={"color": "#00bcd4", "width": 1.5},
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df["_slow_ma"],
        mode="lines", name=f"SMA {slow_ma}",
        line={"color": "#ff9800", "width": 1.5},
    ))

    if show_stop:
        stop_s = df["_stop"].copy().astype(float)
        colors = df["_stop_color"]

        red = stop_s.copy()
        red[colors != "red"] = None
        fig.add_trace(go.Scatter(
            x=df.index, y=red,
            mode="lines", name="Stop ראשוני",
            line={"color": "#F44336", "width": 2, "dash": "dot"},
            connectgaps=False,
        ))

        green = stop_s.copy()
        green[colors != "green"] = None
        fig.add_trace(go.Scatter(
            x=df.index, y=green,
            mode="lines", name="Trailing Stop",
            line={"color": "#4CAF50", "width": 2},
            connectgaps=False,
        ))

    entries = df[df["_entry"]]
    if not entries.empty:
        fig.add_trace(go.Scatter(
            x=entries.index,
            y=(entries["Close"] * 0.997),
            mode="markers", name="כניסה",
            marker={
                "symbol": "triangle-up",
                "size":   13,
                "color":  "#4CAF50",
                "line":   {"color": "#ffffff", "width": 1},
            },
        ))

    exits = df[df["_exit"]]
    if not exits.empty:
        fig.add_trace(go.Scatter(
            x=exits.index,
            y=(exits["Close"] * 1.003),
            mode="markers", name="יציאה",
            marker={
                "symbol": "square",
                "size":   11,
                "color":  "#F44336",
                "line":   {"color": "#ffffff", "width": 1},
            },
        ))

    day_str = df.index[-1].strftime("%d/%m/%Y") if not df.empty else ""
    fig.update_layout(
        height=450,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#111111",
        font={"color": "#ffffff", "size": 11},
        title={
            "text": (
                f"{ticker} — {n_bars}-Bar Trailing Stop | "
                f"Entry: SMA{fast_ma} × SMA{slow_ma} | עד {day_str}"
            ),
            "font": {"color": COLOR["primary"], "size": 13},
            "x": 0,
        },
        xaxis_rangeslider_visible=False,
        legend={"orientation": "h", "y": 1.06, "font": {"size": 10}},
        margin={"t": 55, "b": 20, "l": 20, "r": 20},
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="#222", showgrid=True)
    fig.update_yaxes(gridcolor="#222", showgrid=True, tickprefix="$")
    return fig


def _render_ts_stats(stats: dict) -> None:
    """5-KPI strip showing trailing stop backtest results."""
    def _mini(label: str, val: str, color: str) -> str:
        return (
            f'<div style="background:#1a1f2e;border:1px solid #1f2937;border-radius:6px;'
            f'padding:8px 12px;text-align:center">'
            f'<div style="font-size:10px;color:{COLOR["text_dim"]};margin-bottom:2px">{label}</div>'
            f'<div style="font-size:16px;font-weight:700;color:{color}">{val}</div>'
            f'</div>'
        )

    n  = stats.get("n_trades", 0)
    wr = stats.get("win_rate")
    aw = stats.get("avg_win")
    al = stats.get("avg_loss")
    tp = stats.get("total_pnl_pct")

    wr_c = (COLOR["positive"] if (wr or 0) >= 0.5
            else COLOR["warning"] if (wr or 0) >= 0.35
            else COLOR["negative"])
    tp_c = COLOR["positive"] if (tp or 0) > 0 else COLOR["negative"]

    cards = [
        ("עסקאות שנסגרו", str(n) if n else "0",                       COLOR["primary"]),
        ("שיעור הצלחה",   f"{wr*100:.1f}%" if wr is not None else "—", wr_c),
        ("רווח ממוצע",    f"+{aw:.1f}%" if aw is not None else "—",    COLOR["positive"]),
        ("הפסד ממוצע",    f"{al:.1f}%" if al is not None else "—",     COLOR["negative"]),
        ('סה"כ P&L',      f"{tp:+.1f}%" if tp is not None else "—",    tp_c),
    ]
    cols = st.columns(5)
    for col, (lbl, val, c) in zip(cols, cards):
        with col:
            st.markdown(_mini(lbl, val, c), unsafe_allow_html=True)

    if n == 0:
        ne = stats.get("n_entries", 0)
        msg = (
            "לא נסגרו עסקאות בתקופה זו — אין מספיק חציות MA ב-1 שנה."
            if ne == 0
            else f"נפתחו {ne} עסקאות אך לא נסגרו (עדיין פתוחות בסוף התקופה)."
        )
        st.caption(msg)


def _render_trailing_stop_section(sel: str, prices: dict) -> None:
    """
    Trailing stop backtester — rendered below Monte Carlo in the Charts tab.
    Ticker comes from the shared Charts tab selectbox (sel parameter).
    """
    section_title(
        "📏 Trailing Stop — בקרת סיכון דינמית",
        "בדיקה רטרואקטיבית (1 שנה) — כניסה על חצייה MA, יציאה על סיחרור n-bar",
    )

    with st.expander("📖 איך זה עובד?", expanded=False):
        st.markdown(
            '<div dir="rtl" style="font-size:11px;color:#aaa;line-height:1.9">'
            '<b style="color:#00cf8d">כניסה:</b> MA המהיר חוצה מעל MA האיטי — אות מומנטום קלאסי.<br>'
            '<b style="color:#00cf8d">Stop ראשוני:</b> הנמוך ביותר של N הנרות האחרונים בעת הכניסה — '
            'קו הגנה ראשוני (מנוקד אדום).<br>'
            '<b style="color:#00cf8d">Trailing:</b> בכל פעם שהמחיר שובר שיא חדש של N נרות, '
            'ה-Stop מוזז למעלה לנמוך החדש של N נרות — '
            'מגן על רווחים צבורים, אף פעם לא יורד (ירוק רציף).<br>'
            '<b style="color:#00cf8d">יציאה:</b> כאשר סגירה מתחת ל-Stop הנוכחי — '
            'מסומן בריבוע אדום על הגרף.'
            '</div>',
            unsafe_allow_html=True,
        )

    # ── Controls (no ticker selectbox — sel comes from Charts tab) ───────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        n_bars = st.slider("Lookback (bars)", min_value=1, max_value=10,
                           value=2, key="ts_nbars",
                           help="מספר הנרות לחישוב High/Low לצורך הזזת ה-Stop")
    with c2:
        fast_ma = st.slider("MA מהיר", min_value=5, max_value=100,
                            value=20, key="ts_fast",
                            help="MA הקצר — סיגנל כניסה מהיר יותר, יותר עסקאות")
    with c3:
        slow_ma = st.slider("MA איטי", min_value=20, max_value=200,
                            value=50, key="ts_slow",
                            help="MA הארוך — פילטר מגמה")
    with c4:
        st.markdown('<div style="margin-top:28px"></div>', unsafe_allow_html=True)
        show_stop = st.checkbox("הצג Stop Line", value=True, key="ts_show_stop")

    if fast_ma >= slow_ma:
        st.warning("⚠️ MA מהיר חייב להיות קטן מ-MA האיטי.")
        return

    # ── Fetch OHLCV ──────────────────────────────────────────────────────────
    p     = prices.get(sel) or {}
    ohlcv = p.get("ohlcv")
    if ohlcv is None or ohlcv.empty:
        st.caption(f"אין נתוני OHLCV עבור {sel}.")
        return
    if len(ohlcv) < slow_ma + n_bars + 5:
        st.caption(
            f"אין מספיק ימי מסחר ({len(ohlcv)}) עבור MA{slow_ma}. "
            f"הפחת את ה-MA האיטי."
        )
        return

    # ── Compute & render ─────────────────────────────────────────────────────
    try:
        result_df = _compute_trailing_stop(ohlcv, n_bars=n_bars,
                                           fast_ma=fast_ma, slow_ma=slow_ma)
    except Exception as exc:
        st.warning(f"שגיאה בחישוב: {exc}")
        return

    fig = _build_trailing_stop_figure(result_df, sel, n_bars, fast_ma, slow_ma, show_stop)
    st.plotly_chart(fig, use_container_width=True)

    stats = _trailing_stop_stats(result_df)
    _render_ts_stats(stats)

    color_legend([
        ("#00bcd4", f"SMA {fast_ma} — ממוצע נע מהיר (כניסה)"),
        ("#ff9800", f"SMA {slow_ma} — ממוצע נע איטי (מגמה)"),
        ("#F44336", f"Stop ראשוני ({n_bars}-bar) — לא הוזזה עדיין"),
        ("#4CAF50", f"Trailing Stop ({n_bars}-bar) — הוזזה למעלה"),
        ("#4CAF50", "▲ כניסה — חצייה SMA"),
        ("#F44336", "■ יציאה — סגירה מתחת ל-Stop"),
    ])

    term_glossary([
        ("Trailing Stop",   "עצירת הפסד שזזה בכיוון אחד (למעלה). מגנה על רווחים צבורים."),
        ("Lookback (bars)", f"N={n_bars} — מספר הנרות לאחור לחישוב Stop High/Low."),
        ("MA Cross Entry",  f"כניסה: SMA{fast_ma} חוצה מעל SMA{slow_ma} = מומנטום חיובי."),
        ("Stop ראשוני",     f"Low הנמוך ביותר של {n_bars} הנרות האחרונים בעת הכניסה."),
        ("Trailing",        f"בכל פעם שנשבר שיא חדש של {n_bars} נרות, Stop מוזז ל-Low החדש."),
        ("Win Rate",        "אחוז עסקאות רווחיות (סגירה מעל מחיר כניסה)."),
    ])
