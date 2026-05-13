"""
state.py — SQLite logging of swaps + daily safety budget tracking.
"""
import os
import sqlite3
from datetime import datetime, timezone


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "volume_bot.db")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    _init_schema(con)
    return con


def _init_schema(con: sqlite3.Connection) -> None:
    con.executescript("""
    CREATE TABLE IF NOT EXISTS swaps (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        executed_at     TEXT NOT NULL,
        direction       TEXT NOT NULL,        -- 'buy' (USDC.e→token) or 'sell' (token→USDC.e)
        amount_in_raw   TEXT NOT NULL,
        amount_out_raw  TEXT,
        amount_in_usd   REAL,
        amount_out_usd  REAL,
        cost_usd        REAL,                 -- amount_in_usd - amount_out_usd (loss per swap)
        pool_price      REAL,                 -- USDC.e per token at swap time
        tx_hash         TEXT,
        status          TEXT NOT NULL,        -- 'OK' or 'FAIL'
        notes           TEXT
    );

    CREATE TABLE IF NOT EXISTS daily_totals (
        date            TEXT PRIMARY KEY,
        swaps_count     INTEGER NOT NULL DEFAULT 0,
        volume_usd      REAL    NOT NULL DEFAULT 0,
        cost_usd        REAL    NOT NULL DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_swaps_date ON swaps(executed_at);
    """)
    con.commit()


def record_swap(con, *,
                direction: str,
                amount_in_raw: int, amount_out_raw: int,
                amount_in_usd: float, amount_out_usd: float,
                pool_price: float, tx_hash: str | None,
                status: str, notes: str = "") -> int:
    """Insert swap row + update daily totals."""
    cost = amount_in_usd - amount_out_usd
    cur = con.execute("""
        INSERT INTO swaps (
            executed_at, direction, amount_in_raw, amount_out_raw,
            amount_in_usd, amount_out_usd, cost_usd, pool_price,
            tx_hash, status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (now_iso(), direction, str(amount_in_raw), str(amount_out_raw),
          amount_in_usd, amount_out_usd, cost, pool_price,
          tx_hash, status, notes))

    # Update daily totals (only for OK swaps)
    if status == "OK":
        today = today_str()
        con.execute("""
            INSERT INTO daily_totals (date, swaps_count, volume_usd, cost_usd)
            VALUES (?, 1, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                swaps_count = swaps_count + 1,
                volume_usd  = volume_usd + ?,
                cost_usd    = cost_usd + ?
        """, (today, amount_in_usd, cost, amount_in_usd, cost))

    con.commit()
    return cur.lastrowid


def get_today_totals(con) -> dict:
    today = today_str()
    row = con.execute(
        "SELECT * FROM daily_totals WHERE date = ?", (today,)
    ).fetchone()
    if row is None:
        return {"date": today, "swaps_count": 0, "volume_usd": 0.0, "cost_usd": 0.0}
    return dict(row)


def get_last_direction(con) -> str | None:
    """Returns the last successful swap's direction, or None if no swaps yet."""
    row = con.execute(
        "SELECT direction FROM swaps WHERE status='OK' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row["direction"] if row else None
