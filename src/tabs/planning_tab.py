"""Decision tools: performance history, layer rebalancing, position sizing.

All maths lives in src/history.py; this module only renders it.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import history as hx
from src.config import COLOR, HE
from src.portfolio import get_alerts, get_layer_for_ticker, save_portfolio
from src.ui_helpers import section_title
from src.valuation import compute_holdings

# ── Snapshots ─────────────────────────────────────────────────────────────────

def record_daily_snapshot(portfolio, data, td_str, market_state):
    """Upsert the snapshot for td_str; saves only when the row changed (≈ twice a day).

    Pre-market: skipped — prices are still the previous session's close.
    Session open: provisional row. After hours / weekend / holiday: final row.
    """
    if market_state.get("status_label") == "Pre-Market":
        return
    row = hx.snapshot_row(portfolio, data, td_str, provisional=bool(market_state.get("is_open")))
    if row is None:
        return
    snaps = portfolio.setdefault("snapshots", [])
    if hx.upsert_snapshot(snaps, row):
        save_portfolio(portfolio)


def _perf(portfolio):
    return hx.performance_frame(portfolio.get("snapshots") or [])


def render_since_last(portfolio):
    """One line for היום: flow-adjusted change since the previous snapshot."""
    lc = hx.last_change(_perf(portfolio))
    if not lc:
        st.caption(HE["hist_none"])
        return
    color = COLOR["positive"] if lc["pct"] >= 0 else COLOR["negative"]
    voo = f' &nbsp;|&nbsp; VOO {lc["voo_pct"]:+.2f}%' if lc["voo_pct"] is not None else ""
    flow = (f' &nbsp;|&nbsp; {HE["hist_flow"]} ${lc["flow"]:+,.0f}'
            if abs(lc["flow"]) >= 1 else "")
    st.markdown(
        f'<div dir="rtl" style="font-size:13px;margin:4px 0 10px">'
        f'{HE["hist_since"]} {lc["from"].strftime("%d.%m")}: '
        f'<b style="color:{color}">{lc["pct"]:+.2f}% (${lc["value_delta"]:+,.0f})</b>{voo}{flow}</div>',
        unsafe_allow_html=True,
    )


# ── History ───────────────────────────────────────────────────────────────────

def _kpi(col, label, value, good=None):
    color = COLOR["text_dim"] if good is None else (COLOR["positive"] if good else COLOR["negative"])
    col.markdown(
        f'<div class="kpi-card"><div class="kpi-label">{label}</div>'
        f'<div class="kpi-value" style="color:{color}">{value}</div></div>',
        unsafe_allow_html=True,
    )


def _fmt_pct(v):
    return "—" if v is None else f"{v:+.1f}%"


def render_history(portfolio, data):
    section_title(HE["hist_title"], HE["hist_sub"])
    snaps = portfolio.get("snapshots") or []
    perf  = _perf(portfolio)

    n_real = sum(1 for r in snaps if not r.get("reconstructed"))
    c_info, c_btn = st.columns([4, 1])
    c_info.caption(HE["hist_count"].format(real=n_real, total=len(snaps)))
    if c_btn.button(HE["hist_rebuild"], key="_hist_rebuild", help=HE["hist_rebuild_help"]):
        added = hx.merge_reconstructed(snaps, hx.reconstruct_history(portfolio, data))
        portfolio["snapshots"] = snaps
        save_portfolio(portfolio)
        st.success(HE["hist_rebuilt"].format(n=added))
        st.rerun()

    if perf.empty:
        st.info(HE["hist_none"])
        return

    ytd_start = pd.Timestamp(year=perf.index[-1].year, month=1, day=1)
    k1, k2, k3, k4, k5 = st.columns(5)
    r1m, v1m = hx.period_return(perf, "index", 30), hx.period_return(perf, "voo_index", 30)
    r3m = hx.period_return(perf, "index", 91)
    rytd = hx.period_return(perf, "index", since=ytd_start)
    vytd = hx.period_return(perf, "voo_index", since=ytd_start)
    _kpi(k1, HE["hist_1m"], _fmt_pct(r1m), None if r1m is None else r1m >= 0)
    _kpi(k2, HE["hist_3m"], _fmt_pct(r3m), None if r3m is None else r3m >= 0)
    _kpi(k3, "YTD", _fmt_pct(rytd), None if rytd is None else rytd >= 0)
    alpha = None if rytd is None or vytd is None else rytd - vytd
    _kpi(k4, HE["hist_alpha_ytd"], _fmt_pct(alpha), None if alpha is None else alpha >= 0)
    _kpi(k5, HE["hist_maxdd"], f'{perf["drawdown"].min() * 100:.1f}%', False)
    if v1m is not None:
        st.caption(f"VOO {HE['hist_1m']}: {v1m:+.1f}%")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=perf.index, y=perf["index"], name=HE["hist_portfolio"],
                             line={"color": COLOR["primary"], "width": 2}))
    if perf["voo_index"].notna().any():
        fig.add_trace(go.Scatter(x=perf.index, y=perf["voo_index"], name="VOO",
                                 line={"color": "#888888", "width": 1.5, "dash": "dot"}))
    fig.add_trace(go.Scatter(x=perf.index, y=perf["drawdown"] * 100, name=HE["hist_drawdown"],
                             yaxis="y2", fill="tozeroy",
                             line={"color": COLOR["negative"], "width": 1},
                             fillcolor="rgba(244,67,54,0.15)"))
    fig.update_layout(
        height=380, margin={"t": 20, "b": 30, "l": 40, "r": 40},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#cccccc"}, legend={"orientation": "h", "y": 1.08},
        yaxis={"title": HE["hist_index_axis"], "gridcolor": "#1f2937"},
        yaxis2={"title": "%", "overlaying": "y", "side": "right", "showgrid": False},
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
    if any(r.get("reconstructed") for r in snaps):
        st.caption(HE["hist_reconstructed_note"])


# ── Rebalancing ───────────────────────────────────────────────────────────────

def get_layer_targets(portfolio, layers):
    saved = (portfolio.get("settings") or {}).get("layer_targets") or {}
    defaults = hx.default_layer_targets(layers)
    return {layer: float(saved.get(layer, defaults[layer])) for layer in layers}


def render_rebalance(portfolio, data):
    section_title(HE["reb_title"], HE["reb_sub"])
    holdings = compute_holdings(portfolio, data.get("prices", {}), data.get("ils_usd"))
    current  = holdings["layers"]
    layers   = sorted(set(current) | set(portfolio["layers"]))
    if not current:
        st.info(HE["reb_empty"])
        return

    targets = get_layer_targets(portfolio, layers)
    edited = st.data_editor(
        pd.DataFrame({"layer": layers, "target_pct": [targets[x] for x in layers]}),
        column_config={
            "layer":      st.column_config.TextColumn(HE["layer"], disabled=True),
            "target_pct": st.column_config.NumberColumn(HE["reb_target"], min_value=0.0,
                                                        max_value=100.0, step=1.0, format="%.0f%%"),
        },
        hide_index=True, key="_layer_targets_editor", use_container_width=True,
    )
    new_targets = dict(zip(edited["layer"], edited["target_pct"].astype(float)))
    total_pct = sum(new_targets.values())
    if abs(total_pct - 100) > 0.5:
        st.warning(HE["reb_sum_warn"].format(total=total_pct))
    if new_targets != targets and st.button(HE["reb_save"], key="_save_targets"):
        portfolio.setdefault("settings", {})["layer_targets"] = new_targets
        save_portfolio(portfolio)
        st.rerun()

    new_cash = st.number_input(HE["reb_new_cash"], min_value=0.0, value=0.0, step=500.0,
                               key="_reb_new_cash")
    plan = hx.rebalance_plan(current, new_targets, new_cash)

    rows = ""
    for r in plan.itertuples():
        drift_c = COLOR["negative"] if abs(r.drift_pp) >= 5 else (
            COLOR["warning"] if abs(r.drift_pp) >= 2 else COLOR["positive"])
        rows += (
            f'<tr><td style="padding:5px 8px;font-weight:700">{r.layer}</td>'
            f'<td style="padding:5px 8px">${r.current_usd:,.0f}</td>'
            f'<td style="padding:5px 8px">{r.current_pct:.1f}%</td>'
            f'<td style="padding:5px 8px">{r.target_pct:.0f}%</td>'
            f'<td style="padding:5px 8px;color:{drift_c};font-weight:700">{r.drift_pp:+.1f}pp</td>'
            f'<td style="padding:5px 8px">${r.to_target_usd:+,.0f}</td>'
            f'<td style="padding:5px 8px;color:{COLOR["primary"]};font-weight:700">'
            f'{"$" + format(r.buy_usd, ",.0f") if r.buy_usd >= 1 else "—"}</td></tr>'
        )
    th = f'padding:5px 8px;color:{COLOR["primary"]};border-bottom:1px solid #333;text-align:right'
    st.markdown(
        f'<div dir="rtl" style="font-size:12px"><table style="width:100%;border-collapse:collapse">'
        f'<thead><tr><th style="{th}">{HE["layer"]}</th><th style="{th}">{HE["value"]}</th>'
        f'<th style="{th}">{HE["reb_current"]}</th><th style="{th}">{HE["reb_target"]}</th>'
        f'<th style="{th}">{HE["reb_drift"]}</th><th style="{th}">{HE["reb_to_target"]}</th>'
        f'<th style="{th}">{HE["reb_buy"]}</th></tr></thead><tbody>{rows}</tbody></table></div>',
        unsafe_allow_html=True,
    )
    st.caption(HE["reb_note"])


# ── Position sizing ───────────────────────────────────────────────────────────

def render_position_sizer(portfolio, data, ticker):
    p = (data.get("prices") or {}).get(ticker)
    if not p or not p.get("price"):
        return
    holdings = compute_holdings(portfolio, data.get("prices", {}), data.get("ils_usd"))
    account  = holdings["market_value_usd"]
    ils      = p.get("currency") == "ILS"
    fx       = holdings["ils_usd"] if ils else 1.0
    sym      = "₪" if ils else "$"
    price    = float(p["price"])
    stored   = (get_alerts(portfolio).get(ticker) or {}).get("stop_loss")

    with st.expander(f"{HE['size_title']} — {ticker}", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        acct  = c1.number_input(HE["size_account"], min_value=0.0, value=float(round(account, 0)),
                                step=1000.0, key=f"_sz_acct_{ticker}")
        risk  = c2.number_input(HE["size_risk"], min_value=0.1, max_value=10.0, value=1.0,
                                step=0.25, key=f"_sz_risk_{ticker}")
        entry = c3.number_input(f"{HE['size_entry']} ({sym})", min_value=0.0, value=round(price, 2),
                                step=0.5, key=f"_sz_entry_{ticker}")
        stop  = c4.number_input(f"{HE['size_stop']} ({sym})", min_value=0.0,
                                value=round(float(stored) if stored else price * 0.93, 2),
                                step=0.5, key=f"_sz_stop_{ticker}")
        r = hx.position_size(acct, risk, entry, stop, fx)
        if r is None:
            st.warning(HE["size_invalid"])
            return
        layer = get_layer_for_ticker(portfolio, ticker)
        layer_now = holdings["layers"].get(layer, 0.0) if layer else 0.0
        layer_after = (layer_now + r["position_usd"]) / (account + r["position_usd"]) * 100 if account else 0
        target = get_layer_targets(portfolio, sorted(set(portfolio["layers"]))).get(layer) if layer else None
        st.markdown(
            f'<div dir="rtl" style="font-size:13px;line-height:1.9">'
            f'<b style="color:{COLOR["primary"]};font-size:16px">{r["shares"]:,} {HE["shares"]}</b>'
            f' &nbsp;·&nbsp; {HE["size_position"]} ${r["position_usd"]:,.0f} ({r["position_pct"]:.1f}%)'
            f' &nbsp;·&nbsp; {HE["size_at_risk"]} ${r["risk_usd"]:,.0f}'
            f' &nbsp;·&nbsp; {HE["size_stop_dist"]} {r["stop_pct"]:.1f}%'
            + (f'<br>{HE["layer"]} {layer}: {layer_now / account * 100 if account else 0:.1f}% → '
               f'<b>{layer_after:.1f}%</b>'
               + (f' ({HE["reb_target"]} {target:.0f}%)' if target is not None else "") if layer else "")
            + '</div>',
            unsafe_allow_html=True,
        )
