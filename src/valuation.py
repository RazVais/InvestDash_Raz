"""Portfolio valuation — the single place that turns lots × prices into money.

TASE securities (numeric IDs, or any price entry with currency='ILS') are priced
in NIS. Every USD total in the app must go through compute_holdings() so NIS is
converted with the ILS→USD rate instead of being added to dollars as-is.

Two totals are returned on purpose:
  * cost_usd / value_usd   — P&L basis: only lots whose buy price is known, so
                             cost and value always cover the same shares.
  * market_value_usd       — every priced lot; use for allocation weights,
                             stress tests and "how big is the portfolio".
"""

from typing import Dict, Optional

from src.config import ILS_USD_FALLBACK, is_tase_numeric
from src.data.prices import lookup_buy_price
from src.portfolio import all_tickers, lots_for_ticker


def is_ils(ticker, price_entry) -> bool:
    """True when the ticker is quoted in NIS."""
    if is_tase_numeric(ticker):
        return True
    return bool(price_entry) and price_entry.get("currency") == "ILS"


def lot_buy_price(ticker, lot, prices) -> Optional[float]:
    """Stored lot buy_price wins; otherwise the historical close on buy_date."""
    bp = lot.get("buy_price")
    if bp:
        return float(bp)
    bp = lookup_buy_price(ticker, lot.get("buy_date", ""), prices)
    return float(bp) if bp else None


def compute_holdings(portfolio, prices, ils_usd=None) -> Dict:
    """Value every held lot in native currency and USD.

    Returns:
        {
          "tickers": {t: {layer, shares, currency, price, fx,
                          cost_native, value_native,        # P&L basis
                          cost_usd, value_usd,              # P&L basis
                          market_value_usd}},               # all priced shares
          "layers":  {layer: market_value_usd},
          "cost_usd", "value_usd", "market_value_usd",
          "ils_usd": rate used,
        }
    Watch-only (0-share) lots and tickers without a price are skipped.
    """
    rate = float(ils_usd) if ils_usd else ILS_USD_FALLBACK
    prices = prices or {}
    out = {"tickers": {}, "layers": {}, "cost_usd": 0.0, "value_usd": 0.0,
           "market_value_usd": 0.0, "ils_usd": rate}

    for t in all_tickers(portfolio):
        p = prices.get(t)
        if not p or not p.get("price"):
            continue
        price = float(p["price"])
        ils   = is_ils(t, p)
        fx    = rate if ils else 1.0
        row = {"layer": None, "shares": 0.0, "currency": "ILS" if ils else "USD",
               "price": price, "fx": fx, "cost_native": 0.0, "value_native": 0.0,
               "cost_usd": 0.0, "value_usd": 0.0, "market_value_usd": 0.0}

        for layer, lot in lots_for_ticker(portfolio, t):
            shares = float(lot.get("shares") or 0)
            if shares <= 0:
                continue
            row["layer"] = row["layer"] or layer
            row["shares"] += shares
            mv_usd = shares * price * fx
            row["market_value_usd"] += mv_usd
            out["layers"][layer] = out["layers"].get(layer, 0.0) + mv_usd

            bp = lot_buy_price(t, lot, prices)
            if bp:
                row["cost_native"]  += shares * bp
                row["value_native"] += shares * price

        if row["shares"] <= 0:
            continue
        row["cost_usd"]  = row["cost_native"] * fx
        row["value_usd"] = row["value_native"] * fx
        out["tickers"][t] = row
        out["cost_usd"]         += row["cost_usd"]
        out["value_usd"]        += row["value_usd"]
        out["market_value_usd"] += row["market_value_usd"]

    return out
