"""sql_query — READ-ONLY, port of src/tools/sql.ts. Single SELECT only, runs
against a local demo SQLite DB seeded with the same sample sales data."""

import re
import sqlite3
import threading

from langchain_core.tools import tool

from ..config import DEMO_DB_PATH

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

_SEED = [
    (1, "Acme Corp", "Widget A", 120, 9.5, "2026-05-04", "shipped"),
    (2, "Globex", "Widget B", 40, 24.0, "2026-05-11", "shipped"),
    (3, "Initech", "Widget A", 75, 9.5, "2026-05-18", "pending"),
    (4, "Acme Corp", "Widget C", 200, 4.25, "2026-05-25", "shipped"),
    (5, "Umbrella", "Widget B", 60, 24.0, "2026-06-01", "shipped"),
    (6, "Globex", "Widget C", 150, 4.25, "2026-06-03", "cancelled"),
    (7, "Initech", "Widget B", 30, 24.0, "2026-06-05", "shipped"),
    (8, "Acme Corp", "Widget A", 90, 9.5, "2026-06-08", "pending"),
]

_WRITE_RE = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|pragma|replace)\b", re.I)


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    fresh = not DEMO_DB_PATH.exists()
    conn = sqlite3.connect(DEMO_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if fresh:
        conn.execute(
            """CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                customer TEXT NOT NULL,
                product TEXT NOT NULL,
                qty INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                order_date TEXT NOT NULL,
                status TEXT NOT NULL
            )"""
        )
        conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", _SEED)
        conn.commit()
    _conn = conn
    return conn


def _is_read_only_select(sql: str) -> bool:
    trimmed = re.sub(r";\s*$", "", sql.strip())
    if ";" in trimmed:
        return False                      # single statement only
    if not re.match(r"^select\b", trimmed, re.I):
        return False                      # must start with SELECT
    if _WRITE_RE.search(trimmed):
        return False                      # block sneaky writes via CTE/PRAGMA
    return True


@tool
def sql_query(sql: str) -> dict:
    """Run a READ-ONLY SQL SELECT against the demo database. Schema: orders(id, customer, product, qty, unit_price, order_date, status). Single SELECT statement only — writes are rejected."""
    if not _is_read_only_select(sql):
        return {"success": False, "error": "Rejected: only a single SELECT statement is allowed (read-only v1)."}
    try:
        with _lock:
            rows = [dict(r) for r in _db().execute(sql).fetchall()]
        if not rows:
            return {"success": True, "output": {"rows": [], "note": "query returned no rows"}}
        return {"success": True, "output": {"rows": rows[:50], "totalReturned": len(rows)}}
    except Exception as e:
        return {"success": False, "error": str(e)}
