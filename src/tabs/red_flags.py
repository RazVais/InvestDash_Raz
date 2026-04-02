"""Red flags tab — all flags evaluated automatically against live data. No ידני."""

import streamlit as st

from src.config import COLOR, FLAG_THRESHOLDS, HE, MAJOR_FIRMS, SELL_GRADES
from src.portfolio import all_tickers, lots_for_ticker
from src.ui_helpers import color_legend, term_glossary

# ── Flag definitions ──────────────────────────────────────────────────────────
# (ticker, flag_label, threshold_description, action)
_FLAG_DEFS = [
    ("VOO",    "תיקון שוק משמעותי",      "ירידה של 10%+ משיא 6-חודש",                         "בחינת הגנות (Hedge)"),
    ("CCJ",    "ירידה במחירי האורניום",   "אורניום מתחת ל-$80/lb",                              "בחינת חוזי אספקה"),
    ("FCX",    "ירידה במחירי הנחושת",    "נחושת מתחת ל-$4.2/lb",                               "הערכת כדאיות כריה"),
    ("ETN",    "האטה בתשתיות חשמל",      "שינמוך אנליסטים / תנודתיות גבוהה",                  "בדיקת צבר הזמנות (Backlog)"),
    ("VRT",    "ירידה בביקוש לקירור",    "שינמוך אנליסטים / ירידה מהשיא",                     "מעקב אחרי דוחות Nvidia"),
    ("AMD",    "אובדן נתח שוק ב-AI",     "שינמוך אנליסטים / ירידה מהשיא",                     "בחינת תחרות מול Nvidia"),
    ("AMZN",   "האטה בצמיחת הענן",       "שינמוך אנליסטים / קונצנזוס שלילי",                  "הערכת רווחיות AWS"),
    ("GOOGL",  "האטה בצמיחת הענן",       "שינמוך אנליסטים / קונצנזוס שלילי",                  "מעקב מנועי צמיחה ב-AI"),
    ("CRWD",   "האטה באימוץ הפלטפורמה",  "שינמוך אנליסטים / ירידה מהשיא",                     "בדיקת אירועי פריצה/תקלות"),
    ("ESLT",   "ביטול חוזים / ירידה",    "ירידה של 15%+ משיא / שינמוכים",                     "מעקב תקציבי ביטחון"),
    ("TEVA",   "ירידה במחיר / רגולציה",  "מחיר מתחת ל-$14",                                   "בדיקת אישורי FDA"),
    ("EQX",    "קריסה במחיר הזהב",       "זהב מתחת ל-$4,000/oz",                              "בחינת עלויות הפקה (AISC)"),
    ("🗂 תיק", "הורדת דירוג מבנקים",     "2+ בנקים מובילים מורידים ל-Sell/Underperform",      "בחינת יציאה מהפוזיציה"),
    ("🗂 תיק", "שינוי מבנה התיק",        "VOO יורד מתחת ל-40% מהתיק",                         "איזון מחדש (Rebalancing)"),
    ("🗂 תיק", "סטייה מהתזה",           "מניה עם קונצנזוס Sell או >30% המלצות מכירה",        "בחינת החלפה באלטרנטיבה"),
]


def get_flag_summary(portfolio, data):
    """Return (n_triggered, n_watch) — used by sidebar quick summary."""
    n_trig = n_watch = 0
    for ticker, flag, *_ in _FLAG_DEFS:
        if ticker not in all_tickers(portfolio) and not ticker.startswith("🗂"):
            continue
        status, _ = _evaluate(ticker, flag, portfolio, data)
        if status == "triggered":
            n_trig += 1
        elif status == "watch":
            n_watch += 1
    return n_trig, n_watch


def get_all_flag_statuses(portfolio, data):
    """
    Return list of dicts for every applicable flag.
    Each dict: {ticker, flag, threshold, action, status, detail}
    Used by the email report module.
    """
    result = []
    for ticker, flag, threshold, action in _FLAG_DEFS:
        if ticker not in all_tickers(portfolio) and not ticker.startswith("🗂"):
            continue
        status, detail = _evaluate(ticker, flag, portfolio, data)
        result.append({
            "ticker":    ticker,
            "flag":      flag,
            "threshold": threshold,
            "action":    action,
            "status":    status,
            "detail":    detail,
        })
    return result


def render_red_flags(portfolio, data, td_str):
    market_closed = not data.get("_market_open", True)

    if market_closed:
        st.markdown(
            f'<div dir="rtl" style="color:{COLOR["warning"]};font-size:12px;margin-bottom:8px">'
            f'⚠️ {HE["market_closed_msg"]} ({td_str})</div>',
            unsafe_allow_html=True,
        )

    n_trig, n_watch = get_flag_summary(portfolio, data)
    if n_trig:
        st.error(f"🔴 {n_trig} דגלים מופעלים — פעולה נדרשת")
    elif n_watch:
        st.warning(f"🟡 {n_watch} דגלים במעקב — שים לב")
    else:
        st.success("🟢 כל הדגלים תקינים")

    st.divider()

    _TH = f"text-align:right;padding:5px 8px;color:{COLOR['primary']};border-bottom:1px solid #333;font-size:11px"
    _TD = "padding:5px 8px;font-size:11px;vertical-align:top"

    rows_html = ""
    for i, (ticker, flag, threshold, action) in enumerate(_FLAG_DEFS):
        if ticker not in all_tickers(portfolio) and not ticker.startswith("🗂"):
            continue

        status, detail = _evaluate(ticker, flag, portfolio, data)
        icon_html, row_bg = _status_cell(status)

        if not row_bg:
            row_bg = f"background:{COLOR['bg_dark']}" if i % 2 else ""

        is_pf = ticker.startswith("🗂")
        tk_color = COLOR["warning"] if is_pf else COLOR["primary"]

        rows_html += (
            f'<tr style="{row_bg}">'
            f'<td style="{_TD}">'
            f'  {icon_html}'
            + (f'<br><span style="color:{COLOR["dim"]};font-size:10px">{detail}</span>' if detail else "")
            + f'</td>'
            f'<td style="{_TD};color:{tk_color};font-weight:700">{ticker}</td>'
            f'<td style="{_TD}">{flag}</td>'
            f'<td style="{_TD};color:{COLOR["negative"]};font-size:10px">{threshold}</td>'
            f'<td style="{_TD};font-size:10px">{action}</td>'
            f'</tr>'
        )

    html = (
        f'<div dir="rtl" style="font-size:12px">'
        f'<table style="width:100%;border-collapse:collapse">'
        f'<thead><tr>'
        f'<th style="{_TH}">סטטוס</th>'
        f'<th style="{_TH}">Ticker</th>'
        f'<th style="{_TH}">דגל</th>'
        f'<th style="{_TH}">סף</th>'
        f'<th style="{_TH}">פעולה</th>'
        f'</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)

    st.divider()
    color_legend([
        ("#F44336",  "🔴 מופעל — הסף חצה, נדרשת בחינה מיידית"),
        ("#FF9800",  "🟡 מעקב — מתקרב לסף, שים לב"),
        ("#4CAF50",  "🟢 תקין — הכל בסדר"),
        ("#555555",  "⚫ אין נתונים — לא ניתן לאמת"),
    ])
    term_glossary([
        ("דגל אדום",        "אזהרה אוטומטית המבוססת על נתוני שוק חיים — כל הדגלים מחושבים, אין ידני."),
        ("VOO — תיקון",     "ירידה של 10%+ ממחיר השיא ב-6 חודשים האחרונים — אות לחשיבה על הגנות (Hedge)."),
        ("CCJ — אורניום",   "מחיר חוזה האורניום (UX1=F) — CCJ ישירות חשופה למחיר הסחורה."),
        ("FCX — נחושת",     "מחיר הנחושת (HG=F) — FCX מייצרת נחושת, מחירה תלוי בסחורה."),
        ("EQX — זהב",       "מחיר הזהב (GC=F) — EQX היא חברת כרייה, רווחיה תלויים במחיר הזהב."),
        ("TEVA — מחיר",     "מחיר מניית TEVA מתחת לסף — מדד ישיר לחולשה ספציפית."),
        ("Analyst Proxy",   "לניירות ללא מדד ישיר (ETN, VRT, AMD וכו') — הדגל מבוסס על: קונצנזוס Sell, % המלצות מכירה, שינמוכים, ירידה מהשיא."),
        ("🗂 דירוג",         "2+ בנקים מובילים (JPM, GS, MS, BofA וכו') העבירו להמלצת Sell/Underperform — סיגנל מוסדי."),
        ("🗂 מבנה",          "VOO ירד מתחת ל-40% מהתיק — חשיפה לשוק הרחב נמוכה מדי ביחס לתזה."),
        ("🗂 תזה",           "מניה בתיק עם קונצנזוס Sell או מעל 30% המלצות מכירה — בדוק אם התזה עדיין תקפה."),
        ("סף (Threshold)",  "ערך הגבול שבחצייתו הדגל עובר מ-תקין / מעקב / מופעל."),
    ])


# ── Evaluation logic ──────────────────────────────────────────────────────────

def _evaluate(ticker, flag, portfolio, data):
    """Return (status, detail_str). Statuses: triggered | watch | ok | nodata."""
    prices     = data["prices"]
    upgrades   = data["upgrades"]
    consensus  = data["consensus"]
    commodities = data.get("commodities", {})

    thr = FLAG_THRESHOLDS
    prx = thr["_proxy"]
    ptf = thr["_portfolio"]

    if ticker == "VOO":
        return _check_price_drop("VOO", prices,
                                 thr["VOO"]["drop_pct_trigger"],
                                 thr["VOO"]["drop_pct_warn"])

    elif ticker == "CCJ":
        uranium = commodities.get("uranium")
        if uranium:
            detail = f"אורניום ${uranium:.0f}/lb"
            if uranium < thr["CCJ"]["uranium_trigger"]:
                return "triggered", detail
            if uranium < thr["CCJ"]["uranium_warn"]:
                return "watch", detail
            return "ok", detail
        # Fallback: analyst proxy
        return _analyst_proxy("CCJ", prices, upgrades, consensus, prx)

    elif ticker == "FCX":
        copper = commodities.get("copper")
        if copper:
            detail = f"נחושת ${copper:.2f}/lb"
            if copper < thr["FCX"]["copper_trigger"]:
                return "triggered", detail
            if copper < thr["FCX"]["copper_warn"]:
                return "watch", detail
            return "ok", detail
        # Fallback: analyst proxy
        return _analyst_proxy("FCX", prices, upgrades, consensus, prx)

    elif ticker == "TEVA":
        p = prices.get("TEVA")
        if p:
            detail = f"מחיר ${p['price']:.2f}"
            if p["price"] < thr["TEVA"]["price_trigger"]:
                return "triggered", detail
            if p["price"] < thr["TEVA"]["price_warn"]:
                return "watch", detail
            return "ok", detail

    elif ticker == "EQX":
        gold = commodities.get("gold")
        if gold:
            detail = f"זהב ${gold:,.0f}/oz"
            if gold < thr["EQX"]["gold_trigger"]:
                return "triggered", detail
            if gold < thr["EQX"]["gold_warn"]:
                return "watch", detail
            return "ok", detail

    elif ticker in ("ETN", "VRT", "AMD", "AMZN", "GOOGL", "CRWD"):
        return _analyst_proxy(ticker, prices, upgrades, consensus, prx)

    elif ticker in ("ESLT",):
        return _check_price_drop_plus_downgrades(ticker, prices, upgrades, prx)

    elif ticker == "🗂 תיק" and "הורדת" in flag:
        return _check_major_sell(upgrades, ptf)

    elif ticker == "🗂 תיק" and "מבנה" in flag:
        return _check_voo_allocation(portfolio, prices, ptf)

    elif ticker == "🗂 תיק" and "תזה" in flag:
        return _check_thesis(portfolio, consensus, ptf)

    return "nodata", ""


def _check_price_drop(ticker, prices, trigger_pct, warn_pct):
    p = prices.get(ticker)
    if p and p.get("history") is not None and len(p["history"]) > 0:
        ath  = float(p["history"].max())
        drop = (ath - p["price"]) / ath * 100 if ath else 0
        detail = f"ירד {drop:.1f}% מהשיא (${ath:.0f})"
        if drop >= trigger_pct:
            return "triggered", detail
        if drop >= warn_pct:
            return "watch", detail
        return "ok", detail
    return "nodata", ""


def _check_price_drop_plus_downgrades(ticker, prices, upgrades, prx):
    p    = prices.get(ticker)
    drop = None
    if p and p.get("history") is not None and len(p["history"]) > 0:
        ath  = float(p["history"].max())
        drop = (ath - p["price"]) / ath * 100 if ath else 0

    hits = _count_downgrades(ticker, upgrades)
    detail_parts = []
    if drop is not None:
        detail_parts.append(f"ירד {drop:.1f}% מהשיא")
    if hits:
        detail_parts.append(f"{len(hits)} שינמוכים")
    detail = " | ".join(detail_parts) if detail_parts else ""

    if (drop is not None and drop >= prx["drop_pct_trigger"]) or len(hits) >= prx["downgrade_trigger"]:
        return "triggered", detail
    if (drop is not None and drop >= prx["drop_pct_watch"]) or len(hits) >= prx["downgrade_watch"]:
        return "watch", detail
    if drop is not None:
        return "ok", detail
    return "nodata", ""


def _analyst_proxy(ticker, prices, upgrades, consensus, prx):
    con      = consensus.get(ticker, {})
    label    = con.get("label", "N/A")
    total    = con.get("total", 0)
    sells    = con.get("sell", 0) + con.get("strong_sell", 0)
    sell_f   = (sells / total) if total > 0 else 0
    hits     = _count_downgrades(ticker, upgrades)

    p    = prices.get(ticker)
    drop = None
    if p and p.get("history") is not None and len(p["history"]) > 0:
        ath  = float(p["history"].max())
        drop = (ath - p["price"]) / ath * 100 if ath else 0

    detail_parts = []
    if total > 0:
        detail_parts.append(f"קונצנזוס: {label}")
    if hits:
        detail_parts.append(f"{len(hits)} שינמוכים: {hits[0]}")
    if drop is not None:
        detail_parts.append(f"ירד {drop:.1f}%")
    detail = " | ".join(detail_parts) if detail_parts else ""

    triggered = (
        label == "Sell"
        or sell_f > prx["sell_frac_trigger"]
        or len(hits) >= prx["downgrade_trigger"]
        or (drop is not None and drop >= prx["drop_pct_trigger"])
    )
    watch = (
        label == "Hold"
        or sell_f > prx["sell_frac_watch"]
        or len(hits) >= prx["downgrade_watch"]
        or (drop is not None and drop >= prx["drop_pct_watch"])
    )

    if triggered:
        return "triggered", detail
    if watch:
        return "watch", detail
    if total > 0 or drop is not None:
        return "ok", detail
    return "nodata", ""


def _count_downgrades(ticker, upgrades):
    """Return list of 'firm: grade' strings for recent downgrade actions."""
    df = upgrades.get(ticker)
    hits = []
    if df is not None and not df.empty:
        for _, row in df.head(15).iterrows():
            action = str(row.get("action", "")).lower()
            grade  = str(row.get("to_grade", "")).lower()
            firm   = str(row.get("firm", ""))
            if "down" in action or any(s in grade for s in SELL_GRADES):
                hits.append(f"{firm}: {row.get('to_grade', '')}")
    return hits


def _check_major_sell(upgrades, ptf):
    hits = []
    for t, df in upgrades.items():
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            firm  = str(row.get("firm", "")).lower()
            grade = str(row.get("to_grade", "")).lower()
            if any(mf in firm for mf in MAJOR_FIRMS) and any(s in grade for s in SELL_GRADES):
                hits.append(f"{t}/{row['firm']}")
    n = len(hits)
    detail = f"{n} הורדות מבנקים מובילים: {', '.join(hits[:2])}" if hits else "אין הורדות Sell מבנקים מובילים"
    if n >= ptf["major_sell_trigger"]:
        return "triggered", detail
    if n >= ptf["major_sell_warn"]:
        return "watch", detail
    return "ok", detail


def _check_voo_allocation(portfolio, prices, ptf):
    voo_val = total_val = 0.0
    for t in all_tickers(portfolio):
        p = prices.get(t)
        if not p:
            continue
        for _l, lot in lots_for_ticker(portfolio, t):
            if lot["shares"] > 0:
                val = lot["shares"] * p["price"]
                total_val += val
                if t == "VOO":
                    voo_val += val
    if total_val > 0:
        pct = voo_val / total_val * 100
        detail = f"VOO = {pct:.1f}% מהתיק"
        if pct < ptf["voo_min_pct_trigger"]:
            return "triggered", detail
        if pct < ptf["voo_min_pct_warn"]:
            return "watch", detail
        return "ok", detail
    return "nodata", ""


def _check_thesis(portfolio, consensus, ptf):
    problem = []
    for t in all_tickers(portfolio):
        if t == "VOO":
            continue
        con   = consensus.get(t, {})
        label = con.get("label", "N/A")
        total = con.get("total", 0)
        sells = con.get("sell", 0) + con.get("strong_sell", 0)
        sell_f = (sells / total) if total > 0 else 0
        if label == "Sell" or sell_f > 0.30:
            problem.append(f"{t} ({label})")
    detail = ", ".join(problem) if problem else "כל המניות עם קונצנזוס חיובי"
    if len(problem) >= 2:
        return "triggered", detail
    if len(problem) == 1:
        return "watch", detail
    if any(consensus.get(t, {}).get("total", 0) > 0
           for t in all_tickers(portfolio) if t != "VOO"):
        return "ok", detail
    return "nodata", ""


def _status_cell(status):
    _MAP = {
        "triggered": (f'<span style="color:{COLOR["negative"]};font-weight:700"><span role="img" aria-label="triggered">🔴</span> מופעל</span>', f"background:{COLOR['bg_red']}"),
        "watch":     (f'<span style="color:{COLOR["warning"]};font-weight:700"><span role="img" aria-label="watch">🟡</span> מעקב</span>',     f"background:{COLOR['bg_orange']}"),
        "ok":        (f'<span style="color:{COLOR["positive"]}"><span role="img" aria-label="ok">🟢</span> תקין</span>',                      ""),
        "nodata":    (f'<span style="color:{COLOR["dim"]}"><span role="img" aria-label="no data">⚫</span> אין נתונים</span>',                 ""),
    }
    return _MAP.get(status, _MAP["nodata"])
