"""应用内更新检查：对比 GitHub Releases 最新 tag 与本地版本。

隐私边界：仅向 api.github.com 发起一次无鉴权 GET（UA 标明 Nmail/版本），
不携带任何本机数据；结果缓存 24 小时，可在 设置-通用 中关闭。
发现新版本时写入现有通知中心（type=update，按 ref_id=版本号去重）；
升级到当前版本后自动清理过期的更新通知。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, UTC

import httpx

from app.config import APP_VERSION
from app.db.database import get_conn, get_setting, set_setting

RELEASES_API = "https://api.github.com/repos/nathanpenny520/Nmail/releases/latest"
RELEASES_PAGE = "https://github.com/nathanpenny520/Nmail/releases/latest"
CHECK_INTERVAL_HOURS = 24
_STATE_KEY = "update_check_state"
_HTTP_TIMEOUT = httpx.Timeout(8.0, connect=4.0)

_VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+)+)")


def _parse_version(tag: str) -> tuple[int, ...] | None:
    m = _VERSION_RE.match(tag.strip())
    if not m:
        return None
    return tuple(int(p) for p in m.group(1).split("."))


def _is_newer(latest: str | None, current: str) -> bool:
    latest_v, current_v = _parse_version(latest or ""), _parse_version(current)
    return bool(latest_v and current_v and latest_v > current_v)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _fresh(state: dict) -> bool:
    checked_at = state.get("checked_at") or ""
    try:
        last = datetime.fromisoformat(checked_at)
    except ValueError:
        return False
    return datetime.now(UTC) - last < timedelta(hours=CHECK_INTERVAL_HOURS)


def _fetch_latest() -> dict | None:
    try:
        resp = httpx.get(
            RELEASES_API,
            timeout=_HTTP_TIMEOUT,
            headers={"User-Agent": f"Nmail/{APP_VERSION}", "Accept": "application/vnd.github+json"},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        tag = (data.get("tag_name") or "").strip()
        if not _parse_version(tag):
            return None
        return {"version": tag, "url": data.get("html_url") or RELEASES_PAGE}
    except httpx.HTTPError:
        return None


def _notify_new_version(version: str, url: str) -> None:
    """发现新版本时写一条通知；同版本只写一次（ref_id 去重）。"""
    conn = get_conn()
    exists = conn.execute(
        "SELECT id FROM notifications WHERE type = 'update' AND ref_id = ?", (version,)
    ).fetchone()
    if exists:
        return
    conn.execute(
        "INSERT INTO notifications (type, title, body, ref_id) VALUES (?, ?, ?, ?)",
        ("update", f"有新版本 {version}",
         f"Nmail {version} 已发布，可到 GitHub Releases 下载替换（数据不受影响）。\n{url}\n"
         "（此提醒仅来自一次匿名的版本号对比，可在设置中关闭自动检查）",
         version),
    )
    conn.commit()


def _cleanup_stale_notifications() -> None:
    """已在当前版本之后的历史更新提醒自动清掉。"""
    current = _parse_version(APP_VERSION)
    if not current:
        return
    conn = get_conn()
    stale_ids = [
        r["id"]
        for r in conn.execute("SELECT id, ref_id FROM notifications WHERE type = 'update'").fetchall()
        if (v := _parse_version(r["ref_id"] or "")) and v <= current
    ]
    if stale_ids:
        conn.executemany("DELETE FROM notifications WHERE id = ?", [(i,) for i in stale_ids])
        conn.commit()


def get_state(force: bool = False) -> dict:
    """返回更新检查状态；距上次成功检查不足 24h（且非强制）时用缓存。"""
    enabled = bool(get_setting("update_check_enabled", True))
    state: dict = get_setting(_STATE_KEY, {}) or {}
    if enabled and (force or not _fresh(state)):
        latest = _fetch_latest()
        if latest:  # 拉取失败时保留旧缓存，下次再试
            state = {
                "checked_at": _now_iso(),
                "latest_version": latest["version"],
                "release_url": latest["url"],
            }
            set_setting(_STATE_KEY, state)
            if _is_newer(state["latest_version"], APP_VERSION):
                _notify_new_version(state["latest_version"], state["release_url"])
    _cleanup_stale_notifications()
    latest_version = state.get("latest_version")
    return {
        "enabled": enabled,
        "current_version": APP_VERSION,
        "latest_version": latest_version,
        "is_newer": _is_newer(latest_version, APP_VERSION) if enabled else False,
        "release_url": state.get("release_url") or RELEASES_PAGE,
        "checked_at": state.get("checked_at"),
    }
