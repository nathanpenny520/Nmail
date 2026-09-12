"""文件夹模块测试（v0.4 P2，REDESIGN_PLAN §4）：特殊文件夹识别、缓存往返、
系统文件夹守卫、归档迁移端点契约。IMAP 相关用 monkeypatch 桩掉真实连接。"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core import folders as folders_core
from app.db import database
from app.main import app

client = TestClient(app, base_url="http://127.0.0.1")

database.run_migrations()  # TestClient 不触发 lifespan，迁移在此显式补跑


def _seed_account() -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port) VALUES (?, 'imap.test', 993)",
        (f"f{uuid.uuid4().hex[:8]}@example.com",),
    )
    conn.commit()
    return int(cur.lastrowid)


def test_detect_special_use_matrix():
    assert folders_core.detect_special_use("INBOX", []) is None
    assert folders_core.detect_special_use("Sent Messages", ["\\Sent"]) == "sent"
    assert folders_core.detect_special_use("[Gmail]/All Mail", ["\\HasNoChildren", "\\All"]) == "all"
    # 启发式兜底（无 SPECIAL-USE 的中文服务商）
    assert folders_core.detect_special_use("已发送", []) == "sent"
    assert folders_core.detect_special_use("垃圾邮件", []) == "junk"
    assert folders_core.detect_special_use("Deleted Messages", []) == "trash"
    assert folders_core.detect_special_use("草稿箱", []) == "drafts"
    # 普通文件夹不误判（archive 不做启发式，避免误标不可删）
    assert folders_core.detect_special_use("项目/Nmail", []) is None
    assert folders_core.detect_special_use("我的归档备份", []) is None


def test_system_folder_guard_blocks_rename_delete():
    aid = _seed_account()
    conn = database.get_conn()
    conn.execute(
        "INSERT INTO folders (account_id, name, delim, special_use) VALUES (?, 'Sent', '/', 'sent')",
        (aid,),
    )
    conn.execute(
        "INSERT INTO folders (account_id, name, delim) VALUES (?, '项目', '/')",
        (aid,),
    )
    conn.commit()

    assert folders_core.folder_guard(aid, "INBOX") is not None
    assert folders_core.folder_guard(aid, "Sent") is not None
    assert folders_core.folder_guard(aid, "项目") is None

    # 守卫在 IMAP 之前生效（无凭据也返回 400 而非 502/连接错误）；名字走查询参数
    assert client.patch(
        f"/api/accounts/{aid}/folders",
        params={"name": "Sent"},
        json={"new_name": "Sent2"},
    ).status_code == 400
    assert client.delete(
        f"/api/accounts/{aid}/folders", params={"name": "INBOX"}
    ).status_code == 400


def test_cached_list_and_archive_folder_name():
    aid = _seed_account()
    conn = database.get_conn()
    conn.execute(
        "INSERT INTO folders (account_id, name, delim, special_use) VALUES (?, 'INBOX', '/', NULL)",
        (aid,),
    )
    conn.commit()
    items = folders_core.cached_list(aid)
    assert len(items) == 1 and items[0]["is_system"] is True  # INBOX 视为系统文件夹
    assert folders_core.archive_folder_name(aid) == "Archived"  # 默认归档文件夹名
