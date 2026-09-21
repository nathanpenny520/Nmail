"""前端元数据下发：分类枚举单一来源的 HTTP 出口（IMPROVEMENT_PLAN §3.3c）。

前端启动后拉取一次缓存（api/useMeta.ts），徽章与图表色不再手写——
加分类只改 app/ai/categories.py。

frontend_build（S-0921）：当前 dist 的构建指纹（vite 构建收尾写入 build-id.json，
每请求现读——不重启只重新 build 也能被感知）。前端轮询比对自身编译期注入的
__BUILD_ID__，不一致提示一键刷新：已打开的页面跑在内存里，后端换新前端后
不会自己更新（SPA 缓存策略只保证「刷新一次即最新」，解决不了「要记得刷新」）。
"""
import json

from fastapi import APIRouter

from app.ai.categories import CATEGORIES
from app.config import DIST_DIR

router = APIRouter(prefix="/api/meta", tags=["meta"])


def _frontend_build() -> str | None:
    if DIST_DIR is None:
        return None
    try:
        data = json.loads((DIST_DIR / "build-id.json").read_text())
        return str(data.get("id") or "") or None
    except (OSError, ValueError):
        return None  # 旧 dist / 开发模式无此文件 → 前端不比对


@router.get("")
def get_meta() -> dict:
    return {
        "categories": [
            {"key": c.key, "label": c.label, "color": c.color, "badge_cls": c.badge_cls}
            for c in CATEGORIES
        ],
        "frontend_build": _frontend_build(),
    }
