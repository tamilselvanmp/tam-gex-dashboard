"""US market clock: ET time, trading days, session state, freshness labels."""
from __future__ import annotations

import datetime
from typing import Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# NYSE full-day closures (2026). Extend yearly.
HOLIDAYS = {
    datetime.date(2026, 1, 1),    # New Year's Day
    datetime.date(2026, 1, 19),   # MLK Day
    datetime.date(2026, 2, 16),   # Presidents' Day
    datetime.date(2026, 4, 3),    # Good Friday
    datetime.date(2026, 5, 25),   # Memorial Day
    datetime.date(2026, 6, 19),   # Juneteenth
    datetime.date(2026, 7, 3),    # Independence Day (observed)
    datetime.date(2026, 9, 7),    # Labor Day
    datetime.date(2026, 11, 26),  # Thanksgiving
    datetime.date(2026, 12, 25),  # Christmas
}
# 13:00 ET equity close (SPX options 13:15)
HALF_DAYS = {
    datetime.date(2026, 11, 27),
    datetime.date(2026, 12, 24),
}


def now_et() -> datetime.datetime:
    return datetime.datetime.now(tz=ET)


def is_trading_day(d: datetime.date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS


def today_expiry_date(now: Optional[datetime.datetime] = None) -> datetime.date:
    """ET calendar date used for 0DTE matching."""
    return (now or now_et()).date()


def market_state(now: Optional[datetime.datetime] = None) -> dict:
    """Session for display + cache decisions.

    pre 7:00-9:30 / regular 9:30-16:15 (index options close 16:15) /
    post 16:15-20:00 / closed otherwise. Half days end at 13:15.
    """
    now = now or now_et()
    d, t = now.date(), now.time()
    session = "closed"
    if is_trading_day(d):
        close = datetime.time(13, 15) if d in HALF_DAYS else datetime.time(16, 15)
        if datetime.time(7, 0) <= t < datetime.time(9, 30):
            session = "pre"
        elif datetime.time(9, 30) <= t < close:
            session = "regular"
        elif close <= t < datetime.time(20, 0):
            session = "post"
    return {
        "open": session == "regular",
        "session": session,
        "ny_time": now.strftime("%H:%M"),
        "ny_date": d.isoformat(),
    }


def is_active_window(now: Optional[datetime.datetime] = None) -> bool:
    """True while CBOE snapshots are changing (drives the short cache TTL)."""
    return market_state(now)["session"] in ("pre", "regular", "post")


def freshness(last_trade_time: Optional[datetime.datetime],
              now: Optional[datetime.datetime] = None) -> str:
    """Badge label for the data's age, based on the underlying's last trade."""
    now = now or now_et()
    if last_trade_time is None:
        return "unknown"
    age = (now - last_trade_time).total_seconds()
    if age <= 20 * 60:
        return "delayed-15m"
    if last_trade_time.astimezone(ET).date() == now.date():
        return "intraday"
    return "last-session"
