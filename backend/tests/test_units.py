"""零成本纯函数单元：发件人名单匹配 / 回复主题 / 服务商探测 XML / 更新比较。"""
from __future__ import annotations

import xml.etree.ElementTree as ET

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
