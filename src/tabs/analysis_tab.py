"""Analysis tab — 5-Filter Investment Evaluation for stocks not in portfolio.

Automatically evaluates every ticker from SUGGESTIONS that the user hasn't bought yet,
plus a custom-ticker search box for any other stock.
"""

import json as _json
from typing import Optional

import streamlit as st

from src.config import COLOR, SUGGESTIONS, TICKER_NAMES
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


# ── Claude evaluation (cached per ticker+day) ─────────────────────────────────

@st.cache_data(ttl=3600)
def _run_five_filter_eval(ticker: str, data_summary: str, td_str: str, claude_api_key: str) -> dict:
    """Call Claude Haiku to rate 5 filters. Returns dict keyed by filter_key, or {"_error": msg}."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=claude_api_key)
        prompt = (
            f"נתח את המניה {ticker} לפי 5 פילטרים להשקעה. השתמש בנתוני השוק הבאים כולל ביצועי השנה האחרונה:\n"
            f"{data_summary}\n\n"
            "החזר JSON בלבד (ללא טקסט לפניו או אחריו):\n"
            '{\n'
            '  "revenue_growth":    {"rating": 3, "explanation": "2-3 משפטים בעברית"},\n'
            '  "competitive_pos":   {"rating": 3, "explanation": "2-3 משפטים בעברית"},\n'
            '  "leadership":        {"rating": 3, "explanation": "2-3 משפטים בעברית"},\n'
            '  "market_timing":     {"rating": 3, "explanation": "2-3 משפטים בעברית"},\n'
            '  "risk_assessment":   {"rating": 3, "explanation": "2-3 משפטים בעברית"}\n'
            '}\n\n'
            "rating: מספר שלם 1-5 (1=גרוע, 5=מצוין).\n"
            "קריטריונים:\n"
            "- revenue_growth: צמיחה שנתית לפי ביצועי מחיר שנה אחרונה, מגמה, יציבות הכנסות\n"
            "- competitive_pos: חפיר תחרותי, נתח שוק, כוח תמחור — לפי P/E ו-ROE\n"
            "- leadership: ROE, ניהול חוב, הקצאת הון, מוניטין הנהלה\n"
            "- market_timing: מומנטום (תשואה 1M/3M/1Y), קרבה לשיא/שפל 52 שבוע, סנטימנט אנליסטים\n"
            "- risk_assessment: תנודתיות (בטא), סיכון רגולטורי, שורט, סיכון סקטורי"
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        text  = msg.content[0].text.strip()
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = _json.loads(text[start:end])
            # Validate all 5 keys present
            if all(k in parsed for k in ("revenue_growth", "competitive_pos",
                                          "leadership", "market_timing", "risk_assessment")):
                return parsed
            return {"_error": "תגובת AI חסרת שדות — נסה שוב"}
        return {"_error": f"JSON לא נמצא בתגובה: {text[:120]}"}
    except Exception as exc:
        return {"_error": str(exc)[:200]}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_data_summary(
    ticker: str,
    prices: Optional[dict],
    consensus: Optional[dict],
    targets: Optional[dict],
    fundamentals: Optional[dict],
) -> str:
    lines = [f"Ticker: {ticker}"]
    if prices:
        cur   = prices["price"]
        hi52  = prices["high_52w"]
        lo52  = prices["low_52w"]
        lines.append(f"Price: ${cur:.2f}, Daily Change: {prices['change']:+.2f}%")
        lines.append(f"52W High: ${hi52:.2f} ({(cur - hi52) / hi52 * 100:+.1f}% from high), "
                     f"Low: ${lo52:.2f} ({(cur - lo52) / lo52 * 100:+.1f}% from low)")
        lines.append(f"Beta: {prices['beta']:.2f}, Div Yield: {prices['div_yield']:.2f}%")
        # 1-year price performance from history Series
        hist = prices.get("history")
        if hist is not None and len(hist) >= 2:
            try:
                ret_1y = (float(hist.iloc[-1]) / float(hist.iloc[0]) - 1) * 100
                lines.append(f"1-Year Return: {ret_1y:+.1f}%")
                if len(hist) >= 63:
                    ret_3m = (float(hist.iloc[-1]) / float(hist.iloc[-63]) - 1) * 100
                    lines.append(f"3-Month Return: {ret_3m:+.1f}%")
                if len(hist) >= 21:
                    ret_1m = (float(hist.iloc[-1]) / float(hist.iloc[-21]) - 1) * 100
                    lines.append(f"1-Month Return: {ret_1m:+.1f}%")
            except Exception:
                pass
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


def _stars_html(rating: int) -> str:
    filled = max(0, min(5, rating))
    return (
        '<span style="color:#FFD700;font-size:18px">' + "★" * filled + "</span>"
        + '<span style="color:#444;font-size:18px">' + "★" * (5 - filled) + "</span>"
    )


def _filter_card_html(filter_name: str, icon: str, rating: int, explanation: str) -> str:
    stars = _stars_html(rating)
    bg    = _RATING_COLORS.get(rating, "#444")
    txt   = _RATING_TEXT_COLORS.get(rating, "#fff")
    lbl   = _RATING_LABELS.get(rating, "—")
    return (
        f'<div dir="rtl" style="background:#1a1f2e;border:1px solid #1f2937;'
        f'border-radius:10px;padding:14px 18px;margin-bottom:10px">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
        f'<span style="font-size:13px;font-weight:700;color:{COLOR["primary"]}">{icon} {filter_name}</span>'
        f'{stars}'
        f'</div>'
        f'<div style="display:inline-block;background:{bg};color:{txt};border-radius:12px;'
        f'padding:1px 10px;font-size:11px;font-weight:700;margin-bottom:8px">{lbl}</div>'
        f'<div dir="rtl" style="font-size:12px;color:#cccccc;line-height:1.7">{explanation}</div>'
        f'</div>'
    )


def _score_badge(total: int) -> str:
    if total < 10:
        verdict, color = "לא מומלץ", COLOR["negative"]
    elif total < 15:
        verdict, color = "ניטרלי", COLOR["warning"]
    elif total < 20:
        verdict, color = "מעניין", COLOR["primary"]
    elif total < 23:
        verdict, color = "חזק", COLOR["positive"]
    else:
        verdict, color = "חזק מאוד 🌟", COLOR["positive"]
    return (
        f'<span style="background:{color}22;color:{color};border:1px solid {color}44;'
        f'border-radius:20px;padding:2px 14px;font-size:13px;font-weight:700;'
        f'white-space:nowrap">{total}/25 — {verdict}</span>'
    )


def _render_ticker_section(
    ticker: str,
    name: str,
    theme: str,
    p: Optional[dict],
    con: Optional[dict],
    tgt: Optional[dict],
    fun: Optional[dict],
    td_str: str,
    claude_api_key: str,
    expanded: bool = False,
):
    """Render one ticker's full 5-filter evaluation inside an expander."""
    # Quick header line for the expander label
    price_str  = f"${p['price']:.2f}" if p else "—"
    label      = (con or {}).get("label", "N/A")
    upside_str = "—"
    if p and tgt and tgt.get("mean") and p.get("price"):
        up         = (tgt["mean"] - p["price"]) / p["price"] * 100
        upside_str = f"{up:+.1f}%"

    expander_label = f"{ticker} — {name}  |  {price_str}  |  {label}  |  אפסייד {upside_str}"

    with st.expander(expander_label, expanded=expanded):
        # Theme badge + stats row
        price_color  = COLOR["positive"] if (p or {}).get("change", 0) >= 0 else COLOR["negative"]
        change_str   = f"{p['change']:+.2f}%" if p and p.get("change") is not None else "—"
        label_color  = (
            COLOR["positive"] if "Buy" in label else
            COLOR["negative"] if "Sell" in label else
            COLOR["neutral"]
        )
        upside_color = COLOR["positive"] if upside_str.startswith("+") else (
            COLOR["negative"] if upside_str.startswith("-") else COLOR["text_dim"]
        )

        st.markdown(
            f'<div dir="rtl" style="display:flex;gap:16px;flex-wrap:wrap;'
            f'align-items:center;margin-bottom:12px">'
            f'<span style="background:#00cf8d22;color:{COLOR["primary"]};border-radius:20px;'
            f'padding:2px 12px;font-size:11px">{theme}</span>'
            + (
                f'<span style="font-size:13px;font-weight:700">{price_str} '
                f'<span style="color:{price_color}">{change_str}</span></span>'
                if p else ""
            )
            + f'<span style="font-size:12px;color:{COLOR["text_dim"]}">קונצנזוס: '
            f'<b style="color:{label_color}">{label}</b></span>'
            + (
                f'<span style="font-size:12px;color:{COLOR["text_dim"]}">אפסייד: '
                f'<b style="color:{upside_color}">{upside_str}</b></span>'
                if upside_str != "—" else ""
            )
            + '</div>',
            unsafe_allow_html=True,
        )

        # Claude eval
        eval_result: dict = {}
        if claude_api_key:
            data_summary = _build_data_summary(ticker, p, con, tgt, fun)
            eval_result  = _run_five_filter_eval(ticker, data_summary, td_str, claude_api_key)
            if "_error" in eval_result:
                err_msg = eval_result["_error"]
                st.warning(f"⚠️ שגיאת AI: {err_msg}")
                if st.button("🔄 נסה שוב", key=f"_retry_{ticker}"):
                    st.cache_data.clear()
                    st.rerun()
                eval_result = {}
        else:
            st.info("הוסף `ANTHROPIC_API_KEY` לקובץ `.streamlit/secrets.toml` לקבלת ניתוח AI.")

        # 5 filter cards (2-column pairs)
        total_score = 0
        no_key_msg  = (
            f'<span style="color:{COLOR["text_dim"]};font-size:12px">'
            f'הוסף ANTHROPIC_API_KEY לניתוח AI.</span>'
        )
        for i in range(0, len(_FILTERS), 2):
            pair = _FILTERS[i: i + 2]
            cols = st.columns(len(pair))
            for col, (fkey, fname, ficon) in zip(cols, pair):
                fdata   = eval_result.get(fkey, {})
                rating  = int(fdata.get("rating", 0)) if fdata else 0
                expl    = fdata.get("explanation", "") if fdata else ""
                if not expl and not claude_api_key:
                    expl = no_key_msg
                total_score += rating
                with col:
                    st.markdown(_filter_card_html(fname, ficon, rating, expl),
                                unsafe_allow_html=True)

        # Score
        if eval_result:
            score_pct = int(total_score / 25 * 100)
            st.markdown(
                f'<div dir="rtl" style="display:flex;align-items:center;gap:12px;'
                f'margin-top:4px;margin-bottom:2px">'
                f'<span style="font-size:12px;color:{COLOR["text_dim"]}">ציון כולל:</span>'
                f'{_score_badge(total_score)}'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.progress(score_pct / 100)


# ── Main render ───────────────────────────────────────────────────────────────

def render_analysis(portfolio, data, td_str: str, api_key: str = "", claude_api_key: str = ""):
    section_title(
        "מערכת 5 הפילטרים — ניתוח מניות לא בתיק",
        "הערכת מניות מוצעות לפי 5 קריטריונים מרכזיים — רווחים, תחרות, הנהלה, תזמון וסיכון",
    )

    owned      = set(all_tickers(portfolio))
    candidates = [s for s in SUGGESTIONS if s["ticker"] not in owned]

    # ── Intro expander ────────────────────────────────────────────────────────
    with st.expander("מה זה 5 הפילטרים? 📖", expanded=False):
        st.markdown(
            '<div dir="rtl" style="font-size:13px;color:#cccccc;line-height:1.9">'
            "<b>1. 📈 צמיחת הכנסות</b> — האם ההכנסות גדלות? האם המגמה יציבה?<br>"
            "<b>2. 🏆 עמדה תחרותית</b> — האם לחברה יש חפיר תחרותי? כוח תמחור?<br>"
            "<b>3. 👔 איכות הנהלה</b> — רקורד ביצוע, ROE, ניהול הון ומוניטין?<br>"
            "<b>4. ⏱️ תזמון שוק</b> — מומנטום מחיר, קרבה לשיא/שפל 52 שבוע?<br>"
            "<b>5. ⚠️ הערכת סיכון</b> — תנודתיות, ריבית שורט, סיכון סקטורי?<br><br>"
            "כל פילטר מקבל ציון 1–5 (1=גרוע, 5=מצוין). <b>ציון כולל מתוך 25.</b>"
            "</div>",
            unsafe_allow_html=True,
        )

    # ── Fetch data for all candidates in one batch ────────────────────────────
    if not candidates:
        st.info("כל המניות המוצעות כבר בתיק שלך.")
    else:
        tickers_tuple = tuple(sorted(s["ticker"] for s in candidates))

        with st.spinner("טוען נתוני שוק..."):
            prices_all    = get_stock_data(tickers_tuple, td_str)
            targets_all   = get_analyst_targets(tickers_tuple, td_str)
            consensus_all = get_consensus(tickers_tuple, td_str, api_key)
            fund_all: dict = {}
            if FINVIZ_AVAILABLE:
                fund_all = get_finviz_fundamentals(tickers_tuple, td_str) or {}

        st.markdown(
            f'<div dir="rtl" style="font-size:12px;color:{COLOR["text_dim"]};margin-bottom:4px">'
            f'🔬 {len(candidates)} מניות לניתוח — לחץ על כל מניה להצגת 5 הפילטרים'
            f'</div>',
            unsafe_allow_html=True,
        )

        for i, s in enumerate(candidates):
            t   = s["ticker"]
            p   = prices_all.get(t)
            tgt = targets_all.get(t)
            con = consensus_all.get(t, {})
            fun = fund_all.get(t, {}) if fund_all else {}
            _render_ticker_section(
                ticker=t,
                name=s["name"],
                theme=s["theme"],
                p=p,
                con=con,
                tgt=tgt,
                fun=fun or None,
                td_str=td_str,
                claude_api_key=claude_api_key,
                expanded=(i == 0),  # open first ticker by default
            )

    # ── Custom ticker search ──────────────────────────────────────────────────
    st.divider()
    st.markdown(
        f'<div dir="rtl" style="font-size:13px;font-weight:700;color:{COLOR["primary"]};'
        f'margin-bottom:8px">🔍 ניתוח מניה אחרת</div>',
        unsafe_allow_html=True,
    )

    col_inp, col_btn = st.columns([3, 1])
    with col_inp:
        ticker_input = st.text_input(
            "הכנס סימול מניה",
            placeholder="לדוגמה: TSLA, AAPL, PLTR",
            key="analysis_custom_ticker",
            label_visibility="collapsed",
        ).strip().upper()
    with col_btn:
        analyze_btn = st.button("🔍 נתח", key="analyze_custom_btn", use_container_width=True)

    if analyze_btn and ticker_input:
        st.session_state["_analysis_custom"] = ticker_input

    custom = st.session_state.get("_analysis_custom", ticker_input) or ""

    if custom:
        if custom in owned:
            st.warning(f"{custom} כבר בתיק שלך — השתמש בטאב 'אנליסטים' לניתוח מפורט.")
        else:
            with st.spinner(f"מנתח את {custom}..."):
                cp    = get_stock_data((custom,), td_str).get(custom)
                ctgt  = get_analyst_targets((custom,), td_str).get(custom)
                ccon  = get_consensus((custom,), td_str, api_key).get(custom, {})
                cfun: Optional[dict] = None
                if FINVIZ_AVAILABLE:
                    cfun_all = get_finviz_fundamentals((custom,), td_str)
                    cfun     = (cfun_all or {}).get(custom)

            if not cp:
                st.warning(f"לא נמצאו נתוני מחיר עבור {custom}. בדוק שהסימול תקין.")
            else:
                _render_ticker_section(
                    ticker=custom,
                    name=TICKER_NAMES.get(custom, custom),
                    theme="ניתוח מותאם אישית",
                    p=cp,
                    con=ccon,
                    tgt=ctgt,
                    fun=cfun,
                    td_str=td_str,
                    claude_api_key=claude_api_key,
                    expanded=True,
                )

    # ── Disclaimer ────────────────────────────────────────────────────────────
    st.markdown(
        f'<div dir="rtl" style="font-size:10px;color:{COLOR["text_dim"]};'
        f'border-top:1px solid #222;padding-top:8px;margin-top:12px">'
        f'⚠️ ניתוח זה נוצר על ידי AI ומיועד לצרכי מידע בלבד. '
        f'אינו מהווה ייעוץ השקעות. כל השקעה כרוכה בסיכון — בצע בדיקה עצמאית.'
        f'</div>',
        unsafe_allow_html=True,
    )
