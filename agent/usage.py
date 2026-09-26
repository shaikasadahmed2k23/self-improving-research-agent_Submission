"""Per-day cap on live runs started from the UI, so a public demo cannot drain the free-tier API quotas.

Counts are kept per UTC day in data/usage.sqlite3 (not *.db, so the memory-database picker ignores it). The check and
the increment happen in one IMMEDIATE transaction, so concurrent visitors cannot both take the last slot.
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent import config

SCHEMA = "CREATE TABLE IF NOT EXISTS live_runs (day TEXT PRIMARY KEY, count INTEGER NOT NULL)"


def _path() -> Path:
    return Path(config.DATA_DIR) / "usage.sqlite3"


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _connect() -> sqlite3.Connection:
    _path().parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_path(), isolation_level=None, timeout=10)
    con.execute(SCHEMA)
    return con


def runs_today() -> int:
    with closing(_connect()) as con:
        row = con.execute("SELECT count FROM live_runs WHERE day = ?", (_today(),)).fetchone()
    return row[0] if row else 0


def claim_run(cap: int | None = None) -> tuple[bool, int]:
    """Reserve one live run for today. Returns (allowed, runs used today including this one if allowed). cap 0 = no limit."""
    cap = config.DAILY_RUN_CAP if cap is None else cap
    with closing(_connect()) as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT count FROM live_runs WHERE day = ?", (_today(),)).fetchone()
        used = row[0] if row else 0
        if cap and used >= cap:
            con.execute("ROLLBACK")
            return False, used
        con.execute(
            "INSERT INTO live_runs (day, count) VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET count = count + 1", (_today(),)
        )
        con.execute("COMMIT")
        return True, used + 1


def time_until_reset() -> str:
    """'5h 12m' until the next 00:00 UTC."""
    now = datetime.now(timezone.utc)
    reset = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    minutes = int((reset - now).total_seconds() // 60)
    return f"{minutes // 60}h {minutes % 60}m"
