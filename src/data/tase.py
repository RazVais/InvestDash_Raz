"""TASE (Tel Aviv Stock Exchange) market data fetcher via pymaya.

Handles two distinct security types with different field structures:

  ETF / Stock  — exchange-traded, intraday prices:
    get_details:      LastRate (agorot), BaseRate, Change
    get_price_history: CloseRate, OpenRate, HighRate, LowRate (agorot), TradeDate DD/MM/YYYY

  Mutual Fund (קרן נאמנות) — NAV-priced, no intraday trading:
    get_details:      SellPrice / PurchasePrice / CreationPrice (NIS, not agorot)
    get_price_history: SellPrice / PurchasePrice (NIS), TradeDate ISO format

Price normalisation rule:
  raw >= 1000  →  agorot  →  divide by 100 to get NIS
  raw < 1000   →  already NIS

pymaya sessions are per-thread (threading.local) so this is safe inside ThreadPoolExecutor.
"""

import threading
from datetime import date, timedelta

import pandas as pd

from src.logger import get_logger

_log = get_logger(__name__)

_local = threading.local()
_AGOROT = 100.0


def _maya():
    """Return a per-thread Maya() session (lazy-created)."""
    if not hasattr(_local, "session"):
        from pymaya.maya import Maya
        _local.session = Maya()
    return _local.session


def _to_nis(raw):
    """Convert a raw TASE price to NIS using the agorot heuristic."""
    if raw is None:
        return None
    raw = float(raw)
    return raw / _AGOROT if raw >= 1000 else raw


def _parse_tase_date(raw):
    """Parse a TASE date string — supports DD/MM/YYYY (ETF) and ISO (mutual fund)."""
    if not raw:
        return None
    try:
        return pd.to_datetime(raw, format="%d/%m/%Y")
    except Exception:
        try:
            return pd.to_datetime(raw)  # ISO 8601 fallback
        except Exception:
            return None


# ── Current quote ─────────────────────────────────────────────────────────────

def fetch_tase_current(security_id: str):
    """Fetch live/latest quote for a TASE numeric security.

    Works for exchange-traded ETFs/stocks (LastRate) and mutual funds
    (SellPrice / PurchasePrice / CreationPrice).

    Returns a dict with:
        price      — last / NAV price in NIS
        change_pct — daily % change (0 if not available)
        prev_close — previous close in NIS
        name       — human-readable security name
    or None on failure.
    """
    try:
        d = _maya().get_details(security_id)

        # ── Price (ETF: LastRate in agorot; Fund: SellPrice in NIS) ──────────
        raw = (
            d.get("LastRate")
            or d.get("SellPrice")
            or d.get("PurchasePrice")
            or d.get("CreationPrice")
        )
        if raw is None:
            _log.warning("TASE: no price field found", extra={"security_id": security_id})
            return None

        price = _to_nis(raw)

        # ── Previous close ────────────────────────────────────────────────────
        base_raw = d.get("BaseRate") or raw
        prev_close = _to_nis(base_raw)

        # ── Daily change % ────────────────────────────────────────────────────
        change_pct = float(d.get("Change") or d.get("Rate") or 0.0)

        # ── Name (ETFs have Name; mutual funds only have ManagerShortName) ────
        name = (
            d.get("Name")
            or d.get("CompanyName")
            or d.get("ManagerShortName")
            or ""
        )

        _log.info("TASE fetch_current OK", extra={
            "security_id": security_id, "price_nis": round(price, 2), "sec_name": name,
        })
        return {
            "price":      price,
            "change_pct": change_pct,
            "prev_close": prev_close,
            "name":       name,
        }
    except Exception:
        _log.error("TASE fetch_current failed", exc_info=True,
                   extra={"security_id": security_id})
        return None


# ── Historical OHLCV ──────────────────────────────────────────────────────────

def fetch_tase_history(security_id: str, days: int = 365):
    """Fetch historical daily prices for a TASE numeric security.

    Works for both ETFs (CloseRate/OpenRate/HighRate/LowRate) and
    mutual funds (SellPrice/PurchasePrice as Close/Open, no High/Low).

    Returns a DataFrame with Open/High/Low/Close/Volume (prices in NIS)
    and a timezone-naive DatetimeIndex, or None on failure.
    """
    try:
        end   = date.today()
        start = end - timedelta(days=days + 60)
        rows  = list(_maya().get_price_history(security_id, start, end))
        if not rows:
            return None

        records = []
        for r in rows:
            try:
                dt = _parse_tase_date(r.get("TradeDate"))
                if dt is None:
                    continue

                # ── ETF / stock fields ────────────────────────────────────────
                close_raw = r.get("CloseRate")
                if close_raw is not None:
                    close  = _to_nis(close_raw)
                    open_  = _to_nis(r.get("OpenRate") or close_raw)
                    high   = _to_nis(r.get("HighRate")  or close_raw)
                    low    = _to_nis(r.get("LowRate")   or close_raw)
                    volume = r.get("OverallTurnOverUnits") or 0

                # ── Mutual fund fields ────────────────────────────────────────
                else:
                    nav_raw = (
                        r.get("SellPrice")
                        or r.get("PurchasePrice")
                        or r.get("CreationPrice")
                    )
                    if nav_raw is None:
                        continue
                    close  = _to_nis(nav_raw)
                    open_  = _to_nis(r.get("PurchasePrice") or nav_raw)
                    high   = close
                    low    = close
                    volume = 0

                if close is None:
                    continue

                records.append({
                    "Date":   dt,
                    "Open":   open_,
                    "High":   high,
                    "Low":    low,
                    "Close":  close,
                    "Volume": volume,
                })
            except Exception:
                continue

        if not records:
            return None

        df = (
            pd.DataFrame(records)
            .set_index("Date")
            .sort_index()
            .dropna(subset=["Close"])
        )
        return df if not df.empty else None

    except Exception:
        _log.error("TASE fetch_history failed", exc_info=True,
                   extra={"security_id": security_id})
        return None
