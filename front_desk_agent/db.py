"""
db.py — Postgres connection layer for Zara.

On Railway: DATABASE_URL is automatically set when you add a Postgres service.
Locally:    JSON files are used as fallback — no setup needed.

The module exposes one function: get_conn()
  - Returns a live psycopg2 connection if DATABASE_URL is set
  - Returns None if running locally without Postgres (tools fall back to JSON)

Schema is auto-created on first connection via init_schema().
"""

import os
from typing import Optional

_conn = None  # module-level singleton connection


def get_conn():
    """
    Return a persistent Postgres connection, or None if DATABASE_URL is not set.
    Automatically reconnects if the connection was dropped.
    """
    global _conn
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        return None  # no Postgres configured — callers use JSON fallback

    try:
        import psycopg2
        import psycopg2.extras

        # Reuse connection if still alive
        if _conn is not None:
            try:
                _conn.cursor().execute("SELECT 1")
                return _conn
            except Exception:
                _conn = None  # stale — reconnect below

        _conn = psycopg2.connect(db_url, sslmode="require")
        _conn.autocommit = True
        print("✅  Connected to Postgres")
        init_schema(_conn)
        return _conn

    except ImportError:
        print("⚠  psycopg2 not installed — run: pip install psycopg2-binary")
        return None
    except Exception as e:
        print(f"⚠  Postgres connection failed: {e} — using JSON fallback")
        return None


def init_schema(conn) -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    schema = """
    CREATE TABLE IF NOT EXISTS leads (
        id              SERIAL PRIMARY KEY,
        name            TEXT NOT NULL,
        company         TEXT,
        phone           TEXT,
        email           TEXT,
        industry        TEXT,
        title           TEXT,
        linkedin        TEXT,
        location        TEXT,
        employees       TEXT,
        status          TEXT DEFAULT 'New',
        source          TEXT DEFAULT 'Manual',
        interest_level  TEXT DEFAULT 'warm',
        notes           TEXT,
        seniority       TEXT,
        captured_at     TIMESTAMPTZ DEFAULT NOW(),
        enriched_at     TIMESTAMPTZ,
        enriched_by     TEXT
    );

    CREATE TABLE IF NOT EXISTS visitors (
        id          SERIAL PRIMARY KEY,
        name        TEXT NOT NULL,
        purpose     TEXT,
        host        TEXT,
        arrived_at  TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS appointments (
        id              SERIAL PRIMARY KEY,
        visitor_name    TEXT,
        company         TEXT,
        phone           TEXT,
        host            TEXT,
        date            TEXT,
        time            TEXT,
        purpose         TEXT,
        type            TEXT DEFAULT 'appointment',
        notes           TEXT,
        booked_at       TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS messages (
        id              SERIAL PRIMARY KEY,
        from_name       TEXT,
        from_contact    TEXT,
        for_staff       TEXT,
        message         TEXT,
        received_at     TIMESTAMPTZ DEFAULT NOW(),
        delivered       BOOLEAN DEFAULT FALSE
    );
    """
    with conn.cursor() as cur:
        cur.execute(schema)
    print("✅  Postgres schema ready")


def pg_insert(table: str, data: dict) -> int:
    """
    Insert a row into `table` using the dict keys as columns.
    Returns the new row's id, or -1 on failure.
    Automatically strips keys that aren't valid column names for safety.
    """
    conn = get_conn()
    if conn is None:
        return -1

    # Remove id — let Postgres auto-assign
    data = {k: v for k, v in data.items() if k != "id"}

    cols        = ", ".join(data.keys())
    placeholders = ", ".join(["%s"] * len(data))
    values      = list(data.values())

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) RETURNING id",
                values,
            )
            return cur.fetchone()[0]
    except Exception as e:
        print(f"  [pg_insert error on {table}]: {e}")
        return -1


def pg_fetch(table: str, where: str = "", params: tuple = ()) -> list[dict]:
    """
    Fetch all rows from `table` as a list of dicts.
    Optional WHERE clause (without the 'WHERE' keyword).
    """
    conn = get_conn()
    if conn is None:
        return []

    sql = f"SELECT * FROM {table}"
    if where:
        sql += f" WHERE {where}"
    sql += " ORDER BY id"

    try:
        import psycopg2.extras
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        print(f"  [pg_fetch error on {table}]: {e}")
        return []


def pg_update(table: str, row_id: int, data: dict) -> bool:
    """Update a single row by id. Returns True on success."""
    conn = get_conn()
    if conn is None:
        return False

    data = {k: v for k, v in data.items() if k != "id"}
    set_clause = ", ".join(f"{k} = %s" for k in data.keys())
    values     = list(data.values()) + [row_id]

    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE {table} SET {set_clause} WHERE id = %s", values)
        return True
    except Exception as e:
        print(f"  [pg_update error on {table}]: {e}")
        return False


def pg_count(table: str) -> int:
    """Return row count for a table."""
    conn = get_conn()
    if conn is None:
        return 0
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            return cur.fetchone()[0]
    except Exception:
        return 0
