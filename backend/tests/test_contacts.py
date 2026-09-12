"""通讯录测试（v0.4 P4，REDESIGN_PLAN §5.3）：采集 upsert（去重/计数/manual 保护）、
发送侧地址串采集、写信联想排序、API 增删改查与守卫。"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core import contacts as contacts_core
from app.db import database
from app.main import app

client = TestClient(app, base_url="http://127.0.0.1")

database.run_migrations()


def _aid() -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port) VALUES (?, 'imap.test', 993)",
        (f"c{uuid.uuid4().hex[:8]}@example.com",),
    )
    conn.commit()
    return int(cur.lastrowid)


def test_upsert_collect_and_manual_protection():
    aid = _aid()
    contacts_core.collect_sender("Boss@Example.com ", "老张", aid)
    contacts_core.collect_sender("boss@example.com", None, aid)
    row = database.get_conn().execute(
        "SELECT * FROM contacts WHERE account_id = ?", (aid,)
    ).fetchone()
    assert row["email"] == "boss@example.com"  # 规范化小写
    assert row["name"] == "老张"
    assert row["use_count"] == 2

    # 手动编辑 → source=manual → 采集不再覆盖姓名，但计数照加
    database.get_conn().execute(
        "UPDATE contacts SET name = '张总', source = 'manual' WHERE id = ?", (row["id"],)
    )
    database.get_conn().commit()
    contacts_core.collect_sender("boss@example.com", "不应该覆盖", aid)
    row = database.get_conn().execute("SELECT * FROM contacts WHERE id = ?", (row["id"],)).fetchone()
    assert row["name"] == "张总"
    assert row["use_count"] == 3

    # 非法地址不采集
    contacts_core.collect_sender("not-an-email", "x", aid)
    assert database.get_conn().execute(
        "SELECT COUNT(*) c FROM contacts WHERE account_id = ?", (aid,)
    ).fetchone()["c"] == 1


def test_collect_addresses_and_suggest_ranking():
    aid = _aid()
    n = contacts_core.collect_addresses(
        '张三 <zhang@x.com>, lisi@y.com , bad-addr, zhang@x.com', aid
    )
    assert n == 4  # 全部尝试（非法的静默跳过）
    emails = {
        r["email"]
        for r in database.get_conn().execute(
            "SELECT email FROM contacts WHERE account_id = ?", (aid,)
        ).fetchall()
    }
    assert emails == {"zhang@x.com", "lisi@y.com"}
    assert database.get_conn().execute(
        "SELECT use_count FROM contacts WHERE account_id = ? AND email = 'zhang@x.com'", (aid,)
    ).fetchone()["use_count"] == 2

    # 联想：use_count 高者在前；关键词命中 email 或姓名
    contacts_core.upsert_contact("wang@z.com", "王五", aid)
    items = contacts_core.suggest("zhang")
    assert items and items[0]["email"] == "zhang@x.com"
    items = contacts_core.suggest("王")
    assert items and items[0]["name"] == "王五"
    assert contacts_core.suggest("nomatch-xyz") == []


def test_contacts_api_crud():
    resp = client.post(
        "/api/contacts", json={"email": "Manual@X.com", "name": "手动联系人", "notes": "备注"}
    )
    assert resp.status_code == 200
    cid = resp.json()["contact"]["id"]
    assert resp.json()["contact"]["source"] == "manual"
    assert resp.json()["contact"]["account_id"] is None

    # 重复新增 400；非法地址 400
    assert client.post("/api/contacts", json={"email": "manual@x.com"}).status_code == 400
    assert client.post("/api/contacts", json={"email": "bad"}).status_code == 400

    # 改名（转 manual）与备注
    assert client.patch(f"/api/contacts/{cid}", json={"name": "新名字"}).status_code == 200
    assert client.patch(f"/api/contacts/{cid}", json={"notes": "n2"}).json()["contact"]["notes"] == "n2"

    # 直改邮箱：规范化 + 查重 + 非法拒绝
    patched = client.patch(f"/api/contacts/{cid}", json={"email": "Fixed@X.com "})
    assert patched.status_code == 200 and patched.json()["contact"]["email"] == "fixed@x.com"
    assert client.patch(f"/api/contacts/{cid}", json={"email": "bad"}).status_code == 400
    other = client.post("/api/contacts", json={"email": "other@x.com"}).json()["contact"]["id"]
    assert client.patch(f"/api/contacts/{cid}", json={"email": "other@x.com"}).status_code == 400
    client.delete(f"/api/contacts/{other}")

    # 列表搜索与删除
    assert any(c["id"] == cid for c in client.get("/api/contacts", params={"q": "新名字"}).json()["contacts"])
    assert client.delete(f"/api/contacts/{cid}").json() == {"ok": True}
    assert client.delete(f"/api/contacts/{cid}").status_code == 404
