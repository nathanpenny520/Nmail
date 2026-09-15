"""零成本纯函数单元：发件人名单匹配 / 回复主题 / 服务商探测 XML / 更新比较 / 版本解析。"""
from __future__ import annotations

import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

from app import config
from app.config import APP_VERSION, _version_from_pyproject
from app.core.imap_client import reply_subject
from app.core.pipeline import match_sender_list
from app.core.providers import _server_from_xml
from app.core.update_check import _is_newer


# ── pipeline.match_sender_list ──────────────────────────────
# 契约：pattern 在写入侧（api/sender_lists）已 strip+lower——这里按存储态构造


def test_exact_email_match():
    lists = {"whitelist": ["boss@corp.com"], "blacklist": []}
    assert match_sender_list("boss@corp.com", lists) == "whitelist"
    assert match_sender_list("BOSS@corp.com", lists) == "whitelist"  # 发件人侧大小写不敏感


def test_domain_match_requires_suffix():
    lists = {"whitelist": [], "blacklist": ["@spam.io"]}
    assert match_sender_list("a@spam.io", lists) == "blacklist"
    assert match_sender_list("x@spamio.com", lists) is None  # 后缀不匹配不算域名命中


def test_no_match_and_empty_sender():
    lists = {"whitelist": ["a@b.c"], "blacklist": ["@d.e"]}
    assert match_sender_list("other@x.y", lists) is None
    assert match_sender_list("", lists) is None


# ── imap_client.reply_subject ───────────────────────────────

def test_reply_subject_adds_prefix():
    assert reply_subject("项目进度") == "Re: 项目进度"


def test_reply_subject_keeps_existing():
    assert reply_subject("Re: 项目进度") == "Re: 项目进度"
    assert reply_subject("回复：项目进度") == "回复：项目进度"
    assert reply_subject("RE: x") == "RE: x"  # 大小写变体也算已带前缀


def test_reply_subject_empty():
    assert reply_subject("") == "Re:"


# ── providers._server_from_xml（autoconfig 解析）────────────

def _xml(hostname: str | None, port: str | None = None, socket_type: str | None = None):
    node = ET.Element("incomingServer")
    if hostname is not None:
        ET.SubElement(node, "hostname").text = hostname
    if port is not None:
        ET.SubElement(node, "port").text = port
    if socket_type is not None:
        ET.SubElement(node, "socketType").text = socket_type
    return node


def test_server_from_xml_ssl():
    assert _server_from_xml(_xml("imap.qq.com", "993", "SSL"), 993) == ("imap.qq.com", 993)


def test_server_from_xml_default_port_and_starttls():
    assert _server_from_xml(_xml("smtp.x.com", None, "STARTTLS"), 465) == ("smtp.x.com", 465)


def test_server_from_xml_bad_port_falls_back():
    assert _server_from_xml(_xml("imap.x.com", "abc"), 993) == ("imap.x.com", 993)


def test_server_from_xml_rejects_plaintext():
    assert _server_from_xml(_xml("imap.x.com", "143"), 993) is None


def test_server_from_xml_requires_hostname():
    assert _server_from_xml(_xml(None), 993) is None


# ── update_check._is_newer ──────────────────────────────────

def test_is_newer_semver_compare():
    assert _is_newer("0.2.0", "0.1.0") is True
    assert _is_newer("0.10.0", "0.9.0") is True  # 数值比较，非字典序
    assert _is_newer("0.1.0", "0.1.0") is False
    assert _is_newer("0.1.0", "0.2.0") is False


def test_is_newer_handles_garbage():
    assert _is_newer(None, "0.1.0") is False
    assert _is_newer("not-a-version", "0.1.0") is False


# ── config 版本解析 ─────────────────────────────────────────
# 契约：pyproject.toml 是版本唯一来源（T5）——源码读仓库根、冻结读随包资源、wheel 回退包元数据


def test_app_version_matches_pyproject():
    root = Path(__file__).resolve().parents[2]  # tests/ → backend/ → 仓库根
    with (root / "pyproject.toml").open("rb") as fp:
        assert APP_VERSION == tomllib.load(fp)["project"]["version"]


def test_version_from_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "9.9.9"\n')
    assert _version_from_pyproject(tmp_path) == "9.9.9"
    assert _version_from_pyproject(tmp_path / "nope") is None  # 文件缺失 → None
    (tmp_path / "pyproject.toml").write_text("not toml [")
    assert _version_from_pyproject(tmp_path) is None  # 解析失败 → None


def test_app_version_frozen_reads_bundled_pyproject(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "8.8.8"\n')
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert config._app_version() == "8.8.8"  # 冻结环境读 spec 打入的随包副本


def test_app_version_falls_back_to_metadata(monkeypatch):
    monkeypatch.setattr(config, "_version_from_pyproject", lambda base: None)
    monkeypatch.setattr(config, "_metadata_version", lambda name: "7.7.7")
    assert config._app_version() == "7.7.7"  # site-packages 旁无 pyproject → 包元数据


# ── batch_ops._match_rebuilt（v0.4.1 重建映射）──────────────
# 契约：移动类动作拿不到新 UID 删行重建后，按 message_id 在目标文件夹找回新 id；
# 无 message_id 或服务器上没找回的记 None——CLI/skill 据此把旧 id 换成新 id 续操作

def test_match_rebuilt_mapping():
    from app.core.batch_ops import _match_rebuilt
    from app.db import database

    database.run_migrations()
    conn = database.get_conn()
    aid = int(conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port)"
        " VALUES ('rb-units@example.com', 'imap.test', 993)").lastrowid)
    conn.commit()
    new_id = int(conn.execute(
        "INSERT INTO emails (account_id, folder, uid, message_id)"
        " VALUES (?, 'Archived', 11, '<rb1@test>')", (aid,)).lastrowid)
    conn.commit()

    deleted = [
        {"id": 9001, "message_id": "<rb1@test>"},    # 服务器找回 → 映射到新 id
        {"id": 9002, "message_id": None},            # 原本就无 message_id → None
        {"id": 9003, "message_id": "<rb-ghost@test>"},  # 目标文件夹里没找到 → None
    ]
    assert _match_rebuilt(conn, aid, "Archived", deleted) == {
        "9001": new_id, "9002": None, "9003": None,
    }
