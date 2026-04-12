"""RazDashboard v2 — thin entry point.

IMPORTANT: src.yf_patch must be imported FIRST — before any yfinance import.
It patches yfinance's SQLite caches with in-memory Python dicts to avoid
Windows threading crashes.
"""

import src.yf_patch  # noqa: F401, I001 — MUST be first import

import contextlib
import os
import threading
import time
import streamlit as st
import streamlit.components.v1 as stc

from src.logger    import get_logger
from src.config    import COLOR
from src.market    import get_market_state, market_badge, fmt_trading_day
from src.portfolio import load_portfolio, all_tickers, lots_for_ticker
from src.data.loader import load_all_data
from src.data.prices import lookup_buy_price
from src.email_report import send_alert_async, send_digest_sync, smtp_configured, test_smtp
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
from src.tabs.analysis_tab     import render_analysis

_log = get_logger(__name__)

# ── Navigation structure ──────────────────────────────────────────────────────
_SIDEBAR_TABS = ["סקירה", "תיק שלי", "גרפים", "אנליסטים", "פונדמנטלס"]
_SIDEBAR_ICONS = {
    "סקירה":     "📊",
    "תיק שלי":   "💼",
    "גרפים":     "📈",
    "אנליסטים":  "👥",
    "פונדמנטלס": "📋",
}
_SECONDARY_TABS = ["חדשות", "💡 המלצות", "🔬 ניתוח"]
_ALL_TABS = _SIDEBAR_TABS + _SECONDARY_TABS + ["דגלים אדומים"]

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="RazDashboard — תיק השקעות",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
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
    .main .block-container { padding-top: 0.5rem; padding-bottom: 1rem; }
    /* Dataframe text alignment */
    .stDataFrame td { text-align: right !important; }
    /* Remove default streamlit footer */
    footer { visibility: hidden; }

    /* ── Sidebar navigation buttons ── */
    div.sidebar-nav-active > div > button {
        background: #00cf8d18 !important;
        color: #00cf8d !important;
        border: none !important;
        border-right: 3px solid #00cf8d !important;
        border-radius: 6px !important;
        font-weight: 700 !important;
        text-align: right !important;
        margin-bottom: 2px !important;
    }
    div.sidebar-nav-item > div > button {
        background: transparent !important;
        color: #bbbbbb !important;
        border: none !important;
        border-right: 3px solid transparent !important;
        border-radius: 6px !important;
        text-align: right !important;
        margin-bottom: 2px !important;
    }
    div.sidebar-nav-item > div > button:hover {
        background: #1f2937 !important;
        color: #ffffff !important;
    }

    /* ── Secondary tab bar ── */
    div.sec-tab-active > div > button {
        background: transparent !important;
        color: #00cf8d !important;
        border: none !important;
        border-bottom: 2px solid #00cf8d !important;
        border-radius: 0 !important;
        font-size: 12px !important;
    }
    div.sec-tab-inactive > div > button {
        background: transparent !important;
        color: #888888 !important;
        border: none !important;
        border-bottom: 2px solid transparent !important;
        border-radius: 0 !important;
        font-size: 12px !important;
    }
    div.sec-tab-inactive > div > button:hover {
        color: #ffffff !important;
        border-bottom: 2px solid #555555 !important;
    }

    /* ── Alert bell ── */
    div.bell-red > div > button {
        background: #f4433618 !important;
        color: #f44336 !important;
        border: 1px solid #f4433655 !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        height: 60px !important;
    }
    div.bell-yellow > div > button {
        background: #ff980018 !important;
        color: #ff9800 !important;
        border: 1px solid #ff980055 !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        height: 60px !important;
    }
    div.bell-ok > div > button {
        background: transparent !important;
        color: #555555 !important;
        border: 1px solid #33333355 !important;
        border-radius: 8px !important;
        height: 60px !important;
    }

    /* ── KPI cards ── */
    .kpi-card {
        background: #111827;
        border: 1px solid #1f2937;
        border-radius: 10px;
        padding: 12px 16px;
        direction: rtl;
        height: 78px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .kpi-label { font-size: 10px; color: #888888; margin-bottom: 3px; letter-spacing: 0.5px; text-transform: uppercase; }
    .kpi-value { font-size: 20px; font-weight: 800; color: #ffffff; line-height: 1.2; }
    .kpi-sub   { font-size: 11px; margin-top: 2px; }

    /* ── Accessibility: keyboard focus rings ── */
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
    *:focus:not(:focus-visible) { outline: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sparkline_svg(values, width=54, height=18):
    """Return an inline SVG polyline for a list of float values. Trend-colored."""
    if not values or len(values) < 2:
        return '<span style="color:#444;font-size:10px">—</span>'
    mn, mx   = min(values), max(values)
    span     = (mx - mn) or 1.0
    n        = len(values)
    xs       = [i * width / (n - 1) for i in range(n)]
    ys       = [height - (v - mn) / span * height for v in values]
    pts      = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    color    = "#4caf50" if values[-1] >= values[0] else "#f44336"
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'style="display:inline-block;vertical-align:middle;overflow:visible">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )


def _kpi_card_html(label, value, sub, sub_color):
    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-sub" style="color:{sub_color}">{sub}</div>'
        f'</div>'
    )


# ── KPI header helpers ────────────────────────────────────────────────────────

def _compute_portfolio_totals(portfolio, prices):
    """Return (total_cost, total_value, value_by_ticker)."""
    total_cost = total_value = 0.0
    value_by_ticker = {}
    for ticker in all_tickers(portfolio):
        p = prices.get(ticker)
        if not p:
            continue
        ticker_value = 0.0
        for _layer, lot in lots_for_ticker(portfolio, ticker):
            shares = lot.get("shares", 0.0)
            if shares <= 0:
                continue
            bp = lookup_buy_price(ticker, lot.get("buy_date", ""), prices)
            if bp:
                total_cost += shares * bp
            total_value  += shares * p["price"]
            ticker_value += shares * p["price"]
        value_by_ticker[ticker] = ticker_value
    return total_cost, total_value, value_by_ticker


def _compute_alpha(prices, value_by_ticker, total_value):
    """Return (portfolio_1m_pct, voo_1m_pct)."""
    portfolio_1m = 0.0
    if total_value > 0:
        for ticker, val in value_by_ticker.items():
            p = prices.get(ticker)
            if not p:
                continue
            hist = p.get("history")
            if hist is None or len(hist) < 21:
                continue
            try:
                t_ret = (float(hist.iloc[-1]) / float(hist.iloc[-21]) - 1) * 100
                portfolio_1m += t_ret * (val / total_value)
            except Exception:
                pass
    voo_1m = 0.0
    voo_p  = prices.get("VOO")
    if voo_p:
        hist = voo_p.get("history")
        if hist is not None and len(hist) >= 21:
            with contextlib.suppress(Exception):
                voo_1m = (float(hist.iloc[-1]) / float(hist.iloc[-21]) - 1) * 100
    return portfolio_1m, voo_1m


def _render_bell(n_triggered, n_watch):
    """Render the alert bell button column."""
    if n_triggered > 0:
        bell_label, bell_css = f"🔔  {n_triggered}", "bell-red"
        bell_tip = f"{n_triggered} דגלים מופעלים — לחץ לפרטים"
    elif n_watch > 0:
        bell_label, bell_css = f"🔔  {n_watch}", "bell-yellow"
        bell_tip = f"{n_watch} דגלי מעקב — לחץ לפרטים"
    else:
        bell_label, bell_css, bell_tip = "🔔", "bell-ok", "כל הדגלים תקינים"
    st.markdown(f'<div class="{bell_css}">', unsafe_allow_html=True)
    if st.button(bell_label, key="_bell_btn", help=bell_tip, use_container_width=True):
        st.session_state.active_tab = "דגלים אדומים"
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


# ── KPI header ────────────────────────────────────────────────────────────────

def _render_kpi_header(portfolio, data, n_triggered, n_watch):
    """Four KPI cards: Portfolio Value | P&L | Alpha vs VOO | Alert bell."""
    prices = data.get("prices", {})

    total_cost, total_value, value_by_ticker = _compute_portfolio_totals(portfolio, prices)
    pnl     = total_value - total_cost
    pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0.0

    portfolio_1m, voo_1m = _compute_alpha(prices, value_by_ticker, total_value)
    alpha       = portfolio_1m - voo_1m
    alpha_color = COLOR["positive"] if alpha >= 0 else COLOR["negative"]
    alpha_str   = f"{alpha:+.2f}%" if total_value > 0 else "—"
    alpha_sub   = f"תיק {portfolio_1m:+.1f}% | VOO {voo_1m:+.1f}%" if total_value > 0 else "30 יום"

    col_v, col_pnl, col_alpha, col_bell = st.columns([3, 2, 2, 1])

    with col_v:
        val_str  = f"${total_value:,.0f}" if total_value > 0 else "—"
        cost_str = f"עלות ${total_cost:,.0f}" if total_cost > 0 else "אין נתוני רכישה"
        st.markdown(_kpi_card_html("שווי תיק", val_str, cost_str, COLOR["text_dim"]),
                    unsafe_allow_html=True)

    with col_pnl:
        pnl_color = COLOR["positive"] if pnl >= 0 else COLOR["negative"]
        pnl_str   = f"${pnl:+,.0f}" if total_cost > 0 else "—"
        pnl_sub   = f"{pnl_pct:+.2f}%" if total_cost > 0 else "אין נתוני רכישה"
        st.markdown(_kpi_card_html("רווח / הפסד", pnl_str, pnl_sub, pnl_color),
                    unsafe_allow_html=True)

    with col_alpha:
        st.markdown(_kpi_card_html("Alpha vs VOO", alpha_str, alpha_sub, alpha_color),
                    unsafe_allow_html=True)

    with col_bell:
        _render_bell(n_triggered, n_watch)


# ── Secondary tab bar ─────────────────────────────────────────────────────────

def _render_secondary_tab_bar():
    """Compact tab row for secondary content: News, Recommendations, Daily, Analysis."""
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = _ALL_TABS[0]

    st.markdown(
        '<div style="border-top:1px solid #1f2937;padding-top:4px;margin-top:8px"></div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(len(_SECONDARY_TABS))
    for col, label in zip(reversed(cols), _SECONDARY_TABS):
        is_active = st.session_state.active_tab == label
        css_class = "sec-tab-active" if is_active else "sec-tab-inactive"
        with col:
            st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
            if st.button(label, key=f"_sec_{label}", use_container_width=True):
                st.session_state.active_tab = label
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
    st.markdown(
        '<div style="border-bottom:1px solid #1f2937;margin-bottom:12px"></div>',
        unsafe_allow_html=True,
    )


# ── Auto-alert ────────────────────────────────────────────────────────────────

def _auto_send_alert(portfolio, flag_statuses, td_str, smtp_cfg):
    """Auto-send an alert email when new flags become triggered this run."""
    settings   = get_email_settings(portfolio)
    recipients = settings.get("email_recipients", [])
    if not settings.get("auto_alert") or not recipients or not smtp_configured(smtp_cfg):
        return

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


# ── Email section helpers ─────────────────────────────────────────────────────

def _render_recipient_list(portfolio, recipients):
    """Render the recipient list with add/remove controls. Returns updated list."""
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


def _render_send_controls(portfolio, data, flag_statuses, td_str, recipients, smtp_cfg, settings):
    """Render auto-alert toggle + send/test buttons."""
    configured = smtp_configured(smtp_cfg)
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

    if not configured:
        st.caption("⚙️ הוסף SMTP_HOST / SMTP_USER / SMTP_PASSWORD לקובץ .streamlit/secrets.toml")
    elif not recipients:
        st.caption("הוסף כתובת מייל לשליחה.")
    else:
        if st.button("📤 שלח דוח עכשיו", key="_send_digest_btn", use_container_width=True):
            with st.spinner("📨 שולח..."):
                ok = send_digest_sync(portfolio, data, flag_statuses, td_str, recipients, smtp_cfg)
            if ok:
                st.success("✅ נשלח בהצלחה")
            else:
                st.error("❌ שליחה נכשלה — בדוק הגדרות SMTP")
        if st.button("🔧 בדוק SMTP", key="_test_smtp_btn", use_container_width=True):
            err = test_smtp(smtp_cfg, recipients[0])
            if err:
                st.error(err)
            else:
                st.success(f"✅ מייל בדיקה נשלח ל-{recipients[0]}")


# ── Email section ─────────────────────────────────────────────────────────────

def _render_email_section(portfolio, data, flag_statuses, td_str, smtp_cfg):
    """Sidebar expander: manage recipients, send digest, SMTP test."""
    settings   = get_email_settings(portfolio)
    recipients = list(settings.get("email_recipients", []))
    with st.expander("📧 דוח במייל", expanded=False):
        _render_recipient_list(portfolio, recipients)
        st.divider()
        _render_send_controls(portfolio, data, flag_statuses, td_str, recipients, smtp_cfg, settings)


# ── Sidebar helpers ───────────────────────────────────────────────────────────

def _macro_color(key, val):
    """Return color string for a macro indicator value."""
    if val is None:
        return COLOR["text_dim"]
    if key == "vix":
        return COLOR["negative"] if val >= 30 else (
            COLOR["warning"] if val >= 20 else COLOR["positive"])
    if key == "yield_10y":
        return COLOR["negative"] if val >= 4.5 else (
            COLOR["warning"] if val >= 4.0 else COLOR["positive"])
    return COLOR["text_dim"]


def _macro_hint(key, val):
    """Return short Hebrew hint for a macro indicator value."""
    if val is None:
        return ""
    if key == "vix":
        if val >= 30:
            return "פחד גבוה"
        if val >= 20:
            return "מתח מתון"
        return "שוק רגוע"
    if key == "yield_10y":
        if val >= 4.5:
            return "לחץ על צמיחה"
        if val >= 4.0:
            return "מעקב נדרש"
        return "סביבה נוחה"
    if key == "dxy":
        if val >= 105:
            return "דולר חזק"
        if val <= 98:
            return "דולר חלש"
        return "ניטרלי"
    return ""


def _render_sidebar_nav():
    """Render the primary navigation buttons."""
    st.markdown(
        '<div dir="rtl" style="font-size:10px;color:#888;font-weight:700;'
        'letter-spacing:1px;margin-bottom:6px">ניווט</div>',
        unsafe_allow_html=True,
    )
    for label in _SIDEBAR_TABS:
        icon      = _SIDEBAR_ICONS.get(label, "")
        is_active = st.session_state.active_tab == label
        css_class = "sidebar-nav-active" if is_active else "sidebar-nav-item"
        st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
        if st.button(f"{icon}  {label}", key=f"_nav_{label}", use_container_width=True):
            st.session_state.active_tab = label
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


def _render_macro_watchlist(macro):
    """Render VIX / 10Y / DXY rows with sparklines."""
    st.markdown(
        '<div dir="rtl" style="font-size:10px;color:#888;font-weight:700;'
        'letter-spacing:1px;margin-bottom:8px">מאקרו</div>',
        unsafe_allow_html=True,
    )
    for lbl, key, suffix in [("VIX", "vix", ""), ("10Y", "yield_10y", "%"), ("DXY", "dxy", "")]:
        val     = macro.get(key)
        hist    = macro.get(key + "_hist", [])
        val_str = f"{val:.2f}{suffix}" if val is not None else "—"
        color   = _macro_color(key, val)
        hint    = _macro_hint(key, val)
        spark   = _sparkline_svg(hist)
        st.markdown(
            f'<div dir="rtl" style="display:flex;justify-content:space-between;'
            f'align-items:center;padding:5px 0;border-bottom:1px solid #1a1f2e">'
            f'  <span style="font-size:11px;color:{COLOR["text_dim"]};min-width:28px">{lbl}</span>'
            f'  <span style="flex:1;padding:0 8px">{spark}</span>'
            f'  <div style="text-align:right">'
            f'    <span style="font-size:12px;font-weight:700;color:{color}">{val_str}</span>'
            + (f'<br><span style="font-size:9px;color:{COLOR["text_dim"]}">{hint}</span>' if hint else "")
            + '  </div></div>',
            unsafe_allow_html=True,
        )


def _render_sidebar_tools(market_state):
    """Render the bottom 3-icon tool row (refresh, email toggle, exit)."""
    is_trading_day = market_state.get("is_trading_day", False)
    col_r, col_e, col_x = st.columns(3)
    with col_r:
        if is_trading_day:
            if st.button("🔄", key="_sb_refresh", use_container_width=True, help="רענן נתונים"):
                st.cache_data.clear()
                st.rerun()
        else:
            st.button("🔄", key="_sb_refresh", use_container_width=True,
                      disabled=True, help="השוק סגור — משתמשים בנתונים השמורים")
    with col_e:
        if st.button("📧", key="_sb_email_toggle", use_container_width=True, help="דוח במייל"):
            st.session_state["_email_open"] = not st.session_state.get("_email_open", False)
            st.rerun()
    with col_x:
        if st.button("🔴", key="_sb_exit", use_container_width=True, help="סגור את האפליקציה"):
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


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _render_sidebar(portfolio, data, market_state, smtp_cfg=None, flag_statuses=None, td_str=""):
    """Sidebar: logo/badge, primary nav, macro watchlist with sparklines, tools."""
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = _ALL_TABS[0]

    with st.sidebar:
        st.markdown(
            '<div dir="rtl" style="font-size:16px;font-weight:800;color:#ffffff;'
            'letter-spacing:0.3px;margin-bottom:4px">📊 RazDashboard</div>',
            unsafe_allow_html=True,
        )
        st.markdown(market_badge(market_state), unsafe_allow_html=True)
        st.caption(fmt_trading_day(market_state))
        st.divider()

        _render_sidebar_nav()
        st.divider()

        _render_macro_watchlist(data.get("macro", {}))
        st.divider()

        _render_sidebar_tools(market_state)

        if st.session_state.get("_email_open", False):
            _render_email_section(portfolio, data, flag_statuses or [], td_str, smtp_cfg or {})


# ── Main helpers ──────────────────────────────────────────────────────────────

_TAB_SLOW = {
    "פונדמנטלס":   {"fundamentals", "earnings"},
    "חדשות":        {"news"},
    "אנליסטים":     {"targets", "upgrades"},
    "דגלים אדומים": {"upgrades", "commodities"},
    "סקירה":        {"targets"},
    "גרפים":        {"targets"},
}


def _load_secrets():
    """Load API keys and SMTP config from st.secrets. Returns (api_key, claude_key, smtp_cfg)."""
    try:
        api_key        = st.secrets.get("FINNHUB_API_KEY", "")
        claude_api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
        smtp_cfg = {
            "host":     st.secrets.get("SMTP_HOST", ""),
            "port":     st.secrets.get("SMTP_PORT", 587),
            "user":     st.secrets.get("SMTP_USER", ""),
            "password": st.secrets.get("SMTP_PASSWORD", ""),
        }
        return api_key, claude_api_key, smtp_cfg
    except Exception:
        return "", "", {}


def _render_deferred_banner(active, data):
    """Show a refresh banner when the active tab has data still loading in background."""
    deferred    = data.get("_deferred", frozenset())
    tab_missing = _TAB_SLOW.get(active, set()) & deferred
    if tab_missing:
        col_msg, col_btn = st.columns([6, 1])
        with col_msg:
            st.caption("📡 חלק מהנתונים עדיין בטעינת רקע — לחץ רענן לעדכון מיידי")
        with col_btn:
            if st.button("🔄", key="_bg_refresh", help="רענן נתוני רקע"):
                st.cache_data.clear()
                st.rerun()


def _render_tab_content(active, portfolio, data, market_state, td_str, api_key, claude_api_key):
    """Route to the correct tab renderer based on active tab name."""
    if active == "סקירה":
        render_overview(portfolio, data, market_state, td_str)
    elif active == "תיק שלי":
        render_portfolio(portfolio, data)
    elif active == "גרפים":
        render_charts(portfolio, data)
    elif active == "אנליסטים":
        render_analysts(portfolio, data, td_str, claude_api_key)
    elif active == "פונדמנטלס":
        render_fundamentals(portfolio, data, td_str)
    elif active == "דגלים אדומים":
        render_red_flags(portfolio, data, td_str)
    elif active == "חדשות":
        render_news(portfolio, data, td_str, claude_api_key)
    elif active == "💡 המלצות":
        render_suggestions(portfolio, data, td_str, api_key)
    elif active == "🔬 ניתוח":
        render_analysis(portfolio, data, td_str, api_key, claude_api_key)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    portfolio    = load_portfolio()
    market_state = get_market_state()
    td_str       = market_state["last_trading_day"].isoformat()
    market_open  = market_state.get("is_open", False)
    _log.info("Dashboard starting", extra={"trading_day": td_str, "market_open": market_open})

    api_key, claude_api_key, smtp_cfg = _load_secrets()

    if "active_tab" not in st.session_state:
        st.session_state.active_tab = _ALL_TABS[0]
    active = st.session_state.active_tab

    data = load_all_data(portfolio, market_state, api_key, active_tab=active)

    flag_statuses        = get_all_flag_statuses(portfolio, data)
    n_triggered, n_watch = get_flag_summary(portfolio, data)
    _auto_send_alert(portfolio, flag_statuses, td_str, smtp_cfg)

    _render_sidebar(portfolio, data, market_state, smtp_cfg, flag_statuses, td_str)

    st.markdown(
        '<div dir="rtl" style="font-size:11px;color:#555;margin-bottom:8px">'
        'תיק ה-AI &amp; תשתיות &nbsp;·&nbsp; Yahoo Finance · Finviz · Finnhub'
        '</div>',
        unsafe_allow_html=True,
    )

    _render_kpi_header(portfolio, data, n_triggered, n_watch)
    _render_secondary_tab_bar()
    _render_deferred_banner(active, data)
    _render_tab_content(active, portfolio, data, market_state, td_str, api_key, claude_api_key)


if __name__ == "__main__":
    main()
