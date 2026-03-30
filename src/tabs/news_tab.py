"""News tab — latest articles per ticker."""

import pandas as pd
import streamlit as st

from src.config    import HE, COLOR, TICKER_NAMES
from src.portfolio import all_tickers


def render_news(portfolio, data):
    news    = data["news"]
    tickers = sorted(all_tickers(portfolio))

    sel = st.selectbox(
        "בחר מניה",
        ["הכל"] + tickers,
        key="news_sel",
        format_func=lambda t: t if t == "הכל" else f"{t} — {TICKER_NAMES.get(t,'')}",
    )

    show_tickers = tickers if sel == "הכל" else [sel]

    for t in show_tickers:
        articles = news.get(t, [])
        if not articles:
            continue

        st.markdown(
            f'<div style="direction:rtl;font-weight:700;color:{COLOR["primary"]};'
            f'margin-top:12px;font-size:13px">{t} — {TICKER_NAMES.get(t,"")}</div>',
            unsafe_allow_html=True,
        )

        for art in articles:
            pub  = art.get("published")
            date_str = pub.strftime("%d.%m.%Y %H:%M") if pd.notna(pub) else ""
            link = art.get("link", "#")
            title = art.get("title", "")
            publisher = art.get("publisher", "")

            st.markdown(
                f'<div style="direction:rtl;padding:6px 0;border-bottom:1px solid #222">'
                f'<a href="{link}" target="_blank" style="color:#fff;text-decoration:none;font-size:12px">'
                f'{title}</a>'
                f'<br><span style="font-size:10px;color:{COLOR["text_dim"]}">'
                f'{publisher} &nbsp;·&nbsp; {date_str}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
