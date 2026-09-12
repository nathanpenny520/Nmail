"""服务器文件夹缓存与 CRUD（v0.4 P2，REDESIGN_PLAN §4）。

服务器文件夹为真：LIST/CREATE/RENAME/DELETE 直接作用于 IMAP，本地 folders 表
只做缓存（加速树渲染与按需同步）。特殊文件夹识别优先 RFC 6154 SPECIAL-USE
标记，缺失时按名称启发式兜底（覆盖中文服务商）；「全部邮件」类超大文件夹
（Gmail [Gmail]/All Mail）仅标记不同步。归档语义见 ensure_archive_folder。
"""
from __future__ import annotations

import shutil
import logging

from app.config import get_data_dir
from app.core import imap_client, mailbox
from app.db.database import get_conn

logger = logging.getLogger(__name__)

DEFAULT_ARCHIVE_FOLDER = "Archived"

# SPECIAL-USE 标记 → 规范名（小写匹配）
_FLAG_MAP = {
    "\\sent": "sent",
    "\\drafts": "drafts",
    "\\junk": "junk",
    "\\trash": "trash",
    "\\all": "all",
    "\\flagged": "flagged",
}
# 名称启发式兜底（子串匹配；不识别 archive——避免误把用户普通文件夹标成不可删）
_NAME_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("sent", ("sent", "已发送")),
    ("drafts", ("draft", "草稿")),
    ("junk", ("junk", "spam", "垃圾")),
    ("trash", ("trash", "deleted", "已删除", "废纸")),
    ("all", ("all mail", "全部邮件")),
]


class FolderError(Exception):
    """文件夹操作业务错误（API 层按 status 转 HTTP）。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def detect_special_use(name: str, flags: list[str]) -> str | None:
    lowered_flags = {str(f).lower() for f in flags}
    for flag, key in _FLAG_MAP.items():
        if flag in lowered_flags:
            return key
    name_l = (name or "").lower()
    for key, hints in _NAME_HINTS:
        if any(h in name_l for h in hints):
            return key
    return None


def archive_folder_name(account_id: int) -> str:
    row = get_conn().execute(
        "SELECT archive_folder FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    return (row["archive_folder"] if row and row["archive_folder"] else DEFAULT_ARCHIVE_FOLDER)


def cached_list(account_id: int) -> list[dict]:
    """folders 缓存行（含 is_system / is_archive 派生标记与未读数，供前端树渲染）。"""
    account = get_conn().execute(
        "SELECT archive_folder FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    archive_name = (
        account["archive_folder"] if account and account["archive_folder"] else DEFAULT_ARCHIVE_FOLDER
    )
    rows = get_conn().execute(
        "SELECT name, delim, special_use, subscribed FROM folders"
        " WHERE account_id = ? ORDER BY name",
        (account_id,),
    ).fetchall()
    unread = {
        r["folder"]: r["n"]
        for r in get_conn().execute(
            "SELECT folder, COUNT(*) n FROM emails"
            " WHERE account_id = ? AND is_read = 0 AND archived_local = 0 GROUP BY folder",
            (account_id,),
        ).fetchall()
    }
    return [
        {
            "name": r["name"],
            "delim": r["delim"],
            "special_use": r["special_use"],
            "subscribed": bool(r["subscribed"]),
            "is_system": r["name"].upper() == "INBOX" or bool(r["special_use"]),
            "is_archive": r["name"] == archive_name,
            "unread": unread.get(r["name"], 0),
        }
        for r in rows
    ]


def refresh_cache(account_id: int) -> list[dict]:
    """IMAP LIST 刷新 folders 缓存（服务器增删文件夹以服务器为准），返回缓存列表。"""
    handle = mailbox.load_account(account_id)
    with mailbox.open_imap(handle) as mb:
        listing = imap_client.list_folders(mb)
    if not listing:
        # 空 LIST（网络抖动/异常响应）不清缓存：宁用旧数据，勿把本地文件夹全部 purge（审查 C4）
        logger.warning("refresh_cache: 账号 %s 的 LIST 返回空，保留本地文件夹缓存", account_id)
        return cached_list(account_id)
    conn = get_conn()
    seen: set[str] = set()
    for item in listing:
        name = str(item["name"])
        seen.add(name)
        conn.execute(
            "INSERT INTO folders (account_id, name, delim, special_use, synced_at)"
            " VALUES (?, ?, ?, ?, datetime('now'))"
            " ON CONFLICT(account_id, name) DO UPDATE SET delim = excluded.delim,"
            " special_use = excluded.special_use, synced_at = excluded.synced_at,"
            " updated_at = datetime('now')",
            (account_id, name, item["delim"] or "/", detect_special_use(name, item["flags"])),
        )
    for name in conn.execute(
        "SELECT name FROM folders WHERE account_id = ?", (account_id,)
    ).fetchall():
        if name["name"] not in seen:
            purge_local_folder(account_id, name["name"], cleanup_attachments=False)
    conn.commit()
    return cached_list(account_id)


def get_list(account_id: int, refresh: bool = False) -> list[dict]:
    """树数据源：优先缓存；缓存为空或显式 refresh 时连服务器刷新。"""
    if refresh or not cached_list(account_id):
        return refresh_cache(account_id)
    return cached_list(account_id)


def create_folder(account_id: int, name: str) -> dict:
    name = (name or "").strip().rstrip("/")
    if not name or name.upper() == "INBOX":
        raise FolderError("文件夹名不合法")
    handle = mailbox.load_account(account_id)
    with mailbox.open_imap(handle) as mb:
        if mb.folder.exists(name):
            raise FolderError(f"文件夹「{name}」已存在")
        if not mb.folder.create(name):
            raise FolderError("服务器拒绝创建文件夹", 502)
    refresh_cache(account_id)
    return {"ok": True, "name": name}


def rename_folder(account_id: int, old: str, new: str) -> dict:
    new = (new or "").strip().rstrip("/")
    if not new or new.upper() == "INBOX" or new == old:
        raise FolderError("新名称不合法")
    if folder_guard(account_id, old):
        raise FolderError(folder_guard(account_id, old))
    handle = mailbox.load_account(account_id)
    with mailbox.open_imap(handle) as mb:
        if not mb.folder.rename(old, new):
            raise FolderError("服务器拒绝重命名文件夹", 502)
    # RENAME 后服务器保留 UID 与 UIDVALIDITY——本地缓存/邮件/断点跟随改名
    conn = get_conn()
    conn.execute(
        "UPDATE folders SET name = ?, updated_at = datetime('now')"
        " WHERE account_id = ? AND name = ?",
        (new, account_id, old),
    )
    conn.execute(
        "UPDATE emails SET folder = ? WHERE account_id = ? AND folder = ?",
        (new, account_id, old),
    )
    conn.execute(
        "UPDATE sync_state SET folder = ? WHERE account_id = ? AND folder = ?",
        (new, account_id, old),
    )
    conn.commit()
    return {"ok": True, "name": new}


def delete_folder(account_id: int, name: str) -> dict:
    if name.upper() == "INBOX":
        raise FolderError("收件箱不可删除")
    if folder_guard(account_id, name):
        raise FolderError(folder_guard(account_id, name))
    handle = mailbox.load_account(account_id)
    with mailbox.open_imap(handle) as mb:
        if not mb.folder.delete(name):
            raise FolderError("服务器拒绝删除文件夹", 502)
    purge_local_folder(account_id, name)
    return {"ok": True}


def folder_guard(account_id: int, name: str) -> str | None:
    """系统文件夹守卫：返回不可操作的原因，None=允许改删。"""
    if name.upper() == "INBOX":
        return "收件箱不可改名或删除"
    row = get_conn().execute(
        "SELECT special_use FROM folders WHERE account_id = ? AND name = ?",
        (account_id, name),
    ).fetchone()
    if row and row["special_use"] and row["special_use"] != "flagged":
        return "系统文件夹不可改名或删除"
    return None


def ensure_archive_folder(account_id: int) -> str:
    """确保该账号的服务器端归档文件夹存在，返回其名字（首次归档时惰性创建）。"""
    target = archive_folder_name(account_id)
    handle = mailbox.load_account(account_id)
    with mailbox.open_imap(handle) as mb:
        ensure_archive_with_mb(mb, account_id, target)
    return target


def ensure_archive_with_mb(mb, account_id: int, target: str | None = None) -> str:  # noqa: ANN001
    """在已打开的 IMAP 连接上确保归档文件夹存在（批量移动复用连接时用），返回名字。"""
    target = target or archive_folder_name(account_id)
    if not mb.folder.exists(target) and not mb.folder.create(target):
        raise FolderError(f"服务器拒绝创建归档文件夹「{target}」", 502)
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO folders (account_id, name, delim, special_use, synced_at)"
        " VALUES (?, ?, '/', NULL, datetime('now'))",
        (account_id, target),
    )
    conn.commit()
    return target


def purge_local_folder(account_id: int, name: str, cleanup_attachments: bool = True) -> None:
    """删除/服务器消失的文件夹：清理本地缓存行、邮件行、同步断点与附件目录。"""
    conn = get_conn()
    stale_ids = [
        int(r["id"])
        for r in conn.execute(
            "SELECT id FROM emails WHERE account_id = ? AND folder = ?",
            (account_id, name),
        ).fetchall()
    ]
    conn.execute("DELETE FROM emails WHERE account_id = ? AND folder = ?",
                 (account_id, name))
    conn.execute("DELETE FROM sync_state WHERE account_id = ? AND folder = ?",
                 (account_id, name))
    conn.execute("DELETE FROM folders WHERE account_id = ? AND name = ?", (account_id, name))
    conn.commit()
    if cleanup_attachments and stale_ids:
        att_base = get_data_dir() / "accounts" / str(account_id) / "attachments"
        for eid in stale_ids:
            shutil.rmtree(att_base / str(eid), ignore_errors=True)
    if stale_ids:
        logger.info("purged folder %s of account %s: %d emails", name, account_id, len(stale_ids))
