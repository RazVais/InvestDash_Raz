"""Suggestions tab — 3-5 complementary stock picks based on current portfolio."""

import streamlit as st

from src.config   import COLOR, SUGGESTIONS, TICKER_NAMES
from src.portfolio import all_tickers
from src.data.prices   import get_stock_data
from src.data.analysts import get_consensus, get_analyst_targets
from src.ui_helpers import section_title, color_legend, term_glossary


def render_suggestions(portfolio, data, td_str, api_key=""):
    owned = set(all_tickers(portfolio))

    candidates = [s for s in SUGGESTIONS if s["ticker"] not in owned]

    section_title(
        "המלצות — מניות משלימות",
        "הצעות מגוונות לשיפור התיק — לא ייעוץ השקעות, עשה בדיקה עצמאית",
    )

    if not candidates:
        st.info("כל המניות המוצעות כבר בתיק שלך. עדיין תיק מעולה!")
        return

    # ── Live data for candidates ─────────────────────────────────────────────
    tickers_tuple = tuple(sorted(s["ticker"] for s in candidates))
    prices    = get_stock_data(tickers_tuple, td_str)
    targets   = get_analyst_targets(tickers_tuple, td_str)
    consensus = get_consensus(tickers_tuple, td_str, api_key)

    # ── Render cards ─────────────────────────────────────────────────────────
    for s in candidates:
        t   = s["ticker"]
        p   = prices.get(t)
        tgt = targets.get(t) or {}
        con = consensus.get(t, {})

        price_val  = p["price"]   if p else None
        change_val = p["change"]  if p else None
        label      = con.get("label", "N/A")

        # Upside %
        upside_str = "—"
        upside_color = COLOR["text_dim"]
        if price_val and tgt.get("mean"):
            up = ((tgt["mean"] - price_val) / price_val) * 100
            upside_color = COLOR["positive"] if up >= 0 else COLOR["negative"]
            upside_str = f"{up:+.1f}%"

        # Consensus color
        if "Strong Buy" in label or "Buy" in label:
            label_color = COLOR["positive"]
        elif "Sell" in label:
            label_color = COLOR["negative"]
        else:
            label_color = COLOR["neutral"]

        # Price change color
        change_color = COLOR["positive"] if (change_val or 0) >= 0 else COLOR["negative"]
        price_str  = f"${price_val:.2f}" if price_val else "—"
        change_str = f"{change_val:+.2f}%" if change_val is not None else "—"

        # Complement tags (only show portfolio tickers that actually complement)
        comp_tags = "".join(
            f'<span style="background:{COLOR["bg_dark"]};color:{COLOR["primary"]};'
            f'border:1px solid {COLOR["primary"]}33;border-radius:4px;'
            f'padding:1px 7px;font-size:10px;margin-left:4px">{c}</span>'
            for c in s["complements"]
            if c in owned
        ) or ""

        card_html = (
            f'<div dir="rtl" style="'
            f'background:#111827;border:1px solid #1f2937;border-radius:10px;'
            f'padding:14px 18px;margin-bottom:12px">'

            # Header row: ticker + name + theme badge
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">'
            f'  <div>'
            f'    <span style="font-size:18px;font-weight:800;color:{COLOR["primary"]}">{t}</span>'
            f'    <span style="font-size:13px;color:{COLOR["text_dim"]};margin-right:8px">{s["name"]}</span>'
            f'  </div>'
            f'  <span style="background:#00cf8d22;color:{COLOR["primary"]};border-radius:20px;'
            f'    padding:2px 12px;font-size:11px;white-space:nowrap">{s["theme"]}</span>'
            f'</div>'

            # Rationale
            f'<div style="font-size:12px;color:#cccccc;margin-bottom:10px;line-height:1.6">'
            f'{s["rationale"]}'
            f'</div>'

            # Stats row
            f'<div style="display:flex;gap:24px;align-items:center;flex-wrap:wrap">'
            f'  <div style="font-size:12px">'
            f'    <span style="color:{COLOR["text_dim"]}">מחיר: </span>'
            f'    <span style="font-weight:700">{price_str}</span>'
            f'    <span style="color:{change_color};margin-right:6px"> {change_str}</span>'
            f'  </div>'
            f'  <div style="font-size:12px">'
            f'    <span style="color:{COLOR["text_dim"]}">אפסייד: </span>'
            f'    <span style="color:{upside_color};font-weight:700">{upside_str}</span>'
            f'  </div>'
            f'  <div style="font-size:12px">'
            f'    <span style="color:{COLOR["text_dim"]}">קונצנזוס: </span>'
            f'    <span style="color:{label_color};font-weight:700">{label}</span>'
            f'  </div>'
            # Complement tags
            + (
                f'  <div style="font-size:12px;display:flex;align-items:center;gap:2px">'
                f'    <span style="color:{COLOR["text_dim"]}">משלים: </span>{comp_tags}'
                f'  </div>'
                if comp_tags else ""
            ) +
            f'</div>'  # end stats row
            f'</div>'  # end card
        )
        st.markdown(card_html, unsafe_allow_html=True)

    # ── Disclaimer ───────────────────────────────────────────────────────────
    st.markdown(
        f'<div dir="rtl" style="font-size:10px;color:{COLOR["text_dim"]};'
        f'border-top:1px solid #222;padding-top:8px;margin-top:4px">'
        f'⚠️ תוכן זה הוא לצורכי מידע בלבד ואינו מהווה ייעוץ השקעות. '
        f'כל השקעה כרוכה בסיכון. בצע בדיקה עצמאית לפני כל החלטה.'
        f'</div>',
        unsafe_allow_html=True,
    )

    color_legend([
        (COLOR["positive"], "קונצנזוס Buy / אפסייד חיובי"),
        (COLOR["negative"], "קונצנזוס Sell / אפסייד שלילי"),
        (COLOR["neutral"],  "קונצנזוס Hold / N/A"),
        (COLOR["primary"],  "טיקר משלים מהתיק שלך"),
    ])
    term_glossary([
        ("אפסייד %",    "פוטנציאל עלייה לפי יעד המחיר הממוצע של האנליסטים: (יעד − מחיר) / מחיר × 100."),
        ("קונצנזוס",   "ממוצע המלצות האנליסטים — Strong Buy / Buy / Hold / Sell."),
        ("משלים",      "טיקרים מהתיק הנוכחי שלך שהמניה המוצעת קשורה אליהם תמטית."),
        ("סטרימינג",   "מודל עסקי: רכישה מראש של זכויות על תפוקה עתידית במחיר קבוע — חשיפה לסחורה עם הוצאות תפעול נמוכות."),
    ])
