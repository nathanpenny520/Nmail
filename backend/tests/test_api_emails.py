"""API 层测试：list_emails 筛选矩阵与 batch 归档往返（IMPROVEMENT_PLAN T1）。

TestClient 以 127.0.0.1 为 Host——经 S1 本机来源校验中间件放行。
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.db import database
from app.main import app

client = TestClient(app, base_url="http://127.0.0.1")

database.run_migrations()  # TestClient 不触发 lifespan，迁移在此显式补跑

_counter = {"n": 0}


def _seed_account() -> int:
    _counter["n"] += 1
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port) VALUES (?, 'imap.test', 993)",
        (f"t{uuid.uuid4().hex[:8]}@example.com",),
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_email(account_id: int, uid: int, subject: str, **extra) -> int:
    conn = database.get_conn()
    cols: dict = {
        "account_id": account_id, "folder": "INBOX", "uid": uid,
        "subject": subject, "sender_email": "s@example.com", "body_text": "正文",
    }
    cols.update(extra)
    keys = ",".join(cols)
    cur = conn.execute(
        f"INSERT INTO emails ({keys}) VALUES ({','.join('?' * len(cols))})",
        tuple(cols.values()),
    )
    conn.commit()
    return int(cur.lastrowid)


def _list(**params) -> dict:
    resp = client.get("/api/emails", params=params)
    assert resp.status_code == 200
    return resp.json()


def test_list_filter_matrix():
    aid = _seed_account()
    e_read = _seed_email(aid, 1, "已读星标邮件", is_read=1, starred=1, category="work")
    e_promo = _seed_email(aid, 2, "营销邮件", category="promo")
    e_plain = _seed_email(aid, 3, "普通邮件")
    e_other = _seed_email(aid, 4, "归档里的邮件", folder="Archive")

    base = {"account_id": aid}
    assert _list(**base)["total"] == 3  # 默认只看 INBOX
    assert _list(**base, is_read="true")["total"] == 1
    assert _list(**base, is_read="true")["items"][0]["id"] == e_read
    assert _list(**base, starred="true")["total"] == 1
    assert _list(**base, category="promo")["total"] == 1
    assert _list(**base, category="promo")["items"][0]["id"] == e_promo
    assert _list(**base, folder="Archive")["total"] == 1
    assert _list(**base, folder="Archive")["items"][0]["id"] == e_other

    # 搜索：≥3 字符走 FTS5，<3 字符回退 LIKE；搜索按设计忽略文件夹/归档过滤。
    # 断言带 account_id（base）：全局 LIKE 会被其他测试夹具的邮件污染，账号内口径才稳定
    assert _list(**base, q="营销邮件")["total"] == 1
    assert _list(**base, q="邮")["total"] == 4  # LIKE 命中本账号全部四封（含 Archive 里那封）
    assert _list(**base, q="不存在的词xyz")["total"] == 0


def test_list_filter_sender_recipient_dates_attachments():
    """P1 补全（AGENT_SKILL_PLAN）：sender/recipient 模糊、after/before 按日含当天、
    has_attachments；过滤可与 q 组合；非法日期 400。"""
    aid = _seed_account()
    e_hit = _seed_email(aid, 1, "张三的周报", sender_email="zhangsan@example.com",
                        sender_name="张三", has_attachments=1,
                        recipients='["me@example.com","lee@example.com"]',
                        date="2026-09-10T09:30:00", date_sort="2026-09-10T01:30:00+00:00")
    _seed_email(aid, 2, "李四的邮件", sender_email="lisi@example.com",
                date="2026-08-01T10:00:00", date_sort="2026-08-01T02:00:00+00:00")
    _seed_email(aid, 3, "张三的九月亮点", sender_email="zhangsan@example.com",
                date="2026-09-12T10:00:00", date_sort="2026-09-12T02:00:00+00:00")

    base = {"account_id": aid}
    assert _list(**base, sender="张三")["total"] == 1  # 姓名匹配（仅 e1 带中文名）
    assert _list(**base, sender="张三")["items"][0]["id"] == e_hit
    assert _list(**base, sender="zhangsan@")["total"] == 2  # 地址匹配两封
    assert _list(**base, recipient="lee@")["total"] == 1
    assert _list(**base, recipient="lee@")["items"][0]["id"] == e_hit
    assert _list(**base, after="2026-09-01")["total"] == 2
    assert _list(**base, after="2026-09-01", before="2026-09-10")["total"] == 1
    assert _list(**base, after="2026-09-01", before="2026-09-10")["items"][0]["id"] == e_hit
    assert _list(**base, has_attachments="true")["total"] == 1
    # 过滤与搜索组合
    assert _list(**base, q="周报", sender="zhangsan@")["total"] == 1
    # 非法日期 → 400（内部 API 仍 {"detail"} 形）
    resp = client.get("/api/emails", params={"account_id": aid, "after": "not-a-date"})
    assert resp.status_code == 400
    assert "detail" in resp.json()


def test_batch_archive_async_and_pending():
    """v0.4 归档语义（REDESIGN_PLAN §4.6）：批量 archive=后台 job 移服务器；
    存量本地归档走 archived_pending/migrate 迁移流。"""
    aid = _seed_account()
    ids = [_seed_email(aid, 1, "a"), _seed_email(aid, 2, "b")]
    _seed_email(aid, 3, "c")

    # 批量归档=提交后台 job（job 体需真实 IMAP，此处只验证 API 契约）
    resp = client.post(
        "/api/emails/batch-action",
        json={"ids": ids, "action": "archive"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True and resp.json()["job_id"] is not None

    # 存量迁移流：archived_local=1 的行进入 pending 计数；决策标记端点可用
    conn = database.get_conn()
    conn.execute("UPDATE emails SET archived_local = 1 WHERE id IN (?, ?)", (ids[0], ids[1]))
    conn.commit()
    database.set_setting("archive_migrate_done", "0")  # 模拟 v15 落的「未决策」标记
    pending = client.get("/api/emails/archived_pending").json()
    assert pending["count"] >= 2 and pending["done"] is False
    migrate = client.post("/api/emails/archived_migrate").json()
    assert migrate["ok"] is True and migrate["migrating"] >= 2
    assert client.get("/api/emails/archived_pending").json()["done"] is True
    assert client.post("/api/emails/archived_dismiss").json() == {"ok": True}


def test_batch_validation_errors():
    assert client.post("/api/emails/batch-action", json={"ids": [], "action": "archive"}).status_code == 400
    assert client.post(
        "/api/emails/batch-action", json={"ids": [1], "action": "explode"}
    ).status_code == 400
    assert client.post(
        "/api/emails/batch-action", json={"ids": [1], "action": "move"}
    ).status_code == 400  # move 缺目标文件夹


def test_batch_trash_returns_job():
    """trash/move 走后台任务：立即返回 job_id，任务体在 jobs 表可查。"""
    aid = _seed_account()
    e = _seed_email(aid, 1, "x")
    resp = client.post("/api/emails/batch-action", json={"ids": [e], "action": "trash"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True and "job_id" in body

    job = client.get(f"/api/jobs/{body['job_id']}")
    assert job.status_code == 200
    assert job.json()["kind"] == "imap_batch"
