"""Analysis tab — 5-Filter Investment Evaluation (Buffett & Lynch framework).

Filters map directly to the Buffett/Lynch due-diligence framework:
  1. פונדמנטלס  — Buffett quantitative pillars (ROE, FCF, PEG)
  2. Moat        — Buffett economic moat + Lindy Effect
  3. הנהלה       — Lynch management & capital allocation
  4. שווי        — Buffett margin of safety + second-level thinking
  5. דגלים       — Lynch red flags (debt, dilution, hype, complexity)

Evaluates every ticker from SUGGESTIONS not yet in portfolio,
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
    ("revenue_growth",  "פונדמנטלס ועסקיות",    "📊"),   # Buffett/Lynch quantitative pillars
    ("competitive_pos", "חפיר תחרותי — Moat",    "🏰"),   # Buffett economic moat
    ("leadership",      "הנהלה וניהול הון",       "👔"),   # Lynch capital allocation
    ("market_timing",   "שווי ומרווח ביטחון",    "💰"),   # Buffett margin of safety
    ("risk_assessment", "דגלים אדומים",          "🚩"),   # Lynch red flags
]

_RATING_COLORS = {1: "#f44336", 2: "#ff9800", 3: "#ffeb3b", 4: "#8bc34a", 5: "#00cf8d"}
_RATING_LABELS = {1: "גרוע 🔴", 2: "חלש 🟠", 3: "בינוני 🟡", 4: "טוב 🟢", 5: "מצוין 🌟"}
_RATING_TEXT_COLORS = {1: "#fff", 2: "#fff", 3: "#000", 4: "#000", 5: "#000"}


# ── Claude evaluation (cached per ticker+day) ─────────────────────────────────

_FILTER_KEYS = ("revenue_growth", "competitive_pos", "leadership", "market_timing", "risk_assessment")


def _safe_parse_json(text: str) -> Optional[dict]:
    """Extract and parse the first JSON object in text, tolerating minor formatting issues."""
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    raw = text[start:end]
    # Try direct parse first
    try:
        return _json.loads(raw)
    except _json.JSONDecodeError:
        pass
    # Strip trailing commas before } or ] (common LLM mistake)
    import re
    cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
    try:
        return _json.loads(cleaned)
    except _json.JSONDecodeError:
        return None


@st.cache_data(ttl=3600)
def _run_five_filter_eval(ticker: str, data_summary: str, td_str: str, claude_api_key: str) -> dict:
    """Call Claude Haiku to rate 5 filters. Returns dict keyed by filter_key, or {"_error": msg}."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=claude_api_key)
        prompt = (
            f"Analyze stock {ticker} using the following market data:\n"
            f"{data_summary}\n\n"
            "CRITICAL: ALL explanation values MUST be written in Hebrew (עברית). "
            "Do NOT write any explanation in English. "
            "Return ONLY a JSON object — no text before or after it. "
            "Do not use quotation marks inside explanation values.\n\n"
            "Format:\n"
            '{"revenue_growth":{"rating":3,"explanation":"טקסט בעברית"},'
            '"competitive_pos":{"rating":3,"explanation":"טקסט בעברית"},'
            '"leadership":{"rating":3,"explanation":"טקסט בעברית"},'
            '"market_timing":{"rating":3,"explanation":"טקסט בעברית"},'
            '"risk_assessment":{"rating":3,"explanation":"טקסט בעברית"}}\n\n'
            "Rules:\n"
            "- rating is an integer 1-5 (1=very poor, 5=excellent)\n"
            "- explanation: EXACTLY 2 sentences in Hebrew only, no English words\n"
            "- revenue_growth (Buffett/Lynch quantitative pillars): EPS and revenue growth trend, "
            "ROE vs Buffett 15% threshold, PEG ratio vs growth rate, FCF alignment with net income\n"
            "- competitive_pos (Buffett economic moat): brand power, switching costs, low-cost "
            "producer advantage, pricing power; apply Lindy Effect — how long has this business "
            "model survived, does it have durable competitive advantages?\n"
            "- leadership (Lynch management & capital allocation): insider ownership / skin in the "
            "game, capital allocation quality (share buybacks when undervalued vs Lynch diworseification "
            "— buying unrelated companies), conservative guidance vs stock pumping, debt management\n"
            "- market_timing (Buffett margin of safety): does the current price offer a 20-30% "
            "discount to intrinsic value or analyst consensus target? Apply second-level thinking "
            "(Howard Marks) — is the stock under-loved or priced for perfection?\n"
            "- risk_assessment (Lynch red flags): high debt vs industry peers, growth only by "
            "acquisition rather than organically, sector hype / media darling overvaluation, "
            "constant share dilution, business model too complex to explain in 2 sentences"
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        text   = msg.content[0].text.strip()
        parsed = _safe_parse_json(text)
        if parsed is None:
            return {"_error": f"JSON לא תקין בתגובת AI: {text[:150]}"}
        if all(k in parsed for k in _FILTER_KEYS):
            return parsed
        missing = [k for k in _FILTER_KEYS if k not in parsed]
        return {"_error": f"חסרים שדות בתגובה: {missing}"}
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
        for key in ["P/E", "Forward P/E", "EPS (TTM)", "ROE", "Debt/Eq",
                    "PEG", "P/FCF", "Market Cap", "Short Float", "Inst Own", "Sector"]:
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


def _guru_checklist_html(
    p: Optional[dict],
    con: Optional[dict],
    tgt: Optional[dict],
    fun: Optional[dict],
) -> str:
    """Static Buffett/Lynch quick-checks from raw data — no AI needed."""

    def _pct(s: str) -> Optional[float]:
        try:
            return float(s.strip().rstrip("%").replace(",", ""))
        except Exception:
            return None

    def _num(s: str) -> Optional[float]:
        try:
            return float(s.strip().replace(",", ""))
        except Exception:
            return None

    checks = []

    # ROE > 15% — Buffett profitability standard
    roe = _pct((fun or {}).get("ROE", ""))
    if roe is not None:
        checks.append(("ROE>15%", roe > 15, "Buffett"))

    # Debt/Eq < 1.0 — Lynch: "hard to go bankrupt with zero debt"
    de = _num((fun or {}).get("Debt/Eq", ""))
    if de is not None:
        checks.append(("חוב/הון<1", de < 1.0, "Lynch"))

    # PEG < 1.5 — Lynch: P/E relative to growth rate
    peg = _num((fun or {}).get("PEG", ""))
    if peg is not None and peg > 0:
        checks.append(("PEG<1.5", peg < 1.5, "Lynch"))

    # Margin of safety ≥ 20% — Buffett: buy at 20-30% discount to intrinsic value
    if p and tgt and tgt.get("mean") and p.get("price"):
        upside = (tgt["mean"] - p["price"]) / p["price"] * 100
        checks.append(("מרווח≥20%", upside >= 20, "Buffett"))

    # Short float < 10% — Lynch: low controversy, no crowded short
    sf = _pct((fun or {}).get("Short Float", ""))
    if sf is not None:
        checks.append(("שורט<10%", sf < 10, "Lynch"))

    # Consensus not Sell — analyst sentiment sanity check
    label = (con or {}).get("label", "")
    if label and label != "N/A":
        ok = "Sell" not in label and "Underperform" not in label
        checks.append(("קונצנזוס", ok, ""))

    if not checks:
        return ""

    pills = ""
    for check_label, ok, guru in checks:
        color    = COLOR["positive"] if ok else COLOR["negative"]
        icon     = "✅" if ok else "❌"
        guru_tag = (
            f'<span style="font-size:9px;opacity:0.65"> ({guru})</span>'
            if guru else ""
        )
        pills += (
            f'<span style="display:inline-block;background:{color}18;'
            f'border:1px solid {color}44;border-radius:20px;'
            f'padding:2px 10px;font-size:11px;color:{color};'
            f'margin:2px 4px 2px 0;white-space:nowrap">'
            f'{icon} {check_label}{guru_tag}</span>'
        )

    return (
        f'<div dir="rtl" style="margin-bottom:14px;padding:10px 14px;'
        f'background:#0a1018;border:1px solid #1f2937;border-radius:8px">'
        f'<div style="font-size:10px;color:{COLOR["text_dim"]};'
        f'margin-bottom:6px;font-weight:600">🔍 בדיקות מהירות — Buffett & Lynch</div>'
        f'<div style="display:flex;flex-wrap:wrap">{pills}</div>'
        f'</div>'
    )


def _render_ticker_stats_row(p, con, tgt, theme):
    """Render the theme badge + price/consensus/upside stats row inside an expander."""
    label       = (con or {}).get("label", "N/A")
    price_str   = f"${p['price']:.2f}" if p else "—"
    change_str  = f"{p['change']:+.2f}%" if p and p.get("change") is not None else "—"
    price_color = COLOR["positive"] if (p or {}).get("change", 0) >= 0 else COLOR["negative"]
    label_color = (
        COLOR["positive"] if "Buy" in label else
        COLOR["negative"] if "Sell" in label else
        COLOR["neutral"]
    )
    upside_str = "—"
    if p and tgt and tgt.get("mean") and p.get("price"):
        up         = (tgt["mean"] - p["price"]) / p["price"] * 100
        upside_str = f"{up:+.1f}%"
    upside_color = (
        COLOR["positive"] if upside_str.startswith("+") else
        COLOR["negative"] if upside_str.startswith("-") else
        COLOR["text_dim"]
    )
    st.markdown(
        f'<div dir="rtl" style="display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin-bottom:12px">'
        f'<span style="background:#00cf8d22;color:{COLOR["primary"]};border-radius:20px;padding:2px 12px;font-size:11px">{theme}</span>'
        + (f'<span style="font-size:13px;font-weight:700">{price_str} <span style="color:{price_color}">{change_str}</span></span>' if p else "")
        + f'<span style="font-size:12px;color:{COLOR["text_dim"]}">קונצנזוס: <b style="color:{label_color}">{label}</b></span>'
        + (f'<span style="font-size:12px;color:{COLOR["text_dim"]}">אפסייד: <b style="color:{upside_color}">{upside_str}</b></span>' if upside_str != "—" else "")
        + '</div>',
        unsafe_allow_html=True,
    )
    return label, upside_str


def _render_filter_cards(eval_result, claude_api_key):
    """Render 5 filter cards in 2-column pairs. Returns total score."""
    total_score = 0
    no_key_msg  = f'<span style="color:{COLOR["text_dim"]};font-size:12px">הוסף ANTHROPIC_API_KEY לניתוח AI.</span>'
    for i in range(0, len(_FILTERS), 2):
        pair = _FILTERS[i: i + 2]
        cols = st.columns(len(pair))
        for col, (fkey, fname, ficon) in zip(cols, pair):
            fdata  = eval_result.get(fkey, {})
            rating = int(fdata.get("rating", 0)) if fdata else 0
            expl   = fdata.get("explanation", "") if fdata else ""
            if not expl and not claude_api_key:
                expl = no_key_msg
            total_score += rating
            with col:
                st.markdown(_filter_card_html(fname, ficon, rating, expl), unsafe_allow_html=True)
    return total_score


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
    price_str  = f"${p['price']:.2f}" if p else "—"
    label      = (con or {}).get("label", "N/A")
    upside_str = "—"
    if p and tgt and tgt.get("mean") and p.get("price"):
        up         = (tgt["mean"] - p["price"]) / p["price"] * 100
        upside_str = f"{up:+.1f}%"

    with st.expander(f"{ticker} — {name}  |  {price_str}  |  {label}  |  אפסייד {upside_str}", expanded=expanded):
        _render_ticker_stats_row(p, con, tgt, theme)

        checklist = _guru_checklist_html(p, con, tgt, fun)
        if checklist:
            st.markdown(checklist, unsafe_allow_html=True)

        eval_result: dict = {}
        if claude_api_key:
            eval_result = _run_five_filter_eval(ticker, _build_data_summary(ticker, p, con, tgt, fun), td_str, claude_api_key)
            if "_error" in eval_result:
                st.warning(f"⚠️ שגיאת AI: {eval_result['_error']}")
                if st.button("🔄 נסה שוב", key=f"_retry_{ticker}"):
                    st.cache_data.clear()
                    st.rerun()
                eval_result = {}
        else:
            st.info("הוסף `ANTHROPIC_API_KEY` לקובץ `.streamlit/secrets.toml` לקבלת ניתוח AI.")

        total_score = _render_filter_cards(eval_result, claude_api_key)

        if eval_result:
            st.markdown(
                f'<div dir="rtl" style="display:flex;align-items:center;gap:12px;margin-top:4px;margin-bottom:2px">'
                f'<span style="font-size:12px;color:{COLOR["text_dim"]}">ציון כולל:</span>'
                f'{_score_badge(total_score)}</div>',
                unsafe_allow_html=True,
            )
            st.progress(int(total_score / 25 * 100) / 100)


# ── Candidate & custom-ticker sections ────────────────────────────────────────

def _fetch_candidate_data(candidates, td_str, api_key):
    """Batch-fetch prices/targets/consensus/fundamentals for all candidates."""
    tickers_tuple = tuple(sorted(s["ticker"] for s in candidates))
    with st.spinner("טוען נתוני שוק..."):
        prices_all    = get_stock_data(tickers_tuple, td_str)
        targets_all   = get_analyst_targets(tickers_tuple, td_str)
        consensus_all = get_consensus(tickers_tuple, td_str, api_key)
        fund_all: dict = get_finviz_fundamentals(tickers_tuple, td_str) or {} if FINVIZ_AVAILABLE else {}
    return prices_all, targets_all, consensus_all, fund_all


def _render_candidates(candidates, td_str, api_key, claude_api_key):
    """Fetch and render all candidate tickers."""
    if not candidates:
        st.info("כל המניות המוצעות כבר בתיק שלך.")
        return
    prices_all, targets_all, consensus_all, fund_all = _fetch_candidate_data(candidates, td_str, api_key)
    st.markdown(
        f'<div dir="rtl" style="font-size:12px;color:{COLOR["text_dim"]};margin-bottom:4px">'
        f'🔬 {len(candidates)} מניות לניתוח — לחץ על כל מניה להצגת 5 הפילטרים</div>',
        unsafe_allow_html=True,
    )
    for i, s in enumerate(candidates):
        t = s["ticker"]
        _render_ticker_section(
            ticker=t, name=s["name"], theme=s["theme"],
            p=prices_all.get(t), con=consensus_all.get(t, {}),
            tgt=targets_all.get(t), fun=fund_all.get(t) or None,
            td_str=td_str, claude_api_key=claude_api_key, expanded=(i == 0),
        )


def _render_custom_ticker_section(owned, td_str, api_key, claude_api_key):
    """Render the custom ticker search input and its analysis."""
    st.divider()
    st.markdown(
        f'<div dir="rtl" style="font-size:13px;font-weight:700;color:{COLOR["primary"]};margin-bottom:8px">🔍 ניתוח מניה אחרת</div>',
        unsafe_allow_html=True,
    )
    col_inp, col_btn = st.columns([3, 1])
    with col_inp:
        ticker_input = st.text_input(
            "הכנס סימול מניה", placeholder="לדוגמה: TSLA, AAPL, PLTR",
            key="analysis_custom_ticker", label_visibility="collapsed",
        ).strip().upper()
    with col_btn:
        if st.button("🔍 נתח", key="analyze_custom_btn", use_container_width=True) and ticker_input:
            st.session_state["_analysis_custom"] = ticker_input

    custom = st.session_state.get("_analysis_custom", ticker_input) or ""
    if not custom:
        return
    if custom in owned:
        st.warning(f"{custom} כבר בתיק שלך — השתמש בטאב 'אנליסטים' לניתוח מפורט.")
        return
    with st.spinner(f"מנתח את {custom}..."):
        cp   = get_stock_data((custom,), td_str).get(custom)
        ctgt = get_analyst_targets((custom,), td_str).get(custom)
        ccon = get_consensus((custom,), td_str, api_key).get(custom, {})
        cfun: Optional[dict] = None
        if FINVIZ_AVAILABLE:
            cfun = (get_finviz_fundamentals((custom,), td_str) or {}).get(custom)
    if not cp:
        st.warning(f"לא נמצאו נתוני מחיר עבור {custom}. בדוק שהסימול תקין.")
    else:
        _render_ticker_section(
            ticker=custom, name=TICKER_NAMES.get(custom, custom),
            theme="ניתוח מותאם אישית", p=cp, con=ccon, tgt=ctgt,
            fun=cfun, td_str=td_str, claude_api_key=claude_api_key, expanded=True,
        )


# ── Main render ───────────────────────────────────────────────────────────────

def render_analysis(portfolio, data, td_str: str, api_key: str = "", claude_api_key: str = ""):
    section_title(
        "מערכת 5 הפילטרים — Buffett & Lynch",
        "הערכת מניות לפי פילוסופיית Buffett (ערך/איכות) ו-Lynch (צמיחה/תצפית)",
    )
    owned      = set(all_tickers(portfolio))
    candidates = [s for s in SUGGESTIONS if s["ticker"] not in owned]

    with st.expander("מה זה 5 הפילטרים? 📖", expanded=False):
        st.markdown(
            '<div dir="rtl" style="font-size:13px;color:#cccccc;line-height:1.9">'
            "<b>1. 📊 פונדמנטלס ועסקיות</b> (Buffett/Lynch) — "
            "ROE > 15%? FCF גדל ומתואם לרווח נקי? PEG סביר ביחס לצמיחה?<br>"
            "<b>2. 🏰 חפיר תחרותי — Moat</b> (Buffett) — "
            "מה מונע מהמתחרים לגנוב לקוחות? כוח מיתוג, עלויות מעבר, יצרן זול? "
            "אפקט לינדי — האם המודל עסקי שרד מספר מיתונים?<br>"
            "<b>3. 👔 הנהלה וניהול הון</b> (Lynch) — "
            "האם להנהלה skin in the game? האם ההון מוקצה לרכישות עצמיות או ל-diworseification? "
            "האם ההנחיות שמרניות?<br>"
            "<b>4. 💰 שווי ומרווח ביטחון</b> (Buffett) — "
            "האם המחיר נמוך ב-20-30% מהשווי הפנימי? Second-level thinking — "
            "האם השוק מתמחר יתר על המידה או מתעלם מפוטנציאל?<br>"
            "<b>5. 🚩 דגלים אדומים</b> (Lynch) — "
            "חוב גבוה מהמתחרים? צמיחה רק דרך רכישות? הייפ תקשורתי? "
            "דילול מניות מתמשך? מודל עסקי מורכב מדי?<br><br>"
            "כל פילטר מקבל ציון 1–5 (1=גרוע, 5=מצוין). <b>ציון כולל מתוך 25.</b><br>"
            '<span style="color:#888;font-size:11px">'
            "הפילטרים מבוססים על: Warren Buffett (Berkshire Hathaway), "
            "Peter Lynch (Fidelity Magellan), Howard Marks (Oaktree Capital)"
            "</span>"
            "</div>",
            unsafe_allow_html=True,
        )

    _render_candidates(candidates, td_str, api_key, claude_api_key)
    _render_custom_ticker_section(owned, td_str, api_key, claude_api_key)

    # ── Disclaimer ────────────────────────────────────────────────────────────
    st.markdown(
        f'<div dir="rtl" style="font-size:10px;color:{COLOR["text_dim"]};'
        f'border-top:1px solid #222;padding-top:8px;margin-top:12px">'
        f'⚠️ ניתוח זה נוצר על ידי AI ומיועד לצרכי מידע בלבד. '
        f'אינו מהווה ייעוץ השקעות. כל השקעה כרוכה בסיכון — בצע בדיקה עצמאית.'
        f'</div>',
        unsafe_allow_html=True,
    )
