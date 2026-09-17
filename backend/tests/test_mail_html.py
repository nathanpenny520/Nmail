"""mail_html 消毒层测试：收发双向 XSS 样本与图片控制（IMPROVEMENT_PLAN T1）。"""
from __future__ import annotations

from app.core.mail_html import (
    count_remote_images,
    decorate_outgoing_html,
    html_to_plain_text,
    markdown_body_html,
    markdown_to_email_html,
    sanitize_email_html,
    sanitize_outgoing_html,
    wrap_email_body_html,
)


def _clean(html: str, **kwargs) -> str:
    kwargs.setdefault("allow_remote_images", False)
    out, _blocked = sanitize_email_html(html, **kwargs)
    return out


def test_script_tag_removed():
    out = _clean("<p>hi</p><script>alert(1)</script>")
    assert "<script" not in out
    assert "hi" in out  # 正文保留


def test_event_handler_removed():
    out = _clean('<button onclick="alert(1)">x</button>')
    assert "onclick" not in out


def test_javascript_href_removed():
    out = _clean('<a href="javascript:alert(1)">x</a>')
    assert "javascript:" not in out


def test_iframe_object_removed():
    out = _clean('<iframe src="https://evil.example"></iframe><object data="x"></object>')
    assert "<iframe" not in out
    assert "<object" not in out


def test_remote_image_blocked_by_default_and_counted():
    html = '<img src="http://evil.example/x.png"><img src="https://ok.example/y.gif">'
    out, blocked = sanitize_email_html(html, allow_remote_images=False)
    assert blocked == 2
    assert "evil.example" not in out  # 原地址被占位符替换


def test_remote_image_allowed_with_flag():
    _out, blocked = sanitize_email_html('<img src="http://e.example/x.png">', allow_remote_images=True)
    assert blocked == 0


def test_data_image_stripped_on_receive_but_allowed_outgoing():
    html = '<img src="data:image/png;base64,AAAA">'
    assert "data:" not in _clean(html)  # 收件路径不放行 data:
    assert "data:image/png;base64" in sanitize_outgoing_html(html)  # 发件路径放行（内嵌截图）


def test_outgoing_strips_script():
    out = sanitize_outgoing_html("<p>x</p><script>alert(1)</script>")
    assert "<script" not in out


def test_external_links_get_target_blank():
    out = _clean('<a href="https://example.com">l</a>')
    assert 'target="_blank"' in out


def test_cid_inline_needs_existing_file(tmp_path):
    payload = b"\x89PNG fake"
    f = tmp_path / "logo.png"
    f.write_bytes(payload)
    html = '<img src="cid:logo1">'
    out, blocked = sanitize_email_html(
        html, allow_remote_images=True, cid_map={"logo1": (str(f), "image/png")}
    )
    assert blocked == 0
    assert "data:image/png;base64" in out

    missing, _b = sanitize_email_html(
        html, allow_remote_images=True, cid_map={"nope": (str(tmp_path / "gone.png"), "image/png")}
    )
    assert "cid:" not in missing  # 无对应文件的 cid 图被移除


def test_count_remote_images():
    html = '<img src="http://a/x.png"><img src="https://b/y.gif"><img src="cid:z">'
    assert count_remote_images(html) == 2
    assert count_remote_images("<p>无图</p>") == 0


def test_html_to_plain_text():
    out = html_to_plain_text("<p>行一</p><p>行二</p><br>行三")
    assert "行一" in out and "行二" in out and "行三" in out
    assert "<" not in out


def test_markdown_to_email_html_wrapped():
    out = markdown_to_email_html("# 标题\n\n**加粗**")
    assert "wrap" not in out  # wrap 只是容器，不出现字面
    assert "<h1>" in out and "<strong>" in out


def test_markdown_nl2br_single_newline_kept():
    """nl2br：单个换行转 <br>（模板/签名/AI 起草的用户预期），空行分段不变。"""
    out = markdown_to_email_html("第一行\n第二行\n\n第三行")
    assert "<p>第一行<br />" in out  # 单换行→<br>，同段内
    assert "<p>第三行</p>" in out  # 空行仍分段
    body = markdown_body_html("张三\n产品部")
    assert "张三<br />" in body


def test_plain_text_single_newline_after_br():
    """nl2br 产出 "<br />\\n"：br→\\n 后不得与字面换行叠成双换行（B2 真机测试发现）。"""
    plain = html_to_plain_text(markdown_to_email_html("第一行\n第二行\n\n第三行"))
    assert plain == "第一行\n第二行\n\n第三行"


def test_style_tag_preserved_with_selectors():
    html = "<style>a > b { color: #1366ec } .x{width:50%}</style><p>hi</p>"
    out = _clean(html)
    assert "<style>" in out and "a > b" in out  # 内容原样保留（含子选择器）
    assert "<p>hi</p>" in out


def test_style_css_remote_url_stripped_when_blocked():
    html = (
        "<style>@import url(https://evil.example/x.css);"
        "a{background:url('https://evil.example/t.gif')}"
        "b{background:url(data:image/png;base64,AAAA)}</style>"
    )
    out = _clean(html)
    assert "evil.example" not in out
    assert "@import" not in out
    assert "url(data:image/png;base64,AAAA)" in out  # 内联图保留
    # 放行口径下全部保留
    out2, _ = sanitize_email_html(html, allow_remote_images=True)
    assert "evil.example" in out2 and "@import" in out2


def test_style_attr_remote_url_stripped_when_blocked():
    html = '<div style="background:url(https://evil.example/t.png)">x</div>'
    assert "evil.example" not in _clean(html)  # 拦截态下 style 属性也是追踪通道
    out2, _ = sanitize_email_html(html, allow_remote_images=True)
    assert "evil.example" in out2


def test_tracking_pixel_hidden_when_allowed():
    html = '<img src="https://e.example/p.gif" width="1" height="1"><img src="https://e.example/big.png">'
    out, blocked = sanitize_email_html(html, allow_remote_images=True)
    assert blocked == 0
    assert out.count("display:none") == 1  # 仅声明尺寸 ≤2px 的被隐形
    assert out.count("display:none") < out.count("<img")  # 大图不受影响


def test_remote_img_missing_alt_gets_empty_alt():
    html = '<img src="https://e.example/a.png"><img src="https://e.example/b.png" alt="logo">'
    out, _ = sanitize_email_html(html, allow_remote_images=True)
    assert out.count('alt=""') == 1  # 缺 alt 补空 alt（加载失败不显裂图），自带 alt 不动
    assert 'alt="logo"' in out


def test_style_tag_escape_guard():
    out = _clean("<style>.x::after{content:'</style><script>alert(1)</script>'}</style><p>hi</p>")
    assert "<script" not in out  # </style> 逃逸被截断，后续内容不会变成标签


def test_document_without_style_unchanged():
    out = _clean('<p style="color:red">hi</p>')
    assert "<style>" not in out and 'style="color:red"' in out


def test_outgoing_mark_highlight_preserved():
    # 回归：mark 曾不在发件白名单，高亮发出去即被剥成裸文本
    out = sanitize_outgoing_html('<p>前<mark style="background-color:#fff176">高亮</mark>后</p>')
    assert "<mark" in out and "background-color:#fff176" in out


def test_decorate_outgoing_html_table_and_paragraph():
    html = (
        "<table><tbody><tr><th>表头</th><td>格</td></tr></tbody></table>"
        "<p>段落</p><ul><li><p>列表项</p></li></ul>"
    )
    out = decorate_outgoing_html(html)
    assert "border-collapse:collapse" in out
    assert "border:1px solid #d1d5db;padding:4px 10px" in out  # td/th 边框进内联
    assert "background:#f9fafb" in out  # th 灰底
    assert "margin:0 0 1em" in out  # 普通段落
    assert "margin:0" in out  # li 内段落不撑行距


def test_decorate_keeps_existing_style():
    out = decorate_outgoing_html('<p style="text-align:center">居中</p>')
    assert "text-align:center" in out and "margin:0 0 1em" in out


def test_decorate_blockquote_pre_code():
    html = "<blockquote><p>引用</p></blockquote><pre><code>code()</code></pre><p><code>行内</code></p>"
    out = decorate_outgoing_html(html)
    assert "border-left:3px solid #e5e7eb" in out
    assert out.count("font-family:") == 3  # pre + 两处 code（等宽字体带到收件端）
    assert "background:#f3f4f6" in out  # 行内码底色
    assert "background:none" in out  # pre 内代码不重复行内码样式


def test_send_pipeline_mark_and_table_survive():
    raw = '<p><mark style="background-color:#fff176">高亮</mark></p><table><tr><td>甲</td></tr></table>'
    out = wrap_email_body_html(decorate_outgoing_html(sanitize_outgoing_html(raw)))
    assert "<mark" in out  # 高亮到达收件端
    assert "border:1px solid" in out  # 表格边框到达收件端


def test_plain_text_table_cells_separated():
    out = html_to_plain_text(
        "<table><tr><th>甲</th><th>乙</th></tr><tr><td>1</td><td>2</td></tr></table>"
    )
    assert "甲 乙" in out
    assert "1 2" in out
