"""HTML 邮件消毒与安全渲染预处理。

两层防护：
1. nh3（ammonia）白名单清洗：剔除 script/iframe/事件属性/javascript: URL 等；
2. 远程图片控制：默认移除 http(s) 图片并统计拦截数；cid 内联图按需转 data URL。

另外 http(s) 链接强制 target="_blank"（rel=noopener 由 nh3 link_rel 添加）：
前端在 sandbox iframe 里渲染正文，若链接在 iframe 内导航，多数站点以
X-Frame-Options / CSP frame-ancestors 拒绝被内嵌（浏览器显示「拒绝连接」）。
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

import nh3
from bs4 import BeautifulSoup

MAX_INLINE_IMAGE_BYTES = 2 * 1024 * 1024  # cid 内联图超过 2MB 不内联

_ALLOWED_TAGS = {
    "a", "b", "blockquote", "br", "center", "code", "div", "em", "font", "h1", "h2",
    "h3", "h4", "h5", "h6", "hr", "i", "img", "li", "ol", "p", "pre", "s", "small",
    "span", "strong", "sub", "sup", "table", "tbody", "td", "th", "thead", "tr", "u", "ul",
}

_ALLOWED_ATTRS: dict[str, set[str]] = {
    "*": {"style", "class", "align", "bgcolor", "width", "height", "dir"},
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "width", "height", "border"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
    "font": {"face", "color", "size"},
}

_URL_SCHEMES = {"http", "https", "mailto", "cid"}

_REMOTE_IMG_RE = re.compile(r"<img[^>]+src=[\"']https?://", re.IGNORECASE)
_CID_RE = re.compile(r"^cid:(.+)$", re.IGNORECASE)


def count_remote_images(html: str) -> int:
    return len(_REMOTE_IMG_RE.findall(html or ""))


def sanitize_email_html(
    raw_html: str,
    allow_remote_images: bool,
    cid_map: dict[str, tuple[str, str]] | None = None,
) -> tuple[str, int]:
    """消毒邮件 HTML。

    cid_map: {content_id: (文件路径, mime)}，仅在 allow_remote_images 时内联。
    返回 (消毒后的 HTML, 被拦截的远程图片数)。
    """
    clean = nh3.clean(
        raw_html or "",
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        url_schemes=_URL_SCHEMES,
        link_rel="noopener noreferrer",
    )
    soup = BeautifulSoup(clean, "html.parser")
    blocked = 0

    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if src.startswith(("http://", "https://")):
            if allow_remote_images:
                continue
            blocked += 1
            placeholder = soup.new_tag("span")
            placeholder.string = "[外部图片已拦截]"
            placeholder.attrs["style"] = (
                "display:inline-block;padding:2px 8px;border:1px dashed #c4b5fd;"
                "border-radius:6px;color:#6d28d9;font-size:12px;background:#f5f3ff"
            )
            img.replace_with(placeholder)
        elif (match := _CID_RE.match(src)) and cid_map:
            entry = cid_map.get(match.group(1).strip())
            if entry and Path(entry[0]).exists():
                path, mime = entry
                data = Path(path).read_bytes()
                if len(data) <= MAX_INLINE_IMAGE_BYTES:
                    b64 = base64.b64encode(data).decode("ascii")
                    img.attrs["src"] = f"data:{mime or 'image/png'};base64,{b64}"
                    continue
            img.decompose()
        elif src == "":
            img.decompose()

    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        if href.startswith(("http://", "https://", "//")):
            a.attrs["target"] = "_blank"

    return str(soup), blocked


def sanitize_outgoing_html(html: str) -> str:
    """发件方向消毒：同一套白名单，但额外放行 data: 图片（编辑器内嵌图）。

    收件路径不放行 data:（历史邮件无需支持），发件路径放行以免用户插入的
    截图被静默剥离；nh3 白名单仍剔除脚本/事件属性/javascript: 等。
    """
    return nh3.clean(
        html or "",
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        url_schemes=_URL_SCHEMES | {"data"},
        link_rel="noopener noreferrer",
    )


def html_to_plain_text(html: str) -> str:
    """HTML → 纯文本，作为发出邮件的 text/plain alternative。"""
    soup = BeautifulSoup(html or "", "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(
        ["p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre"]
    ):
        block.append("\n")
    text = soup.get_text()
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def wrap_email_body_html(inner_html: str) -> str:
    """给正文 HTML 套上基础样式外层（无样式的客户端也能正常阅读）。"""
    return (
        '<div style="font-family:-apple-system,\'Segoe UI\',\'Microsoft YaHei\','
        'sans-serif;font-size:14px;line-height:1.65;color:#1f2937;white-space:normal">'
        + inner_html
        + "</div>"
    )


def markdown_to_email_html(markdown_text: str) -> str:
    """写信正文的 Markdown → 带基础样式的 HTML。"""
    import markdown as md_lib

    body = md_lib.markdown(markdown_text or "", extensions=["fenced_code", "tables"])
    return wrap_email_body_html(body)


def markdown_body_html(markdown_text: str) -> str:
    """Markdown → 裸 HTML（无外层样式），供编辑器内插入/模板/签名转换用。"""
    import markdown as md_lib

    return md_lib.markdown(markdown_text or "", extensions=["fenced_code", "tables"])
