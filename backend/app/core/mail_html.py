"""HTML 邮件消毒与安全渲染预处理。

三层防护：
1. nh3（ammonia）白名单清洗：剔除 script/iframe/事件属性/javascript: URL 等；
2. 远程图片控制：默认移除 http(s) 图片并统计拦截数；cid 内联图按需转 data URL；
   放行时追踪像素（声明尺寸≤2px）隐形、缺 alt 的远程图补空 alt（被浏览器
   反追踪拦截时不再显示裂图图标）。
3. <style> 标签放行：nh3 默认把 style 连内容整体剥离且不支持白名单放行
   （tag 与 clean_content_tags 同现会 panic），故先摘出 CSS 自行清洗再注回；
   拦截口径下同步剥 CSS 远程 url()/@import（含 style 属性，nh3 不清洗其内容），
   防 CSS 侧追踪回潮。style 标签仅在沙箱 iframe 渲染，无脚本风险。

另外 http(s) 链接强制 target="_blank"（rel=noopener 由 nh3 link_rel 添加）：
前端在 sandbox iframe 里渲染正文，若链接在 iframe 内导航，多数站点以
X-Frame-Options / CSP frame-ancestors 拒绝被内嵌（浏览器显示「拒绝连接」）。
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

import nh3
from bs4 import BeautifulSoup, NavigableString, Tag

MAX_INLINE_IMAGE_BYTES = 2 * 1024 * 1024  # cid 内联图超过 2MB 不内联

_ALLOWED_TAGS = {
    "a", "b", "blockquote", "br", "center", "code", "col", "colgroup", "div", "em", "font", "h1", "h2",
    "h3", "h4", "h5", "h6", "hr", "i", "img", "li", "mark", "ol", "p", "pre", "s", "small",
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
_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
_CSS_IMPORT_RE = re.compile(r"@import\b[^;]*;?", re.IGNORECASE)
_TINY_ATTR_RE = re.compile(r"^\s*(\d+)")
_TINY_STYLE_RE = re.compile(r"(?:^|[;\s])(?:width|height)\s*:\s*(\d+(?:\.\d+)?)px", re.IGNORECASE)

# 换行语义统一（2026-09-17 用户拍板）：文本源（模板/签名/AI 起草）里单个换行
# =分段（与编辑器 Enter 一致），行尾 ≥2 空格或反斜杠 =紧贴换行（=编辑器
# Shift+Enter，Markdown 硬换行约定）。此前 nl2br 把单换行转 <br>（B2），用户
# 实测后拍板改为段落语义并全局统一。
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_MD_MARKER_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|>|#|\|)")


def _enter_to_paragraph(text: str) -> str:
    """把「Enter=分段」文本规范化为 Markdown 源（模板/签名/AI 文本 → 排版语义）。

    规则：非围栏行的单个换行改双换行（分段）；行尾 ≥2 空格或反斜杠保留单换行
    （Markdown 硬换行→<br>，即紧贴行）；围栏代码块内逐字保留；列表/引用/标题/
    表格行相邻换行保留（块结构靠行相邻解析，拆散即坏）；非结构行的 ≥4 空格缩进
    转 U+00A0（防止分段后落入缩进代码块，同时缩进在收发两端都不折叠）。
    """
    lines = text.split("\n")
    # 预扫描围栏状态：fenced[i] = 第 i 行是否处于围栏内（含围栏行本身）
    fenced = [False] * len(lines)
    in_fence = False
    fence = ""
    for i, line in enumerate(lines):
        m = _FENCE_RE.match(line)
        if m:
            if not in_fence:
                in_fence, fence = True, m.group(1)[:3]
            elif line.lstrip().startswith(fence):
                in_fence = False
            fenced[i] = True
        else:
            fenced[i] = in_fence
    # 缩进代码块风险行（≥4 空格的非结构行）→ 前导空格转 nbsp
    for i, line in enumerate(lines):
        if fenced[i]:
            continue
        stripped = line.lstrip(" ")
        if line[: len(line) - len(stripped)] and not _MD_MARKER_RE.match(line):
            # 占位符（私有区字符）：markdown 会吞行首 nbsp，先占位、转出后还原
            lines[i] = "\ue000" * (len(line) - len(stripped)) + stripped
    # 分隔符决策
    out: list[str] = []
    for i, line in enumerate(lines):
        out.append(line)
        if i == len(lines) - 1:
            break
        nxt = lines[i + 1]
        if (line.endswith("  ") or line.endswith("\\")
                or nxt.strip() == "" or fenced[i + 1] or fenced[i]
                or _MD_MARKER_RE.match(nxt) or _MD_MARKER_RE.match(line)):
            out.append("\n")
        else:
            out.append("\n\n")  # 单换行 → 分段
    return "".join(out)


# Markdown 转换产物的空白规范化（编辑器所见=所发的前提）。python-markdown 的
# 硬换行输出 "<br />\n"：br 后的字面换行在收件端永远折叠（white-space:normal），
# 却会进编辑器文档并被其 break-spaces 渲染成第二个换行——插入后「紧贴行变空行」；
# 行首缩进空格同理（编辑器可见、收件端折叠，发送后「空格被吞」）。转出的 HTML
# 一律：①删 br 后字面 \n；②行首空格串转 U+00A0（任何客户端都不折叠，缩进
# 收发两端一致显示）。
_MD_BR_NEWLINE_RE = re.compile(r"(<br[^>]*>)\n")
_MD_LEADING_SPACES_RE = re.compile(r"(<(?:br|p)(?:\s[^>]*)?>)( +)")


def _normalize_md_html(html: str) -> str:
    """规范 Markdown 转换产物的空白：只处理 br/p 开标签后的文本，<pre> 内换行缩进不受影响。"""
    html = _MD_BR_NEWLINE_RE.sub(r"\1", html)
    return _MD_LEADING_SPACES_RE.sub(
        lambda m: m.group(1) + "\u00a0" * len(m.group(2)), html
    )


def _scrub_css(css: str, allow_remote_images: bool) -> str:
    """按远程图片放行口径清洗 CSS：拦截时剥掉远程 url() 与 @import（data: 内联保留）。"""
    if allow_remote_images:
        return css

    def _repl(m: re.Match) -> str:
        target = (m.group(2) or "").strip().strip("'\"")
        return m.group(0) if target.lower().startswith("data:") else "none"

    return _CSS_URL_RE.sub(_repl, _CSS_IMPORT_RE.sub("", css))


def _append_decl(style: str, decl: str) -> str:
    style = style.strip().rstrip(";").strip()
    return f"{style};{decl}" if style else decl


def _declared_tiny(img: Tag) -> bool:
    """声明尺寸 ≤2px（width/height 属性或内联样式）→ 追踪像素。"""
    for attr in ("width", "height"):
        m = _TINY_ATTR_RE.match(str(img.get(attr) or ""))
        if m and int(m.group(1)) <= 2:
            return True
    return any(float(m.group(1)) <= 2 for m in _TINY_STYLE_RE.finditer(img.get("style") or ""))


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
    # <style> 先摘出（nh3 会连内容整体剥离）：CSS 自行按远程图片口径清洗后注回
    pre_soup = BeautifulSoup(raw_html or "", "html.parser")
    css_blocks = [
        _scrub_css(tag.get_text(), allow_remote_images) for tag in pre_soup.find_all("style")
    ]

    clean = nh3.clean(
        raw_html or "",
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        url_schemes=_URL_SCHEMES,
        link_rel="noopener noreferrer",
    )
    soup = BeautifulSoup(clean, "html.parser")
    blocked = 0

    # 拦截口径下 style 属性里的远程 url() 同样是追踪通道（nh3 不清洗属性内容）
    if not allow_remote_images:
        for el in soup.find_all(style=True):
            el.attrs["style"] = _scrub_css(el.attrs["style"], False)

    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if src.startswith(("http://", "https://")):
            if allow_remote_images:
                if _declared_tiny(img):
                    # 追踪像素（声明尺寸 ≤2px）：放行也隐形，不参与排版
                    img.attrs["style"] = _append_decl(img.get("style") or "", "display:none")
                elif "alt" not in img.attrs:
                    # 缺 alt 的远程图补空 alt：加载失败（如被浏览器反追踪拦截）不显裂图
                    img.attrs["alt"] = ""
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

    css = "\n".join(block for block in css_blocks if block.strip())
    if css.strip():
        tag = soup.new_tag("style")
        # 防 </style> 逃逸：CSS 字符串内 \< 是合法转义，规则位置本就无效
        tag.string = css.replace("</", "<\\/")
        soup.insert(0, tag)

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


# 收件端兜底样式：编辑器排版来自本地 CSS（.ProseMirror），收件人客户端没有——
# 主流邮箱会剥离 <style> 与类、只认内联样式，故发送前把同参数样式写进 style 属性。
# 与 frontend/src/index.css 的 .mail-editor/.mail-preview 保持同参，改动需三处同步。
_DECORATE_MONO = "'Courier New',Consolas,monospace"
_DECORATE_STYLE: dict[str, str] = {
    "p": "margin:0 0 1em",
    "h1": "font-size:1.5em;font-weight:600;margin:0.6em 0 0.3em",
    "h2": "font-size:1.3em;font-weight:600;margin:0.6em 0 0.3em",
    "h3": "font-size:1.15em;font-weight:600;margin:0.6em 0 0.3em",
    "blockquote": (
        "border-left:3px solid #e5e7eb;padding-left:12px;margin:0.5em 0;color:#6b7280"
    ),
    "pre": (
        "background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;"
        f"padding:10px 12px;font-size:13px;font-family:{_DECORATE_MONO}"
    ),
    "table": "border-collapse:collapse",
    "td": "border:1px solid #d1d5db;padding:4px 10px",
    "th": "border:1px solid #d1d5db;padding:4px 10px;background:#f9fafb;font-weight:600",
    "hr": "border:none;border-top:1px solid #e5e7eb",
    "img": "max-width:100%",
}


def decorate_outgoing_html(html: str) -> str:
    """发件方向内联化：把编辑器观感写进内联 style，收件端不依赖自家默认样式。

    在 sanitize_outgoing_html 之后调用（只处理白名单内的标签）；用户已有内联
    样式在后追加（同名声明后者生效，兜底不覆盖用户显式设置）。幂等性不做——
    只在发送管线跑一次，草稿里存的始终是未装饰的编辑器 HTML。
    """
    soup = BeautifulSoup(html or "", "html.parser")
    for el in soup.find_all("p"):
        # li 内段落不额外撑行距（与编辑器 li>p{margin:0} 同参）
        decl = "margin:0" if el.find_parent("li") else _DECORATE_STYLE["p"]
        el.attrs["style"] = _append_decl(el.get("style") or "", decl)
    for tag_name, decl in _DECORATE_STYLE.items():
        if tag_name == "p":
            continue
        for el in soup.find_all(tag_name):
            el.attrs["style"] = _append_decl(el.get("style") or "", decl)
    for el in soup.find_all("code"):
        # pre 内代码只去行内码样式（底色交给 pre），等宽字体仍显式带上（不依赖收件端继承）
        extra = f"background:none;padding:0;font-family:{_DECORATE_MONO}" if el.find_parent("pre") else (
            f"background:#f3f4f6;border-radius:4px;padding:1px 4px;font-size:0.92em;"
            f"font-family:{_DECORATE_MONO}"
        )
        el.attrs["style"] = _append_decl(el.get("style") or "", extra)
    return str(soup)


def html_to_plain_text(html: str) -> str:
    """HTML → 纯文本，作为发出邮件的 text/plain alternative。"""
    soup = BeautifulSoup(html or "", "html.parser")
    for br in soup.find_all("br"):
        nxt = br.next_sibling
        br.replace_with("\n")
        # nl2br 的输出是 "<br />\n"：br 换成的 \n 会与标签后的字面换行叠加成双换行
        # （B2 真机测试发现）——吃掉紧跟的一个换行，保住「单换行→单换行」语义
        if isinstance(nxt, NavigableString) and nxt.startswith("\n"):
            nxt.replace_with(nxt[1:])
    for block in soup.find_all(
        ["p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre"]
    ):
        if block.name in ("p", "div") and block.find_parent(["td", "th"]):
            block.append(" ")  # 单元格内段落用空格衔接，避免整表碎成多行
        else:
            block.append("\n")
    for cell in soup.find_all(["td", "th"]):
        cell.append(" ")  # 单元格之间补空格（无处理时 "表头A表头B" 粘连）
    text = soup.get_text()
    return re.sub(r"\n{3,}", "\n\n", text).replace("\u00a0", " ").strip()


def wrap_email_body_html(inner_html: str) -> str:
    """给正文 HTML 套上基础样式外层（无样式的客户端也能正常阅读）。"""
    return (
        '<div style="font-family:-apple-system,\'Segoe UI\',\'Microsoft YaHei\','
        'sans-serif;font-size:14px;line-height:1.65;color:#1f2937;white-space:normal">'
        + inner_html
        + "</div>"
    )


def markdown_to_email_html(markdown_text: str) -> str:
    """写信正文的 Markdown → 带基础样式的 HTML。换行语义同 markdown_body_html（单换行=分段）。"""
    return wrap_email_body_html(_normalize_md_html(markdown_body_html(markdown_text)))


def markdown_body_html(markdown_text: str) -> str:
    """Markdown → 裸 HTML（无外层样式），供编辑器内插入/模板/签名转换用。

    换行语义：单个换行=分段（与编辑器 Enter 一致），行尾 ≥2 空格=紧贴 <br>
    （与编辑器 Shift+Enter 一致）——全局统一，模板/签名/AI 同规则。
    """
    import markdown as md_lib

    html = md_lib.markdown(_enter_to_paragraph(markdown_text or ""),
                           extensions=["fenced_code", "tables"])
    return _normalize_md_html(html.replace("\ue000", "\u00a0"))


def markdown_to_plain_text(markdown_text: str) -> str:
    """Markdown → 纯文本（系统通知等纯文本场景）：先转 HTML 再派生纯文本。"""
    return html_to_plain_text(markdown_body_html(markdown_text))
