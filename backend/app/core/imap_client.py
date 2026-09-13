"""IMAP/SMTP 客户端封装（imap-tools + 标准库 smtplib）。"""
from __future__ import annotations

import base64
import email.utils
import logging
import re
import smtplib
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage

from imap_tools import AND, MailBox, MailMessageFlags
from imap_tools.errors import MailboxLoginError

from app.config import APP_VERSION
from app.core import netproxy, oauth

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
    # OAuth2 账号（auth_type='oauth2'）：access_token 非空时走 XOAUTH2，
    # password 不参与认证（邮箱层已确保传入的是刚刷新过的有效令牌）
    access_token: str | None = None
    # 代理：全局总开关（netproxy.resolve_proxy），无账号级字段


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
    # 服务器 FLAGS（\Seen/\Flagged 等）——新邮件入库按此初始化 is_read/starred
    flags: frozenset = frozenset()


def _is_netease(server: str) -> bool:
    return any(host in server for host in NETEASE_HOSTS)


class _MailBoxProxy(MailBox):
    """imap_tools 没有注入点（直接 new imaplib.IMAP4_SSL），子类替换建连一环。"""

    def __init__(self, imap4_cls: type, host: str, port: int, timeout: int) -> None:  # noqa: ANN001
        self._imap4_cls = imap4_cls
        super().__init__(host=host, port=port, timeout=timeout)

    def _get_mailbox_client(self):  # noqa: ANN001 — 返回 imaplib.IMAP4_SSL（或其子类）
        return self._imap4_cls(self._host, self._port,
                               ssl_context=self._ssl_context, timeout=self._timeout)


def connect_imap(cfg: MailConfig) -> MailBox:
    """建立已登录的 IMAP 连接，返回可作上下文管理器使用的 MailBox。"""
    # timeout=60：连接与读写都有上限，避免僵死连接永远挂着
    proxy = netproxy.resolve_proxy()
    imap4_cls = netproxy.imap4_ssl_class(proxy)
    mb = _MailBoxProxy(imap4_cls, cfg.imap_server, cfg.imap_port, 60)
    if cfg.access_token:
        mb.xoauth2(cfg.email, cfg.access_token)
    else:
        mb.login(cfg.email, cfg.password)
    if _is_netease(cfg.imap_server):
        try:
            mb.client._simple_command("ID", f'("name" "Nmail" "version" "{APP_VERSION}")')
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
        if cfg.access_token:
            return False, "OAuth 授权登录被拒绝：令牌可能已失效或被撤销，请到 设置-邮箱账号 重新授权"
        return False, "登录被拒绝：请检查邮箱地址与密码（多数服务商要求使用授权码/应用密码，而非网页登录密码）"
    except (TimeoutError, ConnectionRefusedError, OSError):
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


def iter_new_mail(mb: MailBox, folder: str, last_uid: int,
                  first_sync_days: int = 30, chunk_size: int = 25):
    """按 UID 升序分块产出新增邮件（每块为 ≤chunk_size 封的 ParsedMessage 列表）。

    先 SEARCH 拿 UID 清单（轻量，只传 ID），再逐块 FETCH：
    - 块要小（~2s 拉完）：QQ 等服务商会随机掐断持续重负载的连接（实测重负载
      ~8s 处被掐，Windows SSL 层报 `[Errno 22] Invalid argument`），块太大
      会在提交断点前被掐，重试永远原地踏步；
    - 调用方每块入库并提交断点，中断后从断点续传，不会整批重放。
    首次同步（last_uid=0）只拉最近 N 天，避免大邮箱首翻过久；
    注意 IMAP 语义 `UID x:*` 在 x 大于最大 UID 时也会返回最后一封，
    因此仍按 uid > last_uid 过滤一次。
    """
    mb.folder.set(folder)
    if last_uid <= 0:
        # imap-tools 的 INTERNALDATE 条件参数是 date_gte（不是 IMAP 原生的 SINCE 关键字）
        since_date = (datetime.now() - timedelta(days=first_sync_days)).date()
        criteria = AND(date_gte=since_date)
    else:
        criteria = f"UID {last_uid + 1}:*"

    pending = sorted(int(u) for u in mb.uids(criteria) if int(u) > last_uid)
    for start in range(0, len(pending), chunk_size):
        window = pending[start : start + chunk_size]
        parsed: list[ParsedMessage] = []

        def _fetch_one(criteria_str: str, out: list[ParsedMessage]) -> None:
            for msg in mb.fetch(criteria_str, mark_seen=False, bulk=True):
                # 部分版本 imap-tools 返回 str 型 uid，统一转 int
                uid = int(msg.uid) if msg.uid is not None else None
                if uid is None or uid <= last_uid:
                    continue
                out.append(_parse_message(msg, uid))

        # 稠密集合（如收件箱：UID 与日期同调）→ 区间 FETCH 一批拉回；
        # 稀疏集合（如「已删除/已发送」：邮件为移入、日期与 UID 不单调）——
        # 区间/逗号集合都会被服务器展开成 min:max 连续拉取（实测 42 个 UID
        # 拉回 388 封、31s，大文件夹直接撞超时→Windows SSL 报 Errno 22），
        # 只能逐 UID 精确拉取
        span = window[-1] - window[0] + 1
        if span <= len(window) * 2 + 5:
            _fetch_one(f"UID {window[0]}:{window[-1]}", parsed)
        else:
            for uid in window:
                _fetch_one(f"UID {uid}", parsed)
        time.sleep(0.2)  # 块间轻微节流，降低触发服务商频控的概率
        yield parsed


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
        flags=frozenset(msg.flags or ()),
    )


def search_flag_uids(mb: MailBox, folder: str) -> tuple[set[int], set[int]] | None:
    """UID SEARCH 文件夹的未读与星标 UID 集合（FLAGS 对账用，各一条命令）。

    返回 (未读 UID 集, 星标 UID 集)；服务器不支持/网络异常返回 None，调用方整段
    跳过对账——对账尽力而为，绝不阻塞同步主干。
    """
    try:
        mb.folder.set(folder)
        unread = {int(u) for u in mb.uids(AND(seen=False))}
        flagged = {int(u) for u in mb.uids(AND(flagged=True))}
        return unread, flagged
    except Exception:  # noqa: BLE001
        logger.debug("uid flag search failed for %s", folder)
        return None


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


def reply_subject(subject: str) -> str:
    """补 Re: 前缀；已带则原样返回。"""
    trimmed = (subject or "").strip()
    if not trimmed:
        return "Re:"
    if re.match(r"^(re|回复|答复)\s*(:|：)", trimmed, re.IGNORECASE):
        return trimmed
    return f"Re: {trimmed}"


def send_email(
    cfg: MailConfig,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    body_text: str,
    body_html: str | None,
    attachment_paths: list[str] | None = None,
    in_reply_to: str | None = None,
) -> EmailMessage:
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
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body_text or "")
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    for path in attachment_paths or []:
        _attach_file(msg, path, path.replace("\\", "/").rsplit("/", 1)[-1])

    if cfg.smtp_port == 465:
        server: smtplib.SMTP = netproxy.smtp_class(
            netproxy.resolve_proxy(), ssl=True)(
            cfg.smtp_server, cfg.smtp_port, timeout=30)
    else:
        server = netproxy.smtp_class(
            netproxy.resolve_proxy(), ssl=False)(
            cfg.smtp_server, cfg.smtp_port, timeout=30)
    try:
        server.ehlo()
        if cfg.smtp_port != 465:
            server.starttls()
            server.ehlo()
        _smtp_auth(server, cfg)
        server.send_message(msg)
    finally:
        with suppress(Exception):
            server.quit()
    return msg


def _smtp_auth(server: smtplib.SMTP, cfg: MailConfig) -> None:
    """SMTP 登录：OAuth 账号走 XOAUTH2（SASL 初始响应），密码账号走 LOGIN。

    微软不推荐但允许的 465 与 Gmail 465 均广播 AUTH=XOAUTH2；个别服务器不广播
    却支持时回退到裸 docmd（初始响应直接拼在 AUTH 命令后）。
    注意 smtplib 契约：authobject 先被**无参**调用取初始响应，服务器回 334
    挑战时才带参调用——XOAUTH2 的错误挑战约定回空串（让服务器给出最终错误）。
    """
    if not cfg.access_token:
        server.login(cfg.email, cfg.password)
        return
    auth_str = oauth.xoauth2_string(cfg.email, cfg.access_token)
    try:
        server.auth("XOAUTH2", lambda _challenge=None: auth_str if _challenge is None else "")
    except smtplib.SMTPNotSupportedError:
        b64 = base64.b64encode(auth_str.encode("ascii")).decode("ascii")
        code, resp = server.docmd("AUTH", f"XOAUTH2 {b64}")
        if code != 235:
            raise smtplib.SMTPAuthenticationError(code, resp) from None


def _attach_file(msg: EmailMessage, path: str, filename: str) -> None:
    import mimetypes
    import os

    mime, _ = mimetypes.guess_type(filename)
    maintype, _, subtype = (mime or "application/octet-stream").partition("/")
    with open(path, "rb") as fh:
        data = fh.read()
    msg.add_attachment(data, maintype=maintype or "application",
                       subtype=subtype or "octet-stream", filename=os.path.basename(filename))
