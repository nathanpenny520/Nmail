"""mail_html 消毒层测试：收发双向 XSS 样本与图片控制（IMPROVEMENT_PLAN T1）。"""
from __future__ import annotations

from app.core.mail_html import (
    count_remote_images,
    html_to_plain_text,
    markdown_to_email_html,
    sanitize_email_html,
    sanitize_outgoing_html,
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
