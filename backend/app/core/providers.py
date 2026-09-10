"""服务商预设库。

数据为各服务商公开的 IMAP/SMTP 服务器事实性配置，供添加账号时按邮箱域名自动匹配。
"""
from __future__ import annotations

from dataclasses import dataclass

# (名称, 域名元组, IMAP服务器, IMAP端口, SMTP服务器, SMTP端口, 添加账号时展示的提示)
_PRESET_ROWS: list[tuple[str, tuple[str, ...], str, int, str, int, str]] = [
    ("QQ 邮箱", ("qq.com", "vip.qq.com", "foxmail.com"),
     "imap.qq.com", 993, "smtp.qq.com", 465,
     "需在 QQ 邮箱网页版设置-账号中开启 IMAP/SMTP 服务；密码填短信获取的授权码（非 QQ 密码）"),
    ("网易 163", ("163.com",),
     "imap.163.com", 993, "smtp.163.com", 465,
     "需开启 IMAP/SMTP；密码填授权码（非登录密码）。163 授权码有有效期，失效后 Nmail 会提醒你重新授权"),
    ("网易 126", ("126.com",),
     "imap.126.com", 993, "smtp.126.com", 465,
     "需开启 IMAP/SMTP；密码填授权码"),
    ("网易 yeah.net", ("yeah.net",),
     "imap.yeah.net", 993, "smtp.yeah.net", 465,
     "需开启 IMAP/SMTP；密码填授权码"),
    ("新浪邮箱", ("sina.com", "sina.cn"),
     "imap.sina.com", 993, "smtp.sina.com", 465,
     "需开启 IMAP/SMTP；密码填授权码"),
    ("搜狐邮箱", ("sohu.com",),
     "imap.sohu.com", 993, "smtp.sohu.com", 465,
     "需开启 POP3/IMAP/SMTP 服务；密码填授权码"),
    ("Gmail", ("gmail.com", "googlemail.com"),
     "imap.gmail.com", 993, "smtp.gmail.com", 465,
     "需开启两步验证并使用应用专用密码（Google 账号-安全-应用密码）；OAuth 支持在远期版本提供"),
    ("Outlook / Hotmail", ("outlook.com", "hotmail.com", "live.com", "msn.com"),
     "outlook.office365.com", 993, "smtp.office365.com", 587,
     "Microsoft 已限制基础密码认证，个人账号需使用应用密码；企业账号可能需管理员启用 IMAP"),
    ("Yahoo Mail", ("yahoo.com",),
     "imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 465,
     "需在账号安全设置中生成应用密码"),
    ("iCloud 邮箱", ("icloud.com", "me.com", "mac.com"),
     "imap.mail.me.com", 993, "smtp.mail.me.com", 587,
     "需在 Apple 账号中生成 App 专用密码"),
    ("Zoho Mail", ("zoho.com", "zohomail.com"),
     "imap.zoho.com", 993, "smtp.zoho.com", 465,
     "需在设置中开启 IMAP 访问"),
    ("Yandex Mail", ("yandex.com", "yandex.ru"),
     "imap.yandex.com", 993, "smtp.yandex.com", 465,
     "需在设置中开启 IMAP 并使用应用密码"),
    ("GMX Mail", ("gmx.com", "gmx.net"),
     "imap.gmx.com", 993, "mail.gmx.com", 587,
     "需在设置中开启 POP3/IMAP 访问"),
    ("Fastmail", ("fastmail.com",),
     "imap.fastmail.com", 993, "smtp.fastmail.com", 465,
     "需在设置-隐私与安全中生成应用专用密码"),
    ("AOL Mail", ("aol.com",),
     "imap.aol.com", 993, "smtp.aol.com", 465,
     "需在账号安全中生成应用密码"),
    ("阿里云邮箱", ("aliyun.com",),
     "imap.aliyun.com", 993, "smtp.aliyun.com", 465,
     "需在网页版设置中开启 IMAP/SMTP；密码填密码或独立密码"),
    ("腾讯企业邮", ("exmail.qq.com",),
     "imap.exmail.qq.com", 993, "smtp.exmail.qq.com", 465,
     "需管理员开启 IMAP/SMTP；密码填安全登录客户端专用密码"),
    ("网易企业邮", ("qiye.163.com",),
     "imap.qiye.163.com", 993, "smtp.qiye.163.com", 465,
     "需开启 IMAP；密码填客户端授权密码"),
    ("Proton Mail", ("proton.me", "protonmail.com"),
     "127.0.0.1", 1143, "127.0.0.1", 1025,
     "Proton 不开放直连 IMAP，需在本机安装并运行 Proton Mail Bridge 后使用"),
]

# 未匹配到预设时允许手动填写的兜底提示
MANUAL_NOTE = "未识别的服务商：请查阅邮箱帮助页，手动填写 IMAP/SMTP 服务器与端口，密码通常为授权码或应用密码"


@dataclass(frozen=True)
class ProviderPreset:
    name: str
    domains: tuple[str, ...]
    imap_server: str
    imap_port: int
    smtp_server: str
    smtp_port: int
    note: str


PRESETS: list[ProviderPreset] = [ProviderPreset(*row) for row in _PRESET_ROWS]


def match_provider(email: str) -> ProviderPreset | None:
    """按邮箱域名匹配服务商预设；未匹配返回 None。"""
    domain = email.rsplit("@", 1)[-1].strip().lower()
    if not domain:
        return None
    for preset in PRESETS:
        if domain in preset.domains:
            return preset
    return None
