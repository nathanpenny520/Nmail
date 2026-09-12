"""AI 总管家工具集（v0.4 P6，REDESIGN_PLAN §6.2/§6.3）。

薄壳原则：全部转调既有能力（emails 查询、core/batch_ops、core/folders、
core/outbox、core/contacts、jobs），agent 层不写新的邮件操作实现。
工具白名单即安全边界——**明确不提供**任意 HTTP/文件系统/命令类工具（§6.3）。

写类工具的权限门控在 agent 循环里做（grant 缺一拒绝）；此处只管执行与结果
摘要（给模型回灌 + 给用户展示的中文一句话）。summarize/translate 不设工具：
模型拿到 read_email 正文后自己完成（少一层无谓调用）。
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from app.core import contacts as contacts_core
from app.core import folders as folders_core
from app.core import imap_client, jobs, mailbox
from app.db.database import get_conn

MAX_LIST = 20


@dataclass(frozen=True)
class ToolSpec:
    name: str
    kind: str            # read | write
    grant: str           # read | draft | organize | send | delete
    description: str     # 进系统提示词的一句话说明
    params: str          # 参数说明（prompt 用）
    run: Callable[[dict, int, list[int]], dict]  # (args, 主账号 id, 会话范围账号) → 结果 dict


def _email_rows(ids: list[int]) -> list:
    if not ids:
        return []
    ph = ",".join("?" for _ in ids)
    return get_conn().execute(
        f"SELECT id, account_id, folder, uid, subject, sender_name, sender_email, is_read,"
        f" starred, snippet FROM emails WHERE id IN ({ph})",
        ids,
    ).fetchall()


def _scope_guard(rows: list, account_ids: list[int]) -> None:
    """越界防护：操作的邮件必须属于会话范围账号（宁紧勿松）。"""
    for r in rows:
        if r["account_id"] not in account_ids:
            raise PermissionError("部分邮件不在当前会话的账号范围内，已拒绝执行")


# ── 读类工具 ────────────────────────────────────────────────────

def _t_search(args: dict, primary: int, scope: list[int]) -> dict:
    q = str(args.get("q") or "").strip()
    account_id = args.get("account_id") or primary
    limit = min(int(args.get("limit") or 10), MAX_LIST)
    where, params = ["e.archived_local = 0"], []
    if q:
        if len(q) >= 3:
            where.append("e.id IN (SELECT rowid FROM emails_fts WHERE emails_fts MATCH ?)")
            params.append(f'"{q.replace(chr(34), chr(34) * 2)}"')
        else:
            like = f"%{q}%"
            where.append("(e.subject LIKE ? OR e.body_text LIKE ? OR e.sender_email LIKE ?)")
            params += [like, like, like]
    if account_id:
        where.append("e.account_id = ?")
        params.append(account_id)
        where.append("e.folder = 'INBOX'")
    rows = get_conn().execute(
        "SELECT e.id, e.subject, e.sender_name, e.sender_email, e.date, e.snippet, e.is_read"
        " FROM emails e WHERE " + " AND ".join(where) +
        " ORDER BY COALESCE(e.date_sort, e.date) IS NULL, COALESCE(e.date_sort, e.date) DESC"
        " LIMIT ?", [*params, limit],
    ).fetchall()
    return {"count": len(rows), "emails": [
        {"id": r["id"], "subject": r["subject"], "from": r["sender_name"] or r["sender_email"],
         "date": r["date"], "snippet": r["snippet"][:80], "unread": not r["is_read"]}
        for r in rows]}


def _t_list_recent(args: dict, primary: int, scope: list[int]) -> dict:
    account_id = args.get("account_id") or primary
    folder = str(args.get("folder") or "INBOX")
    limit = min(int(args.get("limit") or 10), MAX_LIST)
    rows = get_conn().execute(
        "SELECT id, subject, sender_name, sender_email, date, snippet, is_read FROM emails"
        " WHERE account_id = ? AND folder = ? AND archived_local = 0"
        " ORDER BY COALESCE(date_sort, date) IS NULL, COALESCE(date_sort, date) DESC LIMIT ?",
        (account_id, folder, limit),
    ).fetchall()
    return {"count": len(rows), "emails": [
        {"id": r["id"], "subject": r["subject"], "from": r["sender_name"] or r["sender_email"],
         "date": r["date"], "unread": not r["is_read"]} for r in rows]}


def _t_read_email(args: dict, primary: int, scope: list[int]) -> dict:
    email_id = int(args.get("email_id") or 0)
    rows = _email_rows([email_id])
    _scope_guard(rows, scope)
    if not rows:
        return {"error": "邮件不存在"}
    row = get_conn().execute(
        "SELECT subject, sender_name, sender_email, date, body_text, body_html FROM emails WHERE id = ?",
        (email_id,),
    ).fetchone()
    from app.core.mail_html import html_to_plain_text

    text = (row["body_text"] or "").strip()
    if not text and row["body_html"]:
        text = html_to_plain_text(row["body_html"])
    return {"subject": row["subject"], "from": row["sender_name"] or row["sender_email"],
            "date": row["date"], "body": text[:3000]}


def _t_list_folders(args: dict, primary: int, scope: list[int]) -> dict:
    account_id = args.get("account_id") or primary
    return {"folders": [f["name"] for f in folders_core.cached_list(account_id)]}


def _t_list_contacts(args: dict, primary: int, scope: list[int]) -> dict:
    q = str(args.get("q") or "").strip()
    limit = min(int(args.get("limit") or 15), MAX_LIST)
    where, params = "", []
    if q:
        where = " WHERE email LIKE ? OR name LIKE ?"
        like = f"%{q}%"
        params = [like, like]
    rows = get_conn().execute(
        f"SELECT email, name, use_count, last_seen_at FROM contacts{where}"
        " ORDER BY use_count DESC, last_seen_at DESC LIMIT ?",
        [*params, limit],
    ).fetchall()
    return {"count": len(rows), "contacts": [dict(r) for r in rows]}


def _t_digest_stats(args: dict, primary: int, scope: list[int]) -> dict:
    """邮箱概况统计（仅会话范围账号，防跨账号信息汇总）。"""
    conn = get_conn()
    if not scope:
        return {"收件箱邮件数": 0, "未读": 0, "待回复": 0, "待审草稿": 0, "分类分布": {}}
    ph = ",".join("?" for _ in scope)
    in_scope = f" AND account_id IN ({ph})"

    def stat(sql: str) -> int:
        return int(conn.execute(sql, scope).fetchone()[0] or 0)

    inbox = stat("SELECT COUNT(*) FROM emails WHERE archived_local = 0 AND folder = 'INBOX'" + in_scope)
    unread = stat("SELECT COUNT(*) FROM emails WHERE archived_local = 0 AND folder = 'INBOX' AND is_read = 0" + in_scope)
    need_reply = stat("SELECT COUNT(*) FROM emails WHERE needs_reply = 1 AND archived_local = 0" + in_scope)
    pending = stat("SELECT COUNT(*) FROM user_drafts WHERE status = 'pending_review'" + in_scope)
    by_category = {
        r["category"] or "未分类": r["n"]
        for r in conn.execute(
            "SELECT category, COUNT(*) n FROM emails WHERE archived_local = 0 AND folder = 'INBOX'"
            + in_scope + " GROUP BY category", scope).fetchall()
    }
    return {"收件箱邮件数": inbox, "未读": unread, "待回复": need_reply,
            "待审草稿": pending, "分类分布": by_category}


# ── 写类工具（均返回 undo 信息；agent 层落审计）──────────────────

def _apply_flag(rows: list, flag: str, value: bool) -> dict:
    by_account: dict[int, list] = {}
    for r in rows:
        by_account.setdefault(r["account_id"], []).append(r)
    for aid, acct_rows in by_account.items():
        handle = mailbox.load_account(aid)
        with mailbox.open_imap(handle) as mb:
            by_folder: dict[str, list[str]] = {}
            for r in acct_rows:
                by_folder.setdefault(r["folder"], []).append(str(r["uid"]))
            for folder, uids in by_folder.items():
                mb.folder.set(folder)
                mb.flag(uids, [imap_client.SEEN_FLAG if flag == "read" else imap_client.FLAGGED_FLAG], value)
    ph = ",".join("?" for _ in rows)
    col = "is_read" if flag == "read" else "starred"
    get_conn().execute(
        f"UPDATE emails SET {col} = ? WHERE id IN ({ph})",
        (1 if value else 0, *[r["id"] for r in rows]),
    )
    get_conn().commit()
    return {"updated": len(rows)}


def _t_mark_emails(args: dict, primary: int, scope: list[int]) -> dict:
    ids = [int(i) for i in (args.get("ids") or [])]
    rows = _email_rows(ids)
    _scope_guard(rows, scope)
    undo = [{"id": r["id"], "account_id": r["account_id"], "was": bool(r["is_read"])} for r in rows]
    result = _apply_flag(rows, "read", bool(args.get("read", True)))
    result["undo"] = undo
    return result


def _t_star_emails(args: dict, primary: int, scope: list[int]) -> dict:
    ids = [int(i) for i in (args.get("ids") or [])]
    rows = _email_rows(ids)
    _scope_guard(rows, scope)
    undo = [{"id": r["id"], "account_id": r["account_id"], "was": bool(r["starred"])} for r in rows]
    result = _apply_flag(rows, "star", bool(args.get("star", True)))
    result["undo"] = undo
    return result


def _move_rows(rows: list, dest_provider: Callable[[int], str], label: str) -> dict:
    """逐账号共用连接移动邮件（dest_provider 按账号给出目标文件夹）。"""
    moved, undo, failed = 0, [], 0
    by_account: dict[int, list] = {}
    for r in rows:
        by_account.setdefault(r["account_id"], []).append(r)
    conn = get_conn()
    for aid, acct_rows in by_account.items():
        try:
            handle = mailbox.load_account(aid)
            with mailbox.open_imap(handle) as mb:
                target = dest_provider(aid)
                for r in acct_rows:
                    new_uid = imap_client.move_email(mb, r["folder"], r["uid"], target)
                    if new_uid is None:
                        conn.execute("DELETE FROM emails WHERE id = ?", (r["id"],))
                    else:
                        conn.execute(
                            "UPDATE emails SET folder = ?, uid = ?, archived_local = 0 WHERE id = ?",
                            (target, new_uid, r["id"]),
                        )
                    undo.append({"id": r["id"], "account_id": aid, "from_folder": r["folder"],
                                 "from_uid": r["uid"]})
                    moved += 1
            conn.commit()
        except Exception:  # noqa: BLE001 — 单账号失败不影响其他账号
            failed += len(by_account[aid])
    return {label: moved, "failed": failed, "undo": undo}


def _t_archive_emails(args: dict, primary: int, scope: list[int]) -> dict:
    ids = [int(i) for i in (args.get("ids") or [])]
    rows = _email_rows(ids)
    _scope_guard(rows, scope)
    return _move_rows(rows, folders_core.archive_folder_name, "archived")


def _t_move_emails(args: dict, primary: int, scope: list[int]) -> dict:
    ids = [int(i) for i in (args.get("ids") or [])]
    folder = str(args.get("folder") or "")
    if not folder:
        return {"error": "缺少目标文件夹"}
    rows = _email_rows(ids)
    _scope_guard(rows, scope)
    return _move_rows(rows, lambda _aid: folder, "moved")


def _t_trash_emails(args: dict, primary: int, scope: list[int]) -> dict:
    ids = [int(i) for i in (args.get("ids") or [])]
    rows = _email_rows(ids)
    _scope_guard(rows, scope)
    by_account: dict[int, list] = {}
    for r in rows:
        by_account.setdefault(r["account_id"], []).append(r)
    trashed, failed = 0, 0
    conn = get_conn()
    for aid, acct_rows in by_account.items():
        try:
            handle = mailbox.load_account(aid)
            with mailbox.open_imap(handle) as mb:
                for r in acct_rows:
                    imap_client.trash_email(mb, r["folder"], r["uid"])
                ph = ",".join("?" for _ in acct_rows)
                conn.execute(f"DELETE FROM emails WHERE id IN ({ph})",
                             [r["id"] for r in acct_rows])
            conn.commit()
            trashed += len(acct_rows)
        except Exception:  # noqa: BLE001
            failed += len(acct_rows)
    return {"trashed": trashed, "failed": failed}  # 入废纸篓可服务器端手动恢复，不做 undo


def _t_create_folder(args: dict, primary: int, scope: list[int]) -> dict:
    account_id = args.get("account_id") or primary
    name = str(args.get("name") or "")
    folders_core.create_folder(int(account_id), name)
    return {"created": name}


def _t_create_draft(args: dict, primary: int, scope: list[int]) -> dict:
    """起草回复/新邮件 → 统一草稿表 pending_review（审批后经 outbox 发送）。"""
    to = str(args.get("to") or "").strip()
    subject = str(args.get("subject") or "").strip()
    body = str(args.get("body") or "").strip()
    if not to or not body:
        return {"error": "收件人与正文不能为空"}
    from app.core.mail_html import markdown_to_email_html
    from app.core.imap_client import reply_subject

    email_id = args.get("email_id")
    in_reply_to = None
    if email_id:
        row = _email_rows([int(email_id)])
        _scope_guard(row, scope)
        if row:
            in_reply_to = int(email_id)
            if not subject:
                subject = reply_subject(row[0]["subject"] or "")
    if not subject:
        subject = "（无主题）"
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO user_drafts (account_id, mode, in_reply_to, to_addrs, subject,"
        " body_html, status, origin, instruction)"
        " VALUES (?, 'reply', ?, ?, ?, ?, 'pending_review', 'ai', '总管家起草')",
        (primary, in_reply_to, to, subject, markdown_to_email_html(body)),
    )
    conn.commit()
    return {"draft_id": int(cur.lastrowid), "status": "pending_review",
            "hint": "草稿已进入待审列表，用户批准后发送"}


def _t_send_draft(args: dict, primary: int, scope: list[int]) -> dict:
    """发送待审草稿（自动模式专用直发；审批模式走审批卡后同样到这里）。"""
    from app.core import outbox

    draft_id = int(args.get("draft_id") or 0)
    row = get_conn().execute("SELECT * FROM user_drafts WHERE id = ?", (draft_id,)).fetchone()
    if row is None:
        return {"error": "草稿不存在"}
    if row["account_id"] not in scope:
        raise PermissionError("草稿不属于当前会话的账号范围")
    outbox.send_user_draft(draft_id)
    return {"sent": True, "to": row["to_addrs"], "subject": row["subject"],
            "note": "发送不可撤销"}


def _t_start_organize(args: dict, primary: int, scope: list[int]) -> dict:
    account_id = args.get("account_id") or primary
    job_id = jobs.submit("organize", account_id=int(account_id), folder="INBOX", limit=200)
    return {"job_id": job_id, "hint": "AI 整理已在后台开始，完成后通知"}


TOOLS: dict[str, ToolSpec] = {t.name: t for t in [
    ToolSpec("search_emails", "read", "read",
             "按关键词搜索邮件（标题/正文/发件人，覆盖全部文件夹）",
             '{"q": "关键词", "account_id?": "限定账号", "limit?": "条数≤20"}', _t_search),
    ToolSpec("list_recent_emails", "read", "read",
             "列出某账号某文件夹最近的邮件",
             '{"account_id?": "账号id", "folder?": "默认INBOX", "limit?": "≤20"}', _t_list_recent),
    ToolSpec("read_email", "read", "read",
             "读取一封邮件的正文（截断 3000 字）",
             '{"email_id": "邮件id"}', _t_read_email),
    ToolSpec("list_folders", "read", "read",
             "列出账号的文件夹", '{"account_id?": "账号id"}', _t_list_folders),
    ToolSpec("list_contacts", "read", "read",
             "查通讯录（含往来次数）", '{"q?": "关键词", "limit?": "≤20"}', _t_list_contacts),
    ToolSpec("digest_stats", "read", "read",
             "邮箱概况统计（收件箱/未读/待回复/待审草稿/分类分布）", "{}", _t_digest_stats),
    ToolSpec("mark_emails", "write", "organize",
             "批量标记已读/未读", '{"ids": [邮件id], "read": true|false}', _t_mark_emails),
    ToolSpec("star_emails", "write", "organize",
             "批量加/去星标", '{"ids": [邮件id], "star": true|false}', _t_star_emails),
    ToolSpec("archive_emails", "write", "organize",
             "批量归档（移到该账号服务器端 Archived 文件夹）", '{"ids": [邮件id]}', _t_archive_emails),
    ToolSpec("move_emails", "write", "organize",
             "批量移动到指定文件夹", '{"ids": [邮件id], "folder": "目标文件夹名"}', _t_move_emails),
    ToolSpec("trash_emails", "write", "delete",
             "批量删除（移入废纸篓，高危）", '{"ids": [邮件id]}', _t_trash_emails),
    ToolSpec("create_folder", "write", "organize",
             "在服务器上新建文件夹", '{"account_id?": "账号id", "name": "文件夹名"}', _t_create_folder),
    ToolSpec("create_draft", "write", "draft",
             "起草回复/新邮件（进入待审列表，不会直接发出）",
             '{"email_id?": "回复的邮件id", "to": "收件人", "subject?": "主题", "body": "Markdown 正文"}',
             _t_create_draft),
    ToolSpec("send_draft", "write", "send",
             "发送一条待审草稿（高危；自动模式受收件人白名单与每日限额约束）",
             '{"draft_id": "草稿id"}', _t_send_draft),
    ToolSpec("start_organize", "write", "organize",
             "后台跑一遍 AI 整理（为未分类邮件补分类）", '{"account_id?": "账号id"}', _t_start_organize),
]}


# ── 参数归一化与校验（审查 S1：审批「改参数后批准」原样落库执行）──
# 模型输出与用户手改都可能给错型（如 read:"false" 会被 bool() 当真）。
# 键为参数名，值为期望类型；未列出的参数不校验（工具实现自行忽略）。
_PARAM_TYPES: dict[str, dict[str, str]] = {
    "search_emails": {"q": "str", "limit": "int"},
    "list_recent_emails": {"folder": "str", "limit": "int"},
    "read_email": {"email_id": "int"},
    "list_contacts": {"q": "str", "limit": "int"},
    "mark_emails": {"ids": "ints", "read": "bool"},
    "star_emails": {"ids": "ints", "star": "bool"},
    "archive_emails": {"ids": "ints"},
    "move_emails": {"ids": "ints", "folder": "str"},
    "trash_emails": {"ids": "ints"},
    "create_folder": {"name": "str"},
    "create_draft": {"email_id": "int", "to": "str", "subject": "str", "body": "str"},
    "send_draft": {"draft_id": "int"},
}
_REQUIRED_ARGS: dict[str, tuple[str, ...]] = {
    "read_email": ("email_id",),
    "move_emails": ("folder",),
    "create_folder": ("name",),
    "create_draft": ("to", "body"),
    "send_draft": ("draft_id",),
}


def normalize_args(name: str, args: dict) -> dict:
    """按工具参数表做类型矫正 + 必填校验；失败抛 ValueError（文案可直接回给用户）。

    返回归一化后的新 dict（不改入参）。id/布尔类从严：字符串数字可转，
    布尔只认真值拼写，其余一律拒绝。
    """
    out = dict(args or {})
    for key in _REQUIRED_ARGS.get(name, ()):
        v = out.get(key)
        if v is None or v == "" or v == []:
            raise ValueError(f"缺少必填参数 {key}")
    for key, typ in _PARAM_TYPES.get(name, {}).items():
        if out.get(key) is None:
            continue
        v = out[key]
        try:
            if typ == "int":
                out[key] = int(v)
            elif typ == "ints":
                if isinstance(v, (str, int)):
                    v = [v]
                if not isinstance(v, list):
                    raise ValueError
                out[key] = [int(x) for x in v]
            elif typ == "bool":
                if isinstance(v, str):
                    out[key] = v.strip().lower() in ("1", "true", "yes", "y", "是")
                else:
                    out[key] = bool(v)
            elif typ == "str":
                out[key] = str(v)
        except (TypeError, ValueError):
            raise ValueError(f"参数 {key} 的类型应为 {typ}") from None
    return out


def execute(name: str, args: dict, primary_account: int,
            account_ids: list[int] | None = None) -> dict:
    """执行工具并返回结果；未知工具/异常统一为结构化错误。

    account_ids 为会话范围账号（agent 循环传整组；审批/撤销等单账号场景
    缺省回落 [主账号]）。args 里的 account_id 必须落在范围内，缺省回落
    主账号——模型传任意账号 id 的越权读取/操作（审查 F2）在此统一收口。
    """
    spec = TOOLS.get(name)
    if spec is None:
        return {"error": f"未知工具：{name}"}
    scope = [int(a) for a in (account_ids if account_ids is not None
                              else ([primary_account] if primary_account else []))]
    args = dict(args or {})
    if args.get("account_id") is not None:
        try:
            aid = int(args["account_id"])
        except (TypeError, ValueError):
            return {"error": "account_id 需为整数"}
        if aid not in scope:
            return {"error": "账号不在当前会话范围内，已拒绝执行"}
        args["account_id"] = aid
    try:
        args = normalize_args(name, args)
    except ValueError as exc:
        return {"error": f"参数校验失败：{exc}"}
    try:
        return spec.run(args, primary_account, scope)
    except PermissionError as exc:
        return {"error": str(exc)}
    except mailbox.MailError as exc:
        return {"error": exc.message}
    except Exception as exc:  # noqa: BLE001 — 工具失败回灌给模型而非崩掉会话
        return {"error": f"{type(exc).__name__}: {exc}"[:300]}


def resolve_grants(account_ids: list[int]) -> set[str]:
    """会话范围的授权交集（宁紧勿松）；空名单=无任何授权。

    ai_grants 缺失（理论上 v17 已回填）时按旧 ai_permission 枚举兜底。
    """
    if not account_ids:
        return set()
    grants: set[str] | None = None
    conn = get_conn()
    ph = ",".join("?" for _ in account_ids)
    for row in conn.execute(
        f"SELECT ai_grants, ai_permission FROM accounts WHERE id IN ({ph})", account_ids
    ).fetchall():
        raw = row["ai_grants"]
        if raw:
            import json

            try:
                own = {k for k, v in json.loads(raw).items() if v}
            except ValueError:
                own = set()
        else:
            own = {"read"} if row["ai_permission"] == "readonly" else {"read", "draft", "organize"}
        grants = own if grants is None else (grants & own)
    return grants or set()


def recipient_allowed(to_addrs: str, account_id: int) -> tuple[bool, str]:
    """自动发送的收件人约束（§6.6）：必须 ∈ 通讯录 ∪ 历史往来。

    防邮件正文注入的地址被直接外发。返回 (是否允许, 原因)。
    """
    conn = get_conn()
    for addr in contacts_core.extract_addresses(to_addrs):
        row = conn.execute("SELECT 1 FROM contacts WHERE email = ?", (addr,)).fetchone()
        if row:
            continue
        hit = conn.execute(
            "SELECT 1 FROM emails WHERE account_id = ? AND (sender_email = ? OR recipients LIKE ?) LIMIT 1",
            (account_id, addr, f"%{addr}%"),
        ).fetchone()
        if not hit:
            return False, f"收件人 {addr} 不在通讯录与历史往来中（自动模式拒绝外发）"
    return True, ""
