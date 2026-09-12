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


def test_auto_collect_toggle():
    """采集开关（REDESIGN_PLAN §5.3）：关=收发两侧均不入册；开=恢复。"""
    from app.db.database import set_setting

    set_setting("contacts_auto_collect", False)
    try:
        aid = _aid()
        contacts_core.collect_sender("off1@example.com", "甲", aid)
        assert contacts_core.collect_addresses("off2@x.com", aid) == 0
        assert database.get_conn().execute(
            "SELECT COUNT(*) c FROM contacts WHERE account_id = ?", (aid,)
        ).fetchone()["c"] == 0
    finally:
        set_setting("contacts_auto_collect", True)
    aid = _aid()
    contacts_core.collect_sender("on@example.com", "乙", aid)
    assert database.get_conn().execute(
        "SELECT 1 FROM contacts WHERE email = 'on@example.com'"
    ).fetchone() is not None


def test_agg_list_email_scoped_edit_delete():
    """聚合口径：同邮箱多账号一行；改/删按 email 作用全部行；改邮箱连带组成员表。"""
    tag = uuid.uuid4().hex[:8]
    email = f"dup-{tag}@x.com"
    aid1, aid2 = _aid(), _aid()
    contacts_core.collect_sender(email, "老王", aid1)
    contacts_core.collect_sender(email, None, aid2)

    items = client.get("/api/contacts", params={"q": email}).json()["contacts"]
    assert len(items) == 1
    agg = items[0]
    assert agg["account_rows"] == 2 and agg["use_count"] == 2 and agg["sources"] == ["auto"]

    # 聚合行改姓名/手机 → 全行生效且转 manual；详情返回各账号明细
    assert client.patch(
        f"/api/contacts/{agg['id']}", json={"name": "王总", "phone": "13800000000"}
    ).status_code == 200
    rows = database.get_conn().execute(
        "SELECT name, phone, source FROM contacts WHERE email = ?", (email,)
    ).fetchall()
    assert len(rows) == 2
    assert all(r["name"] == "王总" and r["phone"] == "13800000000" and r["source"] == "manual" for r in rows)
    detail = client.get(f"/api/contacts/{agg['id']}").json()
    assert len(detail["rows"]) == 2 and detail["contact"]["sources"] == ["manual"]

    # 组成员按 email 记；改邮箱连带更新成员表
    g = client.post("/api/contacts/groups", json={"name": f"组{tag}"}).json()["group"]
    assert client.post(
        f"/api/contacts/groups/{g['id']}/members", json={"emails": [email]}
    ).json()["added"] == 1
    client.patch(f"/api/contacts/{agg['id']}", json={"email": f"wang-{tag}@x.com"})
    assert database.get_conn().execute(
        "SELECT email FROM contact_group_members WHERE group_id = ?", (g["id"],)
    ).fetchone()["email"] == f"wang-{tag}@x.com"

    new_email = f"wang-{tag}@x.com"
    # 视图过滤：manual 视图命中、auto 视图排除；在组内 → 未分组视图排除
    assert any(
        c["email"] == new_email
        for c in client.get("/api/contacts", params={"source": "manual"}).json()["contacts"]
    )
    assert not any(
        c["email"] == new_email
        for c in client.get("/api/contacts", params={"source": "auto"}).json()["contacts"]
    )
    assert not any(
        c["email"] == new_email
        for c in client.get("/api/contacts", params={"ungrouped": "true"}).json()["contacts"]
    )
    counts = client.get("/api/contacts").json()["counts"]
    assert {"all", "auto", "manual", "ungrouped"} <= set(counts)

    # 删除 = 该邮箱全部行消失 + 组成员孤儿清理
    assert client.delete(f"/api/contacts/{agg['id']}").json() == {"ok": True}
    assert database.get_conn().execute(
        "SELECT COUNT(*) c FROM contacts WHERE email = ?", (new_email,)
    ).fetchone()["c"] == 0
    assert database.get_conn().execute(
        "SELECT COUNT(*) c FROM contact_group_members WHERE group_id = ?", (g["id"],)
    ).fetchone()["c"] == 0
    client.delete(f"/api/contacts/groups/{g['id']}")


def test_groups_crud_and_members():
    tag = uuid.uuid4().hex[:8]
    g = client.post("/api/contacts/groups", json={"name": f"同事{tag}"}).json()["group"]
    # 同名 400；重命名冲突 400；空名 400
    assert client.post("/api/contacts/groups", json={"name": f"同事{tag}"}).status_code == 400
    other = client.post("/api/contacts/groups", json={"name": f"亲戚{tag}"}).json()["group"]
    assert client.patch(f"/api/contacts/groups/{g['id']}", json={"name": f"亲戚{tag}"}).status_code == 400
    assert client.patch(f"/api/contacts/groups/{g['id']}", json={"name": " "}).status_code == 400

    # 成员：不存在地址跳过、重复添加只计一次、移除生效
    manual = client.post(
        "/api/contacts", json={"email": f"m-{tag}@x.com", "name": "组成员"}
    ).json()["contact"]
    assert client.post(
        f"/api/contacts/groups/{g['id']}/members",
        json={"emails": [f"m-{tag}@x.com", f"ghost-{tag}@x.com"]},
    ).json()["added"] == 1
    assert client.post(
        f"/api/contacts/groups/{g['id']}/members", json={"emails": [f"m-{tag}@x.com"]}
    ).json()["added"] == 0
    groups = client.get("/api/contacts/groups").json()["groups"]
    assert next(x for x in groups if x["id"] == g["id"])["member_count"] == 1
    assert client.post(
        f"/api/contacts/groups/{g['id']}/members/remove", json={"emails": [f"m-{tag}@x.com"]}
    ).json()["removed"] == 1

    # 不存在的组 404；删除组级联清成员
    assert client.post("/api/contacts/groups/999999/members", json={"emails": []}).status_code == 404
    client.delete(f"/api/contacts/{manual['id']}")
    client.delete(f"/api/contacts/groups/{g['id']}")
    client.delete(f"/api/contacts/groups/{other['id']}")
    assert client.get("/api/contacts/groups").status_code == 200  # 端点仍可用
