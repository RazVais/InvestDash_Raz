"""Analysis tab — 5-Filter Investment Evaluation System for stocks not yet in portfolio."""

import json as _json
from typing import Optional

import streamlit as st

from src.config import COLOR, TICKER_NAMES
from src.data.analysts import get_analyst_targets, get_consensus
from src.data.fundamentals import FINVIZ_AVAILABLE, get_finviz_fundamentals
from src.data.prices import get_stock_data
from src.portfolio import all_tickers
from src.ui_helpers import section_title

# ── Filter definitions ────────────────────────────────────────────────────────

_FILTERS = [
    ("revenue_growth",  "צמיחת הכנסות",   "📈"),
    ("competitive_pos", "עמדה תחרותית",   "🏆"),
    ("leadership",      "איכות הנהלה",    "👔"),
    ("market_timing",   "תזמון שוק",      "⏱️"),
    ("risk_assessment", "הערכת סיכון",    "⚠️"),
]

_RATING_COLORS = {1: "#f44336", 2: "#ff9800", 3: "#ffeb3b", 4: "#8bc34a", 5: "#00cf8d"}
_RATING_LABELS = {1: "גרוע 🔴", 2: "חלש 🟠", 3: "בינוני 🟡", 4: "טוב 🟢", 5: "מצוין 🌟"}
_RATING_TEXT_COLORS = {1: "#fff", 2: "#fff", 3: "#000", 4: "#000", 5: "#000"}


# ── Claude evaluation ─────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def _run_five_filter_eval(ticker: str, data_summary: str, td_str: str, claude_api_key: str) -> dict:
    """Call Claude Haiku to rate 5 filters. Returns dict keyed by filter_key."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=claude_api_key)
        prompt = (
            f"נתח את המניה {ticker} לפי 5 פילטרים להשקעה, בהתאם לנתונים:\n"
            f"{data_summary}\n\n"
            "החזר JSON בדיוק בפורמט הבא (ללא טקסט נוסף):\n"
            '{\n'
            '  "revenue_growth":    {"rating": 1, "explanation": "..."},\n'
            '  "competitive_pos":   {"rating": 1, "explanation": "..."},\n'
            '  "leadership":        {"rating": 1, "explanation": "..."},\n'
            '  "market_timing":     {"rating": 1, "explanation": "..."},\n'
            '  "risk_assessment":   {"rating": 1, "explanation": "..."}\n'
            '}\n\n'
            "rating הוא מספר שלם בין 1 ל-5 (1=גרוע, 5=מצוין).\n"
            "explanation הוא 2-3 משפטים בעברית.\n"
            "קריטריונים:\n"
            "- revenue_growth: צמיחה שנתית, מגמה, יציבות הכנסות\n"
            "- competitive_pos: חפיר תחרותי, נתח שוק, כוח תמחור\n"
            "- leadership: ROE, ניהול חוב, הקצאת הון, מוניטין הנהלה\n"
            "- market_timing: מומנטום מחיר, קרבה לשיא/שפל 52 שבוע, סנטימנט\n"
            "- risk_assessment: תנודתיות (בטא), סיכון רגולטורי, ריכוז לקוחות"
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            return _json.loads(text[start:end])
    except Exception:
        pass
    return {}


# ── Data summary builder ──────────────────────────────────────────────────────

def _build_data_summary(
    ticker: str,
    prices: Optional[dict],
    consensus: Optional[dict],
    targets: Optional[dict],
    fundamentals: Optional[dict],
) -> str:
    lines = [f"Ticker: {ticker}"]
    if prices:
        lines.append(f"Price: ${prices['price']:.2f}, Change: {prices['change']:+.2f}%")
        lines.append(f"52W High: ${prices['high_52w']:.2f}, Low: ${prices['low_52w']:.2f}")
        lines.append(f"Beta: {prices['beta']:.2f}, Div Yield: {prices['div_yield']:.2f}%")
    if consensus:
        lines.append(
            f"Consensus: {consensus.get('label','N/A')} "
            f"(SB:{consensus.get('strong_buy',0)} B:{consensus.get('buy',0)} "
            f"H:{consensus.get('hold',0)} S:{consensus.get('sell',0)} "
            f"SS:{consensus.get('strong_sell',0)})"
        )
    if targets:
        lines.append(
            f"Analyst Target: mean=${targets.get('mean',0):.2f}, "
            f"high=${targets.get('high',0):.2f}, low=${targets.get('low',0):.2f}, "
            f"n={targets.get('count',0)}"
        )
    if fundamentals:
        for key in ["P/E", "Forward P/E", "EPS (TTM)", "ROE", "Market Cap",
                    "Short Float", "Inst Own", "Sector"]:
            if fundamentals.get(key):
                lines.append(f"{key}: {fundamentals[key]}")
    return "\n".join(lines)


# ── UI helpers ────────────────────────────────────────────────────────────────

def _stars_html(rating: int) -> str:
    """Return gold/dim star string for rating 0-5."""
    filled = max(0, min(5, rating))
    return (
        '<span style="color:#FFD700;font-size:18px">' + "★" * filled + "</span>"
        + '<span style="color:#444;font-size:18px">' + "★" * (5 - filled) + "</span>"
    )


def _filter_card_html(filter_name: str, icon: str, rating: int, explanation: str) -> str:
    stars     = _stars_html(rating)
    bg        = _RATING_COLORS.get(rating, "#444")
    txt       = _RATING_TEXT_COLORS.get(rating, "#fff")
    lbl       = _RATING_LABELS.get(rating, "—")
    return (
        f'<div dir="rtl" style="background:#1a1f2e;border:1px solid #1f2937;'
        f'border-radius:10px;padding:14px 18px;margin-bottom:10px;height:100%">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
        f'<span style="font-size:14px;font-weight:700;color:{COLOR["primary"]}">{icon} {filter_name}</span>'
        f'{stars}'
        f'</div>'
        f'<div style="display:inline-block;background:{bg};color:{txt};border-radius:12px;'
        f'padding:1px 10px;font-size:11px;font-weight:700;margin-bottom:8px">{lbl}</div>'
        f'<div dir="rtl" style="font-size:12px;color:#cccccc;line-height:1.7">{explanation}</div>'
        f'</div>'
    )


def _no_key_explanation() -> str:
    return (
        f'<span style="color:{COLOR["text_dim"]};font-size:12px">'
        f'הוסף ANTHROPIC_API_KEY לקובץ .streamlit/secrets.toml לקבלת ניתוח AI.</span>'
    )


# ── Main render ───────────────────────────────────────────────────────────────

def render_analysis(portfolio, data, td_str: str, api_key: str = "", claude_api_key: str = ""):
    section_title(
        "מערכת 5 הפילטרים — ניתוח השקעה",
        "הערכת מניות שעדיין אינן בתיק לפי 5 קריטריונים מרכזיים",
    )

    # ── Intro expander ────────────────────────────────────────────────────────
    with st.expander("מה זה 5 הפילטרים? 📖", expanded=False):
        st.markdown(
            '<div dir="rtl" style="font-size:13px;color:#cccccc;line-height:1.9">'
            "<b>1. 📈 צמיחת הכנסות</b> — האם ההכנסות גדלות? האם המגמה יציבה? מה קצב הצמיחה השנתי?<br>"
            "<b>2. 🏆 עמדה תחרותית</b> — האם לחברה יש חפיר תחרותי? האם היא מובילת שוק? כוח תמחור?<br>"
            "<b>3. 👔 איכות הנהלה</b> — רקורד ביצוע, ניהול הון, ROE, מדיניות חוב, מוניטין הנהלה?<br>"
            "<b>4. ⏱️ תזמון שוק</b> — האם המניה חזקה טכנית? מומנטום? קרבה לשיא/שפל 52 שבוע?<br>"
            "<b>5. ⚠️ הערכת סיכון</b> — תנודתיות, ריבית שורט, סיכון סקטורי, פיזור אנליסטים?<br><br>"
            "כל פילטר מקבל ציון 1-5 (1=גרוע, 5=מצוין). <b>ציון כולל מתוך 25.</b>"
            "</div>",
            unsafe_allow_html=True,
        )

    # ── Ticker input ──────────────────────────────────────────────────────────
    owned = set(all_tickers(portfolio))

    col_inp, col_btn = st.columns([3, 1])
    with col_inp:
        ticker_input = st.text_input(
            "הכנס סימול מניה לניתוח",
            placeholder="לדוגמה: MSFT, TSLA, NVDA",
            key="analysis_ticker",
            label_visibility="collapsed",
        ).strip().upper()
    with col_btn:
        analyze_btn = st.button("🔍 נתח", key="analyze_btn", use_container_width=True)

    # Persist across reruns
    if analyze_btn and ticker_input:
        st.session_state["_analysis_ticker"] = ticker_input

    ticker = st.session_state.get("_analysis_ticker", ticker_input) or ""

    if not ticker:
        st.markdown(
            f'<div dir="rtl" style="color:{COLOR["text_dim"]};font-size:13px;margin-top:16px">'
            f'הכנס סימול מניה וקלק על "נתח" לקבלת הערכת 5 הפילטרים.'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    if ticker in owned:
        st.warning(f"{ticker} כבר בתיק שלך — השתמש בטאב 'אנליסטים' לניתוח מפורט.")
        return

    # ── Fetch data ────────────────────────────────────────────────────────────
    with st.spinner(f"מנתח את {ticker}..."):
        prices_data     = get_stock_data((ticker,), td_str)
        targets_data    = get_analyst_targets((ticker,), td_str)
        consensus_data  = get_consensus((ticker,), td_str, api_key)
        fundamentals_data: Optional[dict] = None
        if FINVIZ_AVAILABLE:
            fundamentals_data = get_finviz_fundamentals((ticker,), td_str)

    p   = prices_data.get(ticker)
    tgt = targets_data.get(ticker)
    con = consensus_data.get(ticker, {})
    fun = (fundamentals_data or {}).get(ticker, {}) if fundamentals_data else {}

    # ── Live data summary bar ─────────────────────────────────────────────────
    if p:
        price_color  = COLOR["positive"] if (p.get("change") or 0) >= 0 else COLOR["negative"]
        change_str   = f"{p['change']:+.2f}%" if p.get("change") is not None else "—"
        upside_str   = "—"
        upside_color = COLOR["text_dim"]
        if p.get("price") and tgt and tgt.get("mean"):
            up           = (tgt["mean"] - p["price"]) / p["price"] * 100
            upside_str   = f"{up:+.1f}%"
            upside_color = COLOR["positive"] if up >= 0 else COLOR["negative"]
        label       = con.get("label", "N/A")
        label_color = (
            COLOR["positive"] if "Buy" in label else
            COLOR["negative"] if "Sell" in label else
            COLOR["neutral"]
        )
        st.markdown(
            f'<div dir="rtl" style="background:#111827;border:1px solid #1f2937;'
            f'border-radius:10px;padding:12px 18px;margin-bottom:16px;'
            f'display:flex;gap:28px;flex-wrap:wrap;align-items:center">'
            f'<span style="font-size:18px;font-weight:800;color:{COLOR["primary"]}">{ticker}</span>'
            f'<span style="font-size:13px;color:{COLOR["text_dim"]}">'
            f'{TICKER_NAMES.get(ticker, "")}</span>'
            f'<span style="font-size:14px;font-weight:700">${p["price"]:.2f}'
            f' <span style="color:{price_color}">{change_str}</span></span>'
            f'<span style="font-size:12px;color:{COLOR["text_dim"]}">אפסייד: '
            f'<b style="color:{upside_color}">{upside_str}</b></span>'
            f'<span style="font-size:12px;color:{COLOR["text_dim"]}">קונצנזוס: '
            f'<b style="color:{label_color}">{label}</b></span>'
            + (
                f'<span style="font-size:12px;color:{COLOR["text_dim"]}">בטא: '
                f'<b>{p["beta"]:.2f}</b></span>'
                if p.get("beta") else ""
            ) +
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        st.warning(f"לא נמצאו נתוני מחיר עבור {ticker}. בדוק שהסימול תקין.")

    # ── Build data summary for Claude ────────────────────────────────────────
    data_summary = _build_data_summary(ticker, p, con, tgt, fun or None)

    # ── Get AI ratings ────────────────────────────────────────────────────────
    eval_result: dict = {}
    if claude_api_key:
        eval_result = _run_five_filter_eval(ticker, data_summary, td_str, claude_api_key)

    # ── Filter cards (2 columns) ──────────────────────────────────────────────
    st.markdown(
        f'<div dir="rtl" style="font-size:13px;font-weight:700;color:{COLOR["primary"]};'
        f'margin-bottom:8px">📊 הערכת 5 הפילטרים — {ticker}</div>',
        unsafe_allow_html=True,
    )

    total_score = 0
    # Display in pairs: (0,1), (2,3), then (4,) alone
    for i in range(0, len(_FILTERS), 2):
        pair = _FILTERS[i: i + 2]
        cols = st.columns(len(pair))
        for col, (fkey, fname, ficon) in zip(cols, pair):
            fdata  = eval_result.get(fkey, {})
            rating = int(fdata.get("rating", 0)) if fdata else 0
            expl   = fdata.get("explanation", "") if fdata else ""
            if not expl:
                expl = (
                    _no_key_explanation()
                    if not claude_api_key
                    else f'<span style="color:{COLOR["text_dim"]}">טוען...</span>'
                )
            total_score += rating
            with col:
                st.markdown(
                    _filter_card_html(fname, ficon, rating, expl),
                    unsafe_allow_html=True,
                )

    # ── Overall score ─────────────────────────────────────────────────────────
    st.divider()
    if eval_result:
        score_pct = int(total_score / 25 * 100)
        if total_score < 10:
            verdict, verdict_color = "לא מומלץ", COLOR["negative"]
        elif total_score < 15:
            verdict, verdict_color = "ניטרלי", COLOR["warning"]
        elif total_score < 20:
            verdict, verdict_color = "מעניין", COLOR["primary"]
        elif total_score < 23:
            verdict, verdict_color = "חזק", COLOR["positive"]
        else:
            verdict, verdict_color = "חזק מאוד 🌟", COLOR["positive"]

        st.markdown(
            f'<div dir="rtl" style="display:flex;align-items:center;gap:16px;margin-bottom:6px">'
            f'<span style="font-size:24px;font-weight:800;color:{verdict_color}">'
            f'{total_score}/25</span>'
            f'<span style="font-size:14px;color:{verdict_color};font-weight:700">{verdict}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.progress(score_pct / 100)
        st.caption(f"ציון מבוסס-AI עבור {ticker} לפי 5 פילטרי השקעה")
    elif not claude_api_key:
        st.info("הוסף ANTHROPIC_API_KEY לקובץ .streamlit/secrets.toml לקבלת ציון AI.")

    # ── Fundamentals detail ───────────────────────────────────────────────────
    if fun:
        with st.expander("📋 נתוני יסוד מפורטים", expanded=False):
            items = [
                ("P/E", fun.get("P/E")),
                ("P/E קדימה", fun.get("Forward P/E")),
                ("EPS (TTM)", fun.get("EPS (TTM)")),
                ("ROE", fun.get("ROE")),
                ("שווי שוק", fun.get("Market Cap")),
                ("Short Float", fun.get("Short Float")),
                ("בעלות מוסדית", fun.get("Inst Own")),
                ("סקטור", fun.get("Sector")),
            ]
            shown = [(k, v) for k, v in items if v]
            if shown:
                n_cols = 4
                rows = [shown[i: i + n_cols] for i in range(0, len(shown), n_cols)]
                for row in rows:
                    cols = st.columns(n_cols)
                    for col, (label, val) in zip(cols, row):
                        col.metric(label, val)

    # ── Disclaimer ────────────────────────────────────────────────────────────
    st.markdown(
        f'<div dir="rtl" style="font-size:10px;color:{COLOR["text_dim"]};'
        f'border-top:1px solid #222;padding-top:8px;margin-top:8px">'
        f'⚠️ ניתוח זה נוצר על ידי AI ומיועד לצרכי מידע בלבד. '
        f'אינו מהווה ייעוץ השקעות. כל השקעה כרוכה בסיכון — בצע בדיקה עצמאית.'
        f'</div>',
        unsafe_allow_html=True,
    )
