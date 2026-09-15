"""批量 IMAP 动作（trash/move/archive/unarchive）的任务体（IMPROVEMENT_PLAN §3.4）。

从 api/emails.batch_action 的同步实现迁移为 job：按账号分组共用连接逐账号
执行并上报进度；「服务器成功才动本地」的先后关系与 R2 语义（拿不到新 UID
删行交增量重建）保持不变。打标类快操作仍在端点内同步执行。
v0.4：archive=逐账号移到服务器端归档文件夹（REDESIGN_PLAN §4.6），
unarchive=移回收件箱。
"""
from __future__ import annotations

from app.core import folders, imap_client, jobs, mailbox, rule_proposals
from app.db.database import get_conn


@jobs.runner("imap_batch")
def imap_batch_job(job_id: int, ids: list[int], action: str, folder: str | None = None,
                   account_id: int | None = None) -> dict:
    """trash/move/archive/unarchive 任务体：返回 {updated, failed}，进度按账号上报。"""
    conn = get_conn()
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT e.id, e.account_id, e.folder, e.uid, e.sender_email FROM emails e"
        f" WHERE e.id IN ({placeholders})",
        ids,
    ).fetchall()

    by_account: dict[int, list] = {}
    for r in rows:
        by_account.setdefault(r["account_id"], []).append(r)

    updated = 0
    failed = 0
    total = max(1, len(by_account))
    for index, (aid, account_rows) in enumerate(by_account.items()):
        try:
            handle = mailbox.load_account(aid)
            with mailbox.open_imap(handle) as mb:
                if action == "trash":
                    for r in account_rows:
                        imap_client.trash_email(mb, r["folder"], r["uid"])
                    id_list = [r["id"] for r in account_rows]
                    ph = ",".join("?" for _ in id_list)
                    conn.execute(f"DELETE FROM emails WHERE id IN ({ph})", id_list)
                elif action == "move":
                    for r in account_rows:
                        new_uid = imap_client.move_email(mb, r["folder"], r["uid"], folder or "")
                        if new_uid is None:
                            # 拿不到新 UID 时旧 uid 写进新文件夹会撞 UNIQUE 且被
                            # 增量跳过——删本地行交增量重建（R2 语义）
                            conn.execute("DELETE FROM emails WHERE id = ?", (r["id"],))
                        else:
                            conn.execute(
                                "UPDATE emails SET folder = ?, uid = ? WHERE id = ?",
                                (folder, new_uid, r["id"]),
                            )
                elif action == "archive":
                    target = folders.ensure_archive_with_mb(mb, aid)
                    for r in account_rows:
                        if r["folder"] == target:
                            conn.execute(
                                "UPDATE emails SET archived_local = 0 WHERE id = ?", (r["id"],)
                            )
                            continue
                        new_uid = imap_client.move_email(mb, r["folder"], r["uid"], target)
                        if new_uid is None:
                            conn.execute("DELETE FROM emails WHERE id = ?", (r["id"],))
                        else:
                            conn.execute(
                                "UPDATE emails SET folder = ?, uid = ?, archived_local = 0"
                                " WHERE id = ?",
                                (target, new_uid, r["id"]),
                            )
                elif action == "unarchive":
                    for r in account_rows:
                        if r["folder"] == "INBOX":
                            conn.execute(
                                "UPDATE emails SET archived_local = 0 WHERE id = ?", (r["id"],)
                            )
                            continue
                        new_uid = imap_client.move_email(mb, r["folder"], r["uid"], "INBOX")
                        if new_uid is None:
                            conn.execute("DELETE FROM emails WHERE id = ?", (r["id"],))
                        else:
                            conn.execute(
                                "UPDATE emails SET folder = 'INBOX', uid = ?, archived_local = 0"
                                " WHERE id = ?",
                                (new_uid, r["id"]),
                            )
            conn.commit()
            updated += len(account_rows)
            if action in ("archive", "trash"):
                # §18.5 规则提议：观察用户手动归档/删除（sender 已在移动/删除前快照）
                rule_proposals.observe(
                    [{"id": r["id"], "account_id": aid, "sender_email": r["sender_email"]}
                     for r in account_rows], action)
        except Exception:  # noqa: BLE001 — 单账号失败不影响其他账号
            failed += len(account_rows)
        jobs.report(job_id, stage=action, progress=(index + 1) / total,
                    detail=f"账号 {index + 1}/{total}")
    return {"updated": updated, "failed": failed}
