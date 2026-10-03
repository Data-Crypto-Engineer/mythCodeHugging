"""SQLite persistence.

⚠️ DEPLOYMENT TRUTH (verified): Streamlit Community Cloud runs your app in a
container with an EPHEMERAL filesystem. A SQLite file survives reruns and
reboots of the *session*, but NOT a redeploy or container recycle. We therefore:
  * expose `degraded` so the UI can warn honestly, and
  * fall back to an in-memory database instead of crashing if the FS is read-only.
For durable cloud saves you need an external store (e.g. Turso/libSQL, Supabase,
Postgres). That is a deliberate NOT-included decision: it is an external service.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any

from models.game import GameState
from utils.logger import get_logger

logger = get_logger("storage")

SCHEMA = """
CREATE TABLE IF NOT EXISTS saves (
    session_id TEXT PRIMARY KEY,
    player_name TEXT,
    turn INTEGER DEFAULT 0,
    updated_at TEXT,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    npc_id TEXT NOT NULL,
    turn INTEGER DEFAULT 0,
    note TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS turn_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn INTEGER DEFAULT 0,
    kind TEXT,
    summary TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_saves_updated ON saves(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id, npc_id);
"""


class Storage:
    """Small, thread-safe SQLite wrapper with a graceful degradation path."""

    def __init__(self, path: str = "mythcode.db") -> None:
        self.path = path
        self.degraded = False
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._open()

    # ── plumbing ────────────────────────────────────────────────
    def _open(self) -> None:
        try:
            conn = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.executescript(SCHEMA)
            conn.commit()
            self._conn = conn
            logger.info("Storage ready at %s", self.path)
        except sqlite3.Error as exc:
            logger.warning("Could not open %s (%s). Falling back to in-memory storage.", self.path, exc)
            self.degraded = True
            conn = sqlite3.connect(":memory:", check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.executescript(SCHEMA)
            conn.commit()
            self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        assert self._conn is not None
        return self._conn

    # ── saves ───────────────────────────────────────────────────
    def save_game(self, state: GameState) -> bool:
        state.updated_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(timespec="seconds")
        payload = state.model_dump_json()
        try:
            with self._lock:
                self.conn.execute(
                    """INSERT INTO saves (session_id, player_name, turn, updated_at, payload)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(session_id) DO UPDATE SET
                         player_name=excluded.player_name,
                         turn=excluded.turn,
                         updated_at=excluded.updated_at,
                         payload=excluded.payload""",
                    (state.session_id, state.player.name, state.turn, state.updated_at, payload),
                )
                self.conn.commit()
            return True
        except sqlite3.Error as exc:
            logger.error("save_game failed: %s", exc)
            return False

    def load_game(self, session_id: str) -> GameState | None:
        try:
            with self._lock:
                row = self.conn.execute(
                    "SELECT payload FROM saves WHERE session_id = ?", (session_id,)
                ).fetchone()
        except sqlite3.Error as exc:
            logger.error("load_game failed: %s", exc)
            return None
        if not row:
            return None
        try:
            return GameState.model_validate_json(row["payload"])
        except Exception as exc:  # corrupted save must not crash the app
            logger.error("Corrupted save %s: %s", session_id, exc)
            return None

    def latest_session_id(self) -> str | None:
        try:
            with self._lock:
                row = self.conn.execute(
                    "SELECT session_id FROM saves ORDER BY updated_at DESC LIMIT 1"
                ).fetchone()
            return row["session_id"] if row else None
        except sqlite3.Error:
            return None

    def list_saves(self, limit: int = 5) -> list[dict[str, Any]]:
        try:
            with self._lock:
                rows = self.conn.execute(
                    "SELECT session_id, player_name, turn, updated_at FROM saves "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error:
            return []

    def delete_game(self, session_id: str) -> None:
        try:
            with self._lock:
                self.conn.execute("DELETE FROM saves WHERE session_id = ?", (session_id,))
                self.conn.execute("DELETE FROM memories WHERE session_id = ?", (session_id,))
                self.conn.execute("DELETE FROM turn_log WHERE session_id = ?", (session_id,))
                self.conn.commit()
        except sqlite3.Error as exc:
            logger.error("delete_game failed: %s", exc)

    def purge_all(self) -> None:
        try:
            with self._lock:
                for table in ("saves", "memories", "turn_log"):
                    self.conn.execute(f"DELETE FROM {table}")
                self.conn.commit()
        except sqlite3.Error as exc:
            logger.error("purge_all failed: %s", exc)

    # ── memory & log ────────────────────────────────────────────
    def add_memory(self, session_id: str, npc_id: str, note: str, turn: int = 0) -> None:
        try:
            with self._lock:
                self.conn.execute(
                    "INSERT INTO memories (session_id, npc_id, turn, note) VALUES (?, ?, ?, ?)",
                    (session_id, npc_id, turn, note),
                )
                self.conn.commit()
        except sqlite3.Error as exc:
            logger.error("add_memory failed: %s", exc)

    def memories_for(self, session_id: str, npc_id: str, limit: int = 8) -> list[str]:
        try:
            with self._lock:
                rows = self.conn.execute(
                    "SELECT note FROM memories WHERE session_id=? AND npc_id=? "
                    "ORDER BY id DESC LIMIT ?",
                    (session_id, npc_id, limit),
                ).fetchall()
            return [row["note"] for row in reversed(rows)]
        except sqlite3.Error:
            return []

    def log_turn(self, session_id: str, turn: int, kind: str, summary: str) -> None:
        try:
            with self._lock:
                self.conn.execute(
                    "INSERT INTO turn_log (session_id, turn, kind, summary) VALUES (?, ?, ?, ?)",
                    (session_id, turn, kind, summary[:800]),
                )
                self.conn.commit()
        except sqlite3.Error:
            pass

    def dump_session(self, session_id: str) -> str:
        """Exportable JSON for the player (privacy transparency)."""
        state = self.load_game(session_id)
        return json.dumps(
            {
                "state": json.loads(state.model_dump_json()) if state else None,
                "memories": [
                    row["note"]
                    for row in self.conn.execute(
                        "SELECT note FROM memories WHERE session_id=?", (session_id,)
                    ).fetchall()
                ],
            },
            indent=2,
        )


_STORAGE: Storage | None = None


def get_storage(path: str | None = None) -> Storage:
    global _STORAGE
    if _STORAGE is None:
        if path is None:
            from utils.config import get_settings

            path = get_settings().db_path
        _STORAGE = Storage(path)
    return _STORAGE


def reset_storage_cache() -> None:
    global _STORAGE
    _STORAGE = None
