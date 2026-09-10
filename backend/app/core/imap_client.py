"""IMAP/SMTP 客户端封装（imap-tools + 标准库 smtplib）。"""
from __future__ import annotations

import email.utils
import logging
import re
import smtplib
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage

from imap_tools import AND, MailBox, MailMessageFlags
from imap_tools.errors import MailboxLoginError

logger = logging.getLogger(__name__)

# 网易系服务器必须在选箱前收到 IMAP ID 命令，否则 SELECT 报 "Unsafe Login"
NETEASE_HOSTS = ("163.com", "126.com", "yeah.net", "netease")

SEEN_FLAG = MailMessageFlags.SEEN
FLAGGED_FLAG = MailMessageFlags.FLAGGED


@dataclass
class MailConfig:
    email: str
    password: str
    imap_server: str
    imap_port: int = 993
    smtp_server: str = ""
    smtp_port: int = 465


@dataclass
class ParsedAttachment:
    filename: str
    content_type: str
    payload: bytes
    cid: str | None = None


@dataclass
class ParsedMessage:
    uid: int
    message_id: str
    subject: str
    sender_name: str
    sender_email: str
    recipients: list[str]
    cc: list[str]
    date: datetime | None
    body_text: str
    body_html: str
    attachments: list[ParsedAttachment]


def _is_netease(server: str) -> bool:
    return any(host in server for host in NETEASE_HOSTS)


def connect_imap(cfg: MailConfig) -> MailBox:
    """建立已登录的 IMAP 连接，返回可作上下文管理器使用的 MailBox。"""
    mb = MailBox(cfg.imap_server, port=cfg.imap_port)
    mb.login(cfg.email, cfg.password)
    if _is_netease(cfg.imap_server):
        try:
            mb.client._simple_command("ID", '("name" "Nmail" "version" "0.1.0")')
            mb.client._untagged_response("OK", None, "ID")
        except Exception:  # noqa: BLE001 — ID 失败不影响非网易服务器，留待后续命令暴露问题
            logger.debug("IMAP ID command failed for %s", cfg.imap_server)
    return mb


def test_connection(cfg: MailConfig) -> tuple[bool, str]:
    """验证 IMAP 登录是否可用，返回 (ok, 面向用户的说明)。"""
    try:
        with connect_imap(cfg) as mb:
            mb.folder.list()
        return True, "IMAP 登录成功"
    except MailboxLoginError:
        return False, "登录被拒绝：请检查邮箱地址与密码（多数服务商要求使用授权码/应用密码，而非网页登录密码）"
    except (TimeoutError, ConnectionRefusedError, socket.error, OSError):
        return False, f"无法连接服务器 {cfg.imap_server}:{cfg.imap_port}，请检查服务器地址、端口与网络"
    except Exception as exc:  # noqa: BLE001 — 统一转为用户可读的错误说明
        return False, f"连接失败：{exc}"


def list_folders(mb: MailBox) -> list[dict]:
    return [
        {"name": f.name, "delim": f.delim, "flags": list(f.flags)}
        for f in mb.folder.list()
    ]


def get_uidvalidity(mb: MailBox, folder: str) -> int | None:
    """读取文件夹 UIDVALIDITY；失败返回 None（视为不变）。"""
    try:
        name = f'"{folder}"' if " " in folder else folder
        typ, data = mb.client.status(name, "(UIDVALIDITY)")
        if typ == "OK" and data and data[0]:
            match = re.search(rb"UIDVALIDITY (\d+)", data[0])
            if match:
                return int(match.group(1))
    except Exception:  # noqa: BLE001
        logger.debug("UIDVALIDITY query failed for %s", folder)
    return None


def _find_special_folder(mb: MailBox, marker_flag: str, name_keywords: tuple[str, ...]) -> str | None:
    for info in mb.folder.list():
        attrs = {a.lower() for a in info.flags}
        if marker_flag and marker_flag in attrs:
            return info.name
    for info in mb.folder.list():
        if any(k in info.name.lower() for k in name_keywords):
            return info.name
    return None


def find_trash_folder(mb: MailBox) -> str | None:
    return _find_special_folder(mb, "\\trash", ("trash", "已删除", "deleted"))


def find_sent_folder(mb: MailBox) -> str | None:
    return _find_special_folder(mb, "\\sent", ("sent", "已发送"))


def fetch_new(mb: MailBox, folder: str, last_uid: int, first_sync_days: int = 30) -> list[ParsedMessage]:
    """拉取 folder 中 uid > last_uid 的邮件。

    首次同步（last_uid=0）只拉最近 N 天，避免大邮箱首翻过久；
    注意 IMAP 语义 `UID x:*` 在 x 大于最大 UID 时也会返回最后一封，
    因此调用方必须按 uid > last_uid 再过滤一次。
    """
    mb.folder.set(folder)
    if last_uid <= 0:
        # imap-tools 的 INTERNALDATE 条件参数是 date_gte（不是 IMAP 原生的 SINCE 关键字）
        since_date = (datetime.now() - timedelta(days=first_sync_days)).date()
        criteria = AND(date_gte=since_date)
    else:
        criteria = f"UID {last_uid + 1}:*"

    parsed: list[ParsedMessage] = []
    for msg in mb.fetch(criteria, mark_seen=False, bulk=True):
        # 部分版本 imap-tools 返回 str 型 uid，统一转 int
        uid = int(msg.uid) if msg.uid is not None else None
        if uid is None or uid <= last_uid:
            continue
        parsed.append(_parse_message(msg, uid))
    return parsed


def _parse_message(msg, uid: int) -> ParsedMessage:  # noqa: ANN001 — imap-tools MailMessage
    sender_name, sender_email = email.utils.parseaddr(msg.from_ or "")
    attachments = [
        ParsedAttachment(
            filename=att.filename or f"attachment-{index}",
            content_type=att.content_type or "application/octet-stream",
            payload=att.payload or b"",
            cid=(att.content_id.strip("<>") if att.content_id else None),
        )
        for index, att in enumerate(msg.attachments)
    ]
    return ParsedMessage(
        uid=uid,
        message_id=(msg.headers.get("message-id", [""])[0] if msg.headers else "") or "",
        subject=msg.subject or "",
        sender_name=sender_name or sender_email,
        sender_email=sender_email,
        recipients=[addr for addr in msg.to or []],
        cc=[addr for addr in msg.cc or []],
        date=msg.date,
        body_text=msg.text or "",
        body_html=msg.html or "",
        attachments=attachments,
    )


def set_flag(mb: MailBox, folder: str, uid: int, flag: MailMessageFlags, value: bool) -> None:
    mb.folder.set(folder)
    mb.flag([str(uid)], [flag], value)


def move_email(mb: MailBox, folder: str, uid: int, destination: str) -> int | None:
    """移动邮件到目标文件夹，返回目标文件夹中的新 UID（拿不到则 None）。"""
    mb.folder.set(folder)
    result = mb.move([str(uid)], destination)
    try:
        return int(result[str(uid)])  # type: ignore[index]
    except (TypeError, KeyError, ValueError):
        return None


def trash_email(mb: MailBox, folder: str, uid: int) -> None:
    """删除邮件：优先移入服务器废纸篓，否则标记删除并 expunge。"""
    trash = find_trash_folder(mb)
    if trash and trash != folder:
        move_email(mb, folder, uid, trash)
        return
    mb.folder.set(folder)
    mb.delete([str(uid)])
    mb.expunge()


def append_sent(cfg: MailConfig, message: EmailMessage) -> None:
    """发送成功后把邮件追加到服务器已发送文件夹（尽力而为）。"""
    try:
        with connect_imap(cfg) as mb:
            sent = find_sent_folder(mb)
            if not sent:
                return
            mb.folder.set(sent)
            mb.append(sent, message.as_string(), dt=datetime.now())
    except Exception as exc:  # noqa: BLE001 — 已发送归档失败不影响发送结果
        logger.warning("append sent failed for %s: %s", cfg.email, exc)


def send_email(
    cfg: MailConfig,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    body_text: str,
    body_html: str | None,
    attachment_paths: list[str] | None = None,
) -> None:
    """通过 SMTP 发送邮件；失败抛异常，由调用方转为错误响应。"""
    if not to:
        raise ValueError("收件人不能为空")
    msg = EmailMessage()
    msg["From"] = cfg.email
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=cfg.email.rsplit("@", 1)[-1])
    msg.set_content(body_text or "")
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    for path in attachment_paths or []:
        _attach_file(msg, path, path.replace("\\", "/").rsplit("/", 1)[-1])

    if cfg.smtp_port == 465:
        server: smtplib.SMTP = smtplib.SMTP_SSL(cfg.smtp_server, cfg.smtp_port, timeout=30)
    else:
        server = smtplib.SMTP(cfg.smtp_server, cfg.smtp_port, timeout=30)
    try:
        server.ehlo()
        if cfg.smtp_port != 465:
            server.starttls()
            server.ehlo()
        server.login(cfg.email, cfg.password)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass
    return msg


def _attach_file(msg: EmailMessage, path: str, filename: str) -> None:
    import mimetypes
    import os

    mime, _ = mimetypes.guess_type(filename)
    maintype, _, subtype = (mime or "application/octet-stream").partition("/")
    with open(path, "rb") as fh:
        data = fh.read()
    msg.add_attachment(data, maintype=maintype or "application",
                       subtype=subtype or "octet-stream", filename=os.path.basename(filename))
