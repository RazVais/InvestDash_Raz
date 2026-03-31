"""News tab — company brief, sector, competitors, and latest articles."""

import streamlit as st

from src.config import COLOR, TICKER_NAMES, TICKER_PEERS, TICKER_SECTOR
from src.data.news import get_company_profile, get_today_summary
from src.market import get_market_state
from src.portfolio import all_tickers


def render_news(portfolio, data, td_str=None, claude_api_key=""):
    news    = data["news"]
    tickers = sorted(all_tickers(portfolio))

    if not tickers:
        st.info("הוסף ניירות ערך לתיק כדי לראות חדשות.")
        return

    if td_str is None:
        td_str = str(get_market_state()["last_trading_day"])

    sel = st.selectbox(
        "בחר מניה",
        tickers,
        key="news_sel",
        format_func=lambda t: f"{t} — {TICKER_NAMES.get(t, t)}",
    )

    _render_today_summary(sel, news, td_str, claude_api_key)
    st.divider()
    _render_company_brief(sel, td_str)
    st.divider()
    _render_articles(sel, news)


def _render_today_summary(ticker: str, news: dict, td_str: str, claude_api_key: str):
    """AI-generated Hebrew summary of today's most important news."""
    articles = news.get(ticker, [])
    summary  = get_today_summary(ticker, articles, td_str, claude_api_key)

    st.markdown(
        f'<div dir="rtl" style="font-weight:700;color:{COLOR["primary"]};'
        f'font-size:13px;margin-bottom:8px">🤖 סיכום חדשות היום — {ticker}</div>',
        unsafe_allow_html=True,
    )

    if summary:
        st.markdown(
            f'<div dir="rtl" style="font-size:13px;color:#e0e0e0;line-height:1.8;'
            f'background:#0d1f17;border:1px solid {COLOR["primary"]}33;'
            f'border-radius:8px;padding:14px 16px;margin-bottom:4px">'
            f'{summary}'
            f'</div>',
            unsafe_allow_html=True,
        )
    elif not claude_api_key:
        st.caption("הוסף ANTHROPIC_API_KEY לקובץ .streamlit/secrets.toml לקבלת סיכום יומי בעברית.")
    else:
        st.caption("אין חדשות מ-24 השעות האחרונות.")


def _render_company_brief(ticker: str, td_str: str):
    """Company profile card: description in Hebrew, sector, industry, competitors."""
    profile = get_company_profile(ticker, td_str)

    name     = profile.get("name") or TICKER_NAMES.get(ticker, ticker)
    _static  = TICKER_SECTOR.get(ticker, ("", ""))
    sector   = profile.get("sector") or _static[0]
    industry = profile.get("industry") or _static[1]
    desc     = profile.get("description", "")
    website  = profile.get("website", "")
    emp      = profile.get("employees")

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f'<div dir="rtl" style="margin-bottom:4px">'
        f'<span style="font-size:22px;font-weight:800;color:{COLOR["primary"]}">{ticker}</span>'
        f'<span style="font-size:15px;color:{COLOR["text_dim"]};margin-right:10px"> {name}</span>'
        + (f'<a href="{website}" target="_blank" style="font-size:11px;color:{COLOR["primary"]};'
           f'text-decoration:none;margin-right:8px">🌐 אתר</a>' if website else "")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Sector / industry / employees chips ───────────────────────────────────
    chips = []
    if sector:
        chips.append(("📊", sector))
    if industry:
        chips.append(("🏭", industry))
    if emp:
        chips.append(("👥", f"{emp:,} עובדים"))

    if chips:
        chip_html = "".join(
            f'<span style="background:#1f2937;border:1px solid #374151;border-radius:20px;'
            f'padding:2px 10px;font-size:11px;color:{COLOR["text_dim"]};margin-left:6px">'
            f'{icon} {label}</span>'
            for icon, label in chips
        )
        st.markdown(
            f'<div dir="rtl" style="margin-bottom:10px">{chip_html}</div>',
            unsafe_allow_html=True,
        )

    # ── Description (Hebrew, RTL) ─────────────────────────────────────────────
    if desc:
        sentences = desc.replace("  ", " ").split(". ")
        preview   = ". ".join(sentences[:3]).strip()
        if not preview.endswith("."):
            preview += "."

        st.markdown(
            f'<div dir="rtl" style="font-size:12px;color:#cccccc;line-height:1.8;'
            f'background:#111827;border-radius:8px;padding:12px 16px;margin-bottom:10px">'
            f'{preview}'
            f'</div>',
            unsafe_allow_html=True,
        )
        if len(sentences) > 3:
            with st.expander("קרא עוד"):
                st.markdown(
                    f'<div dir="rtl" style="font-size:12px;color:#cccccc;line-height:1.8">'
                    f'{desc}</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.caption(f"אין תיאור חברה זמין עבור {ticker}.")

    # ── Competitors ───────────────────────────────────────────────────────────
    peers = TICKER_PEERS.get(ticker, [])
    if peers:
        tags = "".join(
            f'<span style="background:#1a1f2e;border:1px solid #2d3748;border-radius:6px;'
            f'padding:3px 10px;font-size:11px;color:#ffffff;margin-left:6px;white-space:nowrap">'
            f'<span style="color:{COLOR["primary"]};font-weight:700">{sym}</span>'
            f' <span style="color:{COLOR["text_dim"]}">{nm}</span></span>'
            for sym, nm in peers
        )
        st.markdown(
            f'<div dir="rtl" style="margin-bottom:6px">'
            f'<span style="font-size:11px;color:{COLOR["text_dim"]};margin-left:8px">מתחרים עיקריים:</span>'
            f'{tags}</div>',
            unsafe_allow_html=True,
        )


def _render_articles(ticker: str, news: dict):
    """Render news articles for the selected ticker."""
    articles = news.get(ticker, [])

    st.markdown(
        f'<div dir="rtl" style="font-weight:700;color:{COLOR["primary"]};'
        f'font-size:13px;margin-bottom:8px">📰 חדשות אחרונות — {ticker}</div>',
        unsafe_allow_html=True,
    )

    if not articles:
        st.info(f"אין חדשות זמינות עבור {ticker} כרגע.")
        return

    for art in articles:
        pub       = art.get("published")
        date_str  = pub.strftime("%d.%m.%Y %H:%M") if pub else ""
        link      = art.get("link", "#")
        title     = art.get("title", "")
        publisher = art.get("publisher", "")

        st.markdown(
            f'<div dir="ltr" style="padding:8px 0;border-bottom:1px solid #1f2937">'
            f'<a href="{link}" target="_blank" '
            f'style="color:#ffffff;text-decoration:none;font-size:13px;font-weight:500;'
            f'line-height:1.5">{title}</a><br>'
            f'<span style="font-size:10px;color:{COLOR["text_dim"]}">'
            f'{publisher}'
            + (f' &nbsp;·&nbsp; {date_str}' if date_str else "")
            + '</span></div>',
            unsafe_allow_html=True,
        )
