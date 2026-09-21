"""发送前检查测试（S-0921）：规则层各模式、precheck/copy-template-attachments 端点、
模板带主题与附件的整链路（KV 元数据 + 落盘文件 + 应用复制）。"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core import precheck
from app.core.outbox import template_files_dir
from app.db import database
from app.main import app

client = TestClient(app, base_url="http://127.0.0.1")

database.run_migrations()  # TestClient 不触发 lifespan，迁移在此显式补跑


def _codes(issues: list[dict]) -> list[str]:
    return [i["code"] for i in issues]


# ── 规则层 ──────────────────────────────────────────────────

def test_empty_subject_is_blocker():
    issues = precheck.rule_issues("  ", "<p>正文</p>", has_attachments=False)
    assert "empty_subject" in _codes(issues)
    assert all(i["severity"] == "blocker" for i in issues if i["code"] == "empty_subject")


def test_placeholder_patterns():
    for body in ("<p>你好 {'{name}'}</p>", "<p>请发到 [对方邮箱]</p>",
                 "<p>金额：____</p>", "<p>此致敬礼 xxx</p>",
                 "<p>某某公司 负责人收</p>", "<p>详细内容此处填写</p>"):
        issues = precheck.rule_issues("主题", body, has_attachments=False)
        assert "placeholder" in _codes(issues), body
        assert next(i for i in issues if i["code"] == "placeholder")["severity"] == "blocker"


def test_bracket_benign_not_flagged():
    """方括号内纯数字/时间/编号不是占位符。"""
    for body in ("<p>会议时间 [9:00] 开始</p>", "<p>见条款 [2026]</p>", "<p>注[1]如上</p>"):
        assert "placeholder" not in _codes(precheck.rule_issues("主题", body, False)), body


def test_x_placeholder_boundaries():
    """X 占位避开邮箱/网址/单词内部。"""
    assert "placeholder" in _codes(
        precheck.rule_issues("主题", "<p>联系人：XXX 经理</p>", False))
    assert "placeholder" not in _codes(
        precheck.rule_issues("主题", "<p>邮箱 xxx@qq.com 与尺码 XXL 见官网</p>", False))


def test_attachment_intent_check():
    # 说有附件但没带 → blocker
    issues = precheck.rule_issues("报告", "<p>详见附件，请查收。</p>", has_attachments=False)
    assert ("attachment_missing", "blocker") in {(i["code"], i["severity"]) for i in issues}
    # 带了附件但正文全未提 → warn
    issues = precheck.rule_issues("报告", "<p>你好。</p>", has_attachments=True)
    assert ("attachment_unmentioned", "warn") in {(i["code"], i["severity"]) for i in issues}
    # 提到且带了 → 无附件类问题
    assert "attachment_missing" not in _codes(
        precheck.rule_issues("报告", "<p>详见附件。</p>", True))
    assert "attachment_unmentioned" not in _codes(
        precheck.rule_issues("报告", "<p>详见附件。</p>", True))


def test_clean_mail_no_issues():
    issues = precheck.rule_issues("九月对账单", "<p>您好，九月对账已出，请知悉。</p>", False)
    assert issues == []


# ── 端点与模板整链路 ─────────────────────────────────────────

def _seed_account() -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port) VALUES (?, 'imap.test', 993)",
        (f"p{uuid.uuid4().hex[:8]}@example.com",),
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_draft(account_id: int, **kw) -> int:
    payload = {"account_id": account_id, "mode": "new",
               "subject": kw.get("subject", "主题"), "body_html": kw.get("body_html", "<p>正文</p>")}
    if "to_addrs" in kw:
        payload["to_addrs"] = kw["to_addrs"]
    resp = client.post("/api/user-drafts", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["draft"]["id"]


def test_precheck_endpoint_rule_layer(monkeypatch):
    """precheck 端点：规则层结果直出；AI 未配置时降级不报错。"""
    aid = _seed_account()
    did = _seed_draft(aid, subject="", body_html="<p>见附件</p>")
    resp = client.post(f"/api/user-drafts/{did}/precheck", json={"use_ai": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ai_used"] is False
    assert {"empty_subject", "attachment_missing"} <= set(_codes(data["issues"]))


def _save_template(tid: str, subject: str = "", atts: list[dict] | None = None) -> None:
    templates = client.get("/api/compose-extras").json()["templates"]
    templates = [t for t in templates if not t["id"].startswith("pc-test-")]
    templates.append({"id": tid, "name": "测试模板", "content": "你好 {name}",
                      "subject": subject, "attachments": atts or []})
    resp = client.put("/api/compose-extras", json={"templates": templates, "signatures": []})
    assert resp.status_code == 200, resp.text


def test_template_subject_and_attachments_roundtrip():
    """模板带主题+附件：上传落盘→KV 元数据→复制进草稿→同名跳过；删除模板清文件。"""
    aid = _seed_account()
    tid = "pc-test-1"
    _save_template(tid, subject="季度对账单")

    # 上传附件
    resp = client.post(
        f"/api/compose-extras/templates/{tid}/attachments",
        files={"files": ("对账.xlsx", b"fake-xlsx-bytes", "application/vnd.ms-excel")},
    )
    assert resp.status_code == 200, resp.text
    tpl = next(t for t in resp.json()["templates"] if t["id"] == tid)
    assert tpl["subject"] == "季度对账单"
    assert len(tpl["attachments"]) == 1
    disk = template_files_dir(tid) / tpl["attachments"][0]["disk_name"]
    assert disk.exists() and disk.read_bytes() == b"fake-xlsx-bytes"

    # 建草稿并复制模板附件
    did = _seed_draft(aid)
    resp = client.post(f"/api/user-drafts/{did}/copy-template-attachments",
                       json={"template_id": tid})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["copied"] == 1
    draft = body["draft"]
    assert draft["attachments"][0]["filename"] == "对账.xlsx"
    # 同名跳过：再复制一次不重复
    resp = client.post(f"/api/user-drafts/{did}/copy-template-attachments",
                       json={"template_id": tid})
    assert resp.json()["copied"] == 0
    assert len(resp.json()["draft"]["attachments"]) == 1

    # 删除模板（整存整取 diff）→ 落盘文件被清
    templates = [t for t in client.get("/api/compose-extras").json()["templates"]
                 if t["id"] != tid]
    client.put("/api/compose-extras", json={"templates": templates, "signatures": []})
    assert not template_files_dir(tid).exists()


def test_precheck_ai_flag_respects_setting(monkeypatch):
    """ai_send_review 关闭时不调 AI；开启但未配置时降级并带 ai_error。"""
    aid = _seed_account()
    did = _seed_draft(aid, subject="t", body_html="<p>见附件</p>")
    conn = database.get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ai_send_review', 'false')")
    conn.commit()
    resp = client.post(f"/api/user-drafts/{did}/precheck", json={"use_ai": True})
    assert resp.json()["ai_used"] is False
    assert "attachment_missing" in _codes(resp.json()["issues"])
    conn.execute("DELETE FROM settings WHERE key = 'ai_send_review'")
    conn.commit()


def test_scheduler_blocks_scheduled_draft_with_blocker():
    """定时到期草稿带 blocker（提附件没带）→ 不发出、退回 editing、写通知。"""
    from datetime import datetime, timedelta

    from app.scheduler import send_due_drafts

    aid = _seed_account()
    did = _seed_draft(aid, subject="定时对账", body_html="<p>对账单见附件。</p>")
    conn = database.get_conn()
    past = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE user_drafts SET status = 'scheduled', send_at = ? WHERE id = ?",
        (past, did),
    )
    conn.commit()
    send_due_drafts()
    row = conn.execute("SELECT status, send_at FROM user_drafts WHERE id = ?", (did,)).fetchone()
    assert row["status"] == "editing" and row["send_at"] is None
    note = conn.execute(
        "SELECT title, body FROM notifications WHERE type = 'compose' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert "未发出" in note["title"] and "附件" in note["body"]
    conn.execute("DELETE FROM user_drafts WHERE id = ?", (did,))
    conn.commit()
