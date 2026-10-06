"""היום — daily check-in: what needs attention, what moved, what's coming.

Composes existing renderers rather than re-implementing them:
  macro strip (overview) → attention list (flags + earnings this week) →
  market pulse + AI session briefing (analysts) → per-ticker daily briefs.
Everything here covers active tickers only (held ∪ starred).
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src.config import COLOR, HE
from src.portfolio import active_tickers
from src.tabs.analysts_tab import _render_market_pulse, _render_session_analysis
from src.tabs.daily_brief_tab import render_daily_brief
from src.tabs.overview import _render_macro_strip
from src.tabs.planning_tab import render_since_last
from src.ui_helpers import esc, section_title

_STATUS_ORDER = {"triggered": 0, "watch": 1}
_STATUS_LABEL = {"triggered": HE["flag_triggered"], "watch": HE["flag_watch"]}
_STATUS_COLOR = {"triggered": COLOR["negative"], "watch": COLOR["warning"]}


def _attention_flags(flags):
    """Non-ok flags, triggered first."""
    hot = [f for f in flags or [] if f.get("status") in _STATUS_ORDER]
    return sorted(hot, key=lambda f: (_STATUS_ORDER[f["status"]], f["ticker"]))


def _earnings_this_week(earnings, tickers, today=None, days=7):
    """[(ticker, date)] for reports due within `days`, soonest first."""
    today = today or date.today()
    horizon = today + timedelta(days=days)
    out = []
    for t in tickers:
        d = (earnings or {}).get(t)
        if d is None or pd.isna(d):
            continue
        d = pd.Timestamp(d).date()
        if today <= d <= horizon:
            out.append((t, d))
    return sorted(out, key=lambda x: x[1])


def _render_attention(data, tickers):
    section_title(HE["today_attention"], HE["today_attention_sub"])
    flags    = _attention_flags(data.get("_flags"))
    earnings = _earnings_this_week(data.get("earnings"), tickers)

    if not flags and not earnings:
        st.markdown(
            f'<div dir="rtl" style="color:{COLOR["positive"]};font-size:13px">'
            f'{HE["today_all_clear"]}</div>',
            unsafe_allow_html=True,
        )
        return

    rows = ""
    for f in flags:
        color = _STATUS_COLOR[f["status"]]
        rows += (
            f'<div style="display:flex;gap:10px;padding:5px 0;border-bottom:1px solid #1f2937">'
            f'<span style="color:{color};font-weight:700;min-width:80px">{_STATUS_LABEL[f["status"]]}</span>'
            f'<span style="font-weight:700;min-width:70px">{esc(f["ticker"])}</span>'
            f'<span style="color:#ccc">{esc(f["flag"])}</span>'
            f'<span style="color:{COLOR["text_dim"]};margin-right:auto">{esc(f.get("detail", ""))}</span>'
            f'</div>'
        )
    for t, d in earnings:
        days_left = (d - date.today()).days
        when = HE["today_earnings_today"] if days_left == 0 else f'{days_left} {HE["today_days"]}'
        rows += (
            f'<div style="display:flex;gap:10px;padding:5px 0;border-bottom:1px solid #1f2937">'
            f'<span style="color:{COLOR["primary"]};font-weight:700;min-width:80px">📅 {HE["today_earnings"]}</span>'
            f'<span style="font-weight:700;min-width:70px">{esc(t)}</span>'
            f'<span style="color:#ccc">{d.strftime("%d.%m")}</span>'
            f'<span style="color:{COLOR["text_dim"]};margin-right:auto">{when}</span>'
            f'</div>'
        )
    st.markdown(f'<div dir="rtl" style="font-size:12px">{rows}</div>', unsafe_allow_html=True)

    if flags and st.button(HE["today_flags_details"], key="_today_flags_btn"):
        st.session_state.active_tab = "דגלים אדומים"
        st.rerun()


def render_today(portfolio, data, td_str, claude_api_key=""):
    tickers = active_tickers(portfolio)
    _render_macro_strip(data.get("macro", {}))
    render_since_last(portfolio)
    _render_attention(data, tickers)
    st.divider()
    _render_market_pulse(tickers, data.get("prices", {}), data.get("consensus", {}),
                         data.get("targets", {}))
    st.divider()
    # Never block the daily check-in on Claude — the background warmup fills these in
    _render_session_analysis(portfolio, data, td_str, claude_api_key, wait_for_ai=False)
    st.divider()
    render_daily_brief(portfolio, data, td_str, claude_api_key, wait_for_ai=False)
