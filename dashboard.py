"""RazDashboard v2 — thin entry point.

IMPORTANT: src.yf_patch must be imported FIRST — before any yfinance import.
It patches yfinance's SQLite caches with in-memory Python dicts to avoid
Windows threading crashes.
"""

import src.yf_patch  # noqa: F401, I001 — MUST be first import

import os
import threading
import time
import streamlit as st
import streamlit.components.v1 as stc

from src.logger    import get_logger
from src.config    import COLOR
from src.market    import get_market_state, market_badge, fmt_trading_day
from src.portfolio import load_portfolio
from src.data.loader import load_all_data
from src.tabs.red_flags import get_flag_summary
from src.tabs.overview         import render_overview
from src.tabs.portfolio_tab    import render_portfolio
from src.tabs.charts           import render_charts
from src.tabs.analysts_tab     import render_analysts
from src.tabs.fundamentals_tab import render_fundamentals
from src.tabs.red_flags        import render_red_flags
from src.tabs.news_tab         import render_news
from src.tabs.suggestions_tab  import render_suggestions

_log = get_logger(__name__)

_TABS = ["סקירה", "תיק שלי", "גרפים", "אנליסטים",
         "פונדמנטלס", "דגלים אדומים", "חדשות", "💡 המלצות"]

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="RazDashboard — תיק השקעות",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ───────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* RTL for main content */
    .main .block-container { direction: rtl; }

    /* Keep plotly charts LTR */
    .js-plotly-plot { direction: ltr; }

    /* Sidebar RTL */
    section[data-testid="stSidebar"] > div { direction: rtl; }

    /* Tighten overall padding */
    .main .block-container { padding-top: 1rem; padding-bottom: 1rem; }

    /* Dataframe text alignment */
    .stDataFrame td { text-align: right !important; }

    /* Remove default streamlit footer */
    footer { visibility: hidden; }

    /* ── Custom nav-tab bar ── */
    div[data-testid="stHorizontalBlock"].nav-row > div { padding: 0 2px; }

    div.nav-tab-active > div > button {
        background: transparent !important;
        color: #00cf8d !important;
        border: none !important;
        border-bottom: 2px solid #00cf8d !important;
        border-radius: 0 !important;
        font-weight: 700 !important;
        font-size: 14px !important;
    }
    div.nav-tab-inactive > div > button {
        background: transparent !important;
        color: #aaaaaa !important;
        border: none !important;
        border-bottom: 2px solid transparent !important;
        border-radius: 0 !important;
        font-size: 14px !important;
    }
    div.nav-tab-inactive > div > button:hover {
        color: #ffffff !important;
        border-bottom: 2px solid #555 !important;
    }

    /* ── Accessibility: keyboard focus rings ───────────────────── */
    *:focus-visible {
        outline: 2px solid #00cf8d !important;
        outline-offset: 2px !important;
    }
    button:focus-visible,
    [role="button"]:focus-visible,
    a:focus-visible {
        outline: 2px solid #00cf8d !important;
        outline-offset: 2px !important;
    }
    *:focus:not(:focus-visible) {
        outline: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _render_nav_tabs():
    """Horizontal tab bar that survives reruns via st.session_state."""
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = _TABS[0]

    # Bottom border under the whole bar
    st.markdown(
        '<div style="border-bottom:1px solid #333;margin-bottom:12px"></div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(len(_TABS))
    # Reverse column order for RTL (rightmost = first tab)
    for col, label in zip(reversed(cols), _TABS):
        is_active = st.session_state.active_tab == label
        css_class = "nav-tab-active" if is_active else "nav-tab-inactive"
        with col:
            st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
            if st.button(label, key=f"_nav_{label}", use_container_width=True):
                st.session_state.active_tab = label
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)


def _render_sidebar(portfolio, data, market_state):
    """Sidebar: market badge, flag summary, macro strip, refresh + exit."""
    with st.sidebar:
        st.markdown(market_badge(market_state), unsafe_allow_html=True)
        st.caption(fmt_trading_day(market_state))
        st.divider()

        n_triggered, n_watch = get_flag_summary(portfolio, data)
        if n_triggered > 0:
            st.markdown(
                f'<div style="direction:rtl;color:{COLOR["negative"]};font-weight:700;font-size:14px">'
                f'🔴 {n_triggered} דגלים מופעלים</div>',
                unsafe_allow_html=True,
            )
        elif n_watch > 0:
            st.markdown(
                f'<div style="direction:rtl;color:{COLOR["warning"]};font-weight:700;font-size:14px">'
                f'🟡 {n_watch} דגלי מעקב</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div style="direction:rtl;color:{COLOR["positive"]};font-weight:700;font-size:14px">'
                f'🟢 כל הדגלים תקינים</div>',
                unsafe_allow_html=True,
            )
        st.divider()

        # Macro strip
        macro     = data.get("macro", {})
        vix       = macro.get("vix")
        yield_10y = macro.get("yield_10y")
        dxy       = macro.get("dxy")

        st.markdown('<div style="direction:rtl;font-size:12px;font-weight:700">מאקרו</div>',
                    unsafe_allow_html=True)

        def _macro_color(key, val):
            if val is None:
                return COLOR["text_dim"]
            if key == "vix":
                return COLOR["negative"] if val >= 30 else (COLOR["warning"] if val >= 20 else COLOR["positive"])
            if key == "yield_10y":
                return COLOR["negative"] if val >= 4.5 else (COLOR["warning"] if val >= 4.0 else COLOR["positive"])
            return COLOR["text_dim"]

        def _macro_hint(key, val):
            """One-line Hebrew explanation of the current reading."""
            if val is None:
                return ""
            if key == "vix":
                if val >= 30:
                    return "פחד גבוה — תנודתיות חריגה בשוק"
                if val >= 20:
                    return "מתח מתון — שמור על זהירות"
                return "שוק רגוע — תנודתיות נמוכה"
            if key == "yield_10y":
                if val >= 4.5:
                    return "תשואה גבוהה — לחץ על מניות צמיחה"
                if val >= 4.0:
                    return "תשואה מוגברת — מעקב נדרש"
                return "תשואה מתונה — סביבה נוחה"
            if key == "dxy":
                if val >= 105:
                    return "דולר חזק — לחץ על סחורות"
                if val <= 98:
                    return "דולר חלש — תמיכה בסחורות"
                return "דולר ניטרלי"
            return ""

        for label, key, val, suffix in [
            ("VIX", "vix",       vix,       ""),
            ("10Y", "yield_10y", yield_10y, "%"),
            ("DXY", "dxy",       dxy,       ""),
        ]:
            val_str = f"{val:.2f}{suffix}" if val is not None else "—"
            color   = _macro_color(key, val)
            hint    = _macro_hint(key, val)
            hint_html = (
                f'<div style="direction:rtl;font-size:9px;color:{COLOR["text_dim"]};'
                f'text-align:right;margin-bottom:4px;line-height:1.3">{hint}</div>'
                if hint else ""
            )
            st.markdown(
                f'<div style="direction:rtl;display:flex;justify-content:space-between;'
                f'font-size:12px;margin-top:4px">'
                f'<span style="color:{COLOR["text_dim"]}">{label}</span>'
                f'<span style="color:{color};font-weight:700">{val_str}</span>'
                f'</div>'
                f'{hint_html}',
                unsafe_allow_html=True,
            )

        st.divider()

        is_trading_day = market_state.get("is_trading_day", False)
        if is_trading_day:
            if st.button("🔄 רענן נתונים", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
        else:
            st.button(
                "🔄 רענן נתונים",
                use_container_width=True,
                disabled=True,
                help="השוק סגור — משתמשים בנתונים השמורים",
            )

        st.divider()

        if st.button("🔴 יציאה", use_container_width=True,
                     help="סגור את האפליקציה וסיים את כל התהליכים"):
            stc.html(
                """<script>
                try { window.top.close(); } catch(e) {}
                try { window.open('', '_self', '').close(); } catch(e) {}
                </script>""",
                height=0,
            )
            st.sidebar.info("האפליקציה נסגרת... ניתן לסגור את הדפדפן.")
            def _shutdown():
                time.sleep(1.2)
                os._exit(0)
            threading.Thread(target=_shutdown, daemon=True).start()
            st.stop()


def main():
    portfolio    = load_portfolio()
    market_state = get_market_state()
    td_str       = market_state["last_trading_day"].isoformat()
    market_open  = market_state.get("is_open", False)

    _log.info("Dashboard starting", extra={"trading_day": td_str, "market_open": market_open})

    try:
        api_key = st.secrets.get("FINNHUB_API_KEY", "")
    except Exception:
        api_key = ""

    data = load_all_data(portfolio, market_state, api_key)

    _render_sidebar(portfolio, data, market_state)

    # ── App header ────────────────────────────────────────────────────────
    st.markdown(
        """
        <div dir="rtl" style="
            display:flex;justify-content:space-between;align-items:center;
            padding:10px 0 4px 0;border-bottom:2px solid #00cf8d;margin-bottom:4px
        ">
            <div>
                <div style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:0.5px">
                    📊 RazDashboard — תיק השקעות
                </div>
                <div style="font-size:11px;color:#aaaaaa;margin-top:3px">
                    תיק ה-AI &amp; תשתיות | נתונים: Yahoo Finance · Finviz · Finnhub
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Navigation (state-preserving tab bar) ─────────────────────────────
    _render_nav_tabs()

    # ── Tab content ───────────────────────────────────────────────────────
    active = st.session_state.get("active_tab", _TABS[0])

    if active == "סקירה":
        render_overview(portfolio, data, market_state, td_str)
    elif active == "תיק שלי":
        render_portfolio(portfolio, data)
    elif active == "גרפים":
        render_charts(portfolio, data)
    elif active == "אנליסטים":
        render_analysts(portfolio, data)
    elif active == "פונדמנטלס":
        render_fundamentals(portfolio, data, td_str)
    elif active == "דגלים אדומים":
        render_red_flags(portfolio, data, td_str)
    elif active == "חדשות":
        render_news(portfolio, data, td_str)
    elif active == "💡 המלצות":
        render_suggestions(portfolio, data, td_str, api_key)


if __name__ == "__main__":
    main()
