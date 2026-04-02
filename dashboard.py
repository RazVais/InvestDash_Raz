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
from src.email_report import send_alert_async, send_digest_async, smtp_configured, test_smtp
from src.portfolio import get_email_settings, set_auto_alert, set_email_recipients
from src.tabs.red_flags import get_all_flag_statuses, get_flag_summary
from src.tabs.overview         import render_overview
from src.tabs.portfolio_tab    import render_portfolio
from src.tabs.charts           import render_charts
from src.tabs.analysts_tab     import render_analysts
from src.tabs.fundamentals_tab import render_fundamentals
from src.tabs.red_flags        import render_red_flags
from src.tabs.news_tab         import render_news
from src.tabs.suggestions_tab  import render_suggestions
from src.tabs.daily_brief_tab  import render_daily_brief
from src.tabs.analysis_tab     import render_analysis

_log = get_logger(__name__)

_TABS_PRIMARY   = ["סקירה", "תיק שלי", "גרפים", "אנליסטים", "פונדמנטלס", "דגלים אדומים"]
_TABS_SECONDARY = ["חדשות", "💡 המלצות", "📋 יומי", "🔬 ניתוח"]
_TABS = _TABS_PRIMARY + _TABS_SECONDARY

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
    """Two-row horizontal tab bar: primary (6 tabs) + secondary (4 tabs)."""
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = _TABS[0]

    def _row(tabs, border_bottom=False):
        cols = st.columns(len(tabs))
        for col, label in zip(reversed(cols), tabs):
            is_active = st.session_state.active_tab == label
            css_class = "nav-tab-active" if is_active else "nav-tab-inactive"
            with col:
                st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
                if st.button(label, key=f"_nav_{label}", use_container_width=True):
                    st.session_state.active_tab = label
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
        if border_bottom:
            st.markdown(
                '<div style="border-bottom:1px solid #333;margin-bottom:2px"></div>',
                unsafe_allow_html=True,
            )

    _row(_TABS_PRIMARY, border_bottom=True)
    _row(_TABS_SECONDARY)
    st.markdown(
        '<div style="border-bottom:2px solid #1f2937;margin-bottom:12px"></div>',
        unsafe_allow_html=True,
    )


def _auto_send_alert(portfolio, flag_statuses, td_str, smtp_cfg):
    """Auto-send an alert email when new flags become triggered this run."""
    settings   = get_email_settings(portfolio)
    recipients = settings.get("email_recipients", [])
    if not settings.get("auto_alert") or not recipients or not smtp_configured(smtp_cfg):
        return

    # Compare to previous run's flag states stored in session_state
    prev = st.session_state.get("_prev_flag_states", {})
    curr = {f"{f['ticker']}|{f['flag']}": f["status"] for f in flag_statuses}
    newly_triggered = [
        f for f in flag_statuses
        if f["status"] == "triggered"
        and prev.get(f"{f['ticker']}|{f['flag']}") != "triggered"
    ]
    st.session_state["_prev_flag_states"] = curr

    if newly_triggered:
        send_alert_async(newly_triggered, td_str, recipients, smtp_cfg)
        _log.info("Auto-alert sent", extra={"flags": [f["ticker"] for f in newly_triggered]})


def _render_email_section(portfolio, data, flag_statuses, td_str, smtp_cfg):
    """Sidebar expander: manage recipients, send digest, SMTP test."""
    settings   = get_email_settings(portfolio)
    recipients = list(settings.get("email_recipients", []))
    configured = smtp_configured(smtp_cfg)

    with st.expander("📧 דוח במייל", expanded=False):
        # ── Recipient list ────────────────────────────────────────────────
        st.markdown(
            f'<div dir="rtl" style="font-size:12px;font-weight:700;'
            f'color:{COLOR["primary"]};margin-bottom:6px">כתובות מייל</div>',
            unsafe_allow_html=True,
        )
        for i, email in enumerate(recipients):
            col_addr, col_del = st.columns([4, 1])
            col_addr.caption(email)
            if col_del.button("✕", key=f"_del_email_{i}", help="הסר"):
                recipients.pop(i)
                set_email_recipients(portfolio, recipients)
                st.rerun()

        # ── Add new recipient ─────────────────────────────────────────────
        new_email = st.text_input(
            "הוסף כתובת", placeholder="user@example.com",
            key="_new_email_input", label_visibility="collapsed",
        ).strip()
        if st.button("➕ הוסף", key="_add_email_btn", use_container_width=True):
            if new_email and "@" in new_email and new_email not in recipients:
                recipients.append(new_email)
                set_email_recipients(portfolio, recipients)
                st.success(f"נוסף: {new_email}")
                st.rerun()
            elif new_email in recipients:
                st.warning("כתובת זו כבר קיימת.")
            else:
                st.error("כתובת לא תקינה.")

        st.divider()

        # ── Auto-alert toggle ─────────────────────────────────────────────
        auto_on = st.toggle(
            "🔔 שלח התרעה אוטומטית בדגל חדש",
            value=bool(settings.get("auto_alert", False)),
            key="_auto_alert_toggle",
            disabled=not configured,
            help="שולח מייל מיידי כשדגל עובר למצב מופעל" if configured
                 else "הגדר SMTP ב-secrets.toml תחילה",
        )
        if auto_on != settings.get("auto_alert", False):
            set_auto_alert(portfolio, auto_on)

        # ── Manual send ───────────────────────────────────────────────────
        if not configured:
            st.caption("⚙️ הוסף SMTP_HOST / SMTP_USER / SMTP_PASSWORD לקובץ .streamlit/secrets.toml")
        elif not recipients:
            st.caption("הוסף כתובת מייל לשליחה.")
        else:
            if st.button("📤 שלח דוח עכשיו", key="_send_digest_btn",
                         use_container_width=True):
                st.session_state["_email_sending"] = True
                send_digest_async(
                    portfolio, data, flag_statuses, td_str, recipients, smtp_cfg,
                    on_done=lambda ok: st.session_state.update(
                        {"_email_sending": False, "_email_last_ok": ok}
                    ),
                )

            if st.session_state.get("_email_sending"):
                st.caption("📨 שולח...")
            elif "_email_last_ok" in st.session_state:
                if st.session_state["_email_last_ok"]:
                    st.success("✅ נשלח בהצלחה")
                else:
                    st.error("❌ שליחה נכשלה — בדוק הגדרות SMTP")

            # SMTP test button
            if st.button("🔧 בדוק SMTP", key="_test_smtp_btn",
                         use_container_width=True):
                err = test_smtp(smtp_cfg, recipients[0])
                if err:
                    st.error(err)
                else:
                    st.success(f"✅ מייל בדיקה נשלח ל-{recipients[0]}")


def _render_sidebar(portfolio, data, market_state, smtp_cfg=None, flag_statuses=None, td_str=""):
    """Sidebar: market badge, flag summary, macro strip, email, refresh + exit."""
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
        _render_email_section(portfolio, data, flag_statuses or [], td_str, smtp_cfg or {})
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
        api_key        = st.secrets.get("FINNHUB_API_KEY", "")
        claude_api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
        smtp_cfg = {
            "host":     st.secrets.get("SMTP_HOST", ""),
            "port":     st.secrets.get("SMTP_PORT", 587),
            "user":     st.secrets.get("SMTP_USER", ""),
            "password": st.secrets.get("SMTP_PASSWORD", ""),
        }
    except Exception:
        api_key        = ""
        claude_api_key = ""
        smtp_cfg       = {}

    active = st.session_state.get("active_tab", _TABS[0])
    data = load_all_data(portfolio, market_state, api_key, active_tab=active)

    # ── Auto-alert: detect newly-triggered flags ──────────────────────────
    flag_statuses = get_all_flag_statuses(portfolio, data)
    _auto_send_alert(portfolio, flag_statuses, td_str, smtp_cfg)

    _render_sidebar(portfolio, data, market_state, smtp_cfg, flag_statuses, td_str)

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

    # ── Deferred-data banner ──────────────────────────────────────────────
    _TAB_SLOW = {
        "פונדמנטלס":    {"fundamentals", "earnings"},
        "חדשות":         {"news"},
        "אנליסטים":      {"targets", "upgrades"},
        "דגלים אדומים":  {"upgrades", "commodities"},
        "סקירה":         {"targets"},
        "גרפים":         {"targets"},
    }
    _deferred    = data.get("_deferred", frozenset())
    _tab_missing = _TAB_SLOW.get(active, set()) & _deferred
    if _tab_missing:
        col_msg, col_btn = st.columns([6, 1])
        with col_msg:
            st.caption("📡 חלק מהנתונים עדיין בטעינת רקע — לחץ רענן לעדכון מיידי")
        with col_btn:
            if st.button("🔄", key="_bg_refresh", help="רענן נתוני רקע"):
                st.cache_data.clear()
                st.rerun()

    # ── Tab content ───────────────────────────────────────────────────────
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
        render_news(portfolio, data, td_str, claude_api_key)
    elif active == "💡 המלצות":
        render_suggestions(portfolio, data, td_str, api_key)
    elif active == "📋 יומי":
        render_daily_brief(portfolio, data, td_str, claude_api_key)
    elif active == "🔬 ניתוח":
        render_analysis(portfolio, data, td_str, api_key, claude_api_key)


if __name__ == "__main__":
    main()
