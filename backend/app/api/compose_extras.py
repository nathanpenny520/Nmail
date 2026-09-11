"""写信台配套数据：模板与签名（settings KV 存储）+ Markdown 转换。

模板/签名整体读写（前端管理后全量保存），不做条目级端点——
数据量小、单用户本地应用，整存整取最简单。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.mail_html import markdown_body_html, sanitize_outgoing_html
from app.db.database import get_setting, set_setting

router = APIRouter(prefix="/api/compose-extras", tags=["compose-extras"])


class TemplateItem(BaseModel):
    id: str
    name: str
    content: str  # Markdown 文本，插入时转 HTML


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
    set_setting("compose_templates", [t.model_dump() for t in payload.templates])
    set_setting("compose_signatures", [s.model_dump() for s in payload.signatures])
    return read_extras()


class MarkdownIn(BaseModel):
    text: str


@router.post("/markdown")
def convert_markdown(payload: MarkdownIn) -> dict:
    """Markdown → 消毒后的 HTML（编辑器/模板/签名插入用）。"""
    return {"html": sanitize_outgoing_html(markdown_body_html(payload.text))}
