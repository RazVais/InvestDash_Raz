"""Daily brief tab — per-ticker feed: price, analyst consensus, flags, and alpha vs VOO."""

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import streamlit as st

from src.config import COLOR, TICKER_NAMES
from src.portfolio import all_tickers
from src.tabs.red_flags import get_all_flag_statuses
from src.ui_helpers import section_title

# ── Claude Haiku brief (cached 1h) ────────────────────────────────────────────

@st.cache_data(ttl=3600)
def _generate_ticker_brief(
    ticker: str,
    brief_data_str: str,
    td_str: str,
    claude_api_key: str,
) -> str:
    """Generate a 2-3 bullet Hebrew brief for ticker via Claude Haiku. Returns HTML string."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=claude_api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    f"כתוב 2-3 נקודות קצרות בעברית על המניה {ticker} בהתאם לנתונים הבאים:\n"
                    f"{brief_data_str}\n\n"
                    "כל נקודה בשורה נפרדת. התמקד ב: (1) סנטימנט אנליסטים, "
                    "(2) סיכון עיקרי אם יש, (3) ביצועים יחסיים. "
                    "ענה בעברית בלבד. אל תוסיף כותרת."
                ),
            }],
        )
        return msg.content[0].text.strip()
    except Exception:
        return ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _consensus_color(label: str) -> str:
    if "Buy" in label or "buy" in label:
        return COLOR["positive"]
    if "Sell" in label or "sell" in label:
        return COLOR["negative"]
    return COLOR["neutral"]


def _change_color(value: float) -> str:
    return COLOR["positive"] if value >= 0 else COLOR["negative"]


def _format_pct(value: float, plus: bool = True) -> str:
    sign = "+" if plus and value >= 0 else ""
    return f"{sign}{value:.1f}%"


def _compute_alpha(
    ticker_history: Optional[pd.Series],
    voo_history: Optional[pd.Series],
    lookback: int = 21,
) -> Optional[float]:
    """1-month alpha of ticker vs VOO. Returns None if insufficient data."""
    if ticker_history is None or voo_history is None:
        return None
    if len(ticker_history) < lookback + 1 or len(voo_history) < lookback + 1:
        return None
    try:
        t_ret = (float(ticker_history.iloc[-1]) / float(ticker_history.iloc[-lookback]) - 1.0) * 100.0
        v_ret = (float(voo_history.iloc[-1]) / float(voo_history.iloc[-lookback]) - 1.0) * 100.0
        return t_ret - v_ret
    except (IndexError, ZeroDivisionError, ValueError):
        return None


def _filter_recent_actions(df: Optional[pd.DataFrame], days: int = 30) -> pd.DataFrame:
    """Return upgrade/downgrade rows from the last `days` calendar days."""
    if df is None or df.empty:
        return pd.DataFrame()
    cutoff = datetime.utcnow() - timedelta(days=days)
    # Keep only rows that are genuine up/downgrades or have notable to_grade
    notable_grades = {
        "buy", "outperform", "strong buy", "overweight",
        "sell", "underperform", "underweight",
    }
    try:
        # Date column may be datetime64 or date objects
        date_col = pd.to_datetime(df["date"], errors="coerce")
        recent = df[date_col >= cutoff].copy()
    except Exception:
        recent = df.copy()

    if recent.empty:
        return pd.DataFrame()

    action_mask = recent["action"].str.contains("Downgrade|Upgrade", case=False, na=False)
    grade_mask = recent["to_grade"].str.lower().isin(notable_grades)
    filtered = recent[action_mask | grade_mask]
    return filtered.head(3)


def _action_pill(action: str, to_grade: str, firm: str) -> str:
    """Build an HTML pill badge for an analyst action."""
    action_lower = action.lower()
    is_positive = (
        "upgrade" in action_lower
        or "initiat" in action_lower
        or to_grade.lower() in {"buy", "outperform", "strong buy", "overweight"}
    )
    arrow = "🔼" if is_positive else "🔽"
    bg_color = "#0d2b1a" if is_positive else "#2d0a0a"
    text_color = COLOR["positive"] if is_positive else COLOR["negative"]
    label = f"{firm}: {action} → {to_grade}" if to_grade else f"{firm}: {action}"
    return (
        f'<span style="display:inline-block;background:{bg_color};'
        f'border:1px solid {text_color}44;border-radius:4px;'
        f'padding:2px 7px;font-size:10px;color:{text_color};'
        f'margin-left:4px;margin-bottom:3px;white-space:nowrap">'
        f'{arrow} {label}</span>'
    )


def _sort_tickers_by_flag(tickers, all_flags):
    """Sort: triggered first, then watch, then ok/nodata."""
    ticker_severity = {}
    for t in tickers:
        flags_for_t = [f for f in all_flags if f["ticker"] == t]
        if any(f["status"] == "triggered" for f in flags_for_t):
            ticker_severity[t] = 0
        elif any(f["status"] == "watch" for f in flags_for_t):
            ticker_severity[t] = 1
        else:
            ticker_severity[t] = 2
    return sorted(tickers, key=lambda t: (ticker_severity.get(t, 2), t))


# ── Card renderer ─────────────────────────────────────────────────────────────

def _render_card(
    ticker: str,
    data: dict,
    all_flags: list,
    voo_history: Optional[pd.Series],
    td_str: str,
    claude_api_key: str,
) -> None:
    """Render one ticker card as an st.markdown HTML block."""
    prices    = data.get("prices", {})
    consensus = data.get("consensus", {})
    targets   = data.get("targets", {})
    upgrades  = data.get("upgrades", {})

    p_data = prices.get(ticker)
    con    = consensus.get(ticker) or {}
    tgt    = targets.get(ticker)

    name = TICKER_NAMES.get(ticker, ticker)

    # ── Price & change ────────────────────────────────────────────────────────
    if p_data:
        price      = p_data.get("price", 0.0)
        change_pct = p_data.get("change", 0.0)
        price_str  = f"${price:,.2f}"
        change_str = _format_pct(change_pct)
        change_col = _change_color(change_pct)
        history    = p_data.get("history")
    else:
        price      = 0.0
        price_str  = "—"
        change_str = "—"
        change_col = COLOR["neutral"]
        history    = None

    # ── Consensus & upside ────────────────────────────────────────────────────
    label    = con.get("label", "N/A")
    con_col  = _consensus_color(label)
    total    = con.get("total", 0)

    if tgt and tgt.get("mean") and p_data and price > 0:
        upside_val = (tgt["mean"] - price) / price * 100.0
        upside_str = _format_pct(upside_val)
        upside_col = _change_color(upside_val)
    else:
        upside_str = "—"
        upside_col = COLOR["neutral"]

    # ── Recent analyst actions ────────────────────────────────────────────────
    upg_df  = upgrades.get(ticker)
    actions = _filter_recent_actions(upg_df, days=30)
    if not actions.empty:
        pill_html = ""
        for _, row in actions.iterrows():
            pill_html += _action_pill(
                str(row.get("action", "")),
                str(row.get("to_grade", "")),
                str(row.get("firm", "")),
            )
        actions_html = f'<div style="margin-top:4px">{pill_html}</div>'
    else:
        actions_html = (
            f'<div style="font-size:11px;color:{COLOR["text_dim"]};margin-top:4px">'
            f'אין שינויים אחרונים</div>'
        )

    # ── Flag row ──────────────────────────────────────────────────────────────
    ticker_flags = [
        f for f in all_flags
        if f["ticker"] == ticker and not str(f["ticker"]).startswith("🗂")
    ]
    if ticker_flags:
        bad_flags = [f for f in ticker_flags if f["status"] in ("triggered", "watch")]
        if bad_flags:
            flag_parts = []
            for f in bad_flags:
                icon = "🔴" if f["status"] == "triggered" else "🟡"
                col  = COLOR["negative"] if f["status"] == "triggered" else COLOR["warning"]
                flag_parts.append(
                    f'<span style="color:{col};font-size:11px;margin-left:8px">'
                    f'{icon} {f["flag"]}</span>'
                )
            flags_html = "".join(flag_parts)
        else:
            flags_html = (
                f'<span style="color:{COLOR["positive"]};font-size:11px">🟢 תקין</span>'
            )
        nodata_flags = [f for f in ticker_flags if f["status"] == "nodata"]
        if nodata_flags and not bad_flags:
            flags_html = (
                f'<span style="color:{COLOR["dim"]};font-size:11px">⚫ אין נתונים</span>'
            )
    else:
        flags_html = (
            f'<span style="color:{COLOR["dim"]};font-size:11px">⚫ אין נתונים</span>'
        )

    # ── Alpha vs VOO ──────────────────────────────────────────────────────────
    alpha = _compute_alpha(history, voo_history, lookback=21)
    if alpha is not None:
        alpha_str = _format_pct(alpha)
        alpha_col = _change_color(alpha)
        alpha_label = f'<span style="color:{alpha_col};font-weight:600">{alpha_str} vs VOO</span>'
    else:
        alpha_label = f'<span style="color:{COLOR["neutral"]}">—</span>'

    # ── AI brief ──────────────────────────────────────────────────────────────
    ai_section_html = ""
    if claude_api_key:
        brief_data_lines = [
            f"קונצנזוס: {label} ({total} אנליסטים)",
        ]
        if upside_str != "—":
            brief_data_lines.append(f"אפסייד: {upside_str}")
        if bad_flags:
            flag_names = ", ".join(f["flag"] for f in bad_flags)
            brief_data_lines.append(f"דגלים: {flag_names}")
        if alpha is not None:
            brief_data_lines.append(f"אלפא חודשי vs VOO: {alpha_str}")
        brief_data_str = "\n".join(brief_data_lines)

        brief_text = _generate_ticker_brief(ticker, brief_data_str, td_str, claude_api_key)
        if brief_text:
            # Turn each line into a visual bullet point
            lines = [ln.strip() for ln in brief_text.split("\n") if ln.strip()]
            bullets = "".join(
                f'<div style="margin-bottom:4px">• {ln}</div>'
                for ln in lines
            )
            ai_section_html = (
                f'<div style="margin-top:10px;padding:10px 12px;'
                f'background:#0a1a11;border:1px solid {COLOR["primary"]}33;'
                f'border-radius:6px;font-size:11px;color:#d0e8da;line-height:1.7">'
                f'<div style="font-size:10px;color:{COLOR["primary"]};'
                f'font-weight:600;margin-bottom:6px">🤖 סיכום AI</div>'
                f'{bullets}</div>'
            )

    # ── Assemble card HTML ────────────────────────────────────────────────────
    card_html = (
        f'<div dir="rtl" style="'
        f'background:#1a1f2e;'
        f'border:1px solid #1f2937;'
        f'border-radius:8px;'
        f'padding:14px 18px;'
        f'margin-bottom:10px;'
        f'font-family:inherit">'

        # Header row: ticker name | price + change
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
        f'  <div>'
        f'    <span style="font-size:16px;font-weight:700;color:{COLOR["primary"]}">{ticker}</span>'
        f'    <span style="font-size:12px;color:{COLOR["text_dim"]};margin-right:6px"> — {name}</span>'
        f'  </div>'
        f'  <div style="text-align:left">'
        f'    <span style="font-size:14px;font-weight:600;color:#ffffff">{price_str}</span>'
        f'    <span style="font-size:12px;color:{change_col};margin-right:6px"> {change_str}</span>'
        f'  </div>'
        f'</div>'

        # Analyst row: consensus | upside
        f'<div style="display:flex;gap:16px;margin-bottom:6px;flex-wrap:wrap">'
        f'  <div style="font-size:11px">'
        f'    <span style="color:{COLOR["text_dim"]}">קונצנזוס: </span>'
        f'    <span style="color:{con_col};font-weight:600">{label}</span>'
        + (f'    <span style="color:{COLOR["dim"]};font-size:10px"> ({total})</span>' if total > 0 else "")
        + f'  </div>'
        f'  <div style="font-size:11px">'
        f'    <span style="color:{COLOR["text_dim"]}">אפסייד: </span>'
        f'    <span style="color:{upside_col};font-weight:600">{upside_str}</span>'
        f'  </div>'
        f'  <div style="font-size:11px">'
        f'    <span style="color:{COLOR["text_dim"]}">אלפא 1M: </span>'
        f'    {alpha_label}'
        f'  </div>'
        f'</div>'

        # Recent analyst actions
        f'<div style="margin-bottom:6px">'
        f'  <span style="font-size:10px;color:{COLOR["text_dim"]}">פעולות אנליסטים (30י): </span>'
        f'{actions_html}'
        f'</div>'

        # Flag row
        f'<div style="margin-bottom:2px">'
        f'  <span style="font-size:10px;color:{COLOR["text_dim"]}">דגלים: </span>'
        f'{flags_html}'
        f'</div>'

        # AI brief (optional)
        + ai_section_html

        + '</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)


# ── Main render function ──────────────────────────────────────────────────────

def render_daily_brief(
    portfolio: dict,
    data: dict,
    td_str: str,
    claude_api_key: str = "",
) -> None:
    """Render the daily brief tab: one card per portfolio ticker, sorted by flag severity."""

    section_title(
        "סקירה יומית ועדכוני אנליסטים",
        "עדכון מהיר לכל מניה בתיק — מחיר, אנליסטים, דגלים וביצועים",
    )

    tickers = all_tickers(portfolio)
    if not tickers:
        st.info("הוסף ניירות ערך לתיק.")
        return

    # Date header
    st.markdown(
        f'<div dir="rtl" style="font-size:11px;color:{COLOR["text_dim"]};margin-bottom:12px">'
        f'📅 עדכון: {td_str}</div>',
        unsafe_allow_html=True,
    )

    # Compute all flag statuses once (used for sorting and per-card rendering)
    all_flags = get_all_flag_statuses(portfolio, data)

    # VOO history (for alpha calculation)
    prices     = data.get("prices", {})
    voo_data   = prices.get("VOO")
    voo_history = voo_data.get("history") if voo_data else None

    # Sort tickers: triggered → watch → ok/nodata, then alphabetically within group
    sorted_tickers = _sort_tickers_by_flag(tickers, all_flags)

    # Two-column layout
    col_left, col_right = st.columns([1, 1])
    for idx, ticker in enumerate(sorted_tickers):
        col = col_left if idx % 2 == 0 else col_right
        with col:
            _render_card(
                ticker=ticker,
                data=data,
                all_flags=all_flags,
                voo_history=voo_history,
                td_str=td_str,
                claude_api_key=claude_api_key,
            )
