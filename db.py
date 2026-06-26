"""
db.py — Persistent storage for Eva bots.

Backend selection:
  DATABASE_URL set → PostgreSQL (use Supabase free tier in production)
  DATABASE_URL not set → SQLite (local dev, file: eva_bots.db)

All functions are synchronous and thread-safe via thread-local connections.
Call from async code using asyncio.to_thread() for heavy operations;
for quick single-row writes (log_message, mood updates) direct calls are fine.
"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)

DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()
_USE_PG: bool = bool(DATABASE_URL)
_PH: str = "%s" if _USE_PG else "?"  # placeholder token

# ── Connection pools (thread-local) ──────────────────────────────────────────

if _USE_PG:
    import psycopg2
    import psycopg2.extras

    _pg_local: threading.local = threading.local()

    def _get_conn():
        if not hasattr(_pg_local, "conn") or _pg_local.conn.closed:
            _pg_local.conn = psycopg2.connect(DATABASE_URL)
            _pg_local.conn.autocommit = False
        return _pg_local.conn

else:
    import sqlite3

    _SQLITE_PATH: str = os.getenv("SQLITE_PATH", "eva_bots.db")
    _sqlite_local: threading.local = threading.local()

    def _get_conn():  # type: ignore[misc]
        if not hasattr(_sqlite_local, "conn"):
            conn = sqlite3.connect(_SQLITE_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            _sqlite_local.conn = conn
        return _sqlite_local.conn


@contextmanager
def _db() -> Generator:
    conn = _get_conn()
    if _USE_PG:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create tables on first run. Idempotent."""
    with _db() as cur:
        if _USE_PG:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id          BIGSERIAL PRIMARY KEY,
                    channel_id  TEXT NOT NULL,
                    pilot_name  TEXT NOT NULL,
                    role        TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    ts          TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_conv ON conversation_history
                (channel_id, pilot_name, ts DESC)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_interactions (
                    user_id     TEXT NOT NULL,
                    pilot_name  TEXT NOT NULL,
                    count       INTEGER DEFAULT 1,
                    last_seen   TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (user_id, pilot_name)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pilot_mood (
                    pilot_name  TEXT PRIMARY KEY,
                    mood_value  REAL DEFAULT 0.5,
                    updated_at  TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS message_log (
                    id          BIGSERIAL PRIMARY KEY,
                    channel_id  TEXT NOT NULL,
                    author      TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    is_bot      BOOLEAN DEFAULT FALSE,
                    ts          TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_msg ON message_log(channel_id, ts DESC)")
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id  TEXT NOT NULL,
                    pilot_name  TEXT NOT NULL,
                    role        TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    ts          DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_conv ON conversation_history
                (channel_id, pilot_name, ts)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_interactions (
                    user_id     TEXT NOT NULL,
                    pilot_name  TEXT NOT NULL,
                    count       INTEGER DEFAULT 1,
                    last_seen   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, pilot_name)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pilot_mood (
                    pilot_name  TEXT PRIMARY KEY,
                    mood_value  REAL DEFAULT 0.5,
                    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS message_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id  TEXT NOT NULL,
                    author      TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    is_bot      INTEGER DEFAULT 0,
                    ts          DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_msg ON message_log(channel_id, ts)")

    logger.info("[DB] Initialized — backend: %s", "postgres" if _USE_PG else "sqlite")


# ── Conversation History ──────────────────────────────────────────────────────

def db_add_conversation_turn(channel_id: str, pilot_name: str, role: str, content: str) -> None:
    with _db() as cur:
        cur.execute(
            f"INSERT INTO conversation_history (channel_id, pilot_name, role, content) "
            f"VALUES ({_PH},{_PH},{_PH},{_PH})",
            (str(channel_id), pilot_name, role, content),
        )
        # Prune: keep last 24 entries per (channel, pilot)
        if _USE_PG:
            cur.execute("""
                DELETE FROM conversation_history
                WHERE id IN (
                    SELECT id FROM conversation_history
                    WHERE channel_id = %s AND pilot_name = %s
                    ORDER BY ts DESC OFFSET 24
                )
            """, (str(channel_id), pilot_name))
        else:
            cur.execute("""
                DELETE FROM conversation_history WHERE id NOT IN (
                    SELECT id FROM conversation_history
                    WHERE channel_id = ? AND pilot_name = ?
                    ORDER BY ts DESC LIMIT 24
                ) AND channel_id = ? AND pilot_name = ?
            """, (str(channel_id), pilot_name, str(channel_id), pilot_name))


def db_get_conversation_history(
    channel_id: str, pilot_name: str, max_turns: int = 6
) -> list[dict]:
    """Returns the last max_turns exchanges as [{role, content}, ...] oldest-first."""
    limit = max_turns * 2
    with _db() as cur:
        if _USE_PG:
            cur.execute("""
                SELECT role, content FROM (
                    SELECT role, content, ts FROM conversation_history
                    WHERE channel_id = %s AND pilot_name = %s
                    ORDER BY ts DESC LIMIT %s
                ) sub ORDER BY ts ASC
            """, (str(channel_id), pilot_name, limit))
        else:
            # Use id (AUTOINCREMENT) for ordering — SQLite DATETIME only has second precision
            cur.execute("""
                SELECT role, content FROM (
                    SELECT id, role, content FROM conversation_history
                    WHERE channel_id = ? AND pilot_name = ?
                    ORDER BY id DESC LIMIT ?
                ) AS recent ORDER BY id ASC
            """, (str(channel_id), pilot_name, limit))
        rows = cur.fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]


def db_clear_conversation_history(channel_id: str, pilot_name: str) -> None:
    with _db() as cur:
        cur.execute(
            f"DELETE FROM conversation_history WHERE channel_id={_PH} AND pilot_name={_PH}",
            (str(channel_id), pilot_name),
        )


# ── User Interactions ─────────────────────────────────────────────────────────

def db_increment_interaction(user_id: str, pilot_name: str) -> None:
    with _db() as cur:
        if _USE_PG:
            cur.execute("""
                INSERT INTO user_interactions (user_id, pilot_name, count)
                VALUES (%s, %s, 1)
                ON CONFLICT (user_id, pilot_name)
                DO UPDATE SET count = user_interactions.count + 1, last_seen = NOW()
            """, (user_id, pilot_name))
        else:
            cur.execute("""
                INSERT INTO user_interactions (user_id, pilot_name, count)
                VALUES (?, ?, 1)
                ON CONFLICT (user_id, pilot_name)
                DO UPDATE SET count = count + 1, last_seen = CURRENT_TIMESTAMP
            """, (user_id, pilot_name))


def db_get_interaction_count(user_id: str, pilot_name: str) -> int:
    with _db() as cur:
        cur.execute(
            f"SELECT count FROM user_interactions WHERE user_id={_PH} AND pilot_name={_PH}",
            (user_id, pilot_name),
        )
        row = cur.fetchone()
        return int(row["count"]) if row else 0


# ── Pilot Mood ────────────────────────────────────────────────────────────────

def db_get_mood(pilot_name: str, default: float = 0.5) -> float:
    with _db() as cur:
        cur.execute(
            f"SELECT mood_value FROM pilot_mood WHERE pilot_name={_PH}", (pilot_name,)
        )
        row = cur.fetchone()
        return float(row["mood_value"]) if row else default


def db_set_mood(pilot_name: str, mood_value: float) -> None:
    mood_value = max(0.0, min(1.0, mood_value))
    with _db() as cur:
        if _USE_PG:
            cur.execute("""
                INSERT INTO pilot_mood (pilot_name, mood_value)
                VALUES (%s, %s)
                ON CONFLICT (pilot_name) DO UPDATE
                SET mood_value = EXCLUDED.mood_value, updated_at = NOW()
            """, (pilot_name, mood_value))
        else:
            cur.execute("""
                INSERT INTO pilot_mood (pilot_name, mood_value) VALUES (?,?)
                ON CONFLICT (pilot_name) DO UPDATE SET mood_value = excluded.mood_value
            """, (pilot_name, mood_value))


# ── Message Log ───────────────────────────────────────────────────────────────

def db_log_message(channel_id: str, author: str, content: str, is_bot: bool = False) -> None:
    if not content or not content.strip():
        return
    is_bot_val = is_bot if _USE_PG else int(is_bot)
    with _db() as cur:
        cur.execute(
            f"INSERT INTO message_log (channel_id, author, content, is_bot) "
            f"VALUES ({_PH},{_PH},{_PH},{_PH})",
            (str(channel_id), author, content[:2000], is_bot_val),
        )
        # Keep only 200 most recent per channel
        if _USE_PG:
            cur.execute("""
                DELETE FROM message_log WHERE id IN (
                    SELECT id FROM message_log WHERE channel_id = %s
                    ORDER BY ts DESC OFFSET 200
                )
            """, (str(channel_id),))
        else:
            cur.execute("""
                DELETE FROM message_log WHERE id NOT IN (
                    SELECT id FROM message_log WHERE channel_id = ?
                    ORDER BY ts DESC LIMIT 200
                ) AND channel_id = ?
            """, (str(channel_id), str(channel_id)))


def db_get_recent_messages(channel_id: str, limit: int = 10) -> list[dict]:
    with _db() as cur:
        cur.execute(
            f"SELECT author, content, is_bot FROM message_log "
            f"WHERE channel_id={_PH} ORDER BY ts DESC LIMIT {_PH}",
            (str(channel_id), limit),
        )
        rows = cur.fetchall()
        return [
            {"author": r["author"], "content": r["content"], "is_bot": bool(r["is_bot"])}
            for r in rows
        ]