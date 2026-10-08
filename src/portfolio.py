"""Portfolio persistence — multi-lot model.

Each ticker can have multiple lots (separate buy events):
  portfolio["layers"]["Layer Name"] = [
      {"ticker": "AMD", "shares": 5.0, "buy_date": "2025-01-15"},
      {"ticker": "AMD", "shares": 3.0, "buy_date": "2025-03-01"},
  ]
"""

from datetime import date
import json
import os
import shutil

import requests

from src.config import PORTFOLIO_FILE, TICKERS_BY_LAYER
from src.logger import get_logger

_log = get_logger(__name__)


# ── Default portfolio (0 shares, today as buy_date) ───────────────────────────
def _build_defaults():
    layers = {}
    today_str = str(date.today())
    for layer, tickers in TICKERS_BY_LAYER.items():
        layers[layer] = [
            {"ticker": t, "shares": 0.0, "buy_date": today_str}
            for t in tickers
        ]
    return {"layers": layers, "settings": {"email_recipients": [], "auto_alert": False}}


# ── Session-state helpers (no-op outside a Streamlit run) ─────────────────────
def _ss_get(key, default=None):
    try:
        import streamlit as st
        return st.session_state.get(key, default)
    except Exception:
        return default


def _ss_set(key, value):
    try:
        import streamlit as st
        st.session_state[key] = value
    except Exception:
        pass


def _clean_layers(data):
    """Validate a loaded portfolio dict and drop empty layers. Raises on bad shape."""
    if not isinstance(data, dict) or not isinstance(data.get("layers"), dict):
        raise ValueError("portfolio JSON has no 'layers' dict")
    data["layers"] = {k: v for k, v in data["layers"].items() if v}
    return data


# ── GitHub Gist storage (cloud persistence) ───────────────────────────────────
def _get_gist_config():
    """Return (gist_id, token) from st.secrets, or (None, None) if not configured."""
    try:
        import streamlit as st
        gist_id = str(st.secrets.get("GIST_ID") or "").strip()
        token   = str(st.secrets.get("GITHUB_TOKEN") or "").strip()
        if gist_id and token:
            return gist_id, token
    except Exception:
        pass
    return None, None


def _gist_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


def _load_from_gist(gist_id, token):
    """Fetch portfolio JSON from a GitHub Gist.

    Returns the portfolio dict, or None when the Gist has no portfolio.json yet
    (a genuinely new setup). Raises on network / auth / parse errors so the
    caller can block saves instead of overwriting real data with defaults.
    """
    resp = requests.get(
        f"https://api.github.com/gists/{gist_id}",
        headers=_gist_headers(token),
        timeout=10,
    )
    resp.raise_for_status()
    content = resp.json()["files"].get("portfolio.json", {}).get("content", "")
    if not content:
        return None
    return _clean_layers(json.loads(content))


def _save_to_gist(portfolio, gist_id, token):
    """Write portfolio JSON to a GitHub Gist. Returns True on success."""
    try:
        resp = requests.patch(
            f"https://api.github.com/gists/{gist_id}",
            headers=_gist_headers(token),
            json={
                "files": {
                    "portfolio.json": {
                        "content": json.dumps(portfolio, indent=2, ensure_ascii=False)
                    }
                }
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception:
        _log.error("Failed to save portfolio to Gist", exc_info=True)
        return False


def _load_from_file():
    """Load portfolio.json. Returns None if missing; raises if unreadable/corrupt.

    A corrupt file is copied to portfolio.json.bak before raising so it can be
    recovered by hand.
    """
    if not PORTFOLIO_FILE.exists():
        return None
    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            return _clean_layers(json.load(f))
    except Exception:
        backup = PORTFOLIO_FILE.with_name(PORTFOLIO_FILE.name + ".bak")
        try:
            shutil.copy2(PORTFOLIO_FILE, backup)
        except Exception:
            _log.error("Could not back up corrupt portfolio file", exc_info=True)
        raise


# ── Load / Save ───────────────────────────────────────────────────────────────
def portfolio_load_failed():
    """True when this session's portfolio failed to load — saves are blocked."""
    return bool(_ss_get("_portfolio_load_failed", False))


def reload_portfolio():
    """Drop the session cache so the next load_portfolio() re-reads storage."""
    _ss_set("_portfolio_cache", None)
    _ss_set("_portfolio_load_failed", False)


def load_portfolio():
    """Load portfolio from Gist (cloud) or local file; cache in session state.

    On a read failure the defaults are shown but the session is marked
    load-failed, so save_portfolio() refuses to overwrite the real data.
    """
    # Session-state cache: avoid a Gist round-trip on every Streamlit rerun
    cached = _ss_get("_portfolio_cache")
    if cached is not None:
        return cached

    data, failed = None, False
    gist_id, token = _get_gist_config()
    if gist_id:
        _log.info("load_portfolio from Gist", extra={"gist_id": gist_id[:8]})
        try:
            data = _load_from_gist(gist_id, token)
        except Exception:
            _log.error("Failed to load portfolio from Gist", exc_info=True)
            failed = True
    else:
        _log.info("load_portfolio from file", extra={"file": str(PORTFOLIO_FILE)})
        try:
            data = _load_from_file()
        except Exception:
            _log.error("Failed to load portfolio.json; saves blocked",
                       exc_info=True, extra={"file": str(PORTFOLIO_FILE)})
            failed = True

    if data is None:
        data = _build_defaults()

    _ss_set("_portfolio_load_failed", failed)
    _ss_set("_portfolio_cache", data)
    return data


def save_portfolio(portfolio):
    """Persist portfolio to Gist (if configured) and local file.

    Returns True when the data was persisted somewhere. Refuses to write when
    the session's load failed (would replace real data with defaults).
    """
    if portfolio_load_failed():
        _log.warning("save_portfolio blocked: portfolio failed to load this session")
        _ss_set("_portfolio_save_error", "blocked")
        return False

    # Update cache immediately so the next rerun returns the new state
    _ss_set("_portfolio_cache", portfolio)
    _ss_set("_portfolio_save_error", None)

    gist_id, token = _get_gist_config()
    if gist_id:
        _log.info("save_portfolio to Gist", extra={"gist_id": gist_id[:8]})
        if not _save_to_gist(portfolio, gist_id, token):
            _ss_set("_portfolio_save_error", "gist")

    # Also write locally — fallback when the Gist is unreachable; no-op on
    # Streamlit Cloud's ephemeral FS
    PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp = PORTFOLIO_FILE.with_name(PORTFOLIO_FILE.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(portfolio, f, indent=2, ensure_ascii=False)
        os.replace(tmp, PORTFOLIO_FILE)
    except Exception:
        _log.warning("Local file write skipped (expected on Streamlit Cloud)")
    return True


# ── Ticker helpers ────────────────────────────────────────────────────────────
def all_tickers(portfolio):
    """Return sorted unique list of all tickers across all layers."""
    return sorted({
        lot["ticker"]
        for lots in portfolio["layers"].values()
        for lot in lots
    })


def held_tickers(portfolio):
    """Sorted tickers with at least one lot holding shares > 0."""
    return sorted({
        lot["ticker"]
        for lots in portfolio["layers"].values()
        for lot in lots
        if float(lot.get("shares") or 0) > 0
    })


def get_starred(portfolio):
    """Watch-only tickers the user starred for full data + AI coverage."""
    return list(portfolio.get("settings", {}).get("starred", []))


def set_starred(portfolio, ticker, starred):
    """Star / unstar a ticker and persist."""
    current = set(get_starred(portfolio))
    if starred:
        current.add(ticker)
    else:
        current.discard(ticker)
    portfolio.setdefault("settings", {})["starred"] = sorted(current)
    save_portfolio(portfolio)


def set_starred_list(portfolio, tickers):
    """Replace the starred list and persist."""
    portfolio.setdefault("settings", {})["starred"] = sorted(set(tickers))
    save_portfolio(portfolio)


def active_tickers(portfolio):
    """Tickers that get analyst/fundamental/news fetches and AI: held ∪ starred.

    Every other watch-only ticker is 'archive' tier — price data only, AI on click.
    """
    universe = set(all_tickers(portfolio))
    return sorted(set(held_tickers(portfolio)) | (set(get_starred(portfolio)) & universe))


def lots_for_ticker(portfolio, ticker):
    """Return list of (layer, lot) for all lots of a given ticker."""
    result = []
    for layer, lots in portfolio["layers"].items():
        for lot in lots:
            if lot["ticker"] == ticker:
                result.append((layer, lot))
    return result


def get_layer_for_ticker(portfolio, ticker):
    """Return the layer name that contains ticker (first match)."""
    for layer, lots in portfolio["layers"].items():
        for lot in lots:
            if lot["ticker"] == ticker:
                return layer
    return None


# ── Trade history ─────────────────────────────────────────────────────────────

def get_trade_history(portfolio):
    """Return the trade history list (all buy and sell events)."""
    return portfolio.setdefault("trade_history", [])


def _append_trade(portfolio, entry):
    """Prepend a trade entry to trade_history (most-recent first). Does NOT save."""
    portfolio.setdefault("trade_history", []).insert(0, entry)


def closed_trade_pnl(buy_price, sell_price, shares, fees=0.0):
    """Net P&L of a long round trip: (sell − buy) × shares − fees."""
    return round((float(sell_price) - float(buy_price)) * float(shares) - float(fees or 0), 2)


def find_closed_trade(portfolio, ticker, buy_date, sell_date):
    """Return the trade_history sell entry for (ticker, buy_date, sell_date), or None."""
    ticker = ticker.upper().strip()
    for entry in portfolio.get("trade_history", []):
        if (entry.get("action") == "sell"
                and entry.get("ticker", "").upper() == ticker
                and entry.get("buy_date", "") == str(buy_date)
                and entry.get("date", "") == str(sell_date)):
            return entry
    return None


def add_closed_trade(portfolio, ticker, shares, buy_price, buy_date,
                     sell_price, sell_date, layer, fees=0.0, setup_type=None, note=""):
    """Manually record a completed buy→sell pair (for backfilling history).

    fees reduce P&L; setup_type feeds the journal's by-setup breakdown.
    """
    ticker = ticker.upper().strip()
    entry = {
        "action":    "sell",
        "ticker":    ticker,
        "shares":    round(float(shares), 4),
        "price":     round(float(sell_price), 4),
        "date":      str(sell_date),
        "layer":     layer,
        "buy_price": round(float(buy_price), 4),
        "buy_date":  str(buy_date),
        "pnl":       closed_trade_pnl(buy_price, sell_price, shares, fees),
        "source":    "manual",
    }
    if fees:
        entry["fees"] = round(float(fees), 2)
    if setup_type:
        entry["setup_type"] = setup_type
    if note and note.strip():
        entry["note"] = note.strip()
    _append_trade(portfolio, entry)
    save_portfolio(portfolio)
    return portfolio


def remove_closed_trade(portfolio, ticker, buy_date, sell_date):
    """Delete one recorded sell (closed trade). Returns True if something was removed."""
    entry = find_closed_trade(portfolio, ticker, buy_date, sell_date)
    if entry is None:
        return False
    portfolio["trade_history"].remove(entry)
    save_portfolio(portfolio)
    return True


def close_lot(portfolio, layer, ticker, buy_date, sell_date, sell_price):
    """Record a sell event and remove the lot — single save operation."""
    ticker = ticker.upper().strip()
    lots = portfolio["layers"].get(layer, [])
    lot = next(
        (x for x in lots if x["ticker"] == ticker and x["buy_date"] == str(buy_date)),
        None,
    )
    if lot and float(lot.get("shares") or 0) > 0:
        shares    = float(lot["shares"])
        buy_price = lot.get("buy_price")
        pnl = (
            round((float(sell_price) - float(buy_price)) * shares, 2)
            if (buy_price and sell_price) else None
        )
        _append_trade(portfolio, {
            "action":    "sell",
            "ticker":    ticker,
            "shares":    round(shares, 4),
            "price":     round(float(sell_price), 4) if sell_price else None,
            "date":      str(sell_date),
            "layer":     layer,
            "buy_price": round(float(buy_price), 4) if buy_price else None,
            "buy_date":  str(buy_date),
            "pnl":       pnl,
        })
    portfolio["layers"][layer] = [
        x for x in lots
        if not (x["ticker"] == ticker and x["buy_date"] == str(buy_date))
    ]
    if not portfolio["layers"][layer] and len(portfolio["layers"]) > 1:
        del portfolio["layers"][layer]
    save_portfolio(portfolio)
    _log.debug("close_lot", extra={"ticker": ticker, "layer": layer, "buy_date": str(buy_date),
                                  "sell_date": str(sell_date), "sell_price": sell_price})
    return portfolio


def close_ticker(portfolio, ticker, sell_date, sell_price):
    """Record sells for all lots of ticker and remove them — single save."""
    ticker = ticker.upper().strip()
    for layer in list(portfolio["layers"].keys()):
        for lot in list(portfolio["layers"][layer]):
            if lot["ticker"] != ticker:
                continue
            shares = float(lot.get("shares") or 0)
            if shares <= 0:
                continue
            buy_price = lot.get("buy_price")
            pnl = (
                round((float(sell_price) - float(buy_price)) * shares, 2)
                if (buy_price and sell_price) else None
            )
            _append_trade(portfolio, {
                "action":    "sell",
                "ticker":    ticker,
                "shares":    round(shares, 4),
                "price":     round(float(sell_price), 4) if sell_price else None,
                "date":      str(sell_date),
                "layer":     layer,
                "buy_price": round(float(buy_price), 4) if buy_price else None,
                "buy_date":  lot.get("buy_date"),
                "pnl":       pnl,
            })
        portfolio["layers"][layer] = [
            x for x in portfolio["layers"][layer] if x["ticker"] != ticker
        ]
        if not portfolio["layers"][layer] and len(portfolio["layers"]) > 1:
            del portfolio["layers"][layer]
    save_portfolio(portfolio)
    _log.debug("close_ticker", extra={"ticker": ticker, "sell_date": str(sell_date),
                                     "sell_price": sell_price})
    return portfolio


# ── Mutations ─────────────────────────────────────────────────────────────────
def add_lot(portfolio, layer, ticker, shares, buy_date, buy_price=None):
    """Add a new buy lot. Creates layer if it doesn't exist."""
    ticker = ticker.upper().strip()
    _log.debug("add_lot", extra={"ticker": ticker, "layer": layer, "shares": shares,
                                "buy_date": str(buy_date), "buy_price": buy_price})
    if layer not in portfolio["layers"]:
        portfolio["layers"][layer] = []
    lot = {
        "ticker":   ticker,
        "shares":   float(shares),
        "buy_date": str(buy_date),
    }
    if buy_price is not None and float(buy_price) > 0:
        lot["buy_price"] = round(float(buy_price), 4)
    portfolio["layers"][layer].append(lot)
    # Record buy in trade history (skip watch-only 0-share additions)
    if float(shares) > 0:
        _append_trade(portfolio, {
            "action": "buy",
            "ticker": ticker,
            "shares": round(float(shares), 4),
            "price":  round(float(buy_price), 4) if buy_price else None,
            "date":   str(buy_date),
            "layer":  layer,
        })
    save_portfolio(portfolio)
    return portfolio


def update_lot(portfolio, layer, ticker, old_date, new_shares, new_date, buy_price=None):
    """Replace an existing lot identified by (ticker, old_date) in layer."""
    ticker = ticker.upper().strip()
    _log.debug("update_lot", extra={"ticker": ticker, "layer": layer, "old_date": str(old_date),
                                   "new_shares": new_shares, "new_date": str(new_date),
                                   "buy_price": buy_price})
    lots = portfolio["layers"].get(layer, [])
    for lot in lots:
        if lot["ticker"] == ticker and lot["buy_date"] == str(old_date):
            lot["shares"]   = float(new_shares)
            lot["buy_date"] = str(new_date)
            if buy_price is not None and float(buy_price) > 0:
                lot["buy_price"] = round(float(buy_price), 4)
            break
    save_portfolio(portfolio)
    return portfolio


def remove_lot(portfolio, layer, ticker, buy_date):
    """Remove one specific lot by (ticker, buy_date) from layer."""
    ticker = ticker.upper().strip()
    _log.debug("remove_lot", extra={"ticker": ticker, "layer": layer, "buy_date": str(buy_date)})
    lots = portfolio["layers"].get(layer, [])
    portfolio["layers"][layer] = [
        lot for lot in lots
        if not (lot["ticker"] == ticker and lot["buy_date"] == str(buy_date))
    ]
    # Clean up empty layers (but keep at least one layer)
    if not portfolio["layers"][layer] and len(portfolio["layers"]) > 1:
        del portfolio["layers"][layer]
    save_portfolio(portfolio)
    return portfolio


# ── Email settings ────────────────────────────────────────────────────────────

def get_email_settings(portfolio):
    """Return {'email_recipients': [...], 'auto_alert': bool}."""
    return portfolio.setdefault("settings", {"email_recipients": [], "auto_alert": False})


def set_email_recipients(portfolio, emails):
    """Persist a new email-recipients list."""
    portfolio.setdefault("settings", {})["email_recipients"] = list(emails)
    save_portfolio(portfolio)


def set_auto_alert(portfolio, enabled: bool):
    """Persist the auto-alert toggle."""
    portfolio.setdefault("settings", {})["auto_alert"] = bool(enabled)
    save_portfolio(portfolio)


def get_alerts(portfolio):
    """Return the alerts dict {ticker: {stop_loss, trailing_stop_pct, price_alerts}}."""
    return portfolio.setdefault("alerts", {})


def set_ticker_alerts(portfolio, ticker, stop_loss, trailing_stop_pct, price_alerts):
    """Persist stop-loss / trailing-stop / price-alerts for a ticker."""
    portfolio.setdefault("alerts", {})[ticker] = {
        "stop_loss":         stop_loss,
        "trailing_stop_pct": trailing_stop_pct,
        "price_alerts":      list(price_alerts),
    }
    save_portfolio(portfolio)


def remove_ticker_alerts(portfolio, ticker):
    """Remove all alert settings for a ticker."""
    portfolio.get("alerts", {}).pop(ticker, None)
    save_portfolio(portfolio)


def remove_ticker(portfolio, ticker):
    """Remove ALL lots for ticker across all layers."""
    ticker = ticker.upper().strip()
    for layer in list(portfolio["layers"].keys()):
        portfolio["layers"][layer] = [
            lot for lot in portfolio["layers"][layer]
            if lot["ticker"] != ticker
        ]
        if not portfolio["layers"][layer] and len(portfolio["layers"]) > 1:
            del portfolio["layers"][layer]
    save_portfolio(portfolio)
    return portfolio
