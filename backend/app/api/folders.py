"""文件夹 API（v0.4 P2，REDESIGN_PLAN §4.4）：缓存列表/刷新/创建/重命名/删除。

服务器文件夹为真，本地 folders 表只做缓存；系统文件夹（INBOX 与 SPECIAL-USE
识别结果）不可改删。原 accounts.py 的两个文件夹端点迁入此处（路径不变）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import mail_error_to_http
from app.core import folders as folders_core
from app.core import mailbox

router = APIRouter(prefix="/api/accounts/{account_id}/folders", tags=["folders"])


@router.get("")
def list_folders(account_id: int, refresh: bool = False) -> dict:
    """树数据源：folders 缓存；缓存为空或 refresh=1 时连服务器 LIST 刷新。"""
    try:
        return {"folders": folders_core.get_list(account_id, refresh=refresh)}
    except mailbox.MailError as exc:
        raise mail_error_to_http(exc) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"获取文件夹失败：{exc}") from exc


class FolderCreateIn(BaseModel):
    name: str


@router.post("")
def create_folder(account_id: int, payload: FolderCreateIn) -> dict:
    """在服务器上创建文件夹（VSCode 资源管理器式；含层级，名内带分隔符）。"""
    try:
        return folders_core.create_folder(account_id, payload.name)
    except folders_core.FolderError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    except mailbox.MailError as exc:
        raise mail_error_to_http(exc) from exc


class FolderRenameIn(BaseModel):
    new_name: str


@router.patch("")
def rename_folder(account_id: int, payload: FolderRenameIn, name: str = Query(...)) -> dict:
    """重命名文件夹：服务器 RENAME，本地缓存/邮件/同步断点跟随（UID 不变）。

    名字走查询参数——IMAP 文件夹名自带分隔符（如 Gmail 的「/」），放路径里
    需逐段转义，易错；查询参数天然整段编码。
    """
    try:
        return folders_core.rename_folder(account_id, name, payload.new_name)
    except folders_core.FolderError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    except mailbox.MailError as exc:
        raise mail_error_to_http(exc) from exc


@router.delete("")
def delete_folder(account_id: int, name: str = Query(...)) -> dict:
    """删除文件夹：服务器 DELETE，本地该文件夹邮件行/断点/缓存一并清理。"""
    try:
        return folders_core.delete_folder(account_id, name)
    except folders_core.FolderError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    except mailbox.MailError as exc:
        raise mail_error_to_http(exc) from exc
