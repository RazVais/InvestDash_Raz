"""מניה — one ticker at a time (chart, Monte Carlo, AI/analyst panel) + idea screening.

The ideas sub-tab merges the old 💡 המלצות and 🔬 ניתוח tabs, which listed the
same curated SUGGESTIONS twice.
"""

import streamlit as st

from src.config import HE
from src.tabs.analysis_tab import render_analysis
from src.tabs.charts import CHART_SECTIONS, render_charts
from src.tabs.planning_tab import render_position_sizer
from src.tabs.suggestions_tab import render_suggestions


def render_ticker(portfolio, data, td_str, api_key="", claude_api_key=""):
    tab_chart, tab_ideas = st.tabs([HE["sub_chart"], HE["sub_ideas"]])
    with tab_chart:
        render_charts(portfolio, data, td_str, claude_api_key, sections=CHART_SECTIONS)
        sel = st.session_state.get("chart_sel")
        if sel:
            render_position_sizer(portfolio, data, sel)
    with tab_ideas:
        render_suggestions(portfolio, data, td_str, api_key)
        st.divider()
        render_analysis(portfolio, data, td_str, api_key, claude_api_key)
