"""Shared UI helpers — section titles, color legends, term glossaries."""

import streamlit as st
from src.config import COLOR


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
