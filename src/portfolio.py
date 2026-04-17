"""Portfolio persistence — multi-lot model.

Each ticker can have multiple lots (separate buy events):
  portfolio["layers"]["Layer Name"] = [
      {"ticker": "AMD", "shares": 5.0, "buy_date": "2025-01-15"},
      {"ticker": "AMD", "shares": 3.0, "buy_date": "2025-03-01"},
  ]
"""

from datetime import date
import json

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


def _load_from_gist(gist_id, token):
    """Fetch portfolio JSON from a GitHub Gist. Returns defaults on any error."""
    try:
        resp = requests.get(
            f"https://api.github.com/gists/{gist_id}",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=10,
        )
        resp.raise_for_status()
        content = resp.json()["files"].get("portfolio.json", {}).get("content", "")
        if content:
            data = json.loads(content)
            data["layers"] = {k: v for k, v in data["layers"].items() if v}
            return data
    except Exception:
        _log.error("Failed to load portfolio from Gist", exc_info=True)
    return _build_defaults()


def _save_to_gist(portfolio, gist_id, token):
    """Write portfolio JSON to a GitHub Gist."""
    try:
        requests.patch(
            f"https://api.github.com/gists/{gist_id}",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={
                "files": {
                    "portfolio.json": {
                        "content": json.dumps(portfolio, indent=2, ensure_ascii=False)
                    }
                }
            },
            timeout=10,
        )
    except Exception:
        _log.error("Failed to save portfolio to Gist", exc_info=True)


# ── Load / Save ───────────────────────────────────────────────────────────────
def load_portfolio():
    """Load portfolio from Gist (cloud) or local file; cache in session state."""
    # Session-state cache: avoid a Gist round-trip on every Streamlit rerun
    try:
        import streamlit as st
        cached = st.session_state.get("_portfolio_cache")
        if cached is not None:
            return cached
    except Exception:
        pass

    gist_id, token = _get_gist_config()
    if gist_id:
        _log.info("load_portfolio from Gist", extra={"gist_id": gist_id[:8]})
        data = _load_from_gist(gist_id, token)
    elif PORTFOLIO_FILE.exists():
        _log.info("load_portfolio from file", extra={"file": str(PORTFOLIO_FILE)})
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["layers"] = {k: v for k, v in data["layers"].items() if v}
        except Exception:
            _log.error("Failed to load portfolio.json; falling back to defaults",
                       exc_info=True, extra={"file": str(PORTFOLIO_FILE)})
            data = _build_defaults()
    else:
        data = _build_defaults()

    try:
        import streamlit as st
        st.session_state["_portfolio_cache"] = data
    except Exception:
        pass

    return data


def save_portfolio(portfolio):
    """Persist portfolio to Gist (if configured) and local file."""
    # Update cache immediately so the next rerun returns the new state
    try:
        import streamlit as st
        st.session_state["_portfolio_cache"] = portfolio
    except Exception:
        pass

    gist_id, token = _get_gist_config()
    if gist_id:
        _log.info("save_portfolio to Gist", extra={"gist_id": gist_id[:8]})
        _save_to_gist(portfolio, gist_id, token)

    # Also write locally — no-op on Streamlit Cloud's ephemeral FS, useful locally
    _log.info("save_portfolio to file", extra={"file": str(PORTFOLIO_FILE)})
    PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(portfolio, f, indent=2, ensure_ascii=False)
    except Exception:
        _log.warning("Local file write skipped (expected on Streamlit Cloud)")


# ── Ticker helpers ────────────────────────────────────────────────────────────
def all_tickers(portfolio):
    """Return sorted unique list of all tickers across all layers."""
    return sorted({
        lot["ticker"]
        for lots in portfolio["layers"].values()
        for lot in lots
    })


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


# ── Mutations ─────────────────────────────────────────────────────────────────
def add_lot(portfolio, layer, ticker, shares, buy_date, buy_price=None):
    """Add a new buy lot. Creates layer if it doesn't exist."""
    ticker = ticker.upper().strip()
    _log.info("add_lot", extra={"ticker": ticker, "layer": layer, "shares": shares,
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
    save_portfolio(portfolio)
    return portfolio


def update_lot(portfolio, layer, ticker, old_date, new_shares, new_date, buy_price=None):
    """Replace an existing lot identified by (ticker, old_date) in layer."""
    ticker = ticker.upper().strip()
    _log.info("update_lot", extra={"ticker": ticker, "layer": layer, "old_date": str(old_date),
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
    _log.info("remove_lot", extra={"ticker": ticker, "layer": layer, "buy_date": str(buy_date)})
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
