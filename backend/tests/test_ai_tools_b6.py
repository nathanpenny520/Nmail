"""AI 总管家人人对等扩充测试（EXPERIENCE_PLAN B6）：模板/签名/联系组/受限设置/立即收信。

直接调工具执行函数（不经 LLM），验证执行、白名单与幂等语义。
"""
from __future__ import annotations

import uuid

from app.ai import agent, tools
from app.core.outbox import _append_signature_if_configured
from app.db import database

database.run_migrations()


def _aid() -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port, ai_permission)"
        f" VALUES ('a{uuid.uuid4().hex[:8]}@example.com', 'imap.test', 993, 'draft_review')"
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_draft(aid: int) -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO user_drafts (account_id, mode, to_addrs, subject, body_html, status, origin)"
        f" VALUES (?, 'reply', 'x@y.com', '标题', '<p>正文</p>', 'pending_review', 'ai')",
        (aid,),
    )
    conn.commit()
    return int(cur.lastrowid)


def test_list_templates_and_apply_creates_pending_draft():
    aid = _aid()
    database.set_setting("compose_templates", [
        {"id": "tpl-1", "name": "周报", "content": "本周进展\n- 完成A"},
    ])
    r = tools._t_list_templates({}, aid, [aid])
    assert r["templates"][0]["name"] == "周报"

    r2 = tools._t_apply_template({"template_id": "tpl-1", "to": "boss@x.com",
                                  "subject": "周报", "extra": "另：下周休眠"}, aid, [aid])
    assert "draft_id" in r2 and r2["status"] == "pending_review"
    row = database.get_conn().execute(
        "SELECT body_html FROM user_drafts WHERE id = ?", (r2["draft_id"],)
    ).fetchone()
    assert "本周进展" in row["body_html"] and "另：下周休眠" in row["body_html"]


def test_apply_template_unknown_id():
    aid = _aid()
    r = tools._t_apply_template({"template_id": "nope", "to": "a@b.com"}, aid, [aid])
    assert "error" in r


def test_apply_signature_appends_once():
    aid = _aid()
    database.set_setting("compose_signatures", [
        {"account_id": aid, "content": "**张三**\n产品部"},
    ])
    draft_id = _seed_draft(aid)

    r = tools._t_apply_signature({"draft_id": draft_id}, aid, [aid])
    assert r["ok"] is True
    row = database.get_conn().execute(
        "SELECT body_html FROM user_drafts WHERE id = ?", (draft_id,)
    ).fetchone()
    assert "<strong>张三</strong>" in row["body_html"]

    # 幂等：再调一次不再追加
    tools._t_apply_signature({"draft_id": draft_id}, aid, [aid])
    row2 = database.get_conn().execute(
        "SELECT body_html FROM user_drafts WHERE id = ?", (draft_id,)
    ).fetchone()
    assert row2["body_html"] == row["body_html"]


def test_apply_signature_no_signature_configured():
    aid = _aid()
    draft_id = _seed_draft(aid)
    r = tools._t_apply_signature({"draft_id": draft_id}, aid, [aid])
    assert "error" in r


def test_manage_contact_group_lifecycle():
    aid = _aid()
    # 组成员必须是通讯录已有联系人（contacts.set_members 语义），先入册
    tools._t_upsert_contact({"email": "m1@x.com", "name": "M1"}, aid, [aid])
    tools._t_upsert_contact({"email": "m2@x.com", "name": "M2"}, aid, [aid])
    r = tools._t_manage_contact_group({"action": "create", "name": "项目组"}, aid, [aid])
    assert r["ok"] is True
    gid = r["group_id"]
    r2 = tools._t_manage_contact_group(
        {"action": "add_members", "group_id": gid, "emails": ["m1@x.com", "m2@x.com"]}, aid, [aid])
    assert r2["changed"] == 2
    r3 = tools._t_manage_contact_group(
        {"action": "remove_members", "group_id": gid, "emails": ["m1@x.com"]}, aid, [aid])
    assert r3["changed"] == 1
    r4 = tools._t_manage_contact_group({"action": "delete", "group_id": gid}, aid, [aid])
    assert r4["ok"] is True
    r5 = tools._t_manage_contact_group({"action": "bad_action"}, aid, [aid])
    assert "error" in r5


def test_set_settings_whitelist_and_validation():
    aid = _aid()
    # 白名单外拒绝
    assert "error" in tools._t_set_settings({"key": "poll_interval_minutes_no"}, aid, [aid])
    # 布尔键矫正
    r = tools._t_set_settings({"key": "auto_insert_signature", "value": "true"}, aid, [aid])
    assert r["ok"] and r["value"] is True
    # 整数范围
    assert "error" in tools._t_set_settings({"key": "poll_interval_minutes", "value": 0}, aid, [aid])
    assert "error" in tools._t_set_settings({"key": "poll_interval_minutes", "value": 999}, aid, [aid])
    # digest_time 格式
    assert "error" in tools._t_set_settings({"key": "digest_time", "value": "25:00"}, aid, [aid])
    r2 = tools._t_set_settings({"key": "digest_time", "value": "08:30"}, aid, [aid])
    assert r2["ok"] and r2["value"] == "08:30"
    # notify_types 合并语义
    tools._t_set_settings({"key": "notify_types", "value": {"new_mail": False}}, aid, [aid])
    r3 = tools._t_set_settings({"key": "notify_types", "value": {"digest": False}}, aid, [aid])
    assert r3["value"] == {"new_mail": False, "digest": False}
    assert database.get_setting("notify_types") == {"new_mail": False, "digest": False}


def test_risky_settings_require_approval_even_in_auto_mode():
    aid = _aid()
    state = agent.RunState(session_id=None, account_ids=[aid], mode="auto",
                           profile_id=None, origin="ui")
    reason = agent._approval_reason(state, "set_settings", {"key": "agent_brief_enabled"})
    assert reason  # 自动模式下仍强制出审批卡
    low = agent._approval_reason(state, "set_settings", {"key": "auto_insert_signature"})
    assert low == ""  # 低风险键自动模式可直接执行
    # 豁免键（白名单外键值不可写，但风险归风险：白名单外在工具层拒绝，审批层不特判）
    risky = agent._approval_reason(state, "set_settings", {"key": "allow_remote_images"})
    assert risky


def test_trigger_sync_dispatches_background_sync(monkeypatch):
    aid = _aid()
    called: list[tuple[int, tuple[str, ...]]] = []
    import app.core.sync as sync_core

    monkeypatch.setattr(sync_core, "start_sync",
                        lambda account, folders=("INBOX",): called.append((account["id"], folders)) or {"started": True})
    r = tools._t_trigger_sync({}, aid, [aid])
    assert r["ok"] is True
    assert called and called[0][0] == aid


def test_outbox_signature_append_idempotent():
    aid = _aid()
    database.set_setting("compose_signatures", [
        {"account_id": aid, "content": "张三"},
    ])
    from app.core.mail_html import markdown_body_html, sanitize_outgoing_html

    sig = sanitize_outgoing_html(markdown_body_html("张三")).strip()
    once = _append_signature_if_configured(aid, "<p>hi</p>")
    assert once.endswith(sig)
    twice = _append_signature_if_configured(aid, once)
    assert twice == once  # 已含同款签名不再追加
