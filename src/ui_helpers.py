"""Shared UI helpers — section titles, color legends, term glossaries, treemap."""

import plotly.graph_objects as go
import streamlit as st

from src.config import COLOR, LAYER_COLORS, TICKER_NAMES


def section_title(title, subtitle=""):
    """Prominent RTL section title with optional grey subtitle line."""
    sub = (
        f'<div style="font-size:11px;color:{COLOR["text_dim"]};margin-top:2px">{subtitle}</div>'
        if subtitle else ""
    )
    st.markdown(
        f'<div dir="rtl" style="margin-bottom:10px">'
        f'<div style="font-size:17px;font-weight:700;color:{COLOR["primary"]};'
        f'border-right:3px solid {COLOR["primary"]};padding-right:8px">{title}</div>'
        f'{sub}</div>',
        unsafe_allow_html=True,
    )


def color_legend(items):
    """
    Horizontal RTL color-dot legend.
    items = [(color_hex, label_str), ...]
    """
    dots = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:4px;margin-left:14px;white-space:nowrap">'
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;'
        f'background:{c};flex-shrink:0"></span>'
        f'<span style="font-size:10px;color:{COLOR["text_dim"]}">{label}</span>'
        f'</span>'
        for c, label in items
    )
    st.markdown(
        f'<div dir="rtl" style="display:flex;flex-wrap:wrap;align-items:center;'
        f'gap:4px;margin:4px 0 10px 0;padding:6px 8px;background:#1a1a1a;'
        f'border-radius:4px">{dots}</div>',
        unsafe_allow_html=True,
    )


def _change_hex(change: float) -> str:
    """Map a daily % change to a Finviz-style heatmap color (dark-theme)."""
    if change >= 3.0:
        return "#1b5e20"
    if change >= 1.5:
        return "#2e7d32"
    if change >= 0.3:
        return "#388e3c"
    if change > -0.3:
        return "#2d3748"
    if change > -1.5:
        return "#c62828"
    if change > -3.0:
        return "#b71c1c"
    return "#7f0000"


def portfolio_treemap(portfolio: dict, prices: dict, height: int = 300) -> None:
    """
    Finviz-style portfolio treemap: grouped by layer (parent), sized by portfolio
    value, colored by daily % change.  Watchlist positions (0 shares) appear as
    small boxes with a 👁 badge so they stay visible but don't dominate sizing.
    """
    ids, labels, parents, values, marker_colors, hovertext = [], [], [], [], [], []

    for layer, lots in portfolio["layers"].items():
        ids.append(layer)
        labels.append(layer)
        parents.append("")
        values.append(0)
        marker_colors.append(LAYER_COLORS.get(layer, "#444444"))
        hovertext.append(f"<b>{layer}</b>")

        # Aggregate shares per ticker within this layer
        seen: dict = {}
        for lot in lots:
            t = lot["ticker"]
            seen[t] = seen.get(t, 0) + lot.get("shares", 0)

        for t, total_shares in seen.items():
            p = prices.get(t)
            if not p:
                continue
            price  = p.get("price", 0) or 0.0
            change = p.get("change", 0.0) or 0.0

            is_watchlist = total_shares <= 0
            val = (price * total_shares) if not is_watchlist else max(price * 0.05, 1.0)

            name = TICKER_NAMES.get(t, t)
            badge = " 👁" if is_watchlist else ""
            label = f"{t}{badge}<br>{change:+.1f}%"
            hover = (
                f"<b>{t}</b> — {name}<br>"
                f"מחיר: ${price:.2f}  ({change:+.2f}%)"
                + (f"<br>שווי: ${val:,.0f}" if not is_watchlist else "<br><i>Watchlist</i>")
            )

            ids.append(f"{layer}/{t}")
            labels.append(label)
            parents.append(layer)
            values.append(val)
            marker_colors.append(_change_hex(change))
            hovertext.append(hover)

    if len(ids) <= len(portfolio.get("layers", {})):
        st.caption("אין נתוני מחיר")
        return

    fig = go.Figure(go.Treemap(
        ids=ids,
        labels=labels,
        parents=parents,
        values=values,
        branchvalues="total",
        marker_colors=marker_colors,
        hovertext=hovertext,
        hoverinfo="text",
        textfont={"size": 11, "color": "#ffffff"},
        pathbar_visible=False,
    ))
    fig.update_layout(
        height=height,
        margin={"t": 0, "b": 0, "l": 0, "r": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#ffffff"},
    )
    st.plotly_chart(fig, use_container_width=True)


def term_glossary(terms, label="📖 מקרא מונחים"):
    """
    Collapsible RTL term-definition table.
    terms = [(term_str, definition_str), ...]
    """
    with st.expander(label, expanded=False):
        rows = "".join(
            f'<tr>'
            f'<td style="padding:4px 16px 4px 0;color:{COLOR["primary"]};font-weight:600;'
            f'font-size:11px;white-space:nowrap;vertical-align:top">{t}</td>'
            f'<td style="padding:4px 0;font-size:11px;color:#cccccc;line-height:1.4">{d}</td>'
            f'</tr>'
            for t, d in terms
        )
        st.markdown(
            f'<div dir="rtl"><table style="border-collapse:collapse;width:100%">'
            f'<tbody>{rows}</tbody></table></div>',
            unsafe_allow_html=True,
        )
