"""Damodaran sector benchmark fetcher — NYU annual Excel files, updated January each year.

Public datasets: https://pages.stern.nyu.edu/~adamodar/pc/datasets/
No authentication required.  Cached for 7 days (Damodaran updates annually in January).
"""

import io
import math
from typing import Optional

import pandas as pd
import requests
import streamlit as st

from src.config import PORTFOLIO_ETFS, TICKER_SECTOR

_BASE_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/"
_TIMEOUT = 15  # seconds per file

# Per-ticker keyword hints for fuzzy-matching Damodaran industry rows (lowercase substrings)
_TICKER_KEYWORDS: dict = {
    "CCJ":   ["uranium", "metals & mining", "mining"],     # Uranium → Metals & Mining
    "FCX":   ["metals & mining", "copper", "mining"],
    "ETN":   ["electrical equipment", "machinery (diversified)"],
    "VRT":   ["computer services", "electronics (consumer"],
    "AMD":   ["semiconductor"],
    "AMZN":  ["retail (online", "retail(online", "information service"],
    "GOOGL": ["information service", "internet software", "advertising"],
    "CRWD":  ["software (system", "computer services"],
    "ESLT":  ["defense", "aerospace/defense"],
    "TEVA":  ["drug (pharma", "drug", "pharmaceutical"],
    "EQX":   ["gold/silver", "gold", "metals & mining"],
}


def _fetch_excel(filename: str) -> Optional[pd.DataFrame]:
    """
    Download an Excel file from Damodaran's NYU dataset directory.
    Tries .xlsx (openpyxl) first, then .xls (xlrd) as fallback.
    Returns DataFrame or None on any failure.
    """
    stem = filename.rsplit(".", 1)[0]
    attempts = [
        (stem + ".xlsx", {"engine": "openpyxl"}),
        (stem + ".xls",  {}),  # auto-detect engine (xlrd for .xls)
    ]
    for url_filename, read_kwargs in attempts:
        try:
            resp = requests.get(_BASE_URL + url_filename, timeout=_TIMEOUT)
            resp.raise_for_status()
            df = pd.read_excel(io.BytesIO(resp.content), header=0, **read_kwargs)
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception:
            continue
    return None


def _find_industry_col(df: pd.DataFrame) -> Optional[str]:
    """Return the column name that holds industry/sector labels."""
    for col in df.columns:
        if "industry" in col.lower() or "sector" in col.lower():
            return col
    return df.columns[0] if len(df.columns) > 0 else None


def _safe_float(val) -> Optional[float]:
    """Convert to float; return None for NaN or unconvertible values."""
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


@st.cache_data(ttl=604800)  # 7 days — Damodaran updates annually in January
def get_damodaran_sector_data() -> dict:
    """
    Fetch and merge Damodaran sector benchmarks from NYU public datasets.

    Returns {industry_name_lower: {name, pe, ev_ebitda, beta, peg, growth_5y}} or {} on failure.
    Graceful degradation: missing files or parse failures return {} without crashing.
    """
    try:
        pe_df   = _fetch_excel("pedata.xls")
        ev_df   = _fetch_excel("vebitda.xls")
        beta_df = _fetch_excel("betas.xls")

        if pe_df is None and ev_df is None:
            return {}

        result: dict = {}

        # ── P/E + PEG + 5-year growth ─────────────────────────────────────────
        if pe_df is not None:
            ind_col = _find_industry_col(pe_df)
            if ind_col:
                pe_df = pe_df.dropna(subset=[ind_col])
                for _, row in pe_df.iterrows():
                    name = str(row[ind_col]).strip()
                    if not name or name.lower() in ("industry name", "nan"):
                        continue
                    result[name.lower()] = {
                        "name":      name,
                        "pe":        _safe_float(row.get("Current PE")),
                        "peg":       _safe_float(row.get("PEG Ratio")),
                        "growth_5y": _safe_float(row.get("Expected growth - next 5 years")),
                        "ev_ebitda": None,
                        "beta":      None,
                    }

        # ── EV/EBITDA ─────────────────────────────────────────────────────────
        if ev_df is not None:
            ind_col = _find_industry_col(ev_df)
            if ind_col:
                ev_df = ev_df.dropna(subset=[ind_col])
                for _, row in ev_df.iterrows():
                    name = str(row[ind_col]).strip()
                    if not name:
                        continue
                    key    = name.lower()
                    ev_val = _safe_float(row.get("EV/EBITDA"))
                    if key in result:
                        result[key]["ev_ebitda"] = ev_val
                    else:
                        result[key] = {
                            "name": name, "pe": None, "peg": None,
                            "growth_5y": None, "ev_ebitda": ev_val, "beta": None,
                        }

        # ── Beta ──────────────────────────────────────────────────────────────
        if beta_df is not None:
            ind_col = _find_industry_col(beta_df)
            if ind_col:
                beta_df = beta_df.dropna(subset=[ind_col])
                for _, row in beta_df.iterrows():
                    name = str(row[ind_col]).strip()
                    if not name:
                        continue
                    key   = name.lower()
                    b_val = _safe_float(row.get("Beta"))
                    if key in result:
                        result[key]["beta"] = b_val
                    else:
                        result[key] = {
                            "name": name, "pe": None, "peg": None,
                            "growth_5y": None, "ev_ebitda": None, "beta": b_val,
                        }

        return result
    except Exception:
        return {}


def get_sector_benchmarks(ticker: str) -> dict:
    """
    Map a portfolio ticker to its Damodaran sector row.

    Returns dict with keys: name, pe, ev_ebitda, beta, peg, growth_5y.
    Returns {} if ticker is an ETF or no sector data is available.
    """
    if ticker in PORTFOLIO_ETFS:
        return {}

    sector_data = get_damodaran_sector_data()
    if not sector_data:
        return {}

    keywords = list(_TICKER_KEYWORDS.get(ticker, []))
    if not keywords:
        # Derive keywords from static TICKER_SECTOR config as fallback
        broad, specific = TICKER_SECTOR.get(ticker, ("", ""))
        keywords = [w.lower() for w in (specific + " " + broad).split() if len(w) > 3]

    ind_keys = list(sector_data.keys())
    for kw in keywords:
        for ind_key in ind_keys:
            if kw in ind_key:
                return sector_data[ind_key]

    # Fallback: "total market" aggregate row
    for ind_key in ind_keys:
        if "total market" in ind_key:
            return sector_data[ind_key]

    return {}
