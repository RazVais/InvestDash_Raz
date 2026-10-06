"""תרגול — trading practice: intraday/backtest setups and both trade journals."""

import streamlit as st

from src.config import HE
from src.tabs.charts import PRACTICE_SECTIONS, render_charts
from src.tabs.trading_journal_ai_tab import render_trading_journal_ai
from src.tabs.trading_journal_tab import render_trading_journal


def render_practice(portfolio, data, td_str, claude_api_key=""):
    tab_setups, tab_journal, tab_ai = st.tabs(
        [HE["sub_setups"], HE["sub_journal"], HE["sub_journal_ai"]]
    )
    with tab_setups:
        render_charts(portfolio, data, td_str, claude_api_key, sections=PRACTICE_SECTIONS)
    with tab_journal:
        render_trading_journal(portfolio, data)
    with tab_ai:
        render_trading_journal_ai(claude_api_key=claude_api_key)
