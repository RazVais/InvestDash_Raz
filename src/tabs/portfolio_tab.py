"""Portfolio tab — multi-lot P&L table, add/edit/remove lot forms."""

from datetime import date

import streamlit as st

from src.config import COLOR, TICKER_NAMES, guess_layer
from src.data.prices import lookup_buy_price
from src.portfolio import (
    add_lot,
    all_tickers,
    lots_for_ticker,
    remove_lot,
    remove_ticker,
    update_lot,
)
from src.ui_helpers import color_legend, section_title, term_glossary


def render_portfolio(portfolio, data):
    prices = data["prices"]

    _render_pnl_table(portfolio, prices)
    st.divider()

    c1, c2, c3 = st.columns(3)
    with c1:
        _form_add_lot(portfolio)
    with c2:
        _form_edit_lot(portfolio)
    with c3:
        _form_remove(portfolio)


def _render_pnl_table(portfolio, prices):
    section_title("פירוט תיק", "עלות, שווי ורווח/הפסד לפי תאריכי קנייה (לוטים)")

    _TH = f"padding:5px 8px;color:{COLOR['primary']};border-bottom:2px solid #333;font-size:11px;text-align:right"
    _TD = "padding:5px 8px;font-size:11px"
    _SPACER = (
        '<tr style="height:6px;background:#0e1117">'
        '<td colspan="7" style="padding:0;border:none"></td>'
        '</tr>'
    )

    rows_html       = ""
    grand_cost      = grand_value = grand_pnl = 0.0

    for t in sorted(all_tickers(portfolio)):
        p = prices.get(t)
        cur_price = p["price"] if p else None
        lot_rows  = []
        t_cost = t_value = t_pnl = t_shares = 0.0

        for _layer, lot in lots_for_ticker(portfolio, t):
            shares = lot.get("shares", 0)
            if shares <= 0:
                continue
            bd = lot["buy_date"]
            bp = lookup_buy_price(t, bd, prices)
            cost  = shares * bp if bp else None
            value = shares * cur_price if cur_price else None
            pnl   = (value - cost) if (cost is not None and value is not None) else None
            pnl_pct = (pnl / cost * 100) if (pnl is not None and cost and cost > 0) else None

            t_shares += shares
            if cost is not None:
                t_cost += cost
            if value is not None:
                t_value += value
            if pnl is not None:
                t_pnl += pnl

            bp_str    = f"${bp:.2f}"    if bp        else "—"
            cost_str  = f"${cost:.0f}"  if cost      else "—"
            value_str = f"${value:.0f}" if value      else "—"
            pnl_c     = COLOR["positive"] if (pnl or 0) >= 0 else COLOR["negative"]
            pnl_str   = f'<span style="color:{pnl_c}">${pnl:+,.0f} ({pnl_pct:+.1f}%)</span>' if pnl is not None else "—"

            lot_rows.append(
                f'<tr style="background:#161616">'
                f'<td style="{_TD};padding-right:20px;color:{COLOR["text_dim"]};'
                f'border-left:3px solid #2a3a2a">{bd}</td>'
                f'<td style="{_TD}"></td>'
                f'<td style="{_TD}">{shares:.3f}</td>'
                f'<td style="{_TD}">{bp_str}</td>'
                f'<td style="{_TD}">{cost_str}</td>'
                f'<td style="{_TD}">{value_str}</td>'
                f'<td style="{_TD}">{pnl_str}</td>'
                f'</tr>'
            )

        if not lot_rows:
            continue

        cur_str   = f"${cur_price:.2f}" if cur_price else "—"
        cost_str  = f"${t_cost:,.0f}"  if t_cost > 0  else "—"
        val_str   = f"${t_value:,.0f}" if t_value > 0 else "—"
        if t_cost > 0 and t_value > 0:
            tot_pnl_c   = COLOR["positive"] if t_pnl >= 0 else COLOR["negative"]
            tot_pnl_pct = (t_pnl / t_cost * 100) if t_cost > 0 else 0.0
            tot_str = (f'<span style="color:{tot_pnl_c};font-weight:700">'
                       f'${t_pnl:+,.0f} ({tot_pnl_pct:+.1f}%)</span>')
        else:
            tot_str = f'<span style="color:{COLOR["text_dim"]}">—</span>'

        # Spacer between ticker groups (not before the first one)
        if rows_html:
            rows_html += _SPACER

        # Ticker header row — top border + left accent bar for visual grouping
        _HDR_TD = (
            f"{_TD};font-weight:700;border-top:2px solid #2a2a2a;"
            f"border-bottom:1px solid #2a2a2a"
        )
        rows_html += (
            f'<tr style="background:{COLOR["bg_dark"]}">'
            f'<td style="{_HDR_TD};color:{COLOR["primary"]};'
            f'border-left:3px solid {COLOR["primary"]}">{t}</td>'
            f'<td style="{_HDR_TD};font-size:10px;color:{COLOR["text_dim"]}">{TICKER_NAMES.get(t,"")}</td>'
            f'<td style="{_HDR_TD}">{t_shares:.3f}</td>'
            f'<td style="{_HDR_TD}">{cur_str}</td>'
            f'<td style="{_HDR_TD}">{cost_str}</td>'
            f'<td style="{_HDR_TD}">{val_str}</td>'
            f'<td style="{_HDR_TD}">{tot_str}</td>'
            f'</tr>'
        )
        rows_html += "".join(lot_rows)

        grand_cost  += t_cost
        grand_value += t_value
        grand_pnl   += t_pnl

    # Grand total
    g_pnl_c   = COLOR["positive"] if grand_pnl >= 0 else COLOR["negative"]
    g_pnl_pct = (grand_pnl / grand_cost * 100) if grand_cost > 0 else 0.0
    rows_html += (
        f'<tr style="background:#0a1a0a;border-top:2px solid {COLOR["primary"]}">'
        f'<td style="{_TD};font-weight:700;color:{COLOR["primary"]}">סה״כ</td>'
        f'<td style="{_TD}"></td>'
        f'<td style="{_TD}"></td>'
        f'<td style="{_TD}"></td>'
        f'<td style="{_TD};font-weight:700">${grand_cost:,.0f}</td>'
        f'<td style="{_TD};font-weight:700">${grand_value:,.0f}</td>'
        f'<td style="{_TD};font-weight:700;color:{g_pnl_c}">${grand_pnl:+,.0f} ({g_pnl_pct:+.1f}%)</td>'
        f'</tr>'
    )

    html = (
        f'<div dir="rtl" style="font-size:12px">'
        f'<table style="width:100%;border-collapse:collapse">'
        f'<thead><tr>'
        f'<th style="{_TH}">Ticker / תאריך</th>'
        f'<th style="{_TH}">שם</th>'
        f'<th style="{_TH}">כמות</th>'
        f'<th style="{_TH}">מחיר קנייה</th>'
        f'<th style="{_TH}">עלות</th>'
        f'<th style="{_TH}">שווי</th>'
        f'<th style="{_TH}">רווח/הפסד</th>'
        f'</tr></thead><tbody>{rows_html}</tbody></table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)
    color_legend([
        ("#4CAF50",  "רווח"),
        ("#F44336",  "הפסד"),
        ("#00cf8d",  "שורת טיקר — סיכום כולל"),
        ("#161616",  "שורת לוט — קנייה ספציפית"),
    ])
    term_glossary([
        ("לוט",           "קנייה אחת של מניה — כמות + תאריך ספציפיים. ניתן להחזיק מספר לוטים לאותו טיקר."),
        ("מחיר קנייה",    "מחיר הסגירה ההיסטורי של הנייר ביום הקנייה — נשלף מ-Yahoo Finance."),
        ("עלות",          "כמות המניות × מחיר הקנייה ההיסטורי."),
        ("שווי",          "כמות המניות × מחיר הסגירה הנוכחי."),
        ("רווח/הפסד $",   "שווי נוכחי − עלות קנייה. ערך חיובי = רווח, שלילי = הפסד."),
        ("רווח/הפסד %",   "(רווח ÷ עלות) × 100. אחוז הרווח/הפסד יחסית לסכום ההשקעה."),
        ("סה\"כ",         "סיכום כל הלוטים של הטיקר — שורה ירוקה בראש כל טיקר."),
        ("מחיר נוכחי",    "מחיר הסגירה האחרון — נשלף מ-Yahoo Finance (עד 30 דקות איחור בשעות מסחר)."),
    ])


_NEW_TICKER_OPTION = "➕ טיקר חדש..."

def _form_add_lot(portfolio):
    with st.expander("➕ הוסף קנייה"):
        existing       = sorted(all_tickers(portfolio))
        ticker_options = existing + [_NEW_TICKER_OPTION]

        ticker_sel = st.selectbox("סימול (Ticker)", ticker_options, key="add_ticker_sel",
                                  format_func=lambda t: t if t != _NEW_TICKER_OPTION else "➕ הוסף טיקר חדש...")

        # Free-text input appears only when "new ticker" is chosen
        if ticker_sel == _NEW_TICKER_OPTION:
            ticker = st.text_input("סימול חדש (Ticker)", key="add_ticker_new",
                                   placeholder="e.g. NVDA").upper().strip()
        else:
            ticker = ticker_sel

        # Auto-assign layer — no user input needed
        layer = guess_layer(ticker) if ticker else list(portfolio["layers"].keys())[0]
        # Ensure the layer exists in this portfolio (it may have been renamed)
        if layer not in portfolio["layers"]:
            layer = list(portfolio["layers"].keys())[0]
        st.markdown(
            f'<div dir="rtl" style="font-size:11px;color:#aaaaaa;margin:4px 0 10px 0">'
            f'שכבה: <b style="color:#00cf8d">{layer}</b>'
            f'</div>',
            unsafe_allow_html=True,
        )

        shares = st.number_input("כמות מניות", min_value=0.001, step=0.001, format="%.3f", key="add_shares")
        bd     = st.date_input("תאריך קנייה", value=date.today(), key="add_date")

        if st.button("שמור קנייה", key="add_btn"):
            if not ticker:
                st.error("הכנס סימול תקין.")
            elif shares <= 0:
                st.error("כמות חייבת להיות גדולה מ-0.")
            else:
                add_lot(portfolio, layer, ticker, shares, bd)
                st.cache_data.clear()
                st.success(f"נוסף: {ticker} × {shares:.3f} @ {bd} — שכבה: {layer}")
                st.rerun()


def _form_edit_lot(portfolio):
    with st.expander("✏️ עדכן לוט"):
        tickers_with_lots = [
            t for t in sorted(all_tickers(portfolio))
            if any(lot["shares"] > 0 for _l, lot in lots_for_ticker(portfolio, t))
        ]
        if not tickers_with_lots:
            st.caption("אין לוטים לעריכה.")
            return

        t_sel = st.selectbox("בחר סימול", tickers_with_lots, key="edit_ticker")
        lots  = [(layer, lot) for layer, lot in lots_for_ticker(portfolio, t_sel) if lot["shares"] > 0]

        if not lots:
            st.caption("אין לוטים.")
            return

        lot_labels = [f"{lot['buy_date']} × {lot['shares']:.3f}" for _l, lot in lots]
        sel_idx    = st.selectbox("בחר לוט", range(len(lots)),
                                   format_func=lambda i: lot_labels[i], key="edit_lot_sel")
        sel_layer, sel_lot = lots[sel_idx]

        new_shares = st.number_input("כמות חדשה", value=float(sel_lot["shares"]),
                                      min_value=0.001, step=0.001, format="%.3f", key="edit_shares")
        new_date   = st.date_input("תאריך חדש", value=sel_lot["buy_date"], key="edit_date")

        if st.button("עדכן לוט", key="edit_btn"):
            update_lot(portfolio, sel_layer, t_sel, sel_lot["buy_date"], new_shares, new_date)
            st.cache_data.clear()
            st.success("לוט עודכן.")
            st.rerun()


def _form_remove(portfolio):
    with st.expander("🗑 הסר"):
        tickers_all = sorted(all_tickers(portfolio))
        if not tickers_all:
            st.caption("אין ניירות ערך בתיק.")
            return

        mode = st.radio("מצב", ["הסר לוט ספציפי", "הסר טיקר שלם"], key="rm_mode", horizontal=True)

        if mode == "הסר לוט ספציפי":
            t_sel = st.selectbox("סימול", tickers_all, key="rm_ticker")
            lots  = [(layer, lot) for layer, lot in lots_for_ticker(portfolio, t_sel)]
            if lots:
                lot_labels = [f"{lot['buy_date']} × {lot['shares']:.3f}" for _l, lot in lots]
                sel_idx    = st.selectbox("לוט", range(len(lots)),
                                           format_func=lambda i: lot_labels[i], key="rm_lot_sel")
                sel_layer, sel_lot = lots[sel_idx]
                if st.button("הסר לוט", key="rm_lot_btn"):
                    remove_lot(portfolio, sel_layer, t_sel, sel_lot["buy_date"])
                    st.cache_data.clear()
                    st.success(f"לוט הוסר: {t_sel} {sel_lot['buy_date']}")
                    st.rerun()
        else:
            t_sel = st.selectbox("סימול להסרה מלאה", tickers_all, key="rm_full_ticker")
            st.warning(f"זה יסיר את כל הלוטים של {t_sel}!")
            if st.button(f"הסר את {t_sel}", key="rm_full_btn"):
                remove_ticker(portfolio, t_sel)
                st.cache_data.clear()
                st.success(f"{t_sel} הוסר מהתיק.")
                st.rerun()
