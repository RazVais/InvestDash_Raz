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

from src.config import COLOR, is_tase_numeric
from src.data.prices import lookup_buy_price
from src.portfolio import save_portfolio, update_lot
from src.ui_helpers import color_legend, section_title, term_glossary

# ── Constants ─────────────────────────────────────────────────────────────────

# CSV column-name normalization: canonical name → accepted raw variants (case-insensitive)
_COL_MAP: Dict[str, List[str]] = {
    "symbol": [
        "symbol", "ticker", "stock",
        "סימול", "סימול המניה", "שם נייר", "נייר ערך", "מניה", "שם", 'ני"ע', "קוד נייר", "נייר",
    ],
    "entry_date": [
        "entry date", "open date", "date opened", "trade date", "date",
        "תאריך", "תאריך ביצוע", "תאריך עסקה", "תאריך קנייה", "תאריך כניסה",
        "תאריך פקודה", "תאריך ערך", "תאריך פתיחה",
    ],
    "entry_time": [
        "entry time", "open time", "time opened",
        "שעת ביצוע", "שעת כניסה", "שעה",
    ],
    "entry_price": [
        "entry price", "open price", "avg entry", "buy price",
        "מחיר", "שער", "מחיר ביצוע", "מחיר קנייה", "מחיר כניסה", "שער ביצוע", "שער קנייה",
    ],
    "exit_date": [
        "exit date", "close date", "date closed",
        "תאריך מכירה", "תאריך יציאה", "תאריך סגירה", "תאריך סיום",
    ],
    "exit_time": [
        "exit time", "close time", "time closed",
        "שעת מכירה", "שעת יציאה", "שעת סגירה",
    ],
    "exit_price": [
        "exit price", "close price", "avg exit", "sell price",
        "מחיר מכירה", "מחיר יציאה", "מחיר סגירה", "שער מכירה", "שער יציאה",
    ],
    "shares": [
        "shares", "qty", "quantity", "size", "units",
        "כמות", "מניות", "יחידות", "נפח", "מס' מניות", "כמות מניות",
    ],
    "pnl": [
        "p&l", "pnl", "realized p&l", "net p&l", "gain/loss", "profit/loss", "net amount",
        "רווח/הפסד", "רווח / הפסד", "רווח והפסד", "תוצאה", "שווי נטו",
        "רווח", "ריווח", "הפסד", "נטו", "סכום נטו",
    ],
    "setup_type": [
        "setup type", "setup", "strategy", "pattern",
        "סוג עסקה", "אסטרטגיה", "סטאפ", "סוג",
    ],
    # Transaction-log specific columns (one row per order)
    "action_type": [
        "action", "type", "transaction type", "order type", "side",
        "סוג פעולה", "פעולה", "סוג הוראה", "סוג עסקה", "כיוון",
    ],
    "value": [
        "value", "amount", "total", "gross amount",
        "שווי", "סכום", "ערך", 'סה"כ', "שווי ביצוע",
    ],
    "commission": [
        "commission", "fee", "fees", "brokerage",
        "עמלה", "דמי ניהול", "עמלת ביצוע",
    ],
}

# Keywords that classify a transaction as buy or sell
_BUY_KEYWORDS  = {"קנייה", "קנ", "buy", "purchase", "long"}
_SELL_KEYWORDS = {"מכירה", "מכ", "sell", "sel", "sale", "short"}

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


# ── Source C: portfolio trade_history (closed/sold lots) ─────────────────────

def _history_to_closed_trades(portfolio: dict) -> pd.DataFrame:
    """Build a trades DataFrame from sell events in portfolio trade_history."""
    history = portfolio.get("trade_history", [])
    rows: List[Dict[str, Any]] = []
    for entry in history:
        if entry.get("action") != "sell":
            continue
        sell_price = entry.get("price")
        buy_price  = entry.get("buy_price")
        shares     = float(entry.get("shares") or 0)
        pnl        = entry.get("pnl")
        if pnl is None and buy_price is not None and sell_price is not None:
            pnl = round((float(sell_price) - float(buy_price)) * shares, 2)
        if pnl is None:
            continue

        buy_date_str  = entry.get("buy_date")
        sell_date_str = entry.get("date")
        sell_date_obj: Optional[datetime.date] = None
        buy_date_obj:  Optional[datetime.date] = None
        try:
            if sell_date_str:
                sell_date_obj = datetime.date.fromisoformat(sell_date_str)
            if buy_date_str:
                buy_date_obj = datetime.date.fromisoformat(buy_date_str)
        except (ValueError, TypeError):
            pass

        rows.append({
            "symbol":            entry.get("ticker", ""),
            "entry_date":        buy_date_str,
            "exit_date":         sell_date_str,
            "entry_date_parsed": buy_date_obj,
            "entry_price":       buy_price,
            "exit_price":        sell_price,
            "shares":            shares,
            "pnl":               round(pnl, 2),
            "layer":             entry.get("layer"),
            "source":            "history",
            "is_win":            pnl > 0,
            "day_of_week": (
                _DOW_LABELS.get(sell_date_obj.weekday())
                if sell_date_obj else None
            ),
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


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


def _classify_action(val: Any) -> str:
    """Classify an action-type cell as 'buy', 'sell', or 'other'."""
    s = str(val).strip().lower()
    if any(k in s for k in _BUY_KEYWORDS):
        return "buy"
    if any(k in s for k in _SELL_KEYWORDS):
        return "sell"
    return "other"


def _to_num(series: "pd.Series") -> "pd.Series":
    """Strip currency/comma formatting and coerce to float."""
    return pd.to_numeric(
        series.astype(str).str.replace(r"[^\d.\-]", "", regex=True),
        errors="coerce",
    )


def _parse_transaction_csv(df: pd.DataFrame, raw_df: pd.DataFrame) -> pd.DataFrame:
    """Handle transaction-log CSVs (one row per buy/sell order).

    Returns ONE ROW PER SYMBOL with:
      - realized_pnl  : sum of broker-reported P&L across all sells for that symbol
      - remaining_shares / avg_buy_price : for positions still open (unrealized P&L
        is added later in render_trading_journal() using current market prices)
      - status        : 'פתוח' (open) | 'סגור' (closed)

    Win/loss is therefore per-position, not per individual trade order.
    """
    df["_action"] = df["action_type"].apply(_classify_action)

    orders = df[df["_action"].isin(["buy", "sell"])].copy()
    if orders.empty:
        found = df["action_type"].dropna().unique()[:8].tolist()
        raise ValueError(
            f"לא זוהו פעולות קנייה/מכירה. ערכי עמודת הפעולה שנמצאו: {found}. "
            "הפקודה צריכה להכיל 'BUY', 'SEL'/'SELL', 'קנייה', 'מכירה' וכד'."
        )

    # Numeric quantities
    orders["_qty"] = _to_num(orders["shares"]).abs() if "shares" in orders.columns else 0.0
    orders["_price"] = _to_num(orders["entry_price"]).abs() if "entry_price" in orders.columns else 0.0

    # Per-row P&L (broker-computed, present in column G of the sample CSV)
    has_pnl_col = "pnl" in orders.columns
    if has_pnl_col:
        orders["_row_pnl"] = (
            orders["pnl"]
            .astype(str)
            .str.replace(r"[₪\$,\s]", "", regex=True)
            .pipe(pd.to_numeric, errors="coerce")
            .fillna(0.0)
        )
    else:
        orders["_row_pnl"] = 0.0

    # Parse datetimes (format "MM/DD/YYYY HH:MM:SS TZ")
    if "entry_date" in orders.columns:
        orders["_dt"] = pd.to_datetime(orders["entry_date"], errors="coerce")
    else:
        orders["_dt"] = pd.NaT

    # Group by symbol — one output row per symbol
    sym_col = "symbol" if "symbol" in orders.columns else None
    groups  = orders.groupby(sym_col, sort=False) if sym_col else [("?", orders)]

    rows: List[Dict[str, Any]] = []
    for ticker, g in groups:
        # Skip rows with no symbol (e.g. CAS cash entries)
        if not ticker or (isinstance(ticker, float) and pd.isna(ticker)):
            continue

        buys  = g[g["_action"] == "buy"]
        sells = g[g["_action"] == "sell"]

        buy_qty   = buys["_qty"].sum()
        sell_qty  = sells["_qty"].sum()
        remaining = max(0.0, buy_qty - sell_qty)

        # Avg buy price = total cost / total shares bought
        buy_cost      = (buys["_qty"] * buys["_price"]).sum()
        avg_buy_price = (buy_cost / buy_qty) if buy_qty > 0 else 0.0

        # Realized P&L — prefer broker-computed column; fall back to value difference
        if has_pnl_col:
            realized_pnl = sells["_row_pnl"].sum()
        else:
            sell_proceeds = (sells["_qty"] * sells["_price"]).sum()
            cost_of_sold  = avg_buy_price * sell_qty
            realized_pnl  = sell_proceeds - cost_of_sold

        # Dates
        buy_dts  = buys["_dt"].dropna()
        sell_dts = sells["_dt"].dropna()
        first_buy_dt  = buy_dts.min()  if len(buy_dts)  > 0 else pd.NaT
        last_sell_dt  = sell_dts.max() if len(sell_dts) > 0 else pd.NaT

        entry_date_str = str(first_buy_dt.date())  if not pd.isna(first_buy_dt)  else None
        exit_date_str  = str(last_sell_dt.date())  if not pd.isna(last_sell_dt)  else None
        entry_date_obj = first_buy_dt.date()        if not pd.isna(first_buy_dt)  else None

        # Time block from the most recent sell (for journal time analysis)
        time_block = "אחר"
        if len(sell_dts) > 0:
            time_block = _assign_time_block(sell_dts.max().time())

        status = "פתוח" if remaining > 0.001 else "סגור"

        # pnl starts as realized; render_trading_journal() adds unrealized for open positions
        rows.append({
            "symbol":           str(ticker),
            "entry_date":       entry_date_str,
            "exit_date":        exit_date_str if status == "סגור" else None,
            "entry_date_parsed": entry_date_obj,
            "shares":           round(buy_qty,        3),
            "remaining_shares": round(remaining,      3),
            "avg_buy_price":    round(avg_buy_price,  4),
            "realized_pnl":     round(realized_pnl,   2),
            "pnl":              round(realized_pnl,   2),  # updated live for open positions
            "status":           status,
            "time_block":       time_block,
            "source":           "csv",
            "is_win":           realized_pnl > 0,
            "day_of_week":      (
                _DOW_LABELS.get(entry_date_obj.weekday())
                if isinstance(entry_date_obj, datetime.date) else None
            ),
        })

    if not rows:
        raise ValueError("לא נמצאו עסקאות קנייה/מכירה בקובץ.")

    return pd.DataFrame(rows)


def _parse_csv_trades(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize CSV columns and build a clean trades DataFrame (Source B).
    Raises ValueError with Hebrew message if required columns are missing.
    """
    df = _normalize_columns(raw_df.copy())

    # ── Transaction-log format: one row per order (buy / sell) ───────────────
    if "action_type" in df.columns:
        return _parse_transaction_csv(df, raw_df)

    if "pnl" not in df.columns:
        # Fallback: compute pnl from entry/exit prices × shares
        has_prices = "exit_price" in df.columns and "entry_price" in df.columns
        has_shares = "shares" in df.columns
        if has_prices and has_shares:
            df["pnl"] = (
                pd.to_numeric(
                    df["exit_price"].astype(str).str.replace(r"[^\d.\-]", "", regex=True),
                    errors="coerce",
                ) -
                pd.to_numeric(
                    df["entry_price"].astype(str).str.replace(r"[^\d.\-]", "", regex=True),
                    errors="coerce",
                )
            ) * pd.to_numeric(
                df["shares"].astype(str).str.replace(r"[^\d.\-]", "", regex=True),
                errors="coerce",
            )
        else:
            found_cols = ", ".join(raw_df.columns[:12].tolist())
            raise ValueError(
                "לא נמצאה עמודת P&L בקובץ. "
                f"עמודות שנמצאו: {found_cols}. "
                "ודא שהקובץ מכיל עמודה בשם: p&l / pnl / רווח/הפסד / gain/loss."
            )

    # Coerce pnl: strip currency symbols and formatting before numeric conversion
    df["pnl"] = (
        df["pnl"]
        .astype(str)
        .str.replace(r"[₪\$,\s]", "", regex=True)
        .pipe(pd.to_numeric, errors="coerce")
    )
    df = df.dropna(subset=["pnl"])
    if df.empty:
        raise ValueError("לא נמצאו שורות עם ערכי P&L תקינים בקובץ.")

    df["is_win"] = df["pnl"] > 0
    df["source"] = "csv"

    # Parse entry_date — dayfirst=True handles DD/MM/YYYY common in Israeli exports
    if "entry_date" in df.columns:
        df["entry_date_parsed"] = pd.to_datetime(
            df["entry_date"], errors="coerce", dayfirst=True
        ).dt.date
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
    """Breakdown by portfolio layer (open lots + closed history trades)."""
    if "layer" not in df.columns or "source" not in df.columns:
        return None
    sub = df[df["source"].isin(["portfolio", "history"]) & df["layer"].notna()]
    if sub.empty:
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
            '<b style="color:#00cf8d">פורמט 1 — היסטוריית הוראות (שורה לכל קנייה/מכירה):</b><br>'
            '<ul style="margin:2px 0 8px 0;padding-right:18px">'
            '<li><b>סוג פעולה / action / type</b> — קנייה / מכירה (חובה לזיהוי)</li>'
            '<li><b>ני"ע / symbol / ticker</b> — סימול הנייר</li>'
            '<li><b>תאריך ביצוע / date / entry date</b> — תאריך העסקה</li>'
            '<li><b>שווי / value / amount</b> — שווי כולל של ההוראה (או: כמות × שער)</li>'
            '<li><b>כמות / shares / qty</b> — כמות מניות</li>'
            '<li><b>שער / entry price</b> — מחיר ביצוע</li>'
            '<li><b>עמלה / commission</b> — עמלה (אופציונלי)</li>'
            '</ul>'
            '<b style="color:#00cf8d">פורמט 2 — יומן עסקאות (שורה לכל עסקה שלמה עם P&L):</b><br>'
            '<ul style="margin:2px 0 8px 0;padding-right:18px">'
            '<li><b>p&l / pnl / רווח/הפסד / gain/loss</b> — רווח/הפסד לעסקה (חובה)</li>'
            '<li><b>symbol / ticker</b> — סימול, entry/exit date, entry/exit price, shares (אופציונלי)</li>'
            '<li><b>setup type / strategy</b> — סוג הסטאפ (אופציונלי)</li>'
            '</ul>'
            '<b style="color:#aaa">💡 טיפ:</b> ייצוא ישיר מ-IBI / הפועלים / לאומי / דיסקונט נתמך אוטומטית.'
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
    history_count   = int((df["source"] == "history").sum())   if "source" in df.columns else 0
    source_detail   = f"תיק פתוח: {portfolio_count}"
    if history_count:
        source_detail += f" | עסקאות סגורות: {history_count}"
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
        wr_color = COLOR["positive"]
        wr_str = f"{wr*100:.1f}%"
    elif wr >= 0.40:
        wr_color = COLOR["warning"]
        wr_str = f"{wr*100:.1f}%"
    else:
        wr_color = COLOR["negative"]
        wr_str = f"{wr*100:.1f}%"

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


# ── Live price enrichment ─────────────────────────────────────────────────────

def _apply_live_prices(csv_raw: pd.DataFrame, prices: dict) -> pd.DataFrame:
    """Return a copy of the CSV DataFrame with unrealized P&L added for open positions.

    Open positions have remaining_shares > 0.  For those, total pnl =
    realized_pnl + (current_price - avg_buy_price) × remaining_shares.
    is_win and current_price columns are updated accordingly.
    Called on every render so the unrealized figure stays fresh without
    re-parsing the CSV.
    """
    if csv_raw.empty or "remaining_shares" not in csv_raw.columns:
        return csv_raw

    df = csv_raw.copy()
    df["current_price"] = None

    for idx, row in df.iterrows():
        if row.get("status") != "פתוח":
            continue
        remaining  = row.get("remaining_shares", 0) or 0
        avg_cost   = row.get("avg_buy_price",    0) or 0
        realized   = row.get("realized_pnl",     0) or 0
        ticker     = str(row.get("symbol", ""))
        if remaining <= 0 or avg_cost <= 0 or not ticker:
            continue
        cur_price = (prices.get(ticker) or {}).get("price")
        if cur_price is None:
            continue
        unrealized = (cur_price - avg_cost) * remaining
        df.at[idx, "pnl"]           = round(realized + unrealized, 2)
        df.at[idx, "is_win"]        = (realized + unrealized) > 0
        df.at[idx, "current_price"] = round(cur_price, 2)

    return df


# ── Main entry point ──────────────────────────────────────────────────────────

def _render_trade_history(portfolio: dict, prices: dict) -> None:
    """Unified trade list: open portfolio lots + history sells + CSV trades (no dups).

    Deduplication strategy: the CSV is the authoritative source. Any ticker that
    appears in the CSV is owned by the CSV — portfolio lots and history sells for
    that same ticker are suppressed so each position appears exactly once.
    """
    rows: List[Dict[str, Any]] = []

    # ── Pre-compute tickers covered by the CSV ────────────────────────────────
    _csv_raw: "pd.DataFrame" = st.session_state.get("_tj_csv_df", pd.DataFrame())
    csv_tickers: set = set()
    if not _csv_raw.empty and "symbol" in _csv_raw.columns:
        for t in _csv_raw["symbol"].dropna():
            s = str(t).strip().upper()
            if s:
                csv_tickers.add(s)

    # ── Source 1: open lots from portfolio (skip tickers owned by CSV) ────────
    for layer, lots in portfolio.get("layers", {}).items():
        for lot in lots:
            shares = float(lot.get("shares") or 0)
            if shares <= 0:
                continue
            ticker    = lot.get("ticker", "")
            if ticker.upper() in csv_tickers:
                continue          # CSV owns this ticker
            buy_date  = lot.get("buy_date", "")
            buy_price = lot.get("buy_price")
            cur_price = (prices.get(ticker) or {}).get("price")
            cost      = buy_price * shares if buy_price else None
            pnl       = round((cur_price - buy_price) * shares, 2) if (buy_price and cur_price) else None
            pnl_pct   = (pnl / cost * 100) if (pnl is not None and cost) else None
            rows.append({
                "entry_date":  buy_date,
                "exit_date":   "",
                "ticker":      ticker,
                "status":      "פתוח",
                "shares":      shares,
                "entry_price": buy_price,
                "exit_price":  cur_price,
                "cost":        cost,
                "pnl":         pnl,
                "pnl_pct":     pnl_pct,
                "layer":       layer,
                "source":      "תיק",
            })

    # ── Source 2: history sells (skip tickers owned by CSV) ──────────────────
    for entry in portfolio.get("trade_history", []):
        if entry.get("action") != "sell":
            continue
        ticker = entry.get("ticker", "")
        if ticker.upper() in csv_tickers:
            continue              # CSV owns this ticker
        buy_price  = entry.get("buy_price")
        sell_price = entry.get("price")
        shares     = float(entry.get("shares") or 0)
        pnl        = entry.get("pnl")
        if pnl is None and buy_price is not None and sell_price is not None:
            pnl = round((float(sell_price) - float(buy_price)) * shares, 2)
        cost    = float(buy_price) * shares if buy_price else None
        pnl_pct = (pnl / cost * 100) if (pnl is not None and cost) else None
        rows.append({
            "entry_date":  entry.get("buy_date", ""),
            "exit_date":   entry.get("date") or "",
            "ticker":      ticker,
            "status":      "סגור",
            "shares":      shares,
            "entry_price": buy_price,
            "exit_price":  sell_price,
            "cost":        cost,
            "pnl":         pnl,
            "pnl_pct":     pnl_pct,
            "layer":       entry.get("layer", ""),
            "source":      "היסטוריה",
        })

    # ── Source 3: CSV (authoritative for its tickers, no further dedup needed) ─
    csv_df = _apply_live_prices(_csv_raw, prices)
    if not csv_df.empty:
        is_txn = "remaining_shares" in csv_df.columns
        for _, row in csv_df.iterrows():
            ticker = str(row.get("symbol") or "")
            if not ticker:
                continue
            if is_txn:
                ep = row.get("avg_buy_price")
                xp = row.get("current_price")
                sh = float(row.get("shares") or 0)
            else:
                ep = row.get("entry_price")
                xp = row.get("exit_price")
                sh = float(row.get("shares") or 0)
            try:
                pnl: Optional[float] = float(row.get("pnl")) if row.get("pnl") is not None else None
            except (TypeError, ValueError):
                pnl = None
            ep_f  = float(ep) if ep is not None else None
            xp_f  = float(xp) if xp is not None else None
            cost  = ep_f * sh  if ep_f else None
            pnl_pct = (pnl / cost * 100) if (pnl is not None and cost) else None
            status  = str(row.get("status") or "סגור")
            rows.append({
                "entry_date":  str(row.get("entry_date") or ""),
                "exit_date":   str(row.get("exit_date") or "") if row.get("exit_date") else "",
                "ticker":      ticker,
                "status":      status,
                "shares":      sh,
                "entry_price": ep_f,
                "exit_price":  xp_f,
                "cost":        cost,
                "pnl":         pnl,
                "pnl_pct":     pnl_pct,
                "layer":       str(row.get("layer") or ""),
                "source":      "CSV",
            })

    section_title("רשימת עסקאות", "עסקאות פתוחות וסגורות — תיק, מכירות ו-CSV")

    if not rows:
        st.info("אין עסקאות לתצוגה. קניות ומכירות חדשות יירשמו כאן אוטומטית, או העלה CSV.")
        return

    # closed first (newest exit), then open (newest entry)
    rows.sort(key=lambda r: (r["status"] == "פתוח", r.get("entry_date") or ""), reverse=True)

    open_rows   = [r for r in rows if r["status"] == "פתוח"]
    closed_rows = [r for r in rows if r["status"] != "פתוח"]
    closed_pnl  = sum(r["pnl"] for r in closed_rows if r["pnl"] is not None)
    unrealized  = sum(r["pnl"] for r in open_rows   if r["pnl"] is not None)
    cp_c = COLOR["positive"] if closed_pnl >= 0 else COLOR["negative"]
    ur_c = COLOR["positive"] if unrealized  >= 0 else COLOR["negative"]

    st.markdown(
        f'<div dir="rtl" style="font-size:12px;color:{COLOR["text_dim"]};'
        f'background:#1a1a1a;border-radius:6px;padding:8px 14px;margin-bottom:14px">'
        f'<b style="color:{COLOR["primary"]}">{len(rows)}</b> עסקאות | '
        f'<b style="color:#4CAF50">{len(open_rows)}</b> פתוחות | '
        f'<b style="color:#aaa">{len(closed_rows)}</b> סגורות | '
        f'<b style="color:{COLOR["primary"]}">{len({r["ticker"] for r in rows})}</b> סימולים | '
        f'ממומש: <b style="color:{cp_c}">${closed_pnl:+,.2f}</b> | '
        f'לא ממומש: <b style="color:{ur_c}">${unrealized:+,.2f}</b>'
        f'</div>',
        unsafe_allow_html=True,
    )

    _TH = (
        f"padding:5px 10px;color:{COLOR['primary']};"
        f"border-bottom:2px solid #333;font-size:11px;text-align:right;white-space:nowrap"
    )
    _TD  = "padding:5px 10px;font-size:11px;text-align:right"
    _TDF = "padding:5px 10px;font-size:11px;text-align:right;font-weight:700"

    hdr = (
        f'<div dir="rtl" style="overflow-x:auto">'
        f'<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f'<thead><tr>'
        f'<th style="{_TH}">תאריך קנייה</th>'
        f'<th style="{_TH}">Ticker</th>'
        f'<th style="{_TH}">מצב</th>'
        f'<th style="{_TH}">כמות</th>'
        f'<th style="{_TH}">מחיר קנייה</th>'
        f'<th style="{_TH}">מחיר מכירה/נוכחי</th>'
        f'<th style="{_TH}">תאריך מכירה</th>'
        f'<th style="{_TH}">רווח/הפסד $</th>'
        f'<th style="{_TH}">רווח/הפסד %</th>'
        f'<th style="{_TH}">מקור</th>'
        f'</tr></thead><tbody>'
    )

    rows_html = ""
    for i, row in enumerate(rows):
        ticker  = row["ticker"]
        sym     = "₪" if is_tase_numeric(ticker) else "$"
        status  = row["status"]
        pnl     = row.get("pnl")
        pnl_pct = row.get("pnl_pct")
        is_open = status == "פתוח"

        if is_open:
            status_html = '<span style="color:#4CAF50;font-weight:700">🟢 פתוח</span>'
            bg = "#0a1a0a" if i % 2 == 0 else "#0d1d0d"
        else:
            icon  = "🟢" if (pnl or 0) >= 0 else "🔴"
            pnl_c = COLOR["positive"] if (pnl or 0) >= 0 else COLOR["negative"]
            status_html = f'<span style="color:{pnl_c};font-weight:700">{icon} סגור</span>'
            bg = "#161616" if i % 2 == 0 else "#1a1a1a"

        ep     = row.get("entry_price")
        xp     = row.get("exit_price")
        ep_str = f"{sym}{ep:,.2f}" if ep is not None else "—"
        xp_str = (
            f'<span style="color:{COLOR["text_dim"]}">{sym}{xp:,.2f}</span>'
            if (is_open and xp is not None)
            else (f"{sym}{xp:,.2f}" if xp is not None else "—")
        )

        if pnl is not None:
            pnl_c      = COLOR["positive"] if pnl >= 0 else COLOR["negative"]
            note       = ' <span style="font-size:9px;color:#888">(לא ממומש)</span>' if is_open else ""
            dollar_str = f'<span style="color:{pnl_c};font-weight:700">{sym}{pnl:+,.2f}</span>{note}'
            pct_str    = (
                f'<span style="color:{pnl_c};font-weight:700">{pnl_pct:+.2f}%</span>'
                if pnl_pct is not None else "—"
            )
        else:
            dollar_str = "—"
            pct_str    = "—"

        source_c = {"תיק": COLOR["primary"], "היסטוריה": "#94a3b8", "CSV": "#f59e0b"}.get(
            row.get("source", ""), "#888"
        )
        src_html = f'<span style="color:{source_c};font-size:10px">{row.get("source","")}</span>'
        exit_str = row["exit_date"] if row["exit_date"] else "—"

        rows_html += (
            f'<tr style="background:{bg}">'
            f'<td style="{_TD}">{row["entry_date"]}</td>'
            f'<td style="{_TD};font-weight:700;color:{COLOR["primary"]}">{ticker}</td>'
            f'<td style="{_TD}">{status_html}</td>'
            f'<td style="{_TD}">{row.get("shares", 0):.3f}</td>'
            f'<td style="{_TD}">{ep_str}</td>'
            f'<td style="{_TD}">{xp_str}</td>'
            f'<td style="{_TD};color:{COLOR["text_dim"]}">{exit_str}</td>'
            f'<td style="{_TD}">{dollar_str}</td>'
            f'<td style="{_TD}">{pct_str}</td>'
            f'<td style="{_TD}">{src_html}</td>'
            f'</tr>'
        )

    # ── Total row ─────────────────────────────────────────────────────────────
    total_pnl  = sum(r["pnl"]  for r in rows if r["pnl"]  is not None)
    total_cost = sum(r["cost"] for r in rows if r["cost"] is not None)
    total_pct  = (total_pnl / total_cost * 100) if total_cost else None
    tot_c      = COLOR["positive"] if total_pnl >= 0 else COLOR["negative"]
    tot_pct_str = f'<span style="color:{tot_c};font-weight:800">{total_pct:+.2f}%</span>' if total_pct is not None else "—"

    rows_html += (
        f'<tr style="background:#0a1229;border-top:2px solid {COLOR["primary"]}">'
        f'<td style="{_TDF};color:{COLOR["primary"]}" colspan="7">סה״כ</td>'
        f'<td style="{_TDF};color:{tot_c}">${total_pnl:+,.2f}</td>'
        f'<td style="{_TDF}">{tot_pct_str}</td>'
        f'<td style="{_TD}"></td>'
        f'</tr>'
    )

    st.markdown(f'{hdr}{rows_html}</tbody></table></div>', unsafe_allow_html=True)
    color_legend([
        (COLOR["primary"],  "עמדות פתוחות (תיק)"),
        (COLOR["positive"], "עסקה סגורה ברווח"),
        (COLOR["negative"], "עסקה סגורה בהפסד"),
        ("#f59e0b",         "מ-CSV"),
    ])

    # ── Edit panel ────────────────────────────────────────────────────────────
    editable = [(i, r) for i, r in enumerate(rows) if r["source"] in ("תיק", "היסטוריה")]
    if not editable:
        return

    with st.expander("✏️ ערוך עסקה"):
        opt_labels = [
            f"{r['ticker']} | {r['entry_date']} | {r['source']}"
            for _, r in editable
        ]
        sel_label = st.selectbox("בחר עסקה", opt_labels, key="tj_edit_sel")
        sel_pos   = opt_labels.index(sel_label)
        sel_row   = editable[sel_pos][1]
        is_hist   = sel_row["source"] == "היסטוריה"

        c1, c2, c3 = st.columns(3)
        with c1:
            new_entry_date = st.text_input(
                "תאריך קנייה", value=sel_row["entry_date"] or "", key="tj_ed_edate"
            )
            new_shares = st.number_input(
                "כמות", value=float(sel_row["shares"] or 0),
                min_value=0.0, step=0.001, format="%.3f", key="tj_ed_shares"
            )
        with c2:
            new_ep = st.number_input(
                "מחיר קנייה",
                value=float(sel_row["entry_price"] or 0),
                min_value=0.0, step=0.01, format="%.4f", key="tj_ed_ep"
            )
            if is_hist:
                new_xp = st.number_input(
                    "מחיר מכירה",
                    value=float(sel_row.get("exit_price") or 0),
                    min_value=0.0, step=0.01, format="%.2f", key="tj_ed_xp"
                )
        with c3:
            if is_hist:
                new_exit_date = st.text_input(
                    "תאריך מכירה",
                    value=sel_row.get("exit_date") or "",
                    key="tj_ed_xdate"
                )

        if st.button("💾 שמור שינויים", key="tj_ed_save", type="primary"):
            if sel_row["source"] == "תיק":
                update_lot(
                    portfolio,
                    sel_row.get("layer", ""),
                    sel_row["ticker"],
                    sel_row["entry_date"],
                    new_shares,
                    new_entry_date.strip() or sel_row["entry_date"],
                    buy_price=new_ep if new_ep > 0 else sel_row.get("entry_price"),
                )
            else:
                orig_buy_d  = sel_row["entry_date"]
                orig_sell_d = sel_row.get("exit_date") or ""
                for hist_entry in portfolio.get("trade_history", []):
                    if (hist_entry.get("action") == "sell"
                            and hist_entry.get("ticker", "").upper() == sel_row["ticker"].upper()
                            and hist_entry.get("buy_date", "") == orig_buy_d
                            and hist_entry.get("date", "") == orig_sell_d):
                        hist_entry["shares"]    = round(new_shares, 4)
                        hist_entry["buy_price"] = round(new_ep, 4)
                        if new_entry_date.strip():
                            hist_entry["buy_date"] = new_entry_date.strip()
                        hist_entry["price"] = round(new_xp, 4)
                        if new_exit_date.strip():
                            hist_entry["date"] = new_exit_date.strip()
                        bp = hist_entry.get("buy_price")
                        sp = hist_entry.get("price")
                        sh = hist_entry.get("shares")
                        if bp and sp and sh:
                            hist_entry["pnl"] = round(
                                (float(sp) - float(bp)) * float(sh), 2
                            )
                        break
                save_portfolio(portfolio)
            st.rerun()


def render_trading_journal(portfolio: dict, data: dict) -> None:
    """Render the trading journal analyzer sub-tab."""
    section_title(
        "יומן עסקאות",
        "ניתוח ביצועי מסחר — כל הלוטים מהתיק + עסקאות סגורות (CSV אופציונלי)",
    )

    # ── Source A: auto-load from portfolio (open lots) ───────────────────────
    portfolio_df = _portfolio_to_trades(portfolio, data)

    # ── Source C: closed trades from trade_history ────────────────────────────
    history_df = _history_to_closed_trades(portfolio)

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

    # Process new upload — retry every render until success (filename stored only on success)
    if uploaded is not None:
        stored_name = st.session_state.get("_tj_csv_filename")
        if stored_name != uploaded.name:
            raw: Optional[pd.DataFrame] = None
            try:
                # Try common encodings — Israeli broker exports use UTF-8 BOM or cp1255
                for enc in ("utf-8-sig", "cp1255", "windows-1255", "utf-8", "latin-1"):
                    try:
                        uploaded.seek(0)
                        candidate = pd.read_csv(uploaded, encoding=enc)
                        if len(candidate.columns) >= 2:
                            raw = candidate
                            break
                    except Exception:
                        continue

                if raw is None:
                    raise ValueError(
                        "לא ניתן לקרוא את הקובץ. "
                        "נסה לשמור מחדש כ-CSV (UTF-8) מתוך Excel."
                    )

                # Detect semicolon-separated files (European/Israeli locale export)
                if len(raw.columns) <= 1:
                    uploaded.seek(0)
                    raw = pd.read_csv(uploaded, sep=";", encoding="utf-8-sig")

                parsed_csv = _parse_csv_trades(raw)
                # Filename stored ONLY on success so failed files are retried on next render
                st.session_state["_tj_csv_filename"] = uploaded.name
                st.session_state["_tj_csv_df"] = parsed_csv

            except ValueError as exc:
                st.error(str(exc))
                if raw is not None:
                    with st.expander("🔍 עמודות שנמצאו בקובץ (לאבחון)", expanded=True):
                        st.caption("רשימת השמות שנמצאו — השווה לטבלת הפורמט הנדרש למעלה:")
                        st.write(list(raw.columns))
                        st.dataframe(raw.head(3))
                st.session_state.pop("_tj_csv_df", None)
            except Exception as exc:
                st.error(f"שגיאה בלתי צפויה בקריאת הקובץ: {exc}")
                if raw is not None:
                    with st.expander("🔍 עמודות שנמצאו (לאבחון)", expanded=True):
                        st.write(list(raw.columns))
                st.session_state.pop("_tj_csv_df", None)

    # Load raw parsed CSV from session_state, then apply live prices to open positions
    _csv_raw: pd.DataFrame = st.session_state.get("_tj_csv_df", pd.DataFrame())
    csv_df = _apply_live_prices(_csv_raw, data.get("prices", {}))
    _render_upload_hint()

    # ── Trade list (all sources) ──────────────────────────────────────────────
    st.divider()
    _render_trade_history(portfolio, data.get("prices", {}))

    # ── Merge sources ─────────────────────────────────────────────────────────
    frames = [f for f in [portfolio_df, history_df, csv_df] if not f.empty]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

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


# ── Public helper for P&L tab ─────────────────────────────────────────────────

def render_closed_trades_summary(prices: Optional[dict] = None) -> None:
    """Render a realized + unrealized P&L section from uploaded CSV.

    Called from portfolio_tab.py so closed-trade data surfaces in the P&L sub-tab
    without modifying portfolio lots.  Accepts prices dict for live valuation of
    open (not-yet-fully-sold) positions.
    """
    _csv_raw: pd.DataFrame = st.session_state.get("_tj_csv_df", pd.DataFrame())
    if _csv_raw.empty:
        return
    csv_df = _apply_live_prices(_csv_raw, prices or {})

    section_title("עסקאות סגורות — מ-CSV", "רווח/הפסד ממומש מקובץ עסקאות שהועלה")

    overall   = _compute_overall(csv_df)
    total_pnl = overall.get("total_pnl") or 0.0
    win_rate  = overall.get("win_rate")
    n_trades  = overall.get("total_trades", 0)
    filename  = st.session_state.get("_tj_csv_filename", "")

    pnl_c = COLOR["positive"] if total_pnl >= 0 else COLOR["negative"]

    # KPI strip
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(
        f'<div style="background:#1a1f2e;border:1px solid #1f2937;border-radius:8px;'
        f'padding:12px 14px;text-align:right;direction:rtl">'
        f'<div style="font-size:10px;color:#888;margin-bottom:3px">💰 רווח/הפסד ממומש</div>'
        f'<div style="font-size:20px;font-weight:800;color:{pnl_c}">${total_pnl:+,.2f}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    c2.markdown(
        f'<div style="background:#1a1f2e;border:1px solid #1f2937;border-radius:8px;'
        f'padding:12px 14px;text-align:right;direction:rtl">'
        f'<div style="font-size:10px;color:#888;margin-bottom:3px">📊 עסקאות סגורות</div>'
        f'<div style="font-size:20px;font-weight:800;color:{COLOR["primary"]}">{n_trades}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if win_rate is not None:
        wr_c = COLOR["positive"] if win_rate >= 0.55 else (COLOR["warning"] if win_rate >= 0.40 else COLOR["negative"])
        c3.markdown(
            f'<div style="background:#1a1f2e;border:1px solid #1f2937;border-radius:8px;'
            f'padding:12px 14px;text-align:right;direction:rtl">'
            f'<div style="font-size:10px;color:#888;margin-bottom:3px">✅ שיעור הצלחה</div>'
            f'<div style="font-size:20px;font-weight:800;color:{wr_c}">{win_rate*100:.1f}%</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    if filename:
        c4.markdown(
            f'<div style="background:#1a1f2e;border:1px solid #1f2937;border-radius:8px;'
            f'padding:12px 14px;text-align:right;direction:rtl">'
            f'<div style="font-size:10px;color:#888;margin-bottom:3px">📄 קובץ</div>'
            f'<div style="font-size:10px;color:#ccc;word-break:break-all">{filename}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div style="margin-top:10px"></div>', unsafe_allow_html=True)

    # Build display table
    is_position_log = "remaining_shares" in csv_df.columns  # from _parse_transaction_csv

    if is_position_log:
        col_rename = {
            "symbol":           "Ticker",
            "entry_date":       "תאריך כניסה",
            "exit_date":        "תאריך יציאה",
            "shares":           "כמות קנויה",
            "remaining_shares": "נותר",
            "avg_buy_price":    "עלות ממוצעת",
            "current_price":    "מחיר נוכחי",
            "realized_pnl":     "ממומש",
            "pnl":              "רווח/הפסד כולל",
            "status":           "מצב",
        }
    else:
        col_rename = {
            "symbol":      "Ticker",
            "entry_date":  "תאריך כניסה",
            "exit_date":   "תאריך יציאה",
            "entry_price": "מחיר כניסה",
            "exit_price":  "מחיר יציאה",
            "shares":      "כמות",
            "pnl":         "רווח/הפסד",
        }

    display_cols = [c for c in col_rename if c in csv_df.columns]
    _HIDDEN = {"source", "is_win", "day_of_week", "time_block", "entry_date_parsed"}
    if display_cols:
        sub = csv_df[display_cols].copy()
        if "pnl" in sub.columns:
            sub = sub.sort_values("pnl", ascending=False)
        sub = sub.rename(columns=col_rename).reset_index(drop=True)
        st.dataframe(sub, use_container_width=True, hide_index=True)
    else:
        raw_cols = [c for c in csv_df.columns if not c.startswith("_") and c not in _HIDDEN]
        if raw_cols:
            st.dataframe(csv_df[raw_cols].head(50), use_container_width=True, hide_index=True)
