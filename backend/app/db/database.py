"""SQLite 连接、版本化迁移与 KV 设置存取。

单用户本地应用：每线程一条连接 + 写锁即可；WAL 提升读写并发。
迁移为有序 SQL 脚本，记录在 schema_migrations 表，启动时按版本号补跑；
个别迁移附带的 Python 回填逻辑放在 run_migrations 迁移循环之后（幂等）。

事务边界（IMPROVEMENT_PLAN §3.2）：连接为 autocommit（isolation_level=None），
单条语句即生效；多语句原子性显式用 tx()——进程内全局写锁 + BEGIN IMMEDIATE，
成功提交、异常回滚。存量 conn.commit() 在 autocommit 下为无害 no-op，
随触碰逐步替换为 tx()。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager, suppress
from datetime import datetime, UTC
from typing import Any
from collections.abc import Iterator

from app.config import get_db_path

_lock = threading.Lock()
# 每线程独立连接（回归 S-0912-0040）：共享一条连接时，Python sqlite3 对并发
# execute 并不安全——语句缓存与参数绑定状态会被并发重置，实测稳定复现
# InterfaceError: bad parameter or other API misuse 与 IndexError: tuple index
# out of range（SQLite 序列化模式只保护单次 C API 调用，兜不住 Python 层的
# 多步执行序列）。WAL 下多连接读写互不阻塞，写侧由 tx() 全局写锁串行。
_local = threading.local()

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
    (
        10,
        """
        -- 语气学习（Tone DNA）退役 → 每账号可编辑的「文风提示词」：
        -- 黑盒自动学习改为用户手写、完全透明；已生成的语气描述原样转存（可改可清）
        ALTER TABLE accounts ADD COLUMN style_prompt TEXT;
        UPDATE accounts SET style_prompt = tone_dna
         WHERE tone_dna IS NOT NULL AND TRIM(tone_dna) != '';
        ALTER TABLE accounts DROP COLUMN tone_dna;
        """,
    ),
    (
        11,
        """
        -- 语气学习功能已退役（v10），残留的历史用量日志一并清除，AI 用量页不再展示该行
        DELETE FROM ai_logs WHERE task_type = 'tone_dna';
        """,
    ),
    (
        12,
        """
        -- 长任务执行器（IMPROVEMENT_PLAN §3.4）：AI 整理、批量 IMAP 动作等
        -- 提交后立即返回 job_id，进度/结果入表，前端经 /api/jobs/* 轮询
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kind        TEXT NOT NULL,               -- organize | imap_batch | ...
            account_id  INTEGER,
            status      TEXT NOT NULL DEFAULT 'running',  -- running | done | failed
            progress    REAL NOT NULL DEFAULT 0,     -- 0..1
            stage       TEXT NOT NULL DEFAULT '',    -- 阶段标识
            detail      TEXT NOT NULL DEFAULT '',    -- 面向用户的阶段明细/错误文案
            result_json TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_active ON jobs(status, updated_at DESC);
        """,
    ),
    (
        13,
        """
        -- Gmail / Outlook OAuth2（XOAUTH2）登录：auth_type 区分密码与 OAuth 账号，
        -- oauth_provider 记录服务商（gmail/outlook）；令牌本体存 secrets.json（oauth_token:*）
        ALTER TABLE accounts ADD COLUMN auth_type TEXT NOT NULL DEFAULT 'password';
        ALTER TABLE accounts ADD COLUMN oauth_provider TEXT NOT NULL DEFAULT '';
        """,
    ),
    (
        14,
        """
        -- 账号级「走代理」开关：被墙服务商（Gmail/Outlook）的 IMAP/SMTP 经全局代理
        -- 地址（settings.network_proxy）连接；地址本体只存一份，账号行只存开关
        ALTER TABLE accounts ADD COLUMN use_proxy INTEGER NOT NULL DEFAULT 0;
        """,
    ),
    (
        15,
        """
        -- v0.4 P2 资源管理器（REDESIGN_PLAN §4/§4.6）：服务器文件夹本地缓存 +
        -- 每账号服务器端归档文件夹；archived_local 语义变为「待服务器归档」暂存标记
        CREATE TABLE IF NOT EXISTS folders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id  INTEGER NOT NULL,
            name        TEXT NOT NULL,
            delim       TEXT NOT NULL DEFAULT '/',
            special_use TEXT,                -- sent|drafts|junk|trash|all|flagged|NULL
            subscribed  INTEGER NOT NULL DEFAULT 1,
            synced_at   TEXT,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(account_id, name)
        );
        ALTER TABLE accounts ADD COLUMN archive_folder TEXT NOT NULL DEFAULT 'Archived';
        -- 存量本地归档需用户决定是否迁移到服务器 Archived（REDESIGN_PLAN §4.6）；
        -- 全新安装无存量则不落此标记（默认即可自动归档）
        INSERT INTO settings (key, value)
        SELECT 'archive_migrate_done', '0'
        WHERE EXISTS (SELECT 1 FROM emails WHERE archived_local = 1);
        """,
    ),
]


def get_conn() -> sqlite3.Connection:
    """当前线程的连接（懒创建，线程内复用）。"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(get_db_path(), check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")  # WAL 推荐档：免逐提交 fsync，断电只丢最后事务不损库
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")  # 跨进程写冲突（如另开 CLI）兜底等待
        _local.conn = conn
    return conn


def close_thread_conn() -> None:
    """关闭并丢弃当前线程的连接——一次性线程（如同步线程）收尾时防连接泄漏。"""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        _local.conn = None
        with suppress(sqlite3.Error):
            conn.close()


_write_lock = threading.Lock()


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    """写事务：进程内全局写锁 + BEGIN IMMEDIATE；成功提交、异常回滚。

    多语句原子性的显式入口（autocommit 连接不会自动开事务）；
    读操作照旧直接 get_conn()（WAL 下读写不互斥）。
    """
    with _write_lock:
        conn = get_conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            with suppress(sqlite3.OperationalError):
                conn.execute("ROLLBACK")  # 事务已被 SQLite 自动回滚时忽略
            raise


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
                    dt = dt.replace(tzinfo=UTC)
                sort_val = dt.astimezone(UTC).isoformat(timespec="seconds")
            except ValueError:
                continue
            conn.execute("UPDATE emails SET date_sort = ? WHERE id = ?", (sort_val, row["id"]))
        conn.commit()


def cleanup_retention() -> None:
    """启动时保留策略（IMPROVEMENT_PLAN R7）：notifications 最多 500 条、
    ai_logs 最多 90 天——本地单机库防无界增长。幂等，随启动执行。"""
    conn = get_conn()
    conn.execute(
        "DELETE FROM notifications WHERE id NOT IN"
        " (SELECT id FROM notifications ORDER BY id DESC LIMIT 500)"
    )
    conn.execute("DELETE FROM ai_logs WHERE created_at < datetime('now', '-90 days')")


def get_setting(key: str, default: Any = None) -> Any:
    row = get_conn().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None or row["value"] is None:
        return default
    try:
        return json.loads(row["value"])
    except (ValueError, TypeError):
        # 表单值损坏时回退默认，避免所有读取该设置的请求 500
        return default


def set_setting(key: str, value: Any) -> None:
    with _lock:
        get_conn().execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET"
            " value = excluded.value, updated_at = datetime('now')",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        get_conn().commit()
