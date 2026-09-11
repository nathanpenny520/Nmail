"""新邮件 AI 流水线。

顺序（对应 docs/PRODUCT_PLAN.md §6）：
白/黑名单（0 成本）→ AI 批量分类 → 营销自动归档 → 按账号权限生成回复草稿 → 通知。
AI 未配置时静默跳过智能步骤（诚实降级：邮件照常进收件箱）。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from app.ai import tasks
from app.ai.categories import AUTO_ARCHIVE_CATEGORIES
from app.core.sync import add_notification
from app.db.database import get_conn

logger = logging.getLogger(__name__)

CLASSIFY_BATCH_SIZE = 20
BODY_HEAD_CHARS = 600
NOREPLY_RE = re.compile(r"no-?reply|donotreply|mailer-daemon", re.IGNORECASE)


def get_sender_lists() -> dict[str, list[str]]:
    rows = get_conn().execute("SELECT pattern, list_type FROM sender_lists").fetchall()
    out: dict[str, list[str]] = {"whitelist": [], "blacklist": []}
    for r in rows:
        out.setdefault(r["list_type"], []).append(r["pattern"].strip().lower())
    return out


def match_sender_list(sender_email: str, lists: dict[str, list[str]]) -> str | None:
    """返回命中的列表类型；条目以 @ 开头表示域名匹配，否则精确匹配。"""
    email = (sender_email or "").strip().lower()
    if not email:
        return None
    for list_type in ("whitelist", "blacklist"):
        for pattern in lists.get(list_type, []):
            if pattern.startswith("@"):
                if email.endswith(pattern) or email.split("@")[-1] == pattern[1:]:
                    return list_type
            elif email == pattern:
                return list_type
    return None


def _body_head(row) -> str:  # noqa: ANN001
    text = (row["body_text"] or "").strip()
    if not text:
        text = BeautifulSoup(row["body_html"] or "", "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:BODY_HEAD_CHARS]


def _apply_classification(results: list[dict]) -> tuple[int, int]:
    """写回分类结果，执行营销自动归档。返回 (归档数, 需回复数)。"""
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    archived = 0
    need_reply = 0
    for r in results:
        to_archive = 1 if r["category"] in AUTO_ARCHIVE_CATEGORIES else 0
        conn.execute(
            "UPDATE emails SET category = ?, importance = ?, needs_reply = ?,"
            " reply_reason = ?, ai_classified_at = ?,"
            " archived_local = CASE WHEN ? = 1 THEN 1 ELSE archived_local END"
            " WHERE id = ?",
            (r["category"], r["importance"], 1 if r["needs_reply"] else 0,
             r["reason"], now, to_archive, r["id"]),
        )
        archived += to_archive
        need_reply += 1 if r["needs_reply"] else 0
    conn.commit()
    return archived, need_reply


def process_new_emails(account: dict, email_ids: list[int]) -> None:
    """同步完成后对新邮件执行智能处理；任何 AI 失败都不影响同步本身。"""
    if not email_ids:
        return
    account_id = int(account["id"])
    conn = get_conn()
    placeholders = ",".join("?" for _ in email_ids)
    rows = conn.execute(
        f"SELECT id, folder, subject, sender_name, sender_email, body_text, body_html"
        f" FROM emails WHERE id IN ({placeholders})",
        email_ids,
    ).fetchall()

    lists = get_sender_lists()
    whitelisted = 0
    blacklisted = 0
    to_classify: list[dict] = []
    for row in rows:
        hit = match_sender_list(row["sender_email"], lists)
        if hit == "whitelist":
            whitelisted += 1
            continue  # 直接留在收件箱，跳过 AI
        if hit == "blacklist":
            conn.execute("UPDATE emails SET archived_local = 1 WHERE id = ?", (row["id"],))
            conn.commit()
            blacklisted += 1
            continue
        to_classify.append({
            "id": row["id"],
            "subject": row["subject"],
            "sender": f'{row["sender_name"]} <{row["sender_email"]}>',
            "body_head": _body_head(row),
            "folder": row["folder"],
            "sender_email": row["sender_email"],
        })

    if blacklisted > 0:
        add_notification("ai_archive", f"黑名单过滤：{blacklisted} 封邮件已自动归档", "", str(account_id))

    if not to_classify:
        return

    try:
        archived_by_ai = 0
        draft_emails: list = []
        for start in range(0, len(to_classify), CLASSIFY_BATCH_SIZE):
            batch = to_classify[start : start + CLASSIFY_BATCH_SIZE]
            try:
                results = tasks.classify_batch(batch, account_id=account_id)
            except Exception as exc:  # noqa: BLE001 — 分类失败跳过该批
                logger.warning("classify batch failed: %s", exc)
                continue
            archived_count, _need = _apply_classification(results)
            archived_by_ai += archived_count

            result_map = {r["id"]: r for r in results}
            for item in batch:
                r = result_map.get(item["id"])
                if r and r["needs_reply"] and item["folder"] == "INBOX" \
                        and not NOREPLY_RE.search(item["sender_email"]):
                    draft_emails.append(item)

        if archived_by_ai > 0:
            add_notification(
                "ai_archive",
                f"AI 已归档 {archived_by_ai} 封营销邮件",
                "可在「已归档」页查看与恢复",
                str(account_id),
            )

        _generate_drafts(account, draft_emails)
    except tasks.AINotConfigured:
        pass  # 未配置 AI：诚实降级，邮件留在收件箱
    except Exception:  # noqa: BLE001
        logger.exception("pipeline failed for account %s", account_id)


def _generate_drafts(account: dict, items: list[dict]) -> None:
    """为需要回复的邮件生成待审草稿（账号权限 gate：readonly 不生成）。"""
    if not items:
        return
    conn = get_conn()
    perm_row = conn.execute(
        "SELECT ai_permission FROM accounts WHERE id = ?", (account["id"],)
    ).fetchone()
    if not perm_row or perm_row["ai_permission"] == "readonly":
        return

    my_email = account["email"]
    created = 0
    for item in items:
        exists = conn.execute(
            "SELECT 1 FROM drafts WHERE email_id = ? AND status = 'pending'",
            (item["id"],),
        ).fetchone()
        if exists:
            continue
        row = conn.execute("SELECT * FROM emails WHERE id = ?", (item["id"],)).fetchone()
        if not row:
            continue
        try:
            content = tasks.generate_reply_draft(row, my_email, account_id=int(account["id"]))
        except Exception as exc:  # noqa: BLE001 — 单封草稿失败不影响其他
            logger.warning("draft generation failed for email %s: %s", item["id"], exc)
            continue
        conn.execute(
            "INSERT INTO drafts (email_id, account_id, content, origin) VALUES (?, ?, ?, 'ai')",
            (item["id"], account["id"], content),
        )
        conn.commit()
        created += 1
        add_notification(
            "ai_draft",
            "已生成回复草稿待审",
            f'{row["subject"][:60]}',
            str(item["id"]),
        )
    if created > 0:
        add_notification(
            "ai_draft_summary",
            f"AI 为 {created} 封邮件生成了回复草稿",
            "到「待审草稿」页审核发送",
            str(account["id"]),
        )


def classify_missing(account_id: int, folder: str = "INBOX", limit: int = 200) -> dict:
    """手动触发：为未分类的历史邮件补跑分类（「AI 整理」按钮）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, subject, sender_name, sender_email, body_text, body_html"
        " FROM emails WHERE account_id = ? AND folder = ? AND ai_classified_at IS NULL"
        " ORDER BY date DESC LIMIT ?",
        (account_id, folder, limit),
    ).fetchall()
    if not rows:
        return {"classified": 0, "archived": 0, "drafts": 0, "skipped_no_ai": False}

    lists = get_sender_lists()
    to_classify = []
    for row in rows:
        if match_sender_list(row["sender_email"], lists):
            continue
        to_classify.append({
            "id": row["id"],
            "subject": row["subject"],
            "sender": f'{row["sender_name"]} <{row["sender_email"]}>',
            "body_head": _body_head(row),
            "folder": folder,
            "sender_email": row["sender_email"],
        })

    try:
        tasks._ai_config()
    except tasks.AINotConfigured:
        return {"classified": 0, "archived": 0, "drafts": 0, "skipped_no_ai": True}

    classified = 0
    archived = 0
    for start in range(0, len(to_classify), CLASSIFY_BATCH_SIZE):
        batch = to_classify[start : start + CLASSIFY_BATCH_SIZE]
        try:
            results = tasks.classify_batch(batch, account_id=account_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("organize classify failed: %s", exc)
            continue
        arch, _ = _apply_classification(results)
        classified += len(results)
        archived += arch
    return {"classified": classified, "archived": archived, "drafts": 0, "skipped_no_ai": False}
