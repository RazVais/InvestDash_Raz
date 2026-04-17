"""Trading Journal tab — retroactive P&L analysis from portfolio lots + optional CSV upload.

Data sources:
  Source A (auto): Portfolio lots from portfolio.json — buy_date, buy_price, current price.
  Source B (opt):  CSV of closed trades uploaded by user (any broker format).

Analysis sections:
  1. Overall statistics (win rate, expectancy, avg win/loss)
  2. By Portfolio Layer (Source A only)
  3. By Setup Type (Source B only, if setup_type column present)
  4. By Time of Day (Source B only, if entry_time column present)
  5. By Day of Week (all trades with a date)
  6. Pattern detection + recommendations (Hebrew)
"""

import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from src.config import COLOR
from src.data.prices import lookup_buy_price
from src.ui_helpers import color_legend, section_title, term_glossary

# ── Constants ─────────────────────────────────────────────────────────────────

# CSV column-name normalization: canonical name → accepted raw variants (case-insensitive)
_COL_MAP: Dict[str, List[str]] = {
    "symbol":      ["symbol", "ticker", "stock"],
    "entry_date":  ["entry date", "open date", "date opened", "trade date", "date"],
    "entry_time":  ["entry time", "open time", "time opened"],
    "entry_price": ["entry price", "open price", "avg entry", "buy price"],
    "exit_date":   ["exit date", "close date", "date closed"],
    "exit_time":   ["exit time", "close time", "time closed"],
    "exit_price":  ["exit price", "close price", "avg exit", "sell price"],
    "shares":      ["shares", "qty", "quantity", "size", "units"],
    "pnl":         ["p&l", "pnl", "realized p&l", "net p&l",
                    "gain/loss", "profit/loss", "net amount"],
    "setup_type":  ["setup type", "setup", "strategy", "pattern"],
}

# Hebrew weekday labels: Monday=0 … Friday=4 (pandas .weekday() convention)
_DOW_LABELS: Dict[int, str] = {
    0: "שני",
    1: "שלישי",
    2: "רביעי",
    3: "חמישי",
    4: "שישי",
}
_DOW_ORDER = ["שני", "שלישי", "רביעי", "חמישי", "שישי"]

# Intraday time blocks
_TIME_BLOCKS = [
    ("09:30–10:30", datetime.time(9, 30),  datetime.time(10, 30)),
    ("10:30–11:30", datetime.time(10, 30), datetime.time(11, 30)),
    ("11:30–12:30", datetime.time(11, 30), datetime.time(12, 30)),
    ("12:30–13:30", datetime.time(12, 30), datetime.time(13, 30)),
    ("13:30–14:30", datetime.time(13, 30), datetime.time(14, 30)),
    ("14:30–16:00", datetime.time(14, 30), datetime.time(16, 0)),
]
_TIME_BLOCK_ORDER = [b[0] for b in _TIME_BLOCKS]


# ── Source A: portfolio lots ───────────────────────────────────────────────────

def _portfolio_to_trades(portfolio: dict, data: dict) -> pd.DataFrame:
    """
    Build a trades DataFrame from all open portfolio lots (Source A).
    Each lot with shares > 0 and a resolvable buy_price becomes one row.
    Returns empty DataFrame if nothing can be resolved.
    """
    prices = data.get("prices") or {}
    rows: List[Dict[str, Any]] = []

    for layer, lots in portfolio.get("layers", {}).items():
        for lot in lots:
            ticker = lot.get("ticker", "").upper().strip()
            shares = float(lot.get("shares") or 0)
            if shares <= 0 or not ticker:
                continue
            bd = lot.get("buy_date")
            # Stored price wins; fall back to historical Yahoo lookup
            buy_price = lot.get("buy_price") or lookup_buy_price(ticker, bd, prices)
            cur_price = (prices.get(ticker) or {}).get("price")
            if buy_price is None or cur_price is None:
                continue
            pnl = (float(cur_price) - float(buy_price)) * shares
            rows.append({
                "symbol":      ticker,
                "entry_date":  bd,
                "entry_price": round(float(buy_price), 4),
                "exit_price":  round(float(cur_price), 4),
                "shares":      shares,
                "pnl":         round(pnl, 2),
                "layer":       layer,
                "source":      "portfolio",
            })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["entry_date_parsed"] = pd.to_datetime(df["entry_date"], errors="coerce").dt.date
    df["is_win"] = df["pnl"] > 0
    df["day_of_week"] = df["entry_date_parsed"].apply(
        lambda d: _DOW_LABELS.get(d.weekday()) if isinstance(d, datetime.date) else None
    )
    return df


# ── Source B: CSV upload ───────────────────────────────────────────────────────

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename raw CSV columns to canonical names using _COL_MAP (case-insensitive)."""
    raw_lower = {c.strip().lower(): c for c in df.columns}
    rename = {}
    for canonical, variants in _COL_MAP.items():
        for v in variants:
            if v in raw_lower:
                rename[raw_lower[v]] = canonical
                break
    return df.rename(columns=rename)


def _assign_time_block(t: Optional[datetime.time]) -> str:
    """Map a datetime.time to one of the six session block labels, or 'אחר'."""
    if t is None:
        return "אחר"
    for label, start, end in _TIME_BLOCKS:
        if start <= t < end:
            return label
    # 16:00 exactly falls in the last block
    if t == datetime.time(16, 0):
        return _TIME_BLOCKS[-1][0]
    return "אחר"


def _parse_time(val: Any) -> Optional[datetime.time]:
    """Try to parse a cell value as datetime.time. Returns None on failure."""
    if isinstance(val, datetime.time):
        return val
    s = str(val).strip()
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
        try:
            return datetime.datetime.strptime(s, fmt).time()
        except ValueError:
            pass
    return None


def _parse_csv_trades(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize CSV columns and build a clean trades DataFrame (Source B).
    Raises ValueError with Hebrew message if required columns are missing.
    """
    df = _normalize_columns(raw_df.copy())

    if "pnl" not in df.columns:
        raise ValueError(
            "לא נמצאה עמודת P&L בקובץ. "
            "ודא שהקובץ מכיל עמודה בשם: p&l, pnl, realized p&l, gain/loss, או profit/loss."
        )

    # Coerce pnl: strip currency formatting before numeric conversion
    df["pnl"] = (
        df["pnl"]
        .astype(str)
        .str.replace(r"[\$,\s]", "", regex=True)
        .pipe(pd.to_numeric, errors="coerce")
    )
    df = df.dropna(subset=["pnl"])
    if df.empty:
        raise ValueError("לא נמצאו שורות עם ערכי P&L תקינים בקובץ.")

    df["is_win"] = df["pnl"] > 0
    df["source"] = "csv"

    # Parse entry_date
    if "entry_date" in df.columns:
        df["entry_date_parsed"] = pd.to_datetime(df["entry_date"], errors="coerce").dt.date
        df["day_of_week"] = df["entry_date_parsed"].apply(
            lambda d: _DOW_LABELS.get(d.weekday()) if isinstance(d, datetime.date) else None
        )
    else:
        df["entry_date_parsed"] = None
        df["day_of_week"] = None

    # Parse entry_time → time block
    if "entry_time" in df.columns:
        df["time_block"] = df["entry_time"].apply(
            lambda v: _assign_time_block(_parse_time(v))
        )

    # Ensure layer column is absent (CSV trades have no layer)
    if "layer" not in df.columns:
        df["layer"] = None

    return df


# ── Statistics computation ────────────────────────────────────────────────────

def _compute_overall(df: pd.DataFrame) -> Dict[str, Any]:
    """Compute aggregate stats across all trades."""
    empty = {
        "total_trades": 0, "win_rate": None, "avg_win": None,
        "avg_loss": None, "expectancy": None, "largest_win": None,
        "largest_loss": None, "total_pnl": None,
    }
    if df.empty:
        return empty

    wins   = df[df["pnl"] > 0]["pnl"]
    losses = df[df["pnl"] <= 0]["pnl"]
    total  = len(df)
    win_rate  = len(wins) / total
    avg_win   = float(wins.mean())   if len(wins)   > 0 else 0.0
    avg_loss  = float(losses.mean()) if len(losses) > 0 else 0.0
    # avg_loss is zero or negative; formula holds either way
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

    return {
        "total_trades": total,
        "win_rate":     win_rate,
        "avg_win":      avg_win,
        "avg_loss":     avg_loss,
        "expectancy":   expectancy,
        "largest_win":  float(wins.max())   if len(wins)   > 0 else 0.0,
        "largest_loss": float(losses.min()) if len(losses) > 0 else 0.0,
        "total_pnl":    float(df["pnl"].sum()),
    }


def _group_stats(g: pd.DataFrame) -> Dict[str, Any]:
    """Return stats dict for a single group (used in all _compute_by_* functions)."""
    wins   = g[g["pnl"] > 0]["pnl"]
    losses = g[g["pnl"] <= 0]["pnl"]
    n = len(g)
    return {
        "עסקאות":       n,
        "שיעור הצלחה":  len(wins) / n if n > 0 else 0.0,
        "רווח ממוצע":   float(wins.mean())   if len(wins)   > 0 else 0.0,
        "הפסד ממוצע":   float(losses.mean()) if len(losses) > 0 else 0.0,
        "רווח/הפסד כולל": float(g["pnl"].sum()),
    }


def _compute_by_layer(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Breakdown by portfolio layer (Source A trades only)."""
    sub = df[df["source"] == "portfolio"]
    if sub.empty or "layer" not in sub.columns:
        return None
    rows = []
    for layer, g in sub.groupby("layer"):
        row = {"שכבה": layer}
        row.update(_group_stats(g))
        rows.append(row)
    if not rows:
        return None
    out = pd.DataFrame(rows).sort_values("רווח/הפסד כולל", ascending=False).reset_index(drop=True)
    return out


def _compute_by_setup(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Breakdown by setup type (CSV trades with setup_type column only)."""
    if "setup_type" not in df.columns:
        return None
    sub = df[df["setup_type"].notna() & (df["setup_type"].astype(str).str.strip() != "")]
    if sub.empty:
        return None
    rows = []
    for setup, g in sub.groupby("setup_type"):
        row = {"סטאפ": setup}
        row.update(_group_stats(g))
        rows.append(row)
    if not rows:
        return None
    return pd.DataFrame(rows).sort_values("רווח/הפסד כולל", ascending=False).reset_index(drop=True)


def _compute_by_time(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Breakdown by intraday time block (requires time_block column from CSV)."""
    if "time_block" not in df.columns:
        return None
    sub = df[df["time_block"].notna() & (df["time_block"] != "אחר")]
    if sub.empty:
        return None
    rows = []
    for block, g in sub.groupby("time_block"):
        row = {"בלוק": block}
        row.update(_group_stats(g))
        rows.append(row)
    if not rows:
        return None
    out = pd.DataFrame(rows)
    # Preserve natural session order
    block_order = {b: i for i, b in enumerate(_TIME_BLOCK_ORDER)}
    out["_order"] = out["בלוק"].map(block_order).fillna(99)
    out = out.sort_values("_order").drop(columns=["_order"]).reset_index(drop=True)
    # Mark best/worst (among groups with >= 3 trades) for row highlighting
    qualified = out[out["עסקאות"] >= 3]
    out["_best"]  = False
    out["_worst"] = False
    if not qualified.empty:
        best_idx  = qualified["רווח/הפסד כולל"].idxmax()
        worst_idx = qualified["רווח/הפסד כולל"].idxmin()
        if best_idx != worst_idx:          # don't highlight same row twice
            out.at[best_idx,  "_best"]  = True
            out.at[worst_idx, "_worst"] = True
    return out


def _compute_by_dow(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Breakdown by day of week (all trades with a parsed date)."""
    if "day_of_week" not in df.columns:
        return None
    sub = df[df["day_of_week"].notna()]
    if sub.empty:
        return None
    rows = []
    for day, g in sub.groupby("day_of_week"):
        row = {"יום": day}
        row.update(_group_stats(g))
        rows.append(row)
    if not rows:
        return None
    out = pd.DataFrame(rows)
    day_order = {d: i for i, d in enumerate(_DOW_ORDER)}
    out["_order"] = out["יום"].map(day_order).fillna(99)
    return out.sort_values("_order").drop(columns=["_order"]).reset_index(drop=True)


# ── Pattern detection ─────────────────────────────────────────────────────────

def _detect_patterns(
    overall: Dict[str, Any],
    layer_df: Optional[pd.DataFrame],
    setup_df: Optional[pd.DataFrame],
    time_df:  Optional[pd.DataFrame],
    dow_df:   Optional[pd.DataFrame],
) -> List[Dict[str, Any]]:
    """Return list of pattern dicts: {type, finding, recommendation} (all Hebrew)."""
    patterns: List[Dict[str, Any]] = []

    def _add(ptype: str, finding: str, rec: str) -> None:
        patterns.append({"type": ptype, "finding": finding, "recommendation": rec})

    # ── Overall level ────────────────────────────────────────────────────────
    wr  = overall.get("win_rate")
    exp = overall.get("expectancy")
    tot = overall.get("total_pnl")

    if wr is not None:
        if wr < 0.40:
            _add("danger",
                 f"שיעור הצלחה כולל נמוך — {wr*100:.1f}% בלבד.",
                 "הפחת גודל פוזיציה ב-50% עד שיעור ההצלחה יעלה מעל 40%.")
        elif wr >= 0.55 and (tot or 0) > 0:
            _add("positive",
                 f"מערכת מסחר יציבה — שיעור הצלחה {wr*100:.1f}% ורווח כולל חיובי.",
                 "שמור על כללי הכניסה הנוכחיים ועל ניהול הסיכון.")

    if exp is not None and exp > 0 and wr is not None and wr < 0.50:
        _add("info",
             f"ציפייה חיובית ({exp:+.2f}$) למרות שיעור הצלחה מתחת ל-50% — יחס סיכוי/סיכון טוב.",
             "ודא שהסטופ-לוס אינו גדל — ה-edge תלוי בשמירה על ה-R:R הנוכחי.")

    # ── By layer ─────────────────────────────────────────────────────────────
    if layer_df is not None and len(layer_df) >= 2:
        q = layer_df[layer_df["עסקאות"] >= 2]
        if len(q) >= 2:
            best  = q.loc[q["שיעור הצלחה"].idxmax()]
            worst = q.loc[q["שיעור הצלחה"].idxmin()]
            if best["שכבה"] != worst["שכבה"]:
                _add("positive",
                     f"השכבה הטובה ביותר: {best['שכבה']} — שיעור הצלחה {best['שיעור הצלחה']*100:.1f}%.",
                     f"שקול להגדיל חשיפה ל-{best['שכבה']}.")
                if worst["שיעור הצלחה"] < 0.40:
                    _add("negative",
                         f"השכבה החלשה ביותר: {worst['שכבה']} — שיעור הצלחה {worst['שיעור הצלחה']*100:.1f}%.",
                         f"בחן מחדש את תזת ההשקעה ב-{worst['שכבה']}.")

    # ── By time block ────────────────────────────────────────────────────────
    if time_df is not None:
        q = time_df[time_df["עסקאות"] >= 3]
        if not q.empty:
            best_row  = q.loc[q["רווח/הפסד כולל"].idxmax()]
            worst_row = q.loc[q["רווח/הפסד כולל"].idxmin()]
            _add("positive",
                 f"בלוק הזמן הטוב ביותר: {best_row['בלוק']} — "
                 f"שיעור הצלחה {best_row['שיעור הצלחה']*100:.1f}%, "
                 f"רווח כולל ${best_row['רווח/הפסד כולל']:+,.0f}.",
                 f"רכז יותר עסקאות בחלון {best_row['בלוק']}.")
            if best_row["בלוק"] != worst_row["בלוק"]:
                _add("negative",
                     f"בלוק הזמן הגרוע ביותר: {worst_row['בלוק']} — "
                     f"שיעור הצלחה {worst_row['שיעור הצלחה']*100:.1f}%.",
                     f"שקול להימנע ממסחר בשעות {worst_row['בלוק']}.")
            # Danger: any block with win_rate < 35%
            danger = q[q["שיעור הצלחה"] < 0.35]
            for _, dr in danger.iterrows():
                _add("danger",
                     f"אזור סכנה: {dr['בלוק']} — שיעור הצלחה {dr['שיעור הצלחה']*100:.1f}% בלבד "
                     f"({int(dr['עסקאות'])} עסקאות).",
                     f"הפסק לסחור בבלוק {dr['בלוק']} עד שתזהה את הגורם להפסדים.")

    # ── By setup ─────────────────────────────────────────────────────────────
    if setup_df is not None:
        q = setup_df[setup_df["עסקאות"] >= 3]
        if not q.empty:
            best_s  = q.loc[q["שיעור הצלחה"].idxmax()]
            worst_s = q.loc[q["שיעור הצלחה"].idxmin()]
            _add("positive",
                 f"ה-Setup הטוב ביותר: {best_s['סטאפ']} — שיעור הצלחה {best_s['שיעור הצלחה']*100:.1f}%.",
                 f"הגדל את מספר העסקאות בסטאפ {best_s['סטאפ']}.")
            if best_s["סטאפ"] != worst_s["סטאפ"]:
                _add("negative",
                     f"ה-Setup החלש ביותר: {worst_s['סטאפ']} — שיעור הצלחה {worst_s['שיעור הצלחה']*100:.1f}%.",
                     f"בצע בדיקת לוגיקה לסטאפ {worst_s['סטאפ']} — תנאי הכניסה ייתכן שאינם אמינים.")
            danger_s = q[q["שיעור הצלחה"] < 0.35]
            for _, dr in danger_s.iterrows():
                _add("danger",
                     f"סטאפ מסוכן: {dr['סטאפ']} — שיעור הצלחה {dr['שיעור הצלחה']*100:.1f}% בלבד.",
                     f"הפסק להשתמש בסטאפ {dr['סטאפ']} בתנאי השוק הנוכחיים.")

    if not patterns:
        _add("info",
             "לא זוהו דפוסים מובהקים עדיין.",
             "נדרש מינימום 3 עסקאות בכל קטגוריה לזיהוי דפוסים אמינים. הוסף עוד עסקאות.")
    return patterns


# ── Render helpers ────────────────────────────────────────────────────────────

def _render_upload_hint() -> None:
    """Collapsible expander listing the expected CSV column names."""
    with st.expander("📋 אילו עמודות נדרשות ב-CSV?", expanded=False):
        st.markdown(
            '<div dir="rtl" style="font-size:11px;color:#aaa;line-height:1.9">'
            '<b style="color:#00cf8d">חובה:</b> עמודת P&L (p&l / pnl / realized p&l / gain/loss / profit/loss / net amount)<br>'
            '<b style="color:#aaa">אופציונלי:</b>'
            '<ul style="margin:4px 0 0 0;padding-right:18px">'
            '<li><b>symbol / ticker / stock</b> — סימול המניה</li>'
            '<li><b>entry date / open date / trade date</b> — תאריך הכניסה</li>'
            '<li><b>entry time / open time</b> — שעת הכניסה (HH:MM)</li>'
            '<li><b>entry price / open price / avg entry</b> — מחיר כניסה</li>'
            '<li><b>exit price / close price / avg exit</b> — מחיר יציאה</li>'
            '<li><b>shares / qty / quantity</b> — מספר מניות</li>'
            '<li><b>setup type / setup / strategy / pattern</b> — סוג הסטאפ (ORB, VWAP Bounce, וכו\')</li>'
            '</ul>'
            '<b style="color:#aaa">טיפ:</b> הוסף עמודת "Setup Type" ידנית ב-Excel לפני ההעלאה.'
            '</div>',
            unsafe_allow_html=True,
        )


def _render_summary_strip(df: pd.DataFrame) -> None:
    """One-line strip: trade count, symbols, date range."""
    n_trades = len(df)
    n_symbols = df["symbol"].nunique() if "symbol" in df.columns else "—"

    dates = df.get("entry_date_parsed", pd.Series(dtype=object)).dropna()
    if len(dates) > 0:
        d_min = str(min(dates))
        d_max = str(max(dates))
        date_range = f"{d_min} — {d_max}"
    else:
        date_range = "—"

    portfolio_count = int((df["source"] == "portfolio").sum()) if "source" in df.columns else 0
    csv_count       = int((df["source"] == "csv").sum())       if "source" in df.columns else 0
    source_detail   = f"תיק: {portfolio_count}"
    if csv_count:
        source_detail += f" | CSV: {csv_count}"

    st.markdown(
        f'<div dir="rtl" style="font-size:12px;color:{COLOR["text_dim"]};'
        f'background:#1a1a1a;border-radius:6px;padding:8px 14px;margin-bottom:14px">'
        f'✅ <b style="color:{COLOR["primary"]}">{n_trades}</b> עסקאות | '
        f'<b style="color:{COLOR["primary"]}">{n_symbols}</b> סימולים | '
        f'תאריכים: {date_range} | {source_detail}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _pnl_color(v: float) -> str:
    return COLOR["positive"] if v > 0 else (COLOR["negative"] if v < 0 else COLOR["neutral"])


def _render_kpi_grid(overall: Dict[str, Any]) -> None:
    """Two rows of 4 KPI cards for overall statistics."""

    def _kpi(label: str, value: str, color: str, sub: str = "") -> str:
        return (
            f'<div style="background:#1a1f2e;border:1px solid #1f2937;border-radius:8px;'
            f'padding:12px 14px;text-align:right;direction:rtl;height:90px">'
            f'<div style="font-size:10px;color:{COLOR["text_dim"]};margin-bottom:3px">{label}</div>'
            f'<div style="font-size:18px;font-weight:800;color:{color};line-height:1.1">{value}</div>'
            f'<div style="font-size:10px;color:{COLOR["text_dim"]};margin-top:2px">{sub}</div>'
            f'</div>'
        )

    def _fmt_pnl(v: Optional[float], prefix: str = "$") -> str:
        if v is None:
            return "—"
        return f'{prefix}{v:+,.2f}' if v != 0 else f'{prefix}0.00'

    wr  = overall.get("win_rate")
    exp = overall.get("expectancy")

    # Win rate color
    if wr is None:
        wr_color = COLOR["neutral"]
        wr_str   = "—"
    elif wr >= 0.55:
        wr_color = COLOR["positive"]; wr_str = f"{wr*100:.1f}%"
    elif wr >= 0.40:
        wr_color = COLOR["warning"];  wr_str = f"{wr*100:.1f}%"
    else:
        wr_color = COLOR["negative"]; wr_str = f"{wr*100:.1f}%"

    exp_str   = _fmt_pnl(exp, "$") if exp is not None else "—"
    exp_color = _pnl_color(exp or 0)

    wins_total  = overall.get("total_trades", 0)
    wins_count  = round((wr or 0) * wins_total)
    wins_sub    = f"{wins_count} / {wins_total} עסקאות" if wins_total else ""

    row1 = st.columns(4)
    row2 = st.columns(4)

    with row1[0]:
        st.markdown(
            _kpi("📊 סה\"כ עסקאות",
                 str(overall.get("total_trades", "—")),
                 COLOR["primary"]),
            unsafe_allow_html=True)
    with row1[1]:
        st.markdown(
            _kpi("✅ שיעור הצלחה", wr_str, wr_color, wins_sub),
            unsafe_allow_html=True)
    with row1[2]:
        v = overall.get("avg_win")
        st.markdown(
            _kpi("📈 רווח ממוצע",
                 f"${v:,.2f}" if v is not None else "—",
                 COLOR["positive"]),
            unsafe_allow_html=True)
    with row1[3]:
        v = overall.get("avg_loss")
        st.markdown(
            _kpi("📉 הפסד ממוצע",
                 f"${v:,.2f}" if v is not None else "—",
                 COLOR["negative"]),
            unsafe_allow_html=True)

    st.markdown('<div style="margin-top:8px"></div>', unsafe_allow_html=True)

    with row2[0]:
        st.markdown(
            _kpi("⚖️ ציפייה (Expectancy)", exp_str, exp_color, "לעסקה ממוצעת"),
            unsafe_allow_html=True)
    with row2[1]:
        v = overall.get("largest_win")
        st.markdown(
            _kpi("🏆 רווח גדול ביותר",
                 f"${v:,.2f}" if v is not None else "—",
                 COLOR["positive"]),
            unsafe_allow_html=True)
    with row2[2]:
        v = overall.get("largest_loss")
        st.markdown(
            _kpi("💔 הפסד גדול ביותר",
                 f"${v:,.2f}" if v is not None else "—",
                 COLOR["negative"]),
            unsafe_allow_html=True)
    with row2[3]:
        v = overall.get("total_pnl")
        pnl_c = _pnl_color(v or 0)
        st.markdown(
            _kpi("💰 רווח/הפסד כולל",
                 f"${v:+,.2f}" if v is not None else "—",
                 pnl_c),
            unsafe_allow_html=True)


def _render_html_table(
    df: pd.DataFrame,
    title: str,
    highlight_rows: Optional[Dict[int, str]] = None,
) -> None:
    """
    Render an analysis DataFrame as a dark-theme RTL HTML table.
    highlight_rows: {row_index: background_hex} for best/worst rows.
    Columns starting with '_' are hidden.
    P&L columns are colored green/red. Win rate column (fraction) shown as %.
    """
    display_cols = [c for c in df.columns if not c.startswith("_")]
    display_df   = df[display_cols].reset_index(drop=True)

    _TH = (
        f"padding:5px 10px;color:{COLOR['primary']};"
        f"border-bottom:2px solid #333;font-size:11px;text-align:right;white-space:nowrap"
    )
    _TD = "padding:6px 10px;font-size:11px;text-align:right"

    # Header
    header_cells = "".join(f'<th style="{_TH}">{c}</th>' for c in display_cols)

    rows_html = ""
    for i, (_, row) in enumerate(display_df.iterrows()):
        if highlight_rows and i in highlight_rows:
            bg_hex = highlight_rows[i]
            # Determine if best (green) or worst (red)
            is_green = COLOR["positive"] in bg_hex or bg_hex.startswith("#0a2")
            border_c = COLOR["positive"] if is_green else COLOR["negative"]
            row_style = (
                f"background:{bg_hex};"
                f"border-left:3px solid {border_c}"
            )
        else:
            row_style = "background:#161616" if i % 2 == 0 else "background:#1a1a1a"

        cells = ""
        for col in display_cols:
            val = row[col]
            cell_style = _TD
            cell_str   = str(val) if val is not None else "—"

            # Format win rate (stored as fraction 0.0–1.0)
            if col == "שיעור הצלחה":
                try:
                    f = float(val)
                    cell_str = f"{f*100:.1f}%"
                    if f >= 0.55:
                        cell_style += f";color:{COLOR['positive']};font-weight:600"
                    elif f < 0.40:
                        cell_style += f";color:{COLOR['negative']};font-weight:600"
                    else:
                        cell_style += f";color:{COLOR['warning']}"
                except (TypeError, ValueError):
                    pass

            # Format P&L columns
            elif col in ("רווח/הפסד כולל", "רווח ממוצע", "הפסד ממוצע"):
                try:
                    f = float(val)
                    c = _pnl_color(f)
                    cell_str   = f"${f:+,.2f}"
                    cell_style += f";color:{c};font-weight:600"
                except (TypeError, ValueError):
                    pass

            cells += f'<td style="{cell_style}">{cell_str}</td>'

        rows_html += f'<tr style="{row_style}">{cells}</tr>'

    html = (
        f'<div dir="rtl" style="overflow-x:auto;margin-top:4px">'
        f'<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def _get_time_highlights(time_df: pd.DataFrame) -> Dict[int, str]:
    """Extract row indices for best/worst time blocks → background hex dict."""
    result: Dict[int, str] = {}
    for i, row in time_df.iterrows():
        if row.get("_best"):
            result[i] = "#0a2a0a"
        elif row.get("_worst"):
            result[i] = "#2a0a0a"
    return result


def _render_patterns(patterns: List[Dict[str, Any]]) -> None:
    """Render pattern dicts as styled HTML cards."""
    _COLORS = {
        "positive": COLOR["positive"],
        "negative": COLOR["negative"],
        "danger":   COLOR["warning"],
        "info":     COLOR["neutral"],
    }
    _ICONS = {
        "positive": "✅",
        "negative": "⚠️",
        "danger":   "🚨",
        "info":     "ℹ️",
    }
    cards_html = ""
    for p in patterns:
        ptype = p.get("type", "info")
        color = _COLORS.get(ptype, COLOR["neutral"])
        icon  = _ICONS.get(ptype, "ℹ️")
        cards_html += (
            f'<div dir="rtl" style="background:{color}12;border:1px solid {color}44;'
            f'border-radius:8px;padding:12px 16px;margin-bottom:8px">'
            f'<div style="font-weight:700;font-size:13px;color:{color};margin-bottom:6px">'
            f'{icon} {p["finding"]}'
            f'</div>'
            f'<div style="font-size:12px;color:#cccccc;line-height:1.6">'
            f'💡 {p["recommendation"]}'
            f'</div></div>'
        )
    st.markdown(cards_html, unsafe_allow_html=True)


# ── Main entry point ──────────────────────────────────────────────────────────

def render_trading_journal(portfolio: dict, data: dict) -> None:
    """Render the trading journal analyzer sub-tab."""
    section_title(
        "יומן עסקאות",
        "ניתוח ביצועי מסחר — כל הלוטים מהתיק + עסקאות סגורות (CSV אופציונלי)",
    )

    # ── Source A: auto-load from portfolio ────────────────────────────────────
    portfolio_df = _portfolio_to_trades(portfolio, data)

    # ── Source B: optional CSV upload ────────────────────────────────────────
    col_upload, col_clear = st.columns([6, 1])
    with col_upload:
        uploaded = st.file_uploader(
            "העלה CSV של עסקאות סגורות (אופציונלי — להוספת עסקאות שנסגרו)",
            type=["csv"],
            key="trade_journal_uploader",
            label_visibility="visible",
        )
    with col_clear:
        st.markdown('<div style="margin-top:28px"></div>', unsafe_allow_html=True)
        has_csv = "_tj_csv_df" in st.session_state
        if st.button("🗑 נקה", key="trade_journal_clear", disabled=not has_csv):
            st.session_state.pop("_tj_csv_df", None)
            st.session_state.pop("_tj_csv_filename", None)
            st.rerun()

    # Process new upload (only if filename changed to avoid re-parsing on every rerun)
    if uploaded is not None:
        stored_name = st.session_state.get("_tj_csv_filename")
        if stored_name != uploaded.name:
            st.session_state["_tj_csv_filename"] = uploaded.name
            try:
                raw = pd.read_csv(uploaded)
                parsed_csv = _parse_csv_trades(raw)
                st.session_state["_tj_csv_df"] = parsed_csv
            except ValueError as exc:
                st.error(str(exc))
                st.session_state.pop("_tj_csv_df", None)
            except Exception as exc:
                st.error(f"שגיאה בלתי צפויה בקריאת הקובץ: {exc}")
                st.session_state.pop("_tj_csv_df", None)

    csv_df: pd.DataFrame = st.session_state.get("_tj_csv_df", pd.DataFrame())
    _render_upload_hint()

    # ── Merge sources ─────────────────────────────────────────────────────────
    if not csv_df.empty and not portfolio_df.empty:
        df = pd.concat([portfolio_df, csv_df], ignore_index=True)
    elif not csv_df.empty:
        df = csv_df
    else:
        df = portfolio_df

    if df.empty:
        st.info(
            "אין נתוני עסקאות לניתוח. "
            "ודא שיש לוטים עם מחיר קנייה מוגדר בתיק, או העלה קובץ CSV."
        )
        return

    _render_summary_strip(df)

    # ── Compute all stats ─────────────────────────────────────────────────────
    overall  = _compute_overall(df)
    layer_df = _compute_by_layer(df)
    setup_df = _compute_by_setup(df)
    time_df  = _compute_by_time(df)
    dow_df   = _compute_by_dow(df)
    patterns = _detect_patterns(overall, layer_df, setup_df, time_df, dow_df)

    # ── Section 1: Overall KPIs ───────────────────────────────────────────────
    st.divider()
    section_title("סטטיסטיקות כלליות", "ביצועי מסחר מצטברים — כל המקורות")
    _render_kpi_grid(overall)
    color_legend([
        (COLOR["positive"], "רווח / שיעור הצלחה ≥ 55%"),
        (COLOR["warning"],  "שיעור הצלחה 40%–55%"),
        (COLOR["negative"], "הפסד / שיעור הצלחה < 40%"),
    ])

    # ── Section 2: By layer ───────────────────────────────────────────────────
    if layer_df is not None:
        st.divider()
        section_title("ביצועים לפי שכבת תיק", "פירוט רווח/הפסד לפי שכבת ההשקעה")
        _render_html_table(layer_df, "ביצועים לפי שכבת תיק")

    # ── Section 3: By setup type ──────────────────────────────────────────────
    if setup_df is not None:
        st.divider()
        section_title("ביצועים לפי סוג סטאפ", "ניתוח יעילות כל אסטרטגיית כניסה")
        _render_html_table(setup_df, "ביצועים לפי סטאפ")

    # ── Section 4: By time of day ─────────────────────────────────────────────
    if time_df is not None:
        st.divider()
        section_title("ביצועים לפי שעת מסחר", "ביצועים לפי בלוקי זמן במהלך יום המסחר")
        display_time = time_df[[c for c in time_df.columns if not c.startswith("_")]]
        _render_html_table(
            display_time,
            "ביצועים לפי שעת מסחר",
            highlight_rows=_get_time_highlights(time_df),
        )

    # ── Section 5: By day of week ─────────────────────────────────────────────
    if dow_df is not None:
        st.divider()
        section_title("ביצועים לפי יום בשבוע", "האם ישנם ימים בשבוע בהם הביצועים טובים יותר?")
        _render_html_table(dow_df, "ביצועים לפי יום בשבוע")

    # ── Section 6: Patterns ───────────────────────────────────────────────────
    st.divider()
    section_title("דפוסים וסיכום", "זיהוי דפוסים אוטומטי והמלצות מבוססות נתונים")
    _render_patterns(patterns)

    term_glossary([
        ("Win Rate", "שיעור עסקאות מרוויחות מסך כל העסקאות."),
        ("Expectancy", "(Win Rate × Avg Win) + (Loss Rate × Avg Loss) — תוחלת רווח לעסקה."),
        ("ציפייה חיובית", "אפילו עם Win Rate מתחת ל-50%, ניתן להיות רווחי אם ה-R:R מספיק גבוה."),
        ("שכבת תיק", "קטגוריית ההשקעה — לדוגמה Compute & Platform, Core (50%), וכו'."),
        ("סטאפ", "אסטרטגיית כניסה — ORB, VWAP Bounce, Momentum וכד'. ניתן להוסיף ידנית ב-CSV."),
        ("אזור סכנה", "שיעור הצלחה מתחת ל-35% עם מינימום 3 עסקאות — אות לבדיקה מחדש."),
    ])
