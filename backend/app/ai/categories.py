"""分类枚举的单一来源（IMPROVEMENT_PLAN §3.3c，原散布 6 处）。

定义一处：prompts 的分类提示词段、tasks 的结果校验、pipeline 的自动归档集合、
digest 的分桶顺序、GET /api/meta 下发（前端徽章类与图表色）全部消费这里。
**加分类 = 本文件加一行 Category**，其余自动跟随。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    key: str
    label: str        # 中文显示名
    color: str        # 图表用色（hex，与徽章色系同源，经调色板校验）
    badge_cls: str    # 前端徽章 Tailwind 类
    description: str  # 分类提示词中的判定说明


CATEGORIES: tuple[Category, ...] = (
    Category("work", "工作", "#6366f1", "bg-indigo-100 text-indigo-700",
             "工作/业务往来，需要人处理的正式通信"),
    Category("personal", "个人", "#10b981", "bg-emerald-100 text-emerald-700",
             "亲友等个人来信"),
    Category("notification", "通知", "#0ea5e9", "bg-sky-100 text-sky-700",
             "系统通知（订单、账单、部署、安全提醒等自动发送）"),
    Category("verification", "验证码", "#f59e0b", "bg-amber-100 text-amber-700",
             "验证码/一次性密码"),
    Category("promo", "营销", "#f43f5e", "bg-rose-100 text-rose-600",
             "营销/推广/订阅通讯/广告"),
    Category("social", "社交", "#8b5cf6", "bg-violet-100 text-violet-700",
             "社交网络通知（点赞、关注、评论）"),
)

#: 有序 key 元组（digest 分桶、前端图表轴序）
CATEGORY_ORDER: tuple[str, ...] = tuple(c.key for c in CATEGORIES)
#: 校验用集合（tasks.classify_batch）
CATEGORY_KEYS: frozenset[str] = frozenset(CATEGORY_ORDER)
#: 自动归档集合（pipeline：营销进「已归档」）
AUTO_ARCHIVE_CATEGORIES: frozenset[str] = frozenset({"promo"})


def categories_prompt_block() -> str:
    """生成分类提示词中的 category 段（条目数与说明随本表自动更新）。"""
    lines = [f"category {len(CATEGORIES)} 选一："]
    lines.extend(f"- {c.key}：{c.description}" for c in CATEGORIES)
    return "\n".join(lines)
