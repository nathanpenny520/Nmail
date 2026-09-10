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
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT NOT NULL UNIQUE,
            provider_name TEXT NOT NULL DEFAULT '',
            imap_server   TEXT NOT NULL,
            imap_port     INTEGER NOT NULL DEFAULT 993,
            smtp_server   TEXT NOT NULL DEFAULT '',
            smtp_port     INTEGER NOT NULL DEFAULT 465,
            color         TEXT NOT NULL DEFAULT '#6366f1',
            status        TEXT NOT NULL DEFAULT 'never_synced',
            status_detail TEXT,
            last_sync_at  TEXT,
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS emails (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id     INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            folder         TEXT NOT NULL DEFAULT 'INBOX',
            uid            INTEGER NOT NULL,
            message_id     TEXT NOT NULL DEFAULT '',
            subject        TEXT NOT NULL DEFAULT '',
            sender_name    TEXT NOT NULL DEFAULT '',
            sender_email   TEXT NOT NULL DEFAULT '',
            recipients     TEXT NOT NULL DEFAULT '[]',
            cc             TEXT NOT NULL DEFAULT '[]',
            date           TEXT,
            snippet        TEXT NOT NULL DEFAULT '',
            body_text      TEXT NOT NULL DEFAULT '',
            body_html      TEXT NOT NULL DEFAULT '',
            is_read        INTEGER NOT NULL DEFAULT 0,
            starred        INTEGER NOT NULL DEFAULT 0,
            archived_local INTEGER NOT NULL DEFAULT 0,
            has_attachments INTEGER NOT NULL DEFAULT 0,
            remote_img_count INTEGER NOT NULL DEFAULT 0,
            created_at     TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(account_id, folder, uid)
        );
        CREATE INDEX IF NOT EXISTS idx_emails_list
            ON emails(account_id, folder, date DESC);
        CREATE INDEX IF NOT EXISTS idx_emails_archived
            ON emails(archived_local, date DESC);

        CREATE TABLE IF NOT EXISTS attachments (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id INTEGER NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            mime     TEXT NOT NULL DEFAULT '',
            size     INTEGER NOT NULL DEFAULT 0,
            path     TEXT NOT NULL,
            cid      TEXT
        );

        CREATE TABLE IF NOT EXISTS sync_state (
            account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            folder      TEXT NOT NULL,
            last_uid    INTEGER NOT NULL DEFAULT 0,
            uidvalidity INTEGER,
            PRIMARY KEY (account_id, folder)
        );

        -- trigram 分词：中文按短子串可检索（<3 字符的查询由应用层回退 LIKE）
        CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts USING fts5(
            subject, sender_text, body_text, tokenize='trigram'
        );
        CREATE TRIGGER IF NOT EXISTS emails_fts_ai AFTER INSERT ON emails BEGIN
            INSERT INTO emails_fts(rowid, subject, sender_text, body_text)
            VALUES (new.id, new.subject,
                    new.sender_name || ' ' || new.sender_email, new.body_text);
        END;
        CREATE TRIGGER IF NOT EXISTS emails_fts_ad AFTER DELETE ON emails BEGIN
            DELETE FROM emails_fts WHERE rowid = old.id;
        END;
        """,
    ),
    (
        3,
        """
        -- P2 AI 层：分类结果、待审草稿、AI 用量、发件人白/黑名单、账号 AI 权限
        ALTER TABLE emails ADD COLUMN category TEXT NOT NULL DEFAULT '';
        ALTER TABLE emails ADD COLUMN importance TEXT NOT NULL DEFAULT '';
        ALTER TABLE emails ADD COLUMN needs_reply INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE emails ADD COLUMN reply_reason TEXT NOT NULL DEFAULT '';
        ALTER TABLE emails ADD COLUMN ai_classified_at TEXT;
        CREATE INDEX IF NOT EXISTS idx_emails_category ON emails(category);

        ALTER TABLE accounts ADD COLUMN ai_permission TEXT NOT NULL DEFAULT 'draft_review';

        CREATE TABLE IF NOT EXISTS drafts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id    INTEGER NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
            account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            content     TEXT NOT NULL,
            origin      TEXT NOT NULL DEFAULT 'ai',
            status      TEXT NOT NULL DEFAULT 'pending',
            instruction TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status, created_at DESC);

        CREATE TABLE IF NOT EXISTS ai_logs (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type         TEXT NOT NULL,
            account_id        INTEGER,
            model             TEXT NOT NULL DEFAULT '',
            prompt_tokens     INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            ok                INTEGER NOT NULL DEFAULT 1,
            summary           TEXT NOT NULL DEFAULT '',
            created_at        TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sender_lists (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern   TEXT NOT NULL UNIQUE,
            list_type TEXT NOT NULL CHECK (list_type IN ('whitelist', 'blacklist')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """,
    ),
    (
        4,
        """
        -- P3：每日摘要历史 + 账号 Tone DNA
        CREATE TABLE IF NOT EXISTS digest_history (
            date         TEXT PRIMARY KEY,
            content_json TEXT NOT NULL,
            is_read      INTEGER NOT NULL DEFAULT 0,
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );
        ALTER TABLE accounts ADD COLUMN tone_dna TEXT;
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
