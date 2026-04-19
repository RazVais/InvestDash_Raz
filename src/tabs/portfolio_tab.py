"""Portfolio tab — multi-lot P&L table, add/edit/remove lot forms."""

from datetime import date

import streamlit as st

from src.config import COLOR, TICKER_NAMES, guess_layer
from src.data.prices import get_current_price_or_daily_avg, lookup_buy_price
from src.portfolio import (
    add_lot,
    all_tickers,
    lots_for_ticker,
    remove_lot,
    remove_ticker,
    update_lot,
)
from src.tabs.trading_journal_tab import render_trading_journal
from src.ui_helpers import color_legend, section_title, term_glossary


def render_portfolio(portfolio, data):
    prices = data["prices"]

    tab_portfolio, tab_journal = st.tabs(["📊 תיק שלי", "📈 יומן עסקאות"])

    with tab_portfolio:
        _render_pnl_table(portfolio, prices)
        st.divider()
        c1, c2, c3 = st.columns(3)
        with c1:
            _form_add_lot(portfolio, prices)
        with c2:
            _form_edit_lot(portfolio, prices)
        with c3:
            _form_remove(portfolio)

    with tab_journal:
        render_trading_journal(portfolio, data)


def _render_pnl_table(portfolio, prices):
    section_title("פירוט תיק", "עלות, שווי ורווח/הפסד לפי תאריכי קנייה (לוטים)")

    _TH = (
        f"padding:5px 8px;color:{COLOR['primary']};"
        f"border-bottom:2px solid #333;font-size:11px;text-align:right"
    )
    _TD = "padding:5px 8px;font-size:11px"
    # Fixed column widths so every per-ticker table fragment is aligned
    _COL_W = ["14%", "22%", "9%", "11%", "12%", "12%", "20%"]
    _COLGROUP = "".join(f'<col style="width:{w}">' for w in _COL_W)

    def _make_table(tbody_html):
        return (
            f'<div dir="rtl" style="font-size:12px;margin:0">'
            f'<table style="width:100%;border-collapse:collapse;table-layout:fixed">'
            f'<colgroup>{_COLGROUP}</colgroup>'
            f'<tbody>{tbody_html}</tbody></table></div>'
        )

    grand_cost = grand_value = grand_pnl = 0.0

    # ── Table header (column labels) ──────────────────────────────
    _, col_hdr = st.columns([1, 24])
    with col_hdr:
        hdr_html = (
            f'<div dir="rtl" style="font-size:12px;margin:0">'
            f'<table style="width:100%;border-collapse:collapse;table-layout:fixed">'
            f'<colgroup>{_COLGROUP}</colgroup>'
            f'<thead><tr>'
            f'<th style="{_TH}">Ticker</th>'
            f'<th style="{_TH}">שם</th>'
            f'<th style="{_TH}">כמות</th>'
            f'<th style="{_TH}">מחיר נוכחי</th>'
            f'<th style="{_TH}">עלות</th>'
            f'<th style="{_TH}">שווי</th>'
            f'<th style="{_TH}">רווח/הפסד</th>'
            f'</tr></thead></table></div>'
        )
        st.markdown(hdr_html, unsafe_allow_html=True)

    # ── Per-ticker rows ───────────────────────────────────────────
    for t in sorted(all_tickers(portfolio)):
        p = prices.get(t)
        cur_price = p["price"] if p else None
        lot_html_rows = ""
        t_cost = t_value = t_pnl = t_shares = 0.0

        for _layer, lot in lots_for_ticker(portfolio, t):
            shares = lot.get("shares", 0)
            if shares <= 0:
                continue
            bd = lot["buy_date"]
            # Stored buy_price wins; fall back to dynamic Yahoo lookup
            bp = lot.get("buy_price") or lookup_buy_price(t, bd, prices)
            cost = shares * bp if bp else None
            value = shares * cur_price if cur_price else None
            pnl = (value - cost) if (cost is not None and value is not None) else None
            pnl_pct = (pnl / cost * 100) if (pnl is not None and cost and cost > 0) else None

            t_shares += shares
            if cost is not None:
                t_cost += cost
            if value is not None:
                t_value += value
            if pnl is not None:
                t_pnl += pnl

            bp_str    = f"${bp:.2f}"    if bp    else "—"
            lot_cost  = f"${cost:.0f}"  if cost  else "—"
            lot_val   = f"${value:.0f}" if value else "—"
            pnl_c = COLOR["positive"] if (pnl or 0) >= 0 else COLOR["negative"]
            pnl_str = (
                f'<span style="color:{pnl_c}">${pnl:+,.0f} ({pnl_pct:+.1f}%)</span>'
                if pnl is not None else "—"
            )

            lot_html_rows += (
                f'<tr style="background:#161616">'
                f'<td style="{_TD};color:{COLOR["text_dim"]};border-left:3px solid #2a3a2a">{bd}</td>'
                f'<td style="{_TD}"></td>'
                f'<td style="{_TD}">{shares:.3f}</td>'
                f'<td style="{_TD}">{bp_str}</td>'
                f'<td style="{_TD}">{lot_cost}</td>'
                f'<td style="{_TD}">{lot_val}</td>'
                f'<td style="{_TD}">{pnl_str}</td>'
                f'</tr>'
            )

        if not lot_html_rows:
            continue

        cur_str  = f"${cur_price:.2f}" if cur_price else "—"
        cost_str = f"${t_cost:,.0f}"   if t_cost > 0  else "—"
        val_str  = f"${t_value:,.0f}"  if t_value > 0 else "—"
        if t_cost > 0 and t_value > 0:
            tot_pnl_c   = COLOR["positive"] if t_pnl >= 0 else COLOR["negative"]
            tot_pnl_pct = t_pnl / t_cost * 100
            tot_str = (
                f'<span style="color:{tot_pnl_c};font-weight:700">'
                f'${t_pnl:+,.0f} ({tot_pnl_pct:+.1f}%)</span>'
            )
        else:
            tot_str = f'<span style="color:{COLOR["text_dim"]}">—</span>'

        _HDR_TD = (
            f"{_TD};font-weight:700;"
            f"border-top:2px solid #2a2a2a;border-bottom:1px solid #2a2a2a"
        )
        summary_row = (
            f'<tr style="background:{COLOR["bg_dark"]}">'
            f'<td style="{_HDR_TD};color:{COLOR["primary"]};'
            f'border-left:3px solid {COLOR["primary"]}">{t}</td>'
            f'<td style="{_HDR_TD};font-size:10px;color:{COLOR["text_dim"]}">'
            f'{TICKER_NAMES.get(t, "")}</td>'
            f'<td style="{_HDR_TD}">{t_shares:.3f}</td>'
            f'<td style="{_HDR_TD}">{cur_str}</td>'
            f'<td style="{_HDR_TD}">{cost_str}</td>'
            f'<td style="{_HDR_TD}">{val_str}</td>'
            f'<td style="{_HDR_TD}">{tot_str}</td>'
            f'</tr>'
        )

        expanded = st.session_state.get(f"lots_{t}", False)
        col_btn, col_row = st.columns([1, 24])
        with col_btn:
            if st.button("▼" if expanded else "▶", key=f"lots_toggle_{t}"):
                st.session_state[f"lots_{t}"] = not expanded
                st.rerun()
        with col_row:
            body = summary_row + (lot_html_rows if expanded else "")
            st.markdown(_make_table(body), unsafe_allow_html=True)

        grand_cost  += t_cost
        grand_value += t_value
        grand_pnl   += t_pnl

    # ── Grand total ───────────────────────────────────────────────
    g_pnl_c   = COLOR["positive"] if grand_pnl >= 0 else COLOR["negative"]
    g_pnl_pct = (grand_pnl / grand_cost * 100) if grand_cost > 0 else 0.0
    _, col_total = st.columns([1, 24])
    with col_total:
        st.markdown(
            _make_table(
                f'<tr style="background:#0a1a0a;border-top:2px solid {COLOR["primary"]}">'
                f'<td style="{_TD};font-weight:700;color:{COLOR["primary"]}">סה״כ</td>'
                f'<td style="{_TD}"></td>'
                f'<td style="{_TD}"></td>'
                f'<td style="{_TD}"></td>'
                f'<td style="{_TD};font-weight:700">${grand_cost:,.0f}</td>'
                f'<td style="{_TD};font-weight:700">${grand_value:,.0f}</td>'
                f'<td style="{_TD};font-weight:700;color:{g_pnl_c}">'
                f'${grand_pnl:+,.0f} ({g_pnl_pct:+.1f}%)</td>'
                f'</tr>'
            ),
            unsafe_allow_html=True,
        )

    # ── Watchlist (0-share tickers) ───────────────────────────────
    watched = [
        t for t in sorted(all_tickers(portfolio))
        if all(lot.get("shares", 0) == 0 for _l, lot in lots_for_ticker(portfolio, t))
    ]
    if watched:
        st.markdown(
            '<div dir="rtl" style="margin-top:18px;margin-bottom:6px;'
            f'font-size:12px;font-weight:700;color:{COLOR["text_dim"]}">📍 מעקב</div>',
            unsafe_allow_html=True,
        )
        _WL_COL = ["14%", "30%", "18%", "38%"]
        wl_colgroup = "".join(f'<col style="width:{w}">' for w in _WL_COL)
        def _wl_table(rows_html):
            return (
                f'<div dir="rtl"><table style="width:100%;border-collapse:collapse;'
                f'table-layout:fixed"><colgroup>{wl_colgroup}</colgroup>'
                f'<tbody>{rows_html}</tbody></table></div>'
            )
        wl_rows = ""
        for t in watched:
            p = prices.get(t) or {}
            cur = p.get("price")
            chg = p.get("change")
            cur_str = f"${cur:.2f}" if cur else "—"
            if chg is not None:
                chg_c   = COLOR["positive"] if chg >= 0 else COLOR["negative"]
                chg_str = f'<span style="color:{chg_c}">{chg:+.2f}%</span>'
            else:
                chg_str = "—"
            wl_rows += (
                f'<tr style="background:#161620">'
                f'<td style="{_TD};color:#aaaaaa;border-left:3px solid #444">{t}</td>'
                f'<td style="{_TD};font-size:10px;color:{COLOR["text_dim"]}">'
                f'{TICKER_NAMES.get(t, "")}</td>'
                f'<td style="{_TD}">{cur_str}</td>'
                f'<td style="{_TD}">{chg_str}</td>'
                f'</tr>'
            )
        _, col_wl = st.columns([1, 24])
        with col_wl:
            st.markdown(_wl_table(wl_rows), unsafe_allow_html=True)

    color_legend([
        ("#4CAF50",  "רווח"),
        ("#F44336",  "הפסד"),
        ("#00cf8d",  "שורת טיקר — סיכום כולל"),
        ("#161616",  "שורת לוט — קנייה ספציפית"),
    ])
    term_glossary([
        ("לוט",          "קנייה אחת של מניה — כמות + תאריך ספציפיים. ניתן להחזיק מספר לוטים לאותו טיקר."),
        ("מחיר קנייה",   "מחיר ביום הקנייה — מוזן ידנית, או נאסף אוטומטית: ממוצע High/Low ביום מסחר פעיל, מחיר סגירה היסטורי מ-Yahoo Finance."),
        ("עלות",         "כמות המניות × מחיר הקנייה ההיסטורי."),
        ("שווי",         "כמות המניות × מחיר הסגירה הנוכחי."),
        ("רווח/הפסד $",  "שווי נוכחי − עלות קנייה. ערך חיובי = רווח, שלילי = הפסד."),
        ("רווח/הפסד %",  "(רווח ÷ עלות) × 100. אחוז הרווח/הפסד יחסית לסכום ההשקעה."),
        ("מחיר נוכחי",   "מחיר הסגירה האחרון — נשלף מ-Yahoo Finance (עד 30 דקות איחור בשעות מסחר)."),
    ])


_NEW_TICKER_OPTION = "➕ טיקר חדש..."

def _form_add_lot(portfolio, prices):
    with st.expander("➕ הוסף נייר ערך"):
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

        watch_only = st.toggle("👁 מעקב בלבד (ללא קנייה)", value=False, key="add_watch_only")

        if not watch_only:
            shares      = st.number_input("כמות מניות", min_value=0.001, step=0.001, format="%.3f", key="add_shares")
            bd          = st.date_input("תאריך קנייה", value=date.today(), key="add_date")
            price_input = st.number_input(
                "מחיר קנייה למניה ($)",
                min_value=0.0, value=0.0, step=0.01, format="%.2f",
                key="add_price",
            )
            st.caption("0 — מחיר יאותר אוטומטית: ממוצע יומי (High+Low)/2 בשעות מסחר, או מחיר סגירה היסטורי.")
        else:
            st.caption("הנייר יופיע בכל לשוניות הניתוח (גרפים, אנליסטים, פונדמנטלס) אך לא בטבלת הרווח/הפסד.")

        btn_label = "הוסף למעקב" if watch_only else "שמור קנייה"
        if st.button(btn_label, key="add_btn"):
            if not ticker:
                st.error("הכנס סימול תקין.")
            elif watch_only:
                add_lot(portfolio, layer, ticker, 0, date.today(), buy_price=None)
                st.cache_data.clear()
                st.success(f"נוסף למעקב: {ticker} — שכבה: {layer}")
                st.rerun()
            elif shares <= 0:
                st.error("כמות חייבת להיות גדולה מ-0.")
            else:
                if price_input > 0:
                    final_price = round(price_input, 4)
                else:
                    final_price = get_current_price_or_daily_avg(ticker, bd, prices)
                add_lot(portfolio, layer, ticker, shares, bd, buy_price=final_price)
                st.cache_data.clear()
                price_str = f" — מחיר: ${final_price:.2f}" if final_price else ""
                st.success(f"נוסף: {ticker} × {shares:.3f} @ {bd}{price_str} — שכבה: {layer}")
                st.rerun()


def _form_edit_lot(portfolio, prices):
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

        lot_labels = [
            f"{lot['buy_date']} × {lot['shares']:.3f}"
            + (f" @ ${lot['buy_price']:.2f}" if lot.get("buy_price") else "")
            for _l, lot in lots
        ]
        sel_idx    = st.selectbox("בחר לוט", range(len(lots)),
                                   format_func=lambda i: lot_labels[i], key="edit_lot_sel")
        sel_layer, sel_lot = lots[sel_idx]

        new_shares   = st.number_input("כמות חדשה", value=float(sel_lot["shares"]),
                                        min_value=0.001, step=0.001, format="%.3f", key="edit_shares")
        new_date     = st.date_input("תאריך חדש", value=sel_lot["buy_date"], key="edit_date")
        stored_price = sel_lot.get("buy_price")
        price_input  = st.number_input(
            "מחיר קנייה למניה ($)",
            min_value=0.0,
            value=float(stored_price) if stored_price else 0.0,
            step=0.01, format="%.2f",
            key="edit_price",
        )
        st.caption("0 — מחיר יאותר אוטומטית לפי התאריך שנבחר.")

        if st.button("עדכן לוט", key="edit_btn"):
            if price_input > 0:
                final_price = round(price_input, 4)
            else:
                detected = get_current_price_or_daily_avg(t_sel, new_date, prices)
                # If auto-detect fails, keep the previously stored price
                final_price = detected if detected is not None else stored_price
            update_lot(portfolio, sel_layer, t_sel, sel_lot["buy_date"], new_shares, new_date,
                       buy_price=final_price)
            st.cache_data.clear()
            price_str = f" — מחיר: ${final_price:.2f}" if final_price else ""
            st.success(f"לוט עודכן.{price_str}")
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
