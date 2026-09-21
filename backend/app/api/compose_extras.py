"""写信台配套数据：模板与签名（settings KV 存储）+ Markdown 转换。

模板/签名整体读写（前端管理后全量保存），不做条目级端点——数据量小、
单用户本地应用，整存整取最简单。模板附件是例外（二进制文件进不了 KV）：
落盘 data_dir/compose_template_files/<template_id>/，KV 只存元数据，上传/删除
走条目级端点；整存整取时前端把元数据原样带回即可。

模板可携带默认主题与附件（S-0921）：应用模板 = 正文插光标处 + 空主题自动填 +
附件复制进草稿；老数据无新字段，行为不变。
"""
from __future__ import annotations

import shutil
from contextlib import suppress
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.mail_html import (
    decorate_outgoing_html,
    markdown_body_html,
    sanitize_outgoing_html,
    wrap_email_body_html,
)
from app.core.outbox import template_files_dir
from app.db.database import get_setting, set_setting

router = APIRouter(prefix="/api/compose-extras", tags=["compose-extras"])

MAX_TEMPLATE_ATTACH_BYTES = 50 * 1024 * 1024  # 单模板附件总量上限（与常见 SMTP 上限对齐）


def _clean_template_files(template_id: str) -> None:
    shutil.rmtree(template_files_dir(template_id), ignore_errors=True)


class TemplateAttachmentMeta(BaseModel):
    filename: str
    mime: str = ""
    size: int = 0
    disk_name: str  # compose_template_files/<template_id>/ 下的落盘名


class TemplateItem(BaseModel):
    id: str
    name: str
    content: str  # Markdown 文本，插入时转 HTML
    subject: str = ""  # 模板默认主题（空=不带；应用时仅当主题框为空才自动填）
    attachments: list[TemplateAttachmentMeta] = Field(default_factory=list)


class SignatureItem(BaseModel):
    account_id: int
    content: str  # Markdown 文本


class ComposeExtrasIn(BaseModel):
    templates: list[TemplateItem] = Field(default_factory=list)
    signatures: list[SignatureItem] = Field(default_factory=list)


@router.get("")
def read_extras() -> dict:
    return {
        "templates": get_setting("compose_templates", []),
        "signatures": get_setting("compose_signatures", []),
    }


@router.put("")
def update_extras(payload: ComposeExtrasIn) -> dict:
    old = get_setting("compose_templates", []) or []
    old_att = {str(t.get("id")): len(t.get("attachments") or [])
               for t in old if isinstance(t, dict)}
    new_ids = {t.id for t in payload.templates}
    # 被删模板 / 附件被清空的模板：清理落盘文件（元数据随 KV 覆盖消失）
    for tid in {str(t.get("id")) for t in old if isinstance(t, dict)} - new_ids:
        _clean_template_files(tid)
    for t in payload.templates:
        if not t.attachments and old_att.get(t.id):
            _clean_template_files(t.id)
    set_setting("compose_templates", [t.model_dump() for t in payload.templates])
    set_setting("compose_signatures", [s.model_dump() for s in payload.signatures])
    return read_extras()


# ── 模板附件（二进制文件，条目级端点；KV 只存元数据）──────────────

def _find_template(templates: list, template_id: str) -> dict | None:  # noqa: ANN001
    return next((t for t in templates
                 if isinstance(t, dict) and str(t.get("id")) == template_id), None)


@router.post("/templates/{template_id}/attachments")
async def upload_template_attachments(template_id: str,
                                      files: list[UploadFile] = File(...)) -> dict:  # noqa: B008
    templates = get_setting("compose_templates", []) or []
    tpl = _find_template(templates, template_id)
    if tpl is None:
        raise HTTPException(404, "模板不存在（先保存模板再添加附件）")
    atts = [TemplateAttachmentMeta(**a) for a in tpl.get("attachments") or []
            if isinstance(a, dict)]
    total = sum(a.size for a in atts)
    target_dir = template_files_dir(template_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        safe_name = Path(f.filename or "attachment").name  # 剥掉路径成分
        data = await f.read()
        total += len(data)
        if total > MAX_TEMPLATE_ATTACH_BYTES:
            raise HTTPException(400, "模板附件总量超过 50MB 上限")
        disk_name = f"{len(atts)}_{safe_name}"
        (target_dir / disk_name).write_bytes(data)
        atts.append(TemplateAttachmentMeta(filename=safe_name, mime=f.content_type or "",
                                           size=len(data), disk_name=disk_name))
    tpl["attachments"] = [a.model_dump() for a in atts]
    set_setting("compose_templates", templates)
    return {"templates": templates}


@router.delete("/templates/{template_id}/attachments/{index}")
def delete_template_attachment(template_id: str, index: int) -> dict:
    templates = get_setting("compose_templates", []) or []
    tpl = _find_template(templates, template_id)
    if tpl is None:
        raise HTTPException(404, "模板不存在")
    atts = [TemplateAttachmentMeta(**a) for a in tpl.get("attachments") or []
            if isinstance(a, dict)]
    if index < 0 or index >= len(atts):
        raise HTTPException(404, "附件不存在")
    removed = atts.pop(index)
    with suppress(OSError):  # 文件可能已不在，静默
        (template_files_dir(template_id) / removed.disk_name).unlink()
    tpl["attachments"] = [a.model_dump() for a in atts]
    set_setting("compose_templates", templates)
    return {"templates": templates}


class MarkdownIn(BaseModel):
    text: str


@router.post("/markdown")
def convert_markdown(payload: MarkdownIn) -> dict:
    """Markdown → 消毒后的 HTML（编辑器/模板/签名插入用）。"""
    return {"html": sanitize_outgoing_html(markdown_body_html(payload.text))}


class HtmlIn(BaseModel):
    html: str


@router.post("/sanitize-html")
def sanitize_html(payload: HtmlIn) -> dict:
    """HTML → 白名单消毒（源码视图回填编辑器前清洗，与发送消毒同口径但不含发送专用放行）。"""
    return {"html": sanitize_outgoing_html(payload.html)}


@router.post("/preview")
def preview_html(payload: HtmlIn) -> dict:
    """收件人视角预览：sanitize → decorate（收件端兜底内联化）→ wrap，
    与 outbox.send_user_draft 的发送管线同参——预览即收件人所见。"""
    html = wrap_email_body_html(decorate_outgoing_html(sanitize_outgoing_html(payload.html)))
    return {"html": html}
