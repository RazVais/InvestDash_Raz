"""Fundamentals tab — valuation table, earnings dates, dividends, EPS trend."""

import contextlib
from datetime import date

import streamlit as st

from src.config import COLOR, PORTFOLIO_ETFS, TICKER_NAMES
from src.data.analysts import get_eps_trend
from src.portfolio import all_tickers
from src.ui_helpers import color_legend, section_title, term_glossary


def render_fundamentals(portfolio, data, td_str):
    prices       = data["prices"]
    fundamentals = data["fundamentals"]
    earnings     = data["earnings"]
    tickers      = sorted(all_tickers(portfolio))

    _render_valuation_table(tickers, fundamentals, prices)
    st.divider()
    _render_earnings_dividends(tickers, prices, earnings)
    st.divider()
    _render_eps_trend(tickers, td_str)


def _render_valuation_table(tickers, fundamentals, prices):
    section_title("נתוני פונדמנטלס", "נתוני הערכת שווי, רווחיות ומבנה ההון לפי Finviz")

    _TH = f"padding:5px 8px;color:{COLOR['primary']};border-bottom:1px solid #333;font-size:11px;text-align:right"
    _TD = "padding:5px 8px;font-size:11px"

    cols1 = [("pe","P/E"), ("forward_pe","P/E קדימה"), ("peg","PEG"), ("pegy","PEGY"),
             ("eps_ttm","EPS"), ("roe","ROE"), ("roa","ROA"), ("pb","P/B"), ("ps","P/S"), ("debt_eq","Debt/Eq")]
    cols2 = [("market_cap","שווי שוק"), ("short_float","Short Float"), ("inst_own","מוסדי"),
             ("sector","סקטור"), ("industry","תעשייה"), ("div_yield_fv","דיבידנד %")]

    def _peg_color(val_str: str) -> str:
        """Green <1 (undervalued growth), yellow 1–2 (fair), red >2 (expensive)."""
        try:
            v = float(str(val_str).replace(",", ""))
            if v <= 0:
                return COLOR["text_dim"]
            if v < 1.0:
                return COLOR["positive"]
            if v < 2.0:
                return COLOR["warning"]
            return COLOR["negative"]
        except (ValueError, TypeError):
            return COLOR["text_dim"]

    def _compute_pegy(f: dict) -> str:
        """PEGY = P/E ÷ (EPS_growth% + div_yield%). Lynch: <1 = attractive."""
        try:
            pe   = float(str(f.get("pe",  "")).replace(",", ""))
            grow = float(str(f.get("eps_next_y", "")).replace("%", "").replace(",", ""))
            dy   = float(str(f.get("div_yield_fv", "0")).replace("%", "").replace(",", ""))
            denom = grow + dy
            if pe <= 0 or denom <= 0:
                return "—"
            return f"{pe / denom:.2f}"
        except (ValueError, TypeError):
            return "—"

    for title, cols in [("ערכים והכנסות", cols1), ("שוק ובעלות", cols2)]:
        st.markdown(f'<b style="direction:rtl">{title}</b>', unsafe_allow_html=True)
        rows = ""
        for t in tickers:
            f = fundamentals.get(t, {})
            # Inject computed PEGY into the fundamentals dict for this render
            f = dict(f)
            if t not in PORTFOLIO_ETFS:
                f["pegy"] = _compute_pegy(f)
            if t in PORTFOLIO_ETFS:
                # ETF: replace all data cells with a single spanning note
                etf_note = (
                    f'<span style="color:{COLOR["text_dim"]};font-size:11px">'
                    f'ETF — אין נתוני פונדמנטלס (ללא רווחים עצמיים, ללא הון עצמי)</span>'
                )
                row = (
                    f'<td style="{_TD};font-weight:700;color:{COLOR["primary"]}">{t}</td>'
                    f'<td colspan="{len(cols)}" style="{_TD}">{etf_note}</td>'
                )
            else:
                row = f'<td style="{_TD};font-weight:700;color:{COLOR["primary"]}">{t}</td>'
                for key, _ in cols:
                    val = f.get(key, "—")
                    # Color PEG and PEGY
                    if key in ("peg", "pegy") and val and val != "—":
                        color = _peg_color(val)
                        val = f'<span style="color:{color};font-weight:700">{val}</span>'
                    row += f'<td style="{_TD}">{val}</td>'
            rows += f"<tr>{row}</tr>"

        header_cells = (
            f'<th style="{_TH}">Ticker</th>'
            + "".join(f'<th style="{_TH}">{lbl}</th>' for _, lbl in cols)
        )
        html = (
            f'<div dir="rtl" style="font-size:12px;overflow-x:auto">'
            f'<table style="width:100%;border-collapse:collapse">'
            f'<thead><tr>{header_cells}</tr></thead>'
            f'<tbody>{rows}</tbody></table></div>'
        )
        st.markdown(html, unsafe_allow_html=True)
        st.write("")
    term_glossary([
        ("P/E",         "Price-to-Earnings — מחיר המניה חלקי הרווח למניה (EPS). P/E גבוה = ציפיות צמיחה גבוהות. S&P500 ממוצע ≈ 20–25."),
        ("P/E קדימה",   "Forward P/E — מחיר המניה חלקי תחזית הרווח ל-12 חודשים הבאים. נמוך מ-P/E ההיסטורי = צמיחה צפויה."),
        ("PEG",         "Price/Earnings-to-Growth (Lynch) — P/E חלקי קצב צמיחת הרווח השנתי. מתחת 1 = צמיחה זולה 🟢, 1–2 = הוגן 🟡, מעל 2 = יקר 🔴."),
        ("PEGY",        "PEG + Yield (Lynch) — P/E חלקי (צמיחה% + תשואת דיבידנד%). מתאים לחברות שמחלקות דיבידנד — מתחת 1 = אטרקטיבי."),
        ("EPS",         "Earnings Per Share (TTM) — רווח למניה ב-12 חודשים האחרונים (Trailing Twelve Months)."),
        ("ROE",         "Return on Equity — תשואה על ההון העצמי. מעל 15% = ניהול הון יעיל. מדד חשוב לרווחיות."),
        ("ROA",         "Return on Assets — תשואה על הנכסים הכוללים. מדד ליעילות השימוש בנכסי החברה."),
        ("P/B",         "Price-to-Book — מחיר המניה חלקי שווי הספרים. מתחת ל-1 = מניה זולה ביחס לנכסים."),
        ("P/S",         "Price-to-Sales — שווי שוק חלקי הכנסות. שימושי לחברות ללא רווח עדיין (סטארטאפ/צמיחה)."),
        ("Debt/Eq",     "Debt-to-Equity — יחס חוב להון עצמי. מעל 2 = ממונף גבוה, מתחת 0.5 = מאזן שמרני."),
        ("שווי שוק",   "Market Cap — מחיר מניה × מספר מניות. Mega Cap > $200B, Large Cap > $10B."),
        ("Short Float", "אחוז המניות שמשקיעים מכרו בחסר (Short) — מעל 10% = לחץ שלילי / פוטנציאל Short Squeeze."),
        ("מוסדי",       "Institutional Ownership — אחוז המניות בידי קרנות, בנקים, ביטוח. מוסדי גבוה = אמון מוסדי."),
        ("דיבידנד %",   "Dividend Yield — הדיבידנד השנתי לחלק מחיר המניה. מדד תשואה שוטפת."),
    ])


def _render_earnings_dividends(tickers, prices, earnings):
    section_title("דוחות רווחים ודיבידנדים", "תאריך הדוח הרבעוני הבא ותשואת הדיבידנד")

    today = date.today()
    _TH   = f"padding:5px 8px;color:{COLOR['primary']};border-bottom:1px solid #333;font-size:11px;text-align:right"
    _TD   = "padding:5px 8px;font-size:12px"
    rows  = ""

    for t in tickers:
        p   = prices.get(t)
        ed  = earnings.get(t)
        div       = p.get("div_yield", 0.0) if p else 0.0
        div_rate  = p.get("div_rate",  0.0) if p else 0.0

        # Days to earnings
        if ed is not None:
            try:
                ed_date = ed.date() if hasattr(ed, "date") else ed
                days    = (ed_date - today).days
                if days < 0:
                    earn_str = f'<span style="color:{COLOR["text_dim"]}">עבר ({ed_date.strftime("%d.%m.%y")})</span>'
                elif days <= 14:
                    earn_str = f'<span style="color:{COLOR["negative"]};font-weight:700">בעוד {days} יום ({ed_date.strftime("%d.%m.%y")})</span>'
                elif days <= 30:
                    earn_str = f'<span style="color:{COLOR["warning"]}">בעוד {days} יום ({ed_date.strftime("%d.%m.%y")})</span>'
                else:
                    earn_str = f'{ed_date.strftime("%d.%m.%Y")} (בעוד {days} יום)'
            except Exception:
                earn_str = str(ed)
        else:
            earn_str = f'<span style="color:{COLOR["text_dim"]}">—</span>'

        if div and div > 0.01:
            rate_part = (
                f' <span style="color:{COLOR["text_dim"]};font-size:10px">(${div_rate:.2f}/מניה/שנה)</span>'
                if div_rate and div_rate > 0 else ""
            )
            div_str = (
                f'<span style="color:{COLOR["positive"]};font-weight:700">{div:.2f}%</span>'
                + rate_part
            )
        else:
            div_str = f'<span style="color:{COLOR["text_dim"]}">ללא דיבידנד</span>'

        rows += (
            f'<tr>'
            f'<td style="{_TD};font-weight:700;color:{COLOR["primary"]}">{t}</td>'
            f'<td style="{_TD};font-size:10px;color:{COLOR["text_dim"]}">{TICKER_NAMES.get(t,"")}</td>'
            f'<td style="{_TD}">{earn_str}</td>'
            f'<td style="{_TD}">{div_str}</td>'
            f'</tr>'
        )

    html = (
        f'<div dir="rtl" style="font-size:12px">'
        f'<table style="width:100%;border-collapse:collapse">'
        f'<thead><tr>'
        f'<th style="{_TH}">Ticker</th>'
        f'<th style="{_TH}">שם</th>'
        f'<th style="{_TH}">דוח הבא</th>'
        f'<th style="{_TH}">דיבידנד</th>'
        f'</tr></thead><tbody>{rows}</tbody></table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)
    color_legend([
        ("#F44336",  "דוח בעוד ≤14 יום — דחיפות גבוהה"),
        ("#FF9800",  "דוח בעוד 15–30 יום — מעקב"),
        ("#4CAF50",  "דיבידנד > 0.05%"),
        ("#aaaaaa",  "ללא דיבידנד / דוח רחוק"),
    ])
    term_glossary([
        ("דוח רווחים",     "Earnings Report — פרסום רבעוני של הכנסות, רווח גולמי, EPS בפועל מול תחזית. משפיע חזק על המחיר."),
        ("EPS Beat",       "הרווח בפועל גבוה מתחזית האנליסטים — בדרך כלל חיובי למחיר."),
        ("EPS Miss",       "הרווח בפועל נמוך מתחזית — בדרך כלל שלילי למחיר."),
        ("Guidance",       "תחזית ההנהלה לרבעון/שנה הבאה — לעתים חשוב יותר מהתוצאות עצמן."),
        ("Ex-Dividend",    "תאריך שאחריו קונים חדשים אינם זכאים לדיבידנד הקרוב."),
        ("Dividend Yield", "תשואת הדיבידנד השנתית ביחס למחיר — VOO משלם ≈1.3%, מניות ערך לרוב מעל 2%."),
    ])


def _render_eps_trend(tickers, td_str):
    section_title("מגמת EPS", "תחזיות רווח למניה — לפי אנליסטים (Yahoo Finance)")
    sel = st.selectbox("בחר סימול", tickers, key="eps_sel_v2",
                       format_func=lambda t: f"{t} — {TICKER_NAMES.get(t,'')}")
    if st.button("טען מגמת EPS", key="eps_btn_v2"):
        result = get_eps_trend(sel, td_str)
        if isinstance(result, str):
            st.error(result)
        elif result is not None and not (hasattr(result, "empty") and result.empty):
            _render_eps_table(result)
        else:
            st.info("אין נתוני מגמת EPS.")

    term_glossary([
        ("Current Estimate",  "תחזית העדכנית ביותר של האנליסטים לרווח למניה (EPS) לאותה תקופה."),
        ("7 / 30 / 60 / 90 Days Ago", "תחזית EPS לפני N ימים — עלייה מול הישן = אנליסטים אופטימיים יותר (ירוק), ירידה = פסימיים יותר (אדום)."),
        ("Current Qtr.",      "הרבעון הפיסקלי הנוכחי (3 חודשים). תאריך הדוח מופיע בכותרת העמודה."),
        ("Next Qtr.",         "הרבעון הפיסקלי הבא — תחזית מוקדמת, פחות בטוחה."),
        ("Current Year",      "שנת הכספים הנוכחית — סכום 4 רבעונים."),
        ("Next Year",         "שנת הכספים הבאה — תחזית ארוכת טווח, כפופה לשינויים משמעותיים."),
        ("EPS",               "Earnings Per Share — רווח נקי של החברה חלקי מספר המניות. הגדלה עקבית = צמיחה בריאה."),
    ], label="📖 מקרא — מגמת EPS")


def _render_eps_table(df):
    """Render the yfinance eps_trend DataFrame as a styled table."""
    _COL = {"0q": "Current Qtr.", "+1q": "Next Qtr.", "0y": "Current Year", "+1y": "Next Year"}
    _ROW = {
        "current":    "Current Estimate",
        "7daysAgo":   "7 Days Ago",
        "30daysAgo":  "30 Days Ago",
        "60daysAgo":  "60 Days Ago",
        "90daysAgo":  "90 Days Ago",
    }

    # Normalise — yfinance may deliver columns or index in either direction
    with contextlib.suppress(Exception):
        df = df.rename(columns=_COL, index=_ROW)

    cols = [v for v in _COL.values() if v in df.columns]
    rows = [v for v in _ROW.values() if v in df.index]
    if not cols or not rows:
        st.dataframe(df, use_container_width=True)
        return

    df = df.loc[rows, cols]

    # Pull "Current Estimate" row for colour comparison
    curr_row = df.loc["Current Estimate"] if "Current Estimate" in df.index else None
    prev_row = df.loc["7 Days Ago"]       if "7 Days Ago"       in df.index else None

    def _cell_color(col, row_label, val):
        """Green if current > 7daysAgo, red if lower, neutral otherwise."""
        if row_label != "Current Estimate" or curr_row is None or prev_row is None:
            return "#cccccc"
        try:
            c = float(curr_row[col])
            p = float(prev_row[col])
            if c > p:
                return "#4CAF50"
            if c < p:
                return "#F44336"
        except Exception:
            pass
        return "#ffffff"

    _TH = ("padding:10px 16px;text-align:left;color:#888888;font-size:12px;"
           "font-weight:400;border-bottom:1px solid #333")
    _TD_label = ("padding:10px 16px;font-size:13px;color:#aaaaaa;"
                 "border-bottom:1px solid #222;white-space:nowrap")
    _TD_val   = "padding:10px 16px;font-size:13px;border-bottom:1px solid #222;text-align:right"

    header = (
        f'<th style="{_TH}">Currency in USD</th>'
        + "".join(f'<th style="{_TH};text-align:right">{c}</th>' for c in cols)
    )

    body = ""
    for row_label in rows:
        is_current = row_label == "Current Estimate"
        weight     = "font-weight:700;color:#ffffff" if is_current else "font-weight:400"
        bg         = "background:#1e2a1e" if is_current else ""
        cells = f'<td style="{_TD_label};{weight};{bg}">{row_label}</td>'
        for col in cols:
            try:
                raw = df.loc[row_label, col]
                val_str = f"{float(raw):.2f}" if raw is not None else "—"
            except Exception:
                val_str = "—"
            color = _cell_color(col, row_label, raw if "raw" in dir() else None)
            fw    = "font-weight:700" if is_current else ""
            cells += (f'<td style="{_TD_val};color:{color};{fw};{bg}">{val_str}</td>')
        body += f'<tr>{cells}</tr>'

    html = (
        '<div style="overflow-x:auto;margin-top:8px">'
        '<table style="width:100%;border-collapse:collapse;background:#111111;'
        'border-radius:8px;overflow:hidden">'
        f'<thead><tr>{header}</tr></thead>'
        f'<tbody>{body}</tbody>'
        '</table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)
