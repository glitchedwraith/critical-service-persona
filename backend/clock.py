"""Simulated clock. All time logic in TrueSignal uses sim_clock, never wall
time (plan.md §3.1).

The sim clock is stored on the `system` DynamoDB table as a singleton row
keyed by id="singleton". Times are "HH:MM" strings within a single hackathon
day — no date component.
"""
import db

SYSTEM_ID = "singleton"
DAY_MINUTES = 24 * 60


def parse(ts):
    """'HH:MM' -> minutes since midnight."""
    h, m = ts.split(":")
    return int(h) * 60 + int(m)


def fmt(minutes):
    """minutes since midnight -> 'HH:MM' (wraps modulo 24h)."""
    minutes = minutes % DAY_MINUTES
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def now():
    """Return current sim time as 'HH:MM'. Raises if the system row is
    missing — run scripts/create_local_tables.py (local) or POST /reset."""
    row = db.get("TABLE_SYSTEM", SYSTEM_ID)
    if row is None or "sim_clock" not in row:
        raise RuntimeError(
            "system singleton missing; seed it via scripts/create_local_tables.py "
            "or POST /reset"
        )
    return row["sim_clock"]


def minutes_between(a, b):
    """Signed minutes from `a` to `b`. Negative if b precedes a within the day."""
    return parse(b) - parse(a)


def is_expired(ts):
    """True if ts is strictly before now()."""
    return parse(ts) < parse(now())


def advance(minutes):
    """Advance sim_clock by `minutes`. Returns the new 'HH:MM' string."""
    new_ts = fmt(parse(now()) + int(minutes))
    db.update("TABLE_SYSTEM", SYSTEM_ID, {"sim_clock": new_ts})
    return new_ts


__all__ = [
    "SYSTEM_ID", "parse", "fmt", "now", "minutes_between", "is_expired", "advance",
]
