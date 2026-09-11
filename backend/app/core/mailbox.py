"""账号凭据/连接/发送统一入口。

全项目唯一的 MailConfig 构造点：查账号行 + 读密钥 → AccountHandle（含就绪 cfg）；
唯一的 SMTP 发送路径：send_message（发送 + 归档 Sent）。
添加账号入库前、改密预检的表单直连 test_connection 属预检路径（密码来自请求
而非凭据库），不经此处。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Iterator

from imap_tools import MailBox

from app.core import imap_client
from app.db.database import get_conn
from app.security import get_secret


class MailError(Exception):
    """业务级邮件错误；code ∈ not_found | missing_credential"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class AccountHandle:
    """账号行 + 就绪连接配置（含密码）。"""
    row: sqlite3.Row
    cfg: imap_client.MailConfig

    @property
    def id(self) -> int:
        return int(self.row["id"])


def load_account(account_id: int) -> AccountHandle:
    """查账号 + 密钥，缺一即抛 MailError。全项目唯一的 MailConfig 构造点。"""
    row = get_conn().execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if row is None:
        raise MailError("not_found", "账号不存在")
    password = get_secret(f"account_pwd:{account_id}")
    if not password:
        raise MailError("missing_credential", "缺少密码凭证，请在 设置-账号 中重新保存授权码")
    cfg = imap_client.MailConfig(
        email=row["email"], password=password,
        imap_server=row["imap_server"], imap_port=int(row["imap_port"]),
        smtp_server=row["smtp_server"] or "",
        smtp_port=int(row["smtp_port"] or 465),
    )
    return AccountHandle(row=row, cfg=cfg)


def has_credentials(account_id: int) -> bool:
    """轻量检查（不查账号行）：提交后台任务前快速判断。"""
    return bool(get_secret(f"account_pwd:{account_id}"))


@contextmanager
def open_imap(handle: AccountHandle) -> Iterator[MailBox]:
    """建立已登录 IMAP 连接（超时与网易 ID 握手由 imap_client.connect_imap 处理）。"""
    with imap_client.connect_imap(handle.cfg) as mb:
        yield mb


def split_addresses(raw: str) -> list[str]:
    """逗号/分号分隔的地址串 → 去空列表（原 api/emails.re_split，随发送收口迁入）。"""
    return [x for x in (raw or "").replace(";", ",").split(",") if x.strip()]


def send_message(
    handle: AccountHandle,
    *,
    to: list[str],
    subject: str,
    text: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    html: str | None = None,
    attachment_paths: list[str] | None = None,
    in_reply_to: str | None = None,
) -> EmailMessage:
    """唯一 SMTP 发送路径：构建 → 发送 → 归档 Sent（尽力而为）。

    正文约定：html 须为**已消毒**的最终 HTML（发件方向消毒在各内容来源处完成后传入；
    纯文本 text 必传——富文本来源用 html_to_plain_text 派生，Markdown 来源用原文）。
    in_reply_to 写入 In-Reply-To/References 供对方客户端串线。
    SMTP/网络错误抛原异常（调用方翻译为面向用户的文案）；SMTP 未配置抛
    MailError("smtp_missing")；归档 Sent 失败仅告警不影响发送结果。
    """
    if not handle.cfg.smtp_server:
        raise MailError("smtp_missing", "该账号未配置 SMTP 服务器")
    sent = imap_client.send_email(
        handle.cfg, to, cc or [], bcc or [], subject, text, html,
        attachment_paths, in_reply_to=in_reply_to,
    )
    imap_client.append_sent(handle.cfg, sent)
    return sent
