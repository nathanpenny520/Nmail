"""SQLite 连接、版本化迁移与 KV 设置存取。

单用户本地应用：单连接 + 写锁即可；WAL 提升读写并发。
迁移为有序 SQL 脚本，记录在 schema_migrations 表，启动时按版本号补跑。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any

from app.config import get_db_path

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS settings (
            key        TEXT PRIMARY KEY,
            value      TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            type       TEXT NOT NULL,
            title      TEXT NOT NULL,
            body       TEXT,
            ref_id     TEXT,
            is_read    INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """,
    ),
]


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(get_db_path(), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def run_migrations() -> None:
    conn = get_conn()
    with _lock:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version INTEGER PRIMARY KEY,"
            " applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
        for version, sql in MIGRATIONS:
            if version in applied:
                continue
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
        conn.commit()


def get_setting(key: str, default: Any = None) -> Any:
    row = get_conn().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None or row["value"] is None:
        return default
    return json.loads(row["value"])


def set_setting(key: str, value: Any) -> None:
    with _lock:
        get_conn().execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET"
            " value = excluded.value, updated_at = datetime('now')",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        get_conn().commit()
