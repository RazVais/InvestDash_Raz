"""Portfolio persistence — multi-lot model.

Each ticker can have multiple lots (separate buy events):
  portfolio["layers"]["Layer Name"] = [
      {"ticker": "AMD", "shares": 5.0, "buy_date": "2025-01-15"},
      {"ticker": "AMD", "shares": 3.0, "buy_date": "2025-03-01"},
  ]
"""

from datetime import date
import json

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


# ── Load / Save ───────────────────────────────────────────────────────────────
def load_portfolio():
    """Load portfolio.json; create from defaults if missing."""
    _log.info("load_portfolio", extra={"file": str(PORTFOLIO_FILE)})
    if PORTFOLIO_FILE.exists():
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Remove empty layers
            data["layers"] = {
                k: v for k, v in data["layers"].items() if v
            }
            return data
        except Exception:
            _log.error("Failed to load portfolio.json; falling back to defaults", exc_info=True, extra={"file": str(PORTFOLIO_FILE)})
    return _build_defaults()


def save_portfolio(portfolio):
    _log.info("save_portfolio", extra={"file": str(PORTFOLIO_FILE)})
    PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(portfolio, f, indent=2, ensure_ascii=False)
    except Exception:
        _log.error("Failed to save portfolio.json", exc_info=True, extra={"file": str(PORTFOLIO_FILE)})


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
