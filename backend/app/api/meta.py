"""前端元数据下发：分类枚举单一来源的 HTTP 出口（IMPROVEMENT_PLAN §3.3c）。

前端启动后拉取一次缓存（api/useMeta.ts），徽章与图表色不再手写——
加分类只改 app/ai/categories.py。
"""
from fastapi import APIRouter

from app.ai.categories import CATEGORIES

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("")
def get_meta() -> dict:
    return {
        "categories": [
            {"key": c.key, "label": c.label, "color": c.color, "badge_cls": c.badge_cls}
            for c in CATEGORIES
        ],
    }
