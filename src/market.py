"""Market state detection — NYSE calendar aware, graceful fallback."""

from datetime import datetime, timedelta
import pytz
from src.config import HE

try:
    import exchange_calendars as xcals
    _nyse = xcals.get_calendar("XNYS")
    CALENDAR_AVAILABLE = True
except Exception:
    CALENDAR_AVAILABLE = False

NYSE_TZ = pytz.timezone("America/New_York")


def get_market_state():
    """Return dict: is_trading_day, is_open, last_trading_day (date), status_label."""
    now_et = datetime.now(NYSE_TZ)
    today  = now_et.date()

    if CALENDAR_AVAILABLE:
        try:
            is_session = _nyse.is_session(str(today))
        except Exception:
            is_session = today.weekday() < 5
    else:
        is_session = today.weekday() < 5

    if not is_session:
        if CALENDAR_AVAILABLE:
            try:
                last_td = _nyse.previous_session(str(today)).date()
            except Exception:
                last_td = _prev_weekday(today)
        else:
            last_td = _prev_weekday(today)
        label = "Weekend" if today.weekday() >= 5 else "Holiday"
        return {
            "is_trading_day": False,
            "is_open":        False,
            "last_trading_day": last_td,
            "status_label":   label,
        }

    market_open  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)
    is_open = market_open <= now_et <= market_close

    if now_et < market_open:
        label = "Pre-Market"
    elif is_open:
        label = "Open"
    else:
        label = "After Hours"

    return {
        "is_trading_day": True,
        "is_open":        is_open,
        "last_trading_day": today,
        "status_label":   label,
    }


def _prev_weekday(d):
    """Walk back to the nearest Mon–Fri day."""
    d = d - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def market_badge(state):
    """Return HTML badge string for current market status."""
    _MAP = {
        "Open":        HE["market_open"],
        "Pre-Market":  HE["market_pre"],
        "After Hours": HE["market_after"],
        "Weekend":     HE["market_weekend"],
        "Holiday":     HE["market_holiday"],
    }
    label = _MAP.get(state["status_label"], state["status_label"])
    colors = {
        HE["market_open"]:    ("#4CAF50", "#1a3a1a"),
        HE["market_pre"]:     ("#FF9800", "#3a2a00"),
        HE["market_after"]:   ("#9E9E9E", "#2a2a2a"),
        HE["market_weekend"]: ("#9E9E9E", "#2a2a2a"),
        HE["market_holiday"]: ("#FF9800", "#3a2a00"),
    }
    fg, bg = colors.get(label, ("#9E9E9E", "#2a2a2a"))
    return (
        f'<span style="background:{bg};color:{fg};border:1px solid {fg};'
        f'border-radius:12px;padding:2px 10px;font-size:12px;font-weight:600">'
        f'&#9679; {label}</span>'
    )


def fmt_trading_day(state):
    """Return human-readable last trading day string."""
    ltd = state["last_trading_day"]
    if hasattr(ltd, "strftime"):
        return ltd.strftime("%a %d %b %Y")
    return str(ltd)
