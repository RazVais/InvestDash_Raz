"""Portfolio tab — multi-lot P&L table, add/edit/remove lot forms."""

from datetime import date

import streamlit as st

from src.config import COLOR, HE, TICKER_NAMES, guess_layer, is_tase_numeric
from src.data.prices import get_current_price_or_daily_avg, lookup_buy_price
from src.journal import prepend_entry
from src.logger import get_logger
from src.portfolio import (
    add_closed_trade,
    add_lot,
    all_tickers,
    close_lot,
    close_ticker,
    get_alerts,
    get_starred,
    lots_for_ticker,
    remove_lot,
    remove_ticker,
    set_starred_list,
    set_ticker_alerts,
    update_lot,
)
from src.tabs.overview import (
    _render_allocation_donut,
    _render_correlation_matrix,
    _render_pnl_summary,
    _render_portfolio_heatmap,
    _render_stress_test,
)
from src.tabs.trading_journal_tab import render_closed_trades_summary
from src.ui_helpers import color_legend, section_title, term_glossary

_log = get_logger(__name__)



def render_portfolio(portfolio, data, td_str="", claude_api_key=""):
    """תיק — everything about what you own: P&L, securities, analysts, charts, stops."""
    from src.tabs.analysts_tab import render_analyst_views
    from src.tabs.overview import render_securities
    from src.tabs.planning_tab import render_history, render_rebalance

    prices = data["prices"]

    (tab_portfolio, tab_history, tab_rebalance, tab_securities, tab_analysts,
     tab_visuals, tab_stops) = st.tabs([
        HE["sub_pnl"], HE["sub_history"], HE["sub_rebalance"], HE["sub_securities"],
        HE["sub_analysts"], HE["sub_visuals"], HE["sub_stops"],
    ])

    with tab_history:
        render_history(portfolio, data)

    with tab_rebalance:
        render_rebalance(portfolio, data)

    with tab_portfolio:
        _render_pnl_table(portfolio, prices)
        render_closed_trades_summary(prices)
        st.divider()
        c1, c2, c3 = st.columns(3)
        with c1:
            _form_add_lot(portfolio, prices)
        with c2:
            _form_edit_lot(portfolio, prices)
        with c3:
            _form_remove(portfolio, prices)
        _form_add_closed_trade(portfolio, prices)

    with tab_visuals:
        col1, col2 = st.columns([1, 1])
        with col1:
            _render_pnl_summary(portfolio, prices, data.get("ils_usd"))
        with col2:
            _render_allocation_donut(portfolio, prices, data.get("ils_usd"))
        st.divider()
        _render_portfolio_heatmap(portfolio, prices)
        st.divider()
        _render_correlation_matrix(prices)
        st.divider()
        _render_stress_test(portfolio, prices, data.get("ils_usd"))

    with tab_securities:
        render_securities(portfolio, data, td_str)

    with tab_analysts:
        render_analyst_views(portfolio, data, td_str, claude_api_key)

    with tab_stops:
        _render_stops_tab(portfolio, prices)


def _render_pnl_table(portfolio, prices):
    section_title("פירוט תיק", "עלות, שווי ורווח/הפסד לפי תאריכי קנייה (לוטים)")

    _TH = (
        f"padding:5px 8px;color:{COLOR['primary']};"
        f"border-bottom:2px solid #333;font-size:11px;text-align:right"
    )
    _TD = "padding:5px 8px;font-size:11px"
    _COL_W = ["14%", "22%", "9%", "11%", "12%", "12%", "20%"]
    _COLGROUP = "".join(f'<col style="width:{w}">' for w in _COL_W)

    def _make_table(tbody_html):
        return (
            f'<div dir="rtl" style="font-size:12px;margin:0">'
            f'<table style="width:100%;border-collapse:collapse;table-layout:fixed">'
            f'<colgroup>{_COLGROUP}</colgroup>'
            f'<tbody>{tbody_html}</tbody></table></div>'
        )

    # ── Sort controls ─────────────────────────────────────────────
    _SORT_OPTS = ["Ticker", "שווי", "רווח $", "רווח %", "עלות"]
    _, _sc1, _sc2 = st.columns([4, 2, 1])
    with _sc1:
        _sort_col = st.selectbox(
            "מיין לפי", _SORT_OPTS, key="pnl_sort_col", label_visibility="collapsed",
        )
    with _sc2:
        _sort_asc = st.checkbox("↑", value=True, key="pnl_sort_asc", help="סדר עולה")

    def _ticker_sort_val(t):
        if _sort_col == "Ticker":
            return t
        p = prices.get(t)
        cur = p["price"] if p else None
        tc = tv = tp = 0.0
        for _l, lot in lots_for_ticker(portfolio, t):
            s = lot.get("shares", 0)
            if s <= 0:
                continue
            bp = lot.get("buy_price") or lookup_buy_price(t, lot["buy_date"], prices)
            cost  = s * bp if bp else 0.0
            value = s * cur if cur else 0.0
            tc += cost
            tv += value
            tp += value - cost
        pct = (tp / tc * 100) if tc > 0 else 0.0
        return {"שווי": tv, "רווח $": tp, "רווח %": pct, "עלות": tc}.get(_sort_col, 0.0)

    _sorted_tickers = sorted(
        all_tickers(portfolio), key=_ticker_sort_val, reverse=not _sort_asc,
    )

    grand_cost = grand_value = grand_pnl = 0.0
    tase_cost = tase_value = tase_pnl = 0.0

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
    for t in _sorted_tickers:
        p         = prices.get(t)
        cur_price = p["price"] if p else None
        is_tase   = is_tase_numeric(t) or (p.get("currency") == "ILS" if p else False)
        sym       = "₪" if is_tase else "$"
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

            bp_str    = f"{sym}{bp:.2f}"    if bp    else "—"
            lot_cost  = f"{sym}{cost:.0f}"  if cost  else "—"
            lot_val   = f"{sym}{value:.0f}" if value else "—"
            pnl_c = COLOR["positive"] if (pnl or 0) >= 0 else COLOR["negative"]
            pnl_str = (
                f'<span style="color:{pnl_c}">{sym}{pnl:+,.0f} ({pnl_pct:+.1f}%)</span>'
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

        # TASE badge for numeric tickers
        tase_badge = (
            '<span style="font-size:9px;color:#888;border:1px solid #555;'
            'border-radius:3px;padding:0 3px;margin-right:4px">TASE ₪</span>'
            if is_tase else ""
        )

        cur_str  = f"{sym}{cur_price:.2f}" if cur_price else "—"
        cost_str = f"{sym}{t_cost:,.0f}"   if t_cost > 0  else "—"
        val_str  = f"{sym}{t_value:,.0f}"  if t_value > 0 else "—"
        if t_cost > 0 and t_value > 0:
            tot_pnl_c   = COLOR["positive"] if t_pnl >= 0 else COLOR["negative"]
            tot_pnl_pct = t_pnl / t_cost * 100
            tot_str = (
                f'<span style="color:{tot_pnl_c};font-weight:700">'
                f'{sym}{t_pnl:+,.0f} ({tot_pnl_pct:+.1f}%)</span>'
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
            f'border-left:3px solid {COLOR["primary"]}">{tase_badge}{t}</td>'
            f'<td style="{_HDR_TD};font-size:10px;color:{COLOR["text_dim"]}">'
            f'{TICKER_NAMES.get(t) or (p.get("name", "") if p else "")}</td>'
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

        if is_tase:
            tase_cost  += t_cost
            tase_value += t_value
            tase_pnl   += t_pnl
        else:
            grand_cost  += t_cost
            grand_value += t_value
            grand_pnl   += t_pnl

    # ── Grand total (USD) ─────────────────────────────────────────
    g_pnl_c   = COLOR["positive"] if grand_pnl >= 0 else COLOR["negative"]
    g_pnl_pct = (grand_pnl / grand_cost * 100) if grand_cost > 0 else 0.0
    _, col_total = st.columns([1, 24])
    with col_total:
        st.markdown(
            _make_table(
                f'<tr style="background:#0a1a0a;border-top:2px solid {COLOR["primary"]}">'
                f'<td style="{_TD};font-weight:700;color:{COLOR["primary"]}">סה״כ USD</td>'
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

    # ── TASE total (ILS) — shown only when TASE positions exist ──
    if tase_cost > 0 or tase_value > 0:
        t_pnl_c   = COLOR["positive"] if tase_pnl >= 0 else COLOR["negative"]
        t_pnl_pct = (tase_pnl / tase_cost * 100) if tase_cost > 0 else 0.0
        _, col_tase = st.columns([1, 24])
        with col_tase:
            st.markdown(
                _make_table(
                    f'<tr style="background:#0a0a1a;border-top:1px solid #334">'
                    f'<td style="{_TD};font-weight:700;color:#7c9fbf">סה״כ TASE ₪</td>'
                    f'<td style="{_TD};font-size:9px;color:{COLOR["text_dim"]}">מחירים בש״ח</td>'
                    f'<td style="{_TD}"></td>'
                    f'<td style="{_TD}"></td>'
                    f'<td style="{_TD};font-weight:700">₪{tase_cost:,.0f}</td>'
                    f'<td style="{_TD};font-weight:700">₪{tase_value:,.0f}</td>'
                    f'<td style="{_TD};font-weight:700;color:{t_pnl_c}">'
                    f'₪{tase_pnl:+,.0f} ({t_pnl_pct:+.1f}%)</td>'
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
        starred = set(get_starred(portfolio))
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
                f'<td style="{_TD};color:#aaaaaa;border-left:3px solid #444">'
                f'{"⭐ " if t in starred else ""}{t}</td>'
                f'<td style="{_TD};font-size:10px;color:{COLOR["text_dim"]}">'
                f'{TICKER_NAMES.get(t, "")}</td>'
                f'<td style="{_TD}">{cur_str}</td>'
                f'<td style="{_TD}">{chg_str}</td>'
                f'</tr>'
            )
        _, col_wl = st.columns([1, 24])
        with col_wl:
            st.markdown(_wl_table(wl_rows), unsafe_allow_html=True)
            # Star tier: starred watch names get analyst data, news and daily AI
            sel = st.multiselect(
                HE["starred"], options=watched,
                default=[t for t in watched if t in starred],
                help=HE["star_help"], key="_starred_sel",
            )
            if set(sel) != (starred & set(watched)):
                set_starred_list(portfolio, sel)
                st.rerun()

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
            price_str = f" — מחיר: ${final_price:.2f}" if final_price else ""
            st.success(f"לוט עודכן.{price_str}")
            st.rerun()


def _reinvest_preview(t, lots_to_sell, prices):
    """Render a reinvestment preview card before the user confirms a removal.

    Shows current-price proceeds, original cost (if buy_price stored), P&L,
    and highlights the net cash available to reinvest.
    Uses stored buy_price only — no extra network calls.
    """
    p = prices.get(t) or {}
    cur_price = p.get("price")
    if not cur_price:
        return

    is_tase = is_tase_numeric(t) or p.get("currency") == "ILS"
    sym = "₪" if is_tase else "$"

    total_shares = sum(lot.get("shares", 0) for lot in lots_to_sell)
    proceeds     = total_shares * cur_price
    total_cost   = sum(
        lot.get("shares", 0) * lot["buy_price"]
        for lot in lots_to_sell
        if lot.get("buy_price")
    )
    has_cost = total_cost > 0
    pnl      = (proceeds - total_cost) if has_cost else None
    pnl_pct  = (pnl / total_cost * 100) if (pnl is not None and total_cost > 0) else None
    pnl_c    = COLOR["positive"] if (pnl or 0) >= 0 else COLOR["negative"]

    header = f'<div style="font-size:11px;color:#888;margin-bottom:4px">{t} — {total_shares:.3f} מניות @ {sym}{cur_price:.2f}</div>'
    cost_row = (
        f'<div style="display:flex;justify-content:space-between;font-size:12px;padding:2px 0">'
        f'<span style="color:#aaa">עלות מקורית</span><span>{sym}{total_cost:,.2f}</span></div>'
        if has_cost else ""
    )
    pnl_row = (
        f'<div style="display:flex;justify-content:space-between;font-size:12px;padding:2px 0">'
        f'<span style="color:#aaa">רווח/הפסד</span>'
        f'<span style="color:{pnl_c}">{sym}{pnl:+,.2f} ({pnl_pct:+.1f}%)</span></div>'
        if pnl is not None else ""
    )
    reinvest_row = (
        f'<div style="display:flex;justify-content:space-between;font-size:15px;font-weight:700;'
        f'padding:6px 0 2px;border-top:1px solid #2a4a2a;margin-top:4px">'
        f'<span style="color:{COLOR["primary"]}">💰 לרינבסטמנט</span>'
        f'<span style="color:{COLOR["primary"]}">{sym}{proceeds:,.2f}</span></div>'
    )
    st.markdown(
        f'<div style="background:#0d1f0d;border:1px solid #2a4a2a;border-radius:8px;'
        f'padding:10px 14px;margin-bottom:8px">'
        f'{header}{cost_row}{pnl_row}{reinvest_row}</div>',
        unsafe_allow_html=True,
    )


def _form_remove(portfolio, prices):
    with st.expander("🗑 מכירה / הסרה"):
        tickers_all = sorted(all_tickers(portfolio))
        if not tickers_all:
            st.caption("אין ניירות ערך בתיק.")
            return

        mode = st.radio("מצב", ["מכור לוט ספציפי", "מכור/הסר טיקר שלם"], key="rm_mode", horizontal=True)

        if mode == "מכור לוט ספציפי":
            t_sel = st.selectbox("סימול", tickers_all, key="rm_ticker")
            is_tase = is_tase_numeric(t_sel)
            sym = "₪" if is_tase else "$"
            lots  = [(layer, lot) for layer, lot in lots_for_ticker(portfolio, t_sel)]
            if lots:
                lot_labels = [
                    f"{lot['buy_date']} × {lot['shares']:.3f}"
                    + (f" @ {sym}{lot['buy_price']:.2f}" if lot.get("buy_price") else "")
                    for _l, lot in lots
                ]
                sel_idx    = st.selectbox("לוט", range(len(lots)),
                                           format_func=lambda i: lot_labels[i], key="rm_lot_sel")
                sel_layer, sel_lot = lots[sel_idx]
                _reinvest_preview(t_sel, [sel_lot], prices)

                has_shares = float(sel_lot.get("shares") or 0) > 0
                sell_price_lot = 0.0
                sell_date_lot  = date.today()
                if has_shares:
                    st.markdown(
                        '<div dir="rtl" style="font-size:11px;color:#94a3b8;margin:6px 0 2px">פרטי מכירה:</div>',
                        unsafe_allow_html=True,
                    )
                    sc1, sc2 = st.columns(2)
                    default_price = (prices.get(t_sel) or {}).get("price") or 0.0
                    sell_date_lot = sc1.date_input(
                        "תאריך מכירה", value=date.today(), key="sell_date_lot"
                    )
                    sell_price_lot = sc2.number_input(
                        f"מחיר מכירה ({sym})",
                        min_value=0.0,
                        value=round(float(default_price), 2),
                        step=0.01, format="%.2f",
                        key="sell_price_lot",
                    )

                if st.button("מכור / הסר לוט", key="rm_lot_btn"):
                    if has_shares and sell_price_lot > 0:
                        close_lot(portfolio, sel_layer, t_sel,
                                  sel_lot["buy_date"], sell_date_lot, sell_price_lot)
                        pnl_str = ""
                        if sel_lot.get("buy_price"):
                            pnl = (sell_price_lot - sel_lot["buy_price"]) * sel_lot["shares"]
                            pnl_str = f" | רווח/הפסד: {sym}{pnl:+,.2f}"
                        st.success(f"נמכר: {t_sel} {sel_lot['buy_date']} @ {sym}{sell_price_lot:.2f}{pnl_str}")
                    else:
                        remove_lot(portfolio, sel_layer, t_sel, sel_lot["buy_date"])
                        st.success(f"לוט הוסר: {t_sel} {sel_lot['buy_date']}")
                    st.rerun()
        else:
            t_sel    = st.selectbox("סימול", tickers_all, key="rm_full_ticker")
            is_tase  = is_tase_numeric(t_sel)
            sym      = "₪" if is_tase else "$"
            all_lots = [lot for _l, lot in lots_for_ticker(portfolio, t_sel) if lot.get("shares", 0) > 0]
            sell_price_full = 0.0
            sell_date_full  = date.today()
            if all_lots:
                _reinvest_preview(t_sel, all_lots, prices)

            if all_lots:
                st.markdown(
                    '<div dir="rtl" style="font-size:11px;color:#94a3b8;margin:6px 0 2px">פרטי מכירה:</div>',
                    unsafe_allow_html=True,
                )
                fc1, fc2 = st.columns(2)
                default_price = (prices.get(t_sel) or {}).get("price") or 0.0
                sell_date_full = fc1.date_input(
                    "תאריך מכירה", value=date.today(), key="sell_date_full"
                )
                sell_price_full = fc2.number_input(
                    f"מחיר מכירה ({sym})",
                    min_value=0.0,
                    value=round(float(default_price), 2),
                    step=0.01, format="%.2f",
                    key="sell_price_full",
                )

            st.warning(f"זה יסיר את כל הלוטים של {t_sel}!")
            if st.button(f"מכור / הסר את {t_sel}", key="rm_full_btn"):
                if all_lots and sell_price_full > 0:
                    close_ticker(portfolio, t_sel, sell_date_full, sell_price_full)
                    st.success(f"{t_sel} נמכר @ {sym}{sell_price_full:.2f} והוסר מהתיק.")
                else:
                    remove_ticker(portfolio, t_sel)
                    st.success(f"{t_sel} הוסר מהתיק.")
                st.rerun()


# ── Trade history helpers ─────────────────────────────────────────────────────

def _form_add_closed_trade(portfolio, prices):
    """Expander to manually record a past closed trade (buy + sell pair)."""
    with st.expander("📝 הוסף עסקה סגורה ידנית (לגיבוי היסטוריה)"):
        existing = sorted(all_tickers(portfolio))
        ticker_opts = existing + ["➕ טיקר אחר..."]
        t_sel = st.selectbox("סימול", ticker_opts, key="ct_ticker_sel",
                             format_func=lambda t: t if t != "➕ טיקר אחר..." else "➕ הקלד טיקר אחר")
        if t_sel == "➕ טיקר אחר...":
            ticker = st.text_input("סימול", key="ct_ticker_new", placeholder="e.g. NVDA").upper().strip()
        else:
            ticker = t_sel

        layer = guess_layer(ticker) if ticker else list(portfolio["layers"].keys())[0]
        if layer not in portfolio["layers"]:
            layer = list(portfolio["layers"].keys())[0]
        is_tase = is_tase_numeric(ticker) if ticker else False
        sym = "₪" if is_tase else "$"

        c1, c2 = st.columns(2)
        shares     = c1.number_input("כמות מניות", min_value=0.001, step=0.001, format="%.3f", key="ct_shares")
        buy_date   = c1.date_input("תאריך קנייה", key="ct_buy_date")
        buy_price  = c1.number_input(f"מחיר קנייה ({sym})", min_value=0.0, step=0.01, format="%.2f", key="ct_buy_price")
        sell_date  = c2.date_input("תאריך מכירה", value=date.today(), key="ct_sell_date")
        sell_price = c2.number_input(f"מחיר מכירה ({sym})", min_value=0.0, step=0.01, format="%.2f", key="ct_sell_price")

        if ticker and buy_price > 0 and sell_price > 0 and shares > 0:
            pnl = (sell_price - buy_price) * shares
            pnl_c = "#4CAF50" if pnl >= 0 else "#F44336"
            st.markdown(
                f'<div dir="rtl" style="font-size:12px;color:{pnl_c};font-weight:700;margin:4px 0">'
                f'רווח/הפסד: {sym}{pnl:+,.2f} ({(pnl / (buy_price * shares) * 100):+.1f}%)'
                f'</div>',
                unsafe_allow_html=True,
            )

        if st.button("שמור עסקה", key="ct_save"):
            if not ticker:
                st.error("הכנס סימול.")
            elif buy_price <= 0 or sell_price <= 0 or shares <= 0:
                st.error("יש להזין כמות, מחיר קנייה ומחיר מכירה.")
            else:
                add_closed_trade(portfolio, ticker, shares, buy_price, buy_date,
                                 sell_price, sell_date, layer)
                pnl = (sell_price - buy_price) * shares
                st.success(
                    f"נשמר: {ticker} × {shares:.3f} | קנייה {sym}{buy_price:.2f} @ {buy_date} "
                    f"→ מכירה {sym}{sell_price:.2f} @ {sell_date} | רווח/הפסד: {sym}{pnl:+,.2f}"
                )
                st.rerun()


# ── Stops & Alerts tab ────────────────────────────────────────────────────────

def _log_stops_to_journal(ticker, current_price, stop_loss, trailing_stop_pct, price_alerts):
    """Append a risk-management note to the trading journal (no Claude call needed)."""

    dist_str = ""
    if stop_loss and current_price:
        dist = (current_price - stop_loss) / current_price * 100
        dist_str = f" ({dist:.1f}% below current ${current_price:.2f})"

    parts = []
    if stop_loss:
        parts.append(f"Stop loss ${stop_loss:.2f}{dist_str}")
    if trailing_stop_pct:
        parts.append(f"Trailing stop {trailing_stop_pct:.1f}%")
    if price_alerts:
        for a in price_alerts:
            arrow = "↑" if a.get("direction") == "above" else "↓"
            parts.append(f"Alert {arrow}${a['price']:.2f}" + (f" ({a['note']})" if a.get("note") else ""))

    entry = {
        "date":              str(date.today()),
        "ticker":            ticker,
        "setup_type":        "other",
        "direction":         "Long",
        "entry_price":       round(current_price, 2) if current_price else None,
        "stop_price":        stop_loss,
        "target_price":      None,
        "r_multiple_entry":  None,
        "position_size":     None,
        "execution_quality": None,
        "emotional_state":   "disciplined",
        "result":            "Open",
        "actual_r":          None,
        "did_right":         "; ".join(parts) if parts else "Set risk levels",
        "would_change":      "",
        "_type":             "stop_note",
    }
    try:
        if not prepend_entry(entry):
            st.warning(HE["journal_corrupt"])
    except Exception:
        _log.warning("Could not write stop note to journal", exc_info=True)


def _render_stops_tab(portfolio, prices):
    alerts = get_alerts(portfolio)

    all_t = sorted(all_tickers(portfolio))
    owned = [
        t for t in all_t
        if any(lot.get("shares", 0) > 0 for _l, lot in lots_for_ticker(portfolio, t))
    ]
    watched = [t for t in all_t if t not in owned]

    # ── Section 1: Owned stocks ───────────────────────────────────────────────
    st.markdown(
        '<div dir="rtl" style="font-size:14px;font-weight:700;color:#00cf8d;margin-bottom:8px">'
        '📌 ניירות ערך בבעלות — עצירות והתראות</div>',
        unsafe_allow_html=True,
    )

    if not owned:
        st.caption("אין ניירות ערך בבעלות.")
    else:
        # Summary status table
        _TH = f"padding:5px 8px;color:{COLOR['primary']};border-bottom:2px solid #333;font-size:11px;text-align:right"
        _TD = "padding:5px 8px;font-size:11px"
        hdr = (
            '<div dir="rtl"><table style="width:100%;border-collapse:collapse">'
            '<thead><tr>'
            f'<th style="{_TH}">Ticker</th>'
            f'<th style="{_TH}">מחיר נוכחי</th>'
            f'<th style="{_TH}">Stop Loss</th>'
            f'<th style="{_TH}">מרחק %</th>'
            f'<th style="{_TH}">Trailing %</th>'
            f'<th style="{_TH}">Trailing $</th>'
            f'<th style="{_TH}">התראות מחיר</th>'
            '</tr></thead><tbody>'
        )
        rows = ""
        for t in owned:
            p    = prices.get(t) or {}
            cur  = p.get("price")
            al   = alerts.get(t, {})
            stop = al.get("stop_loss")
            trl  = al.get("trailing_stop_pct")
            palerts = al.get("price_alerts", [])
            sym  = "₪" if (is_tase_numeric(t) or p.get("currency") == "ILS") else "$"

            cur_str  = f"{sym}{cur:.2f}" if cur else "—"
            stop_str = f"{sym}{stop:.2f}" if stop else "—"
            trl_str  = f"{trl:.1f}%" if trl else "—"

            if trl and cur:
                tp = cur * (1 - trl / 100)
                trl_p_str = f"{sym}{tp:.2f}"
            else:
                trl_p_str = "—"

            if stop and cur:
                dist = (cur - stop) / cur * 100
                if dist < 5:
                    dist_color = COLOR["negative"]
                elif dist < 10:
                    dist_color = COLOR["warning"]
                else:
                    dist_color = COLOR["positive"]
                dist_str = f'<span style="color:{dist_color};font-weight:700">{dist:.1f}%</span>'
            else:
                dist_str = "—"

            alert_badges = ""
            for a in palerts:
                arrow = "↑" if a.get("direction") == "above" else "↓"
                ac = COLOR["positive"] if a.get("direction") == "above" else COLOR["negative"]
                note_part = f' <span style="font-weight:400;opacity:.8">{a["note"]}</span>' if a.get("note") else ""
                alert_badges += (
                    f'<span style="background:{ac}22;color:{ac};border:1px solid {ac}44;'
                    f'font-size:9px;font-weight:700;padding:2px 7px;border-radius:4px;'
                    f'margin-right:4px;display:inline-block">{arrow}{sym}{a["price"]:.2f}{note_part}</span>'
                )

            rows += (
                f'<tr style="border-bottom:1px solid #1e2d45">'
                f'<td style="{_TD};font-weight:700;color:{COLOR["primary"]}">{t}</td>'
                f'<td style="{_TD}">{cur_str}</td>'
                f'<td style="{_TD}">{stop_str}</td>'
                f'<td style="{_TD}">{dist_str}</td>'
                f'<td style="{_TD}">{trl_str}</td>'
                f'<td style="{_TD}">{trl_p_str}</td>'
                f'<td style="{_TD}">{alert_badges if alert_badges else "—"}</td>'
                f'</tr>'
            )

        st.markdown(
            f'<div dir="rtl" style="background:#0f1729;border:1px solid #1e2d45;'
            f'border-radius:8px;padding:8px;margin-bottom:12px">'
            f'{hdr}{rows}</tbody></table></div></div>',
            unsafe_allow_html=True,
        )

        # Per-ticker expanders
        for t in owned:
            p   = prices.get(t) or {}
            cur = p.get("price")
            al  = alerts.get(t, {})
            sym = "₪" if (is_tase_numeric(t) or p.get("currency") == "ILS") else "$"
            name = TICKER_NAMES.get(t) or p.get("name", "")
            label = f"{t} — {name}" if name else t

            with st.expander(f"⚙️ {label}"):
                c1, c2 = st.columns(2)
                new_stop = c1.number_input(
                    f"Stop Loss ({sym})",
                    min_value=0.0,
                    value=float(al.get("stop_loss") or 0.0),
                    step=0.5,
                    format="%.2f",
                    key=f"stop_{t}",
                )
                new_trail = c2.number_input(
                    "Trailing Stop (%)",
                    min_value=0.0,
                    max_value=50.0,
                    value=float(al.get("trailing_stop_pct") or 0.0),
                    step=0.5,
                    format="%.1f",
                    key=f"trail_{t}",
                )

                st.markdown(
                    '<div dir="rtl" style="font-size:11px;color:#94a3b8;margin-top:6px;margin-bottom:4px">'
                    '⚡ התראות מחיר</div>',
                    unsafe_allow_html=True,
                )

                existing_alerts = list(al.get("price_alerts", []))

                # Show existing alerts with remove buttons
                to_remove = []
                for idx, a in enumerate(existing_alerts):
                    arrow = "↑" if a.get("direction") == "above" else "↓"
                    ca1, ca2 = st.columns([5, 1])
                    ca1.markdown(
                        f'{arrow} **{sym}{a["price"]:.2f}**'
                        + (f' — {a["note"]}' if a.get("note") else ""),
                    )
                    if ca2.button("✕", key=f"rm_alert_{t}_{idx}"):
                        to_remove.append(idx)
                if to_remove:
                    existing_alerts = [a for i, a in enumerate(existing_alerts) if i not in to_remove]
                    set_ticker_alerts(
                        portfolio, t,
                        new_stop or None,
                        new_trail or None,
                        existing_alerts,
                    )
                    st.rerun()

                # Add new alert row
                na1, na2, na3, na4 = st.columns([2, 2, 3, 1])
                new_dir   = na1.selectbox("כיוון", ["above ↑", "below ↓"], key=f"ndir_{t}", label_visibility="collapsed")
                new_ap    = na2.number_input(f"מחיר ({sym})", min_value=0.0, step=0.5, format="%.2f", key=f"nap_{t}", label_visibility="collapsed")
                new_note  = na3.text_input("הערה", key=f"nnote_{t}", label_visibility="collapsed", placeholder="הערה (אופציונלי)")
                if na4.button("➕", key=f"add_alert_{t}") and new_ap > 0:
                    existing_alerts.append({
                        "price":     round(new_ap, 2),
                        "direction": "above" if "above" in new_dir else "below",
                        "note":      new_note.strip(),
                    })
                    set_ticker_alerts(portfolio, t, new_stop or None, new_trail or None, existing_alerts)
                    _log_stops_to_journal(t, cur, new_stop or None, new_trail or None, existing_alerts)
                    st.rerun()

                st.markdown("")
                bc1, bc2 = st.columns([3, 1])
                if bc1.button("💾 שמור עצירות", key=f"save_stop_{t}", type="primary"):
                    set_ticker_alerts(
                        portfolio, t,
                        new_stop or None,
                        new_trail or None,
                        existing_alerts,
                    )
                    _log_stops_to_journal(t, cur, new_stop or None, new_trail or None, existing_alerts)
                    st.success(f"✓ {t} — עודכן")
                    st.rerun()
                if bc2.button("🗑 נקה", key=f"clear_stop_{t}"):
                    set_ticker_alerts(portfolio, t, None, None, [])
                    st.rerun()

    # ── Section 2: Watch-only tickers ────────────────────────────────────────
    st.divider()
    st.markdown(
        '<div dir="rtl" style="font-size:14px;font-weight:700;color:#64748b;margin-bottom:8px">'
        '👁 מעקב בלבד — התראות מחיר</div>',
        unsafe_allow_html=True,
    )

    if not watched:
        st.caption("אין ניירות ערך במעקב בלבד.")
        return

    # Watch-only summary table
    _TH2 = f"padding:5px 8px;color:{COLOR['primary']};border-bottom:2px solid #333;font-size:11px;text-align:right"
    _TD2 = "padding:5px 8px;font-size:11px"
    w_hdr = (
        '<div dir="rtl"><table style="width:100%;border-collapse:collapse">'
        '<thead><tr>'
        f'<th style="{_TH2}">Ticker</th>'
        f'<th style="{_TH2}">מחיר נוכחי</th>'
        f'<th style="{_TH2}">שינוי %</th>'
        f'<th style="{_TH2}">התראות מחיר</th>'
        '</tr></thead><tbody>'
    )
    w_rows = ""
    for t in watched:
        p   = prices.get(t) or {}
        cur = p.get("price")
        chg = p.get("change")
        al  = alerts.get(t, {})
        sym = "₪" if (is_tase_numeric(t) or p.get("currency") == "ILS") else "$"

        cur_str = f"{sym}{cur:.2f}" if cur else "—"
        if chg is not None:
            cc = COLOR["positive"] if chg >= 0 else COLOR["negative"]
            chg_str = f'<span style="color:{cc}">{chg:+.2f}%</span>'
        else:
            chg_str = "—"

        palerts = al.get("price_alerts", [])
        badge_html = ""
        for a in palerts:
            arrow = "↑" if a.get("direction") == "above" else "↓"
            ac = COLOR["positive"] if a.get("direction") == "above" else COLOR["negative"]
            note_part = f' <span style="font-weight:400;opacity:.8">{a["note"]}</span>' if a.get("note") else ""
            badge_html += (
                f'<span style="background:{ac}22;color:{ac};border:1px solid {ac}44;'
                f'font-size:9px;font-weight:700;padding:2px 7px;border-radius:4px;'
                f'margin-right:4px;display:inline-block">'
                f'{arrow}{sym}{a["price"]:.2f}{note_part}</span>'
            )

        w_rows += (
            f'<tr style="border-bottom:1px solid #1e2d45">'
            f'<td style="{_TD2};font-weight:700;color:{COLOR["text_dim"]}">{t}</td>'
            f'<td style="{_TD2}">{cur_str}</td>'
            f'<td style="{_TD2}">{chg_str}</td>'
            f'<td style="{_TD2}">{badge_html if badge_html else "—"}</td>'
            f'</tr>'
        )

    st.markdown(
        f'<div dir="rtl" style="background:#0f1729;border:1px solid #1e2d45;'
        f'border-radius:8px;padding:8px;margin-bottom:12px">'
        f'{w_hdr}{w_rows}</tbody></table></div></div>',
        unsafe_allow_html=True,
    )

    # Per-ticker alert forms for watch-only
    for t in watched:
        p   = prices.get(t) or {}
        al  = alerts.get(t, {})
        sym = "₪" if (is_tase_numeric(t) or p.get("currency") == "ILS") else "$"
        name = TICKER_NAMES.get(t) or p.get("name", "")
        label = f"{t} — {name}" if name else t

        with st.expander(f"⚡ {label} — התראות"):
            existing_alerts = list(al.get("price_alerts", []))

            to_remove = []
            for idx, a in enumerate(existing_alerts):
                arrow = "↑" if a.get("direction") == "above" else "↓"
                wa1, wa2 = st.columns([5, 1])
                wa1.markdown(
                    f'{arrow} **{sym}{a["price"]:.2f}**'
                    + (f' — {a["note"]}' if a.get("note") else ""),
                )
                if wa2.button("✕", key=f"rm_walert_{t}_{idx}"):
                    to_remove.append(idx)
            if to_remove:
                existing_alerts = [a for i, a in enumerate(existing_alerts) if i not in to_remove]
                set_ticker_alerts(portfolio, t, None, None, existing_alerts)
                st.rerun()

            wn1, wn2, wn3, wn4 = st.columns([2, 2, 3, 1])
            w_dir  = wn1.selectbox("כיוון", ["above ↑", "below ↓"], key=f"wdir_{t}", label_visibility="collapsed")
            w_ap   = wn2.number_input(f"מחיר ({sym})", min_value=0.0, step=0.5, format="%.2f", key=f"wap_{t}", label_visibility="collapsed")
            w_note = wn3.text_input("הערה", key=f"wnote_{t}", label_visibility="collapsed", placeholder="הערה (אופציונלי)")
            if wn4.button("➕", key=f"wadd_{t}") and w_ap > 0:
                existing_alerts.append({
                    "price":     round(w_ap, 2),
                    "direction": "above" if "above" in w_dir else "below",
                    "note":      w_note.strip(),
                })
                set_ticker_alerts(portfolio, t, None, None, existing_alerts)
                st.rerun()
