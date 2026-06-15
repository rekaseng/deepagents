"""Task store — same schema/semantics as the TS sql.js store, on real SQLite.
Conversation state itself lives in the LangGraph checkpointer; this store keeps
the task records the web UI lists (sessions sidebar, steps view)."""

import json
import sqlite3
import threading
import time
from typing import Any, Optional

from ..config import TASK_DB_PATH

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    conn = sqlite3.connect(TASK_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            goal TEXT NOT NULL,
            result TEXT,
            steps TEXT,
            created_at INTEGER NOT NULL,
            session_id TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS processed_messages (
            message_id TEXT PRIMARY KEY,
            processed_at INTEGER NOT NULL
        )"""
    )
    conn.commit()
    _conn = conn
    return conn


# session_id defaults to the task's own id: trigger runs (email/schedule)
# become single-turn sessions without their call sites changing.
def save_task(task_id: str, goal: str, result: str, steps: Any, session_id: Optional[str] = None) -> None:
    with _lock:
        _db().execute(
            "INSERT OR REPLACE INTO tasks (id, goal, result, steps, created_at, session_id) VALUES (?,?,?,?,?,?)",
            (task_id, goal, result, json.dumps(steps, default=str), int(time.time() * 1000), session_id or task_id),
        )
        _db().commit()


def get_task(task_id: str) -> Optional[dict]:
    row = _db().execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        return None
    task = dict(row)
    try:
        task["steps"] = json.loads(task["steps"] or "[]")
    except json.JSONDecodeError:
        task["steps"] = []
    return task


def is_processed(message_id: str) -> bool:
    row = _db().execute("SELECT 1 FROM processed_messages WHERE message_id = ?", (message_id,)).fetchone()
    return row is not None


def mark_processed(message_id: str) -> None:
    with _lock:
        _db().execute(
            "INSERT OR REPLACE INTO processed_messages (message_id, processed_at) VALUES (?,?)",
            (message_id, int(time.time() * 1000)),
        )
        _db().commit()


def list_sessions(limit: int = 30) -> list[dict]:
    rows = _db().execute(
        """SELECT t1.session_id AS id,
                  (SELECT goal FROM tasks t2 WHERE t2.session_id = t1.session_id
                   ORDER BY t2.created_at ASC LIMIT 1) AS title,
                  COUNT(*) AS turns,
                  MAX(t1.created_at) AS updated_at
           FROM tasks t1
           GROUP BY t1.session_id
           ORDER BY updated_at DESC
           LIMIT ?""",
        (max(1, int(limit)),),
    ).fetchall()
    return [dict(r) for r in rows]


def list_session_tasks(session_id: str) -> list[dict]:
    rows = _db().execute(
        """SELECT id, goal, result, steps, created_at FROM tasks
           WHERE session_id = ? ORDER BY created_at ASC""",
        (session_id,),
    ).fetchall()
    out = []
    for r in rows:
        task = dict(r)
        try:
            task["steps"] = json.loads(task["steps"] or "[]")
        except json.JSONDecodeError:
            task["steps"] = []
        out.append(task)
    return out


def list_tasks(limit: int = 20) -> list[dict]:
    rows = _db().execute(
        "SELECT id, goal, result, created_at FROM tasks ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
