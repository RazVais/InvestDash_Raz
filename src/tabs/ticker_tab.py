"""מניה — one ticker at a time (chart, Monte Carlo, AI/analyst panel) + idea screening.

Any ticker can be analysed here, not only portfolio holdings: "🔍 נתח מניה חדשה"
fetches its data on demand and adds it to the picker for this session only.
"⭐ הוסף למעקב" then saves it as a starred watch-only name.

The ideas sub-tab merges the old 💡 המלצות and 🔬 ניתוח tabs, which listed the
same curated SUGGESTIONS twice.
"""

from datetime import date
import re
from typing import Dict, List, Optional

import streamlit as st

from src.config import HE, guess_layer, is_tase_numeric
from src.data.analysts import get_analyst_targets, get_consensus, get_upgrades_downgrades
from src.data.fundamentals import FINVIZ_AVAILABLE, get_finviz_fundamentals
from src.data.news import get_news
from src.data.prices import get_stock_data_with_info
from src.portfolio import add_lot, all_tickers, set_starred
from src.tabs.analysis_tab import render_analysis
from src.tabs.charts import CHART_SECTIONS, render_charts
from src.tabs.planning_tab import render_position_sizer
from src.tabs.suggestions_tab import render_suggestions

_ADHOC_KEY = "adhoc_tickers"
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def normalize_ticker(raw: str) -> Optional[str]:
    """Upper-case and validate a typed symbol (US-style or TASE numeric ID); None if invalid."""
    t = (raw or "").strip().upper().lstrip("$")
    if is_tase_numeric(t) or _TICKER_RE.match(t):
        return t
    return None


def _adhoc() -> List[str]:
    return st.session_state.setdefault(_ADHOC_KEY, [])


def fetch_adhoc_data(tickers, td_str, api_key="") -> Dict[str, dict]:
    """Fetch the per-ticker data the מניה page needs for tickers outside the loader.

    All fetchers are cached (prices 30 min, the rest 7 days / per day), so
    re-rendering an ad-hoc ticker costs nothing after the first look.
    """
    tickers = tuple(tickers)
    if not tickers:
        return {}
    out = {
        "prices":    get_stock_data_with_info(tickers, td_str),
        "targets":   get_analyst_targets(tickers),
        "consensus": get_consensus(tickers, td_str, api_key),
        "upgrades":  get_upgrades_downgrades(tickers),
        "news":      get_news(tickers, td_str),
    }
    if FINVIZ_AVAILABLE:
        out["fundamentals"] = get_finviz_fundamentals(tickers)
    return out


def merge_data(data: dict, extra: Dict[str, dict]) -> dict:
    """New data dict with ad-hoc entries layered on top (never mutates `data`)."""
    merged = dict(data)
    for key, values in (extra or {}).items():
        merged[key] = {**(data.get(key) or {}), **(values or {})}
    return merged


def _render_add_box(portfolio, td_str, api_key):
    """Text box + button that adds any ticker to the picker for this session."""
    with st.form("adhoc_add", clear_on_submit=True, border=False):
        c_in, c_btn = st.columns([4, 1])
        raw = c_in.text_input(HE["adhoc_label"], placeholder=HE["adhoc_placeholder"],
                              label_visibility="collapsed")
        submitted = c_btn.form_submit_button(HE["adhoc_btn"], use_container_width=True)
    if not submitted or not raw.strip():
        return
    t = normalize_ticker(raw)
    if t is None:
        st.error(HE["adhoc_invalid"].format(t=raw.strip()))
        return
    if t in all_tickers(portfolio):
        st.session_state.chart_sel = t
        st.info(HE["adhoc_owned"].format(t=t))
        return
    with st.spinner(HE["adhoc_loading"].format(t=t)):
        p = get_stock_data_with_info((t,), td_str).get(t)
    if not p or p.get("ohlcv") is None or p["ohlcv"].empty:
        st.error(HE["adhoc_no_data"].format(t=t))
        return
    lst = _adhoc()
    if t not in lst:
        lst.append(t)
    st.session_state.chart_sel = t


def _render_adhoc_bar(portfolio, sel):
    """Shown above the chart when the selected ticker is ad-hoc: keep it or drop it."""
    c_msg, c_keep, c_drop = st.columns([4, 1.3, 1])
    c_msg.markdown(
        f'<div dir="rtl" style="font-size:12px;color:#ff9800;padding-top:8px">'
        f'{HE["adhoc_not_saved"].format(t=sel)}</div>',
        unsafe_allow_html=True,
    )
    if c_keep.button(HE["adhoc_keep"], key=f"_adhoc_keep_{sel}", use_container_width=True):
        add_lot(portfolio, guess_layer(sel), sel, 0, date.today(), buy_price=None)
        set_starred(portfolio, sel, True)
        _adhoc().remove(sel)
        st.rerun()
    if c_drop.button(HE["adhoc_drop"], key=f"_adhoc_drop_{sel}", use_container_width=True):
        _adhoc().remove(sel)
        owned = sorted(all_tickers(portfolio))
        st.session_state.chart_sel = owned[0] if owned else None
        st.rerun()


def render_ticker(portfolio, data, td_str, api_key="", claude_api_key=""):
    _render_add_box(portfolio, td_str, api_key)
    owned = set(all_tickers(portfolio))
    adhoc = [t for t in _adhoc() if t not in owned]  # drop ones since added to the portfolio
    st.session_state[_ADHOC_KEY] = adhoc
    view = merge_data(data, fetch_adhoc_data(adhoc, td_str, api_key)) if adhoc else data

    tab_chart, tab_ideas = st.tabs([HE["sub_chart"], HE["sub_ideas"]])
    with tab_chart:
        sel = st.session_state.get("chart_sel")
        if sel in adhoc:
            _render_adhoc_bar(portfolio, sel)
        render_charts(portfolio, view, td_str, claude_api_key, sections=CHART_SECTIONS,
                      extra_tickers=adhoc)
        sel = st.session_state.get("chart_sel")
        if sel:
            render_position_sizer(portfolio, view, sel)
    with tab_ideas:
        render_suggestions(portfolio, data, td_str, api_key)
        st.divider()
        render_analysis(portfolio, data, td_str, api_key, claude_api_key)
