"""Trading Journal AI tab — conversational trade logging with Claude Haiku."""

import json
import re
from typing import Dict, List, Optional

import streamlit as st

from src import ai
from src.config import HE, SETUP_TYPES
from src.journal import JournalReadError, load_journal, save_journal
from src.ui_helpers import esc, fmt_api_error

# ── Constants ─────────────────────────────────────────────────────────────────
_SYSTEM = (
    "You are a trading journal AI. When a user describes a trade, respond in TWO parts:\n\n"
    "PART 1: One sentence. Flag rule violations: no impulse trades, stop always predefined, never average down.\n\n"
    "PART 2: Extract to JSON:\n\n"
    '{"date":null,"ticker":"","setup_type":"breakout|pullback_ema|range|vcp|other",'
    '"direction":"Long|Short","entry_price":null,"stop_price":null,"target_price":null,'
    '"r_multiple_entry":null,"position_size":null,"execution_quality":null,'
    '"emotional_state":"calm|anxious|FOMO|revenge|disciplined",'
    '"result":"Win|Loss|Breakeven|Open","actual_r":null,"did_right":"","would_change":""}\n\n'
    "Use null for missing fields. setup_type: exactly one of breakout, pullback_ema, range, vcp, other. "
    "direction: Long or Short. result: Win, Loss, Breakeven, or Open. "
    "emotional_state: calm, anxious, FOMO, revenge, or disciplined. "
    "execution_quality: number 1-5.\n\n"
    "On REVIEW: win rate, avg R won/lost, most common setup, execution mistakes, "
    "emotion/result correlation, one concrete fix to implement immediately."
)

_PLACEHOLDER = (
    "e.g. Bought NVDA on 12/3, breakout at $138.50, stop $134, target $148, "
    "2% size, execution 4/5, calm. Won at $146.20."
)


# ── Persistence (all file access goes through src/journal.py) ────────────────
def _load_trades() -> List[Dict]:
    try:
        st.session_state.tj_load_failed = False
        return load_journal()
    except JournalReadError:
        st.session_state.tj_load_failed = True
        return []


def _save_trades(trades: List[Dict]) -> None:
    if st.session_state.get("tj_load_failed"):
        st.error(HE["journal_corrupt"])  # never overwrite a file we couldn't read
        return
    save_journal(trades)


# ── Session state ─────────────────────────────────────────────────────────────
def _init() -> None:
    if "tj_msgs" not in st.session_state:
        st.session_state.tj_msgs = []        # display list: {role, text, flagged, json_str}
    if "tj_hist" not in st.session_state:
        st.session_state.tj_hist = []        # Claude API message list: {role, content}
    if "tj_trades" not in st.session_state:
        st.session_state.tj_trades = _load_trades()
    if "tj_review" not in st.session_state:
        st.session_state.tj_review = None
    if "tj_edit_idx" not in st.session_state:
        st.session_state.tj_edit_idx = None


# ── Claude API ────────────────────────────────────────────────────────────────
def _call_claude(messages: List[Dict], api_key: str) -> str:
    return ai.ask(api_key, 1200, system=_SYSTEM, messages=messages, purpose="journal",
                  allow_truncated=True)


# ── Parse response ────────────────────────────────────────────────────────────
def _extract_trade_json(text: str):
    """Return (trade_dict, json_str, start_index) for the first JSON object with a
    "ticker" key, or (None, None, None). Handles nested objects, unlike a regex."""
    dec = json.JSONDecoder()
    i = text.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(text, i)
            if isinstance(obj, dict) and "ticker" in obj:
                return obj, text[i:end], i
        except ValueError:
            pass
        i = text.find("{", i + 1)
    return None, None, None


def _parse(text: str):
    """Return (part1_text, flagged, json_str_or_None, trade_dict_or_None)."""
    trade, json_str, jm = _extract_trade_json(text)

    p2 = re.search(r"PART\s*2", text, re.IGNORECASE)
    if p2:
        p1 = text[: p2.start()]
    elif jm is not None:
        p1 = text[:jm]
    else:
        p1 = text

    p1 = re.sub(r"^PART\s*1[:\s]*", "", p1, flags=re.IGNORECASE).strip()
    flagged = bool(re.search(
        r"violation|impulse|no stop|average down|missing stop|undefined stop", p1, re.IGNORECASE
    ))
    return p1, flagged, json_str, trade


# ── Trade card HTML ───────────────────────────────────────────────────────────
def _card_html(t: Dict) -> str:
    # Fields are Claude-extracted / user-typed — escape for unsafe_allow_html
    ticker = esc(t.get("ticker") or "???")
    date_s = esc(t.get("date") or "—")
    dir_s  = esc(t.get("direction") or "")
    result = esc(t.get("result") or "Open")
    setup  = esc((t.get("setup_type") or "other").replace("_", " ").upper())

    def fp(v: Optional[float]) -> str:
        return f"${float(v):.2f}" if v is not None else "—"

    entry   = fp(t.get("entry_price"))
    stop    = fp(t.get("stop_price"))
    target  = fp(t.get("target_price"))
    r_en    = f"{float(t['r_multiple_entry']):.1f}R" if t.get("r_multiple_entry") is not None else "—"
    actual  = float(t["actual_r"]) if t.get("actual_r") is not None else None
    exec_q  = float(t["execution_quality"]) if t.get("execution_quality") is not None else None
    emo     = esc(t.get("emotional_state") or "")

    # Direction badge
    dc = {"Long": "#0ea5e9", "Short": "#fb7185"}.get(dir_s, "#64748b")
    dir_bdg = (
        f'<span style="background:{dc}18;color:{dc};border:1px solid {dc}40;'
        f'font-size:9px;font-weight:800;padding:2px 7px;border-radius:4px;'
        f'text-transform:uppercase;letter-spacing:.5px">{dir_s}</span>'
    ) if dir_s else ""

    # Result badge
    rc_map = {"Win": "#22c55e", "Loss": "#ef4444", "Breakeven": "#64748b", "Open": "#f59e0b"}
    rc = rc_map.get(result, "#f59e0b")
    res_bdg = (
        f'<span style="background:{rc}18;color:{rc};border:1px solid {rc}40;'
        f'font-size:9px;font-weight:800;padding:2px 7px;border-radius:4px;'
        f'text-transform:uppercase;letter-spacing:.5px">{result}</span>'
    )

    # Execution dots
    dots = ""
    if exec_q is not None:
        filled = round(exec_q)
        dots = "".join(
            f'<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
            f'background:{"#00cf8d" if i <= filled else "#1e2d45"};margin-right:2px"></span>'
            for i in range(1, 6)
        )

    # Emotion chip
    emo_style = {
        "calm":        ("#4ade80",  "#22c55e15"),
        "disciplined": ("#00cf8d",  "#00cf8d15"),
        "anxious":     ("#f59e0b",  "#f59e0b15"),
        "FOMO":        ("#ef4444",  "#ef444415"),
        "revenge":     ("#fb7185",  "#fb718515"),
    }
    ec, ebg = emo_style.get(emo, ("#64748b", "#64748b15"))
    emo_chip = (
        f'<span style="background:{ebg};color:{ec};font-size:10px;font-weight:700;'
        f'padding:2px 8px;border-radius:10px">{emo}</span>'
    ) if emo else ""

    # Actual R bar
    r_bar = ""
    if actual is not None:
        pos  = actual >= 0
        pct  = min(abs(actual) / 5 * 100, 100)
        rlbl = f"+{actual:.2f}R" if pos else f"{actual:.2f}R"
        rcol = "#22c55e" if pos else "#ef4444"
        r_bar = (
            f'<div style="margin-top:2px">'
            f'<div style="display:flex;justify-content:space-between;font-size:10px;'
            f'color:#64748b;margin-bottom:3px"><span>Actual R</span>'
            f'<span style="color:{rcol};font-weight:800">{rlbl}</span></div>'
            f'<div style="height:5px;background:#1e2d45;border-radius:3px;overflow:hidden">'
            f'<div style="width:{pct:.0f}%;height:100%;background:{rcol};border-radius:3px">'
            f'</div></div></div>'
        )

    # Notes
    notes = ""
    if t.get("did_right") or t.get("would_change"):
        notes = '<div style="border-top:1px solid #1e2d45;margin-top:4px;padding-top:8px">'
        if t.get("did_right"):
            notes += (
                f'<div style="font-size:11px;color:#94a3b8;margin-bottom:3px">'
                f'<b style="color:#e2e8f0">✓</b> {esc(t["did_right"])}</div>'
            )
        if t.get("would_change"):
            notes += (
                f'<div style="font-size:11px;color:#94a3b8">'
                f'<b style="color:#e2e8f0">△</b> {esc(t["would_change"])}</div>'
            )
        notes += "</div>"

    metrics = (
        f'<div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">'
        f'<div><div style="font-size:8px;color:#64748b;text-transform:uppercase;'
        f'font-weight:700;letter-spacing:.5px;margin-bottom:2px">R at Entry</div>'
        f'<div style="font-size:13px;font-weight:800">{r_en}</div></div>'
    )
    if dots:
        metrics += (
            f'<div><div style="font-size:8px;color:#64748b;text-transform:uppercase;'
            f'font-weight:700;letter-spacing:.5px;margin-bottom:3px">Execution</div>'
            f'{dots}</div>'
        )
    if emo_chip:
        metrics += (
            f'<div><div style="font-size:8px;color:#64748b;text-transform:uppercase;'
            f'font-weight:700;letter-spacing:.5px;margin-bottom:2px">Mindset</div>'
            f'{emo_chip}</div>'
        )
    metrics += "</div>"

    return (
        f'<div style="background:#0f1729;border:1px solid #1e2d45;border-radius:10px;'
        f'padding:13px;display:flex;flex-direction:column;gap:9px;margin-bottom:10px;direction:ltr">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start">'
        f'<div><div style="font-size:18px;font-weight:900;letter-spacing:.4px">{ticker}</div>'
        f'<div style="font-size:10px;color:#64748b">{date_s}</div></div>'
        f'<div style="display:flex;gap:5px">{dir_bdg}{res_bdg}</div></div>'
        f'<div style="font-size:9px;font-weight:700;color:#00cf8d;text-transform:uppercase;'
        f'letter-spacing:1px">{setup}</div>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px">'
        f'<div><div style="font-size:8px;color:#64748b;text-transform:uppercase;font-weight:700;'
        f'letter-spacing:.5px">Entry</div>'
        f'<div style="font-size:13px;font-weight:700;font-variant-numeric:tabular-nums">{entry}</div></div>'
        f'<div><div style="font-size:8px;color:#64748b;text-transform:uppercase;font-weight:700;'
        f'letter-spacing:.5px">Stop</div>'
        f'<div style="font-size:13px;font-weight:700;color:#ef4444;font-variant-numeric:tabular-nums">{stop}</div></div>'
        f'<div><div style="font-size:8px;color:#64748b;text-transform:uppercase;font-weight:700;'
        f'letter-spacing:.5px">Target</div>'
        f'<div style="font-size:13px;font-weight:700;color:#22c55e;font-variant-numeric:tabular-nums">{target}</div></div>'
        f'</div>'
        f'{metrics}'
        f'{r_bar}'
        f'{notes}'
        f'</div>'
    )


# ── Helpers ───────────────────────────────────────────────────────────────────
def _sf(v, default: float = 0.0) -> float:
    """None-safe float conversion for edit form fields."""
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _none_if_zero(v: float) -> Optional[float]:
    return None if v == 0.0 else v


# ── Inline edit form ──────────────────────────────────────────────────────────
def _render_edit_form(idx: int, t: Dict) -> None:
    """Render an inline edit form replacing the card at index idx."""
    st.caption(f"✏️ Editing — {t.get('ticker', '?')}")

    setup_opts = list(SETUP_TYPES)
    emo_opts   = ["calm", "disciplined", "anxious", "FOMO", "revenge"]
    dir_opts   = ["Long", "Short"]
    res_opts   = ["Open", "Win", "Loss", "Breakeven"]

    cur_setup = t.get("setup_type") or "other"
    cur_emo   = t.get("emotional_state") or "calm"
    cur_dir   = t.get("direction") or "Long"
    cur_res   = t.get("result") or "Open"

    with st.form(key=f"tj_edit_form_{idx}", clear_on_submit=False):
        c1, c2, c3, c4 = st.columns(4)
        ticker    = c1.text_input("Ticker",    value=t.get("ticker") or "")
        date_v    = c2.text_input("Date",      value=t.get("date") or "")
        direction = c3.selectbox("Direction",  dir_opts,
                                 index=dir_opts.index(cur_dir) if cur_dir in dir_opts else 0)
        result    = c4.selectbox("Result",     res_opts,
                                 index=res_opts.index(cur_res) if cur_res in res_opts else 0)

        c1, c2, c3 = st.columns(3)
        entry_price  = c1.number_input("Entry $",  value=_sf(t.get("entry_price")),  step=0.01, format="%.2f")
        stop_price   = c2.number_input("Stop $",   value=_sf(t.get("stop_price")),   step=0.01, format="%.2f")
        target_price = c3.number_input("Target $", value=_sf(t.get("target_price")), step=0.01, format="%.2f")

        c1, c2, c3 = st.columns(3)
        r_entry  = c1.number_input("R at Entry", value=_sf(t.get("r_multiple_entry")), step=0.1,  format="%.1f")
        actual_r = c2.number_input("Actual R",   value=_sf(t.get("actual_r")),         step=0.1,  format="%.1f")
        exec_q   = c3.number_input("Execution (1–5)", value=_sf(t.get("execution_quality"), 3.0),
                                   min_value=1.0, max_value=5.0, step=1.0, format="%.0f")

        c1, c2 = st.columns(2)
        setup = c1.selectbox("Setup", setup_opts,
                             index=setup_opts.index(cur_setup) if cur_setup in setup_opts else 4)
        emo   = c2.selectbox("Mindset", emo_opts,
                             index=emo_opts.index(cur_emo) if cur_emo in emo_opts else 0)

        did_right    = st.text_area("✓ Did right",      value=t.get("did_right") or "",    height=55)
        would_change = st.text_area("△ Would change",   value=t.get("would_change") or "", height=55)

        sc1, sc2 = st.columns(2)
        save_btn   = sc1.form_submit_button("💾 Save",   use_container_width=True, type="primary")
        cancel_btn = sc2.form_submit_button("✕ Cancel", use_container_width=True)

    if save_btn:
        updated = dict(t)
        updated.update({
            "ticker":           ticker.strip().upper() or t.get("ticker"),
            "date":             date_v.strip() or t.get("date"),
            "direction":        direction,
            "result":           result,
            "entry_price":      _none_if_zero(entry_price),
            "stop_price":       _none_if_zero(stop_price),
            "target_price":     _none_if_zero(target_price),
            "r_multiple_entry": _none_if_zero(r_entry),
            "actual_r":         _none_if_zero(actual_r),
            "execution_quality": exec_q,
            "setup_type":       setup,
            "emotional_state":  emo,
            "did_right":        did_right.strip(),
            "would_change":     would_change.strip(),
        })
        st.session_state.tj_trades[idx] = updated
        _save_trades(st.session_state.tj_trades)
        st.session_state.tj_edit_idx = None
        st.rerun()

    if cancel_btn:
        st.session_state.tj_edit_idx = None
        st.rerun()


# ── Main render ───────────────────────────────────────────────────────────────
def render_trading_journal_ai(claude_api_key: str = "") -> None:
    _init()
    if st.session_state.get("tj_load_failed"):
        st.error(HE["journal_corrupt"])

    trades   = st.session_state.tj_trades
    n        = len(trades)
    has_key  = bool(claude_api_key)

    # ── Header ──
    st.markdown(
        f'<div dir="ltr" style="display:flex;align-items:center;gap:10px;margin-bottom:4px">'
        f'<span style="font-size:18px;font-weight:800;color:#00cf8d">🤖 Trading Journal AI</span>'
        f'<span style="background:#00cf8d;color:#000;font-size:10px;font-weight:800;'
        f'padding:2px 9px;border-radius:10px">{n} trade{"s" if n != 1 else ""}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    hc1, hc2, hc3 = st.columns([6, 1, 1])
    with hc2:
        do_review = st.button(
            "📊 REVIEW",
            disabled=(n == 0 or not has_key),
            use_container_width=True,
        )
    with hc3:
        do_clear = st.button("✕ Clear chat", type="secondary", use_container_width=True)

    if do_clear:
        st.session_state.tj_msgs   = []
        st.session_state.tj_hist   = []
        st.session_state.tj_review = None
        # Trade cards are intentionally preserved — use the 🗑 button on each card to delete
        st.rerun()

    if do_review:
        _handle_review(claude_api_key)

    st.divider()

    # ── Two-column body ──
    col_chat, col_cards = st.columns([1, 1.1], gap="medium")

    # ── Chat (left) ──
    with col_chat:
        # Seed opening message
        if not st.session_state.tj_msgs:
            st.session_state.tj_msgs.append({
                "role": "assistant",
                "text": "Tell me about your last trade.",
                "flagged": False,
                "json_str": None,
            })

        chat_area = st.container(height=530, border=False)
        with chat_area:
            for m in st.session_state.tj_msgs:
                with st.chat_message(m["role"]):
                    if m["role"] == "assistant":
                        color = "#f59e0b" if m.get("flagged") else "#a3e6cc"
                        st.markdown(
                            f'<div dir="ltr" style="color:{color};font-size:13px;line-height:1.55">'
                            f'{esc(m["text"])}</div>',
                            unsafe_allow_html=True,
                        )
                        if m.get("json_str"):
                            with st.expander("📋 Extracted JSON", expanded=False):
                                st.code(m["json_str"], language="json")
                    else:
                        st.markdown(
                            f'<div dir="ltr" style="font-size:13px">{esc(m["text"])}</div>',
                            unsafe_allow_html=True,
                        )

        if not has_key:
            st.caption("⚠️ Add ANTHROPIC_API_KEY to .streamlit/secrets.toml to enable AI responses.")

        prompt = st.chat_input(_PLACEHOLDER, disabled=not has_key)
        if prompt:
            _handle_message(prompt, claude_api_key)
            st.rerun()

    # ── Cards (right) ──
    with col_cards:
        if st.session_state.tj_review:
            st.markdown(
                f'<div style="background:#0f1729;border:1px solid #1e2d45;border-radius:10px;'
                f'padding:15px;margin-bottom:12px">'
                f'<div style="font-size:11px;font-weight:800;color:#00cf8d;'
                f'letter-spacing:.5px;margin-bottom:8px">📊 TRADE REVIEW</div>'
                f'<div dir="ltr" style="font-size:12px;line-height:1.7;white-space:pre-wrap">'
                f'{esc(st.session_state.tj_review)}</div></div>',
                unsafe_allow_html=True,
            )

        if not trades:
            st.markdown(
                '<div style="display:flex;flex-direction:column;align-items:center;'
                'padding:60px 0;color:#64748b;gap:8px">'
                '<div style="font-size:36px">📋</div>'
                '<div style="font-size:14px;font-weight:600">No trades yet</div>'
                '<div style="font-size:11px">Describe a trade in the chat</div></div>',
                unsafe_allow_html=True,
            )
        else:
            editing_idx = st.session_state.get("tj_edit_idx")
            # No fixed height when editing so the form has room
            if editing_idx is not None:
                cards_area = st.container(border=False)
            else:
                cards_area = st.container(height=580, border=False)
            with cards_area:
                for i, t in enumerate(trades):
                    if editing_idx == i:
                        _render_edit_form(i, t)
                    else:
                        st.markdown(_card_html(t), unsafe_allow_html=True)
                        b1, b2, _ = st.columns([1, 1, 4])
                        with b1:
                            if st.button("✏️", key=f"tj_edit_{i}", help="Edit trade",
                                         use_container_width=True):
                                st.session_state.tj_edit_idx = i
                                st.rerun()
                        with b2:
                            if st.button("🗑", key=f"tj_del_{i}", help="Delete trade",
                                         use_container_width=True):
                                st.session_state.tj_trades.pop(i)
                                _save_trades(st.session_state.tj_trades)
                                if st.session_state.tj_edit_idx == i:
                                    st.session_state.tj_edit_idx = None
                                st.rerun()


# ── Message handler ───────────────────────────────────────────────────────────
def _handle_message(text: str, api_key: str) -> None:
    st.session_state.tj_msgs.append({"role": "user", "text": text})
    st.session_state.tj_hist.append({"role": "user", "content": text})

    try:
        reply = _call_claude(st.session_state.tj_hist, api_key)
    except Exception as exc:
        reply = f"⚠️ {fmt_api_error(exc)}"

    p1, flagged, json_str, trade = _parse(reply)

    st.session_state.tj_msgs.append({
        "role": "assistant",
        "text": p1,
        "flagged": flagged,
        "json_str": json_str,
    })
    st.session_state.tj_hist.append({"role": "assistant", "content": reply})

    if trade and trade.get("ticker"):
        st.session_state.tj_trades.insert(0, trade)
        _save_trades(st.session_state.tj_trades)


# ── Review handler ────────────────────────────────────────────────────────────
def _handle_review(api_key: str) -> None:
    trades = st.session_state.tj_trades
    if not trades:
        return
    payload = f"REVIEW — {len(trades)} trades:\n{json.dumps(trades, indent=2)}"
    msgs = [*st.session_state.tj_hist, {"role": "user", "content": payload}]
    try:
        reply = _call_claude(msgs, api_key)
        st.session_state.tj_review = reply
    except Exception as exc:
        st.session_state.tj_review = f"⚠️ {fmt_api_error(exc)}"
