"""Portfolio history, target allocation and position sizing — pure logic, no Streamlit.

Daily snapshots live in portfolio["snapshots"] (saved with the portfolio, so they
work with the Gist backend too). One row per trading day:
    {"date": "YYYY-MM-DD", "value_usd", "cost_usd", "voo_close",
     "shares": {ticker: n}, "px": {ticker: usd price}, "by_layer": {layer: usd},
     "provisional": bool, "reconstructed": bool}
"provisional" rows were written while the market was open and are replaced by
the closing value on the first load after the close.

Returns are time-weighted. The cash flow between two snapshots is
Σ (shares_t − shares_{t−1}) × px_t — exact for buys and sells — so adding or
selling shares is never counted as performance.
"""

import math
import re
from typing import Dict, List, Optional

import pandas as pd

from src.valuation import compute_holdings

# ── Snapshots ─────────────────────────────────────────────────────────────────

def snapshot_row(portfolio, data, td_str, provisional) -> Optional[Dict]:
    """Build today's snapshot row, or None if the price data is incomplete."""
    prices   = data.get("prices") or {}
    holdings = compute_holdings(portfolio, prices, data.get("ils_usd"))
    held = {lot["ticker"] for lots in portfolio["layers"].values() for lot in lots
            if float(lot.get("shares") or 0) > 0}
    if not held or any(t not in holdings["tickers"] for t in held):
        return None  # a missing price would record a fake drop
    voo = prices.get("VOO") or {}
    tick = holdings["tickers"]
    return {
        "date":        td_str,
        "value_usd":   round(holdings["market_value_usd"], 2),
        "cost_usd":    round(holdings["cost_usd"], 2),
        "voo_close":   round(float(voo["price"]), 4) if voo.get("price") else None,
        "shares":      {t: round(r["shares"], 6) for t, r in tick.items()},
        "px":          {t: round(r["price"] * r["fx"], 6) for t, r in tick.items()},
        "by_layer":    {k: round(v, 2) for k, v in holdings["layers"].items()},
        "provisional": bool(provisional),
    }


def upsert_snapshot(snapshots: List[Dict], row: Dict) -> bool:
    """Insert/replace today's row. Returns True if the list changed (caller saves).

    Final rows are never overwritten; a provisional row is replaced by a final one
    (or refreshed by a newer provisional value only if it moved > 0.5%).
    """
    for i, existing in enumerate(snapshots):
        if existing.get("date") != row["date"]:
            continue
        if not existing.get("provisional") and not existing.get("reconstructed"):
            return False
        if row["provisional"] and existing.get("provisional"):
            prev = existing.get("value_usd") or 0
            if prev and abs(row["value_usd"] - prev) / prev < 0.005:
                return False
        snapshots[i] = row
        return True
    snapshots.append(row)
    snapshots.sort(key=lambda r: r["date"])
    return True


def reconstruct_history(portfolio, data, days=252) -> List[Dict]:
    """Approximate past daily values from today's lots × price history.

    Lots count from their buy date; closed positions and old FX rates are not
    modelled, so rows are marked reconstructed=True and never replace real rows.
    """
    prices   = data.get("prices") or {}
    holdings = compute_holdings(portfolio, prices, data.get("ils_usd"))
    voo_hist = (prices.get("VOO") or {}).get("history")
    if voo_hist is None or len(voo_hist) == 0:
        return []
    dates = _naive_index(voo_hist)[-days:]
    shares: Dict[str, pd.Series] = {}
    px: Dict[str, pd.Series] = {}
    for t, row in holdings["tickers"].items():
        hist = (prices.get(t) or {}).get("history")
        if hist is None or len(hist) == 0:
            continue
        px[t] = pd.Series(hist.values, index=_naive_index(hist)).reindex(dates).ffill() * row["fx"]
        n = pd.Series(0.0, index=dates)
        for lots in portfolio["layers"].values():
            for lot in lots:
                if lot["ticker"] == t and float(lot.get("shares") or 0) > 0:
                    n[dates >= pd.Timestamp(lot.get("buy_date") or dates[0])] += float(lot["shares"])
        shares[t] = n
    voo = pd.Series(voo_hist.values, index=_naive_index(voo_hist)).reindex(dates)
    out = []
    for i, d in enumerate(dates):
        sh = {t: float(shares[t].iloc[i]) for t in shares if shares[t].iloc[i] > 0}
        pr = {t: float(px[t].iloc[i]) for t in sh if not pd.isna(px[t].iloc[i])}
        value = sum(sh[t] * pr[t] for t in pr)
        if value <= 0:
            continue
        out.append({
            "date": d.strftime("%Y-%m-%d"), "value_usd": round(value, 2), "cost_usd": None,
            "voo_close": None if pd.isna(voo.iloc[i]) else round(float(voo.iloc[i]), 4),
            "shares": sh, "px": pr, "by_layer": {},
            "provisional": False, "reconstructed": True,
        })
    return out


def merge_reconstructed(snapshots: List[Dict], rows: List[Dict]) -> int:
    """Add reconstructed rows for dates with no real snapshot. Returns rows added."""
    have = {r["date"] for r in snapshots}
    new = [r for r in rows if r["date"] not in have]
    snapshots.extend(new)
    snapshots.sort(key=lambda r: r["date"])
    return len(new)


def _naive_index(series):
    idx = pd.DatetimeIndex(series.index)
    return idx.tz_localize(None) if idx.tz is not None else idx


# ── Performance ───────────────────────────────────────────────────────────────

def performance_frame(snapshots: List[Dict]) -> pd.DataFrame:
    """Daily frame with flow-adjusted portfolio index and rebased VOO (both start at 100).

    Columns: value, cost, flow, ret, index, voo_index, drawdown.
    ret_t = (value_t − flow_t) / value_{t−1} − 1
    """
    rows = [r for r in snapshots if r.get("value_usd")]
    if len(rows) < 2:
        return pd.DataFrame()
    rows = sorted(rows, key=lambda r: r["date"])
    flows = [0.0] + [_flow(a, b) for a, b in zip(rows, rows[1:])]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["flow"] = flows
    df = df.set_index("date").sort_index()
    df = df.rename(columns={"value_usd": "value", "cost_usd": "cost"})
    prev = df["value"].shift(1)
    df["ret"] = ((df["value"] - df["flow"]) / prev - 1).fillna(0.0)
    df["index"] = 100 * (1 + df["ret"]).cumprod()
    if "voo_close" in df and df["voo_close"].notna().any():
        voo = df["voo_close"].ffill()
        first = voo.dropna().iloc[0]
        df["voo_index"] = 100 * voo / first
    else:
        df["voo_index"] = float("nan")
    df["drawdown"] = df["index"] / df["index"].cummax() - 1
    return df


def _flow(prev: Dict, cur: Dict) -> float:
    """Money added (+) or taken out (−) between two snapshots, valued at today's prices."""
    sh0, sh1, px1 = prev.get("shares"), cur.get("shares"), cur.get("px")
    if sh0 is None or sh1 is None or px1 is None:
        return 0.0  # legacy rows without share counts — assume no flow
    return sum((sh1.get(t, 0.0) - sh0.get(t, 0.0)) * px1.get(t, (prev.get("px") or {}).get(t, 0.0))
               for t in set(sh0) | set(sh1))


def period_return(perf: pd.DataFrame, column: str, days: Optional[int] = None,
                  since: Optional[pd.Timestamp] = None) -> Optional[float]:
    """% change of perf[column] over the last `days` calendar days (or since a date)."""
    if perf.empty or column not in perf:
        return None
    s = perf[column].dropna()
    if len(s) < 2:
        return None
    start = since if since is not None else s.index[-1] - pd.Timedelta(days=days or 0)
    base = s[s.index <= start]
    base_val = base.iloc[-1] if len(base) else s.iloc[0]
    return (s.iloc[-1] / base_val - 1) * 100


def last_change(perf: pd.DataFrame) -> Optional[Dict]:
    """Change vs the previous snapshot: value delta, flow-adjusted %, VOO %."""
    if perf.empty or len(perf) < 2:
        return None
    a, b = perf.iloc[-2], perf.iloc[-1]
    voo = None
    if not (math.isnan(a.get("voo_index", float("nan"))) or math.isnan(b.get("voo_index", float("nan")))):
        voo = (b["voo_index"] / a["voo_index"] - 1) * 100
    return {"from": perf.index[-2], "value_delta": b["value"] - a["value"] - b["flow"],
            "pct": b["ret"] * 100, "voo_pct": voo, "flow": b["flow"]}


# ── Target allocation & rebalancing ───────────────────────────────────────────

_PCT_IN_NAME = re.compile(r"\((\d{1,3})%\)")


def default_layer_targets(layers: List[str]) -> Dict[str, float]:
    """Targets from names like 'Core (50%)'; the remainder split equally among the rest."""
    fixed = {}
    for layer in layers:
        m = _PCT_IN_NAME.search(layer)
        if m:
            fixed[layer] = float(m.group(1))
    rest = [layer for layer in layers if layer not in fixed]
    remainder = max(0.0, 100.0 - sum(fixed.values()))
    each = remainder / len(rest) if rest else 0.0
    return {**fixed, **{layer: round(each, 2) for layer in rest}}


def rebalance_plan(current: Dict[str, float], targets: Dict[str, float],
                   new_cash: float = 0.0) -> pd.DataFrame:
    """Per-layer current vs target, and how to deploy `new_cash` (buys only).

    Columns: layer, current_usd, current_pct, target_pct, drift_pp, to_target_usd, buy_usd.
    new_cash goes to underweight layers in proportion to their shortfall measured
    against the post-deposit total; nothing is sold.
    """
    layers = sorted(set(current) | set(targets))
    total = sum(current.values())
    after = total + max(new_cash, 0.0)
    rows = []
    for layer in layers:
        cur = current.get(layer, 0.0)
        tgt = targets.get(layer, 0.0)
        rows.append({
            "layer": layer,
            "current_usd": cur,
            "current_pct": cur / total * 100 if total else 0.0,
            "target_pct": tgt,
            "drift_pp": (cur / total * 100 if total else 0.0) - tgt,
            "to_target_usd": tgt / 100 * total - cur,
            "_gap_after": max(tgt / 100 * after - cur, 0.0),
        })
    df = pd.DataFrame(rows)
    gap_sum = df["_gap_after"].sum() if not df.empty else 0.0
    cash = max(new_cash, 0.0)
    df["buy_usd"] = df["_gap_after"] / gap_sum * min(cash, gap_sum) if gap_sum else 0.0
    if cash > gap_sum and gap_sum and not df.empty:
        # More cash than shortfall — spread the excess by target weight
        excess = cash - gap_sum
        df["buy_usd"] += df["target_pct"] / max(df["target_pct"].sum(), 1e-9) * excess
    return df.drop(columns="_gap_after")


# ── Position sizing ───────────────────────────────────────────────────────────

def position_size(account_usd: float, risk_pct: float, entry: float, stop: float,
                  fx: float = 1.0) -> Optional[Dict]:
    """Shares to buy so that hitting `stop` loses risk_pct % of the account.

    entry/stop are in the security's own currency; fx converts to USD (NIS → USD).
    Returns None for invalid input (stop must be below entry for a long).
    """
    if account_usd <= 0 or risk_pct <= 0 or entry <= 0 or stop <= 0 or stop >= entry:
        return None
    risk_usd       = account_usd * risk_pct / 100
    risk_per_share = (entry - stop) * fx
    shares         = math.floor(risk_usd / risk_per_share)
    position_usd   = shares * entry * fx
    return {
        "shares":        shares,
        "risk_usd":      shares * risk_per_share,
        "position_usd":  position_usd,
        "position_pct":  position_usd / account_usd * 100,
        "stop_pct":      (entry - stop) / entry * 100,
    }
