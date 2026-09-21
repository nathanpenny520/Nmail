"""发送前检查（precheck）规则层：零成本、零 AI 依赖，所有发送入口共用。

检查项（人工发送由前端先调 precheck 端点弹卡、可越过；定时发送与 AI 发送在
发送前强制执行——blocker 不发出、退回来源态并通知）：
- 空主题（blocker）：收件人难以检索，定时/自动路径直接拦
- 模板占位符残留（blocker）：{xxx}、[xxx]、___、Xx 序列、常见中文占位词——
  模板信"部分地方没改正"的核心痛点，纯正则即可覆盖大半
- 附件意图核对：正文提到附件但草稿没有附件（blocker）；有附件但正文全未提及（warn）

AI 深审（主题与正文匹配、错别字等）在 ai.tasks.review_send_draft，由 API 层与
scheduler 按需叠加——本模块保持零 AI 依赖（core 分层约束）。
"""
from __future__ import annotations

import re

from app.core.mail_html import html_to_plain_text
from app.db.database import get_conn

# 占位符模式：正文里正常出现的花括号/方括号/填空线/X 序列大概率是模板没改净。
# 误报靠「人工可越过」消化，定时/自动路径退回也不丢内容
_PLACEHOLDER_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\{[^{}\n]{1,40}\}"), "花括号占位符"),
    (re.compile(r"\[[^\[\]\n]{1,24}\]"), "方括号占位符"),
    (re.compile(r"_{3,}"), "下划线填空"),
    # X 占位（xx/XXX）：边界排除邮箱/网址/单词内部，避免误伤 xxx@x.com、XXL
    (re.compile(r"(?<![\w@.+-])[Xx]{2,}(?![\w@.+-])"), "X 占位"),
    (re.compile(r"此处填写|待补充|待填写|在此输入|某某某|某某公司|某公司|某先生|某女士"), "中文占位词"),
)
# 方括号里纯数字/时间/编号不是占位符（如 [2026]、[9:00]、[1]）
_BRACKET_BENIGN = re.compile(r"^[\d\s:.\-/#]+$")
# 附件意图词（中英文）
_ATTACHMENT_HINT = re.compile(r"附件|随附|附上|attached|attachment", re.IGNORECASE)


def rule_issues(subject: str, body_html: str, has_attachments: bool) -> list[dict]:
    """对一封信的规则检查。返回 Issue 列表：
    ``{"code", "severity": "blocker"|"warn", "message"}``。"""
    issues: list[dict] = []
    if not (subject or "").strip():
        issues.append({
            "code": "empty_subject", "severity": "blocker",
            "message": "主题为空——收件人难以检索和识别这封邮件",
        })
    text = html_to_plain_text(body_html or "")
    for pat, label in _PLACEHOLDER_PATTERNS:
        m = pat.search(text)
        # 方括号白名单对括号内内容判定（m.group() 含括号本身，需剥掉）
        if m and not (label == "方括号占位符" and _BRACKET_BENIGN.match(m.group()[1:-1])):
            issues.append({
                "code": "placeholder", "severity": "blocker",
                "message": f"正文疑似有未替换的{label}「{m.group()[:20]}」——模板改漏了？",
            })
            break  # 一处即报，不重复刷屏
    mentions = bool(_ATTACHMENT_HINT.search(text))
    if mentions and not has_attachments:
        issues.append({
            "code": "attachment_missing", "severity": "blocker",
            "message": "正文提到了附件，但草稿没有添加任何附件",
        })
    elif has_attachments and not mentions:
        issues.append({
            "code": "attachment_unmentioned", "severity": "warn",
            "message": "已添加附件，但正文没有提及——确认附件确实是这封信要带的",
        })
    return issues


def draft_rule_issues(draft_id: int, row) -> list[dict]:  # noqa: ANN001 — sqlite3.Row
    """便利封装：从 user_drafts 行取主题/正文，查附件计数后跑规则检查。"""
    n_att = get_conn().execute(
        "SELECT COUNT(*) n FROM user_draft_attachments WHERE draft_id = ?", (draft_id,)
    ).fetchone()["n"]
    return rule_issues(row["subject"], row["body_html"], n_att > 0)
