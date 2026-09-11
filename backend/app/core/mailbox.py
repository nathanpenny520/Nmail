"""账号凭据/连接统一入口。

全项目唯一的 MailConfig 构造点：查账号行 + 读密钥 → AccountHandle（含就绪 cfg）。
API 层的 _imap_for 等 8 处拼装将逐步迁移至此（IMPROVEMENT_PLAN §3.1）；
添加账号入库前的表单直连 test_connection 属预检路径，不经此处。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
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
