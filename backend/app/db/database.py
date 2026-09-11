"""SQLite 连接、版本化迁移与 KV 设置存取。

单用户本地应用：单连接 + 写锁即可；WAL 提升读写并发。
迁移为有序 SQL 脚本，记录在 schema_migrations 表，启动时按版本号补跑；
个别迁移附带的 Python 回填逻辑放在 run_migrations 迁移循环之后（幂等）。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
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
    (
        5,
        """
        -- P4：AI 会话持久化（总管家对话，后续单邮件问答共用）
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT NOT NULL DEFAULT '新对话',
            kind       TEXT NOT NULL DEFAULT 'manager',
            account_id INTEGER,
            pinned     INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS chat_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content    TEXT NOT NULL,
            model      TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session
            ON chat_messages(session_id, id);
        CREATE INDEX IF NOT EXISTS idx_chat_sessions_list
            ON chat_sessions(pinned DESC, updated_at DESC);
        """,
    ),
    (
        6,
        """
        -- P4：外部图片信任白名单（sender_lists 增加 image_trust 类型，重建表以替换 CHECK 约束）
        CREATE TABLE sender_lists_v6 (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern   TEXT NOT NULL UNIQUE,
            list_type TEXT NOT NULL CHECK (list_type IN ('whitelist', 'blacklist', 'image_trust')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO sender_lists_v6 (id, pattern, list_type, created_at)
            SELECT id, pattern, list_type, created_at FROM sender_lists;
        DROP TABLE sender_lists;
        ALTER TABLE sender_lists_v6 RENAME TO sender_lists;
        """,
    ),
    (
        7,
        """
        -- 排序修复：原 date 列是混合时区的 ISO 字符串，字典序比较会错序；
        -- date_sort 为统一转 UTC 后的 ISO 串，列表按它排序
        ALTER TABLE emails ADD COLUMN date_sort TEXT;
        CREATE INDEX IF NOT EXISTS idx_emails_date_sort ON emails(date_sort DESC);
        """,
    ),
    (
        8,
        """
        -- 写信工作台：用户手写草稿（与 AI 待审 drafts 表相互独立）。
        -- 正文存 HTML（编辑器产出），发送时消毒并派生纯文本 alternative。
        -- in_reply_to 为软引用（无外键）：被引用邮件可能随时被同步删除。
        CREATE TABLE IF NOT EXISTS user_drafts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            mode        TEXT NOT NULL DEFAULT 'new',
            in_reply_to INTEGER,
            to_addrs    TEXT NOT NULL DEFAULT '',
            cc_addrs    TEXT NOT NULL DEFAULT '',
            bcc_addrs   TEXT NOT NULL DEFAULT '',
            subject     TEXT NOT NULL DEFAULT '',
            body_html   TEXT NOT NULL DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'editing',
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_user_drafts_status
            ON user_drafts(status, updated_at DESC);
        """,
    ),
    (
        9,
        """
        -- 写信台二期：附件持久化 + 定时发送
        ALTER TABLE user_drafts ADD COLUMN send_at TEXT;
        CREATE TABLE IF NOT EXISTS user_draft_attachments (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_id   INTEGER NOT NULL REFERENCES user_drafts(id) ON DELETE CASCADE,
            filename   TEXT NOT NULL,
            mime       TEXT NOT NULL DEFAULT '',
            size       INTEGER NOT NULL DEFAULT 0,
            path       TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_user_draft_att ON user_draft_attachments(draft_id);
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

    # 迁移 v7 的 Python 回填：历史邮件的 date_sort（UTC 归一化，混合时区无法 SQL 转换）
    pending = conn.execute(
        "SELECT COUNT(*) AS n FROM emails WHERE date_sort IS NULL AND date IS NOT NULL"
    ).fetchone()["n"]
    if pending:
        rows = conn.execute(
            "SELECT id, date FROM emails WHERE date_sort IS NULL AND date IS NOT NULL"
        ).fetchall()
        for row in rows:
            try:
                dt = datetime.fromisoformat(row["date"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                sort_val = dt.astimezone(timezone.utc).isoformat(timespec="seconds")
            except ValueError:
                continue
            conn.execute("UPDATE emails SET date_sort = ? WHERE id = ?", (sort_val, row["id"]))
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
