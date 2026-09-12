"""对外 API（v0.4 P7，REDESIGN_PLAN §7）：/api/ext/v1/*，供用户自己的脚本/自动化经
本机进程或自建隧道调用。

认证：X-Api-Key 请求头（sha256 哈希存 api_keys 表，明文存 secrets.json 所见即所存）；
scope 分级 read / write / send / agent；限流 60 次/分钟（内存滑动窗），可选每 Key 每日
上限；调用全量记 api_calls（30 天保留，/health 除外）。服务仍只绑定 127.0.0.1——
外部设备走用户自建隧道（cloudflared/Tailscale/SSH，示例见 docs/对外API使用指南.md）。
/api/ext/* 豁免 Host/Origin 来源校验（main.py），改持 API Key——自定义请求头浏览器
跨站带不上（触发预检而本服务不应答），drive-by 风险由 Key 兜住。

端点全部薄壳转调既有能力（api/emails、user_drafts、folders、contacts、digest、
ai/agent），不实现新的邮件操作。
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.ai import agent, tasks
from app.api import contacts as contacts_api
from app.api import digest as digest_api
from app.api import emails as emails_api
from app.api import user_drafts
from app.api.ai import AgentDecisionIn
from app.core import folders as folders_core
from app.core import sync as sync_engine
from app.db.database import get_conn, get_setting

router = APIRouter(prefix="/api/ext/v1", tags=["ext-api"])

RATE_LIMIT_PER_MIN = 60
SCOPES = ("read", "write", "send", "agent")

# ── 认证、限流与每日上限 ─────────────────────────────────────

_rate_buckets: dict[int, deque[float]] = defaultdict(deque)
_daily_counters: dict[int, tuple[str, int]] = {}
_last_used_flush: dict[int, float] = {}


def _check_rate(key_id: int) -> None:
    """60 次/分钟滑动窗 + 每 Key 每日上限（内存计数，重启清零——本地单机软限制）。"""
    now = time.monotonic()
    dq = _rate_buckets[key_id]
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= RATE_LIMIT_PER_MIN:
        raise HTTPException(429, f"调用过于频繁（上限 {RATE_LIMIT_PER_MIN} 次/分钟）")
    dq.append(now)


def _check_daily_limit(row) -> None:  # noqa: ANN001 — sqlite3.Row
    limit = row["daily_limit"]
    if not limit:
        return
    today = time.strftime("%Y-%m-%d")
    count = _daily_counters.get(int(row["id"]), ("", 0))
    n = count[1] + 1 if count[0] == today else 1
    if n > int(limit):
        raise HTTPException(429, f"已达该 Key 的每日调用上限（{limit} 次/天），明天再试或到设置调整")
    _daily_counters[int(row["id"])] = (today, n)


def require_key(*required: str):
    """API Key 认证依赖工厂：require_key("read") / require_key("write") 等。

    校验顺序：总开关 → Key 有效性 → scope → 限流/每日上限。通过后在
    request.state.ext_key_id 落 Key id（main.py 的调用日志中间件消费）。
    """

    def dep(request: Request):
        if not bool(get_setting("api_enabled", False)):
            raise HTTPException(403, "对外 API 未启用：请到 设置-API 打开开关")
        presented = request.headers.get("x-api-key", "")
        if not presented:
            raise HTTPException(401, "缺少 X-Api-Key 请求头")
        key_hash = hashlib.sha256(presented.encode()).hexdigest()
        row = get_conn().execute(
            "SELECT * FROM api_keys WHERE key_hash = ? AND revoked = 0", (key_hash,)
        ).fetchone()
        if row is None:
            raise HTTPException(401, "API Key 无效或已吊销")
        if not set(required) <= set(json.loads(row["scopes"] or "[]")):
            raise HTTPException(403, f"该 Key 缺少所需 scope：{'/'.join(required)}（到 设置-API 调整）")
        _check_rate(int(row["id"]))
        _check_daily_limit(row)
        key_id = int(row["id"])
        request.state.ext_key_id = key_id
        # last_used_at 节流回写：每 Key 至多 60s 一次，避免高频调用刷库
        now = time.monotonic()
        if now - _last_used_flush.get(key_id, 0) > 60:
            _last_used_flush[key_id] = now
            conn = get_conn()
            conn.execute("UPDATE api_keys SET last_used_at = datetime('now') WHERE id = ?", (key_id,))
            conn.commit()
        return row

    return dep


# 依赖单例（B008：参数默认值不写函数调用；FastAPI 支持复用同一 Depends 实例）
READ_KEY = Depends(require_key("read"))
WRITE_KEY = Depends(require_key("write"))
SEND_KEY = Depends(require_key("send"))
AGENT_KEY = Depends(require_key("agent"))


def log_ext_call(request: Request, status: int) -> None:
    """api_calls 落一行（main.py 中间件经线程池调用）；日志开关关闭时不记。"""
    if not bool(get_setting("api_log_enabled", True)):
        return
    key_id = getattr(request.state, "ext_key_id", None) or 0
    try:
        conn = get_conn()
        conn.execute(
            "INSERT INTO api_calls (key_id, method, path, status) VALUES (?, ?, ?, ?)",
            (key_id, request.method, request.url.path, status),
        )
        conn.commit()
    except Exception:  # noqa: BLE001 — 日志失败不影响响应
        pass


# ── 端点：存活探测（免认证，隧道连通性自测用）──────────────────

@router.get("/health")
def ext_health() -> dict:
    return {"ok": True}


# ── 端点：read ──────────────────────────────────────────────

@router.get("/accounts")
def ext_accounts(_: Any = READ_KEY) -> dict:
    rows = get_conn().execute("SELECT * FROM accounts ORDER BY id").fetchall()
    return {"accounts": [
        {
            "id": r["id"], "email": r["email"], "color": r["color"],
            "status": r["status"], "status_detail": r["status_detail"],
            "last_sync_at": r["last_sync_at"],
        }
        for r in rows
    ]}


@router.get("/emails")
def ext_list_emails(
    account_id: int | None = None,
    folder: str | None = None,
    q: str | None = None,
    is_read: bool | None = None,
    starred: bool | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _: Any = READ_KEY,
) -> dict:
    """列表/搜索：与内部 /api/emails 同一实现（FTS5 检索、排序、上限 200）。"""
    return emails_api.list_emails(
        account_id=account_id, folder=folder, q=q, is_read=is_read,
        starred=starred, category=category, limit=limit, offset=offset,
    )


@router.get("/emails/{email_id}")
def ext_get_email(email_id: int, _: Any = READ_KEY) -> dict:
    """详情：返回与内部一致的消毒 HTML（远程图片默认拦截）。"""
    return emails_api.get_email(email_id, images=False)


@router.get("/emails/{email_id}/attachments/{attachment_id}")
def ext_download_attachment(email_id: int, attachment_id: int, _: Any = READ_KEY):
    return emails_api.download_attachment(attachment_id)


@router.get("/drafts")
def ext_list_drafts(status: str = "pending_review", _: Any = READ_KEY) -> dict:
    """草稿列表（统一草稿体系；默认列 AI 待审）。"""
    return user_drafts.list_drafts(status=status)


@router.get("/folders")
def ext_folders(account_id: int, _: Any = READ_KEY) -> dict:
    """账号文件夹缓存列表（不触发服务器 LIST；先经 POST /folders/sync 按需同步）。"""
    try:
        return {"folders": folders_core.get_list(account_id, refresh=False)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"获取文件夹失败：{exc}") from exc


@router.get("/contacts")
def ext_contacts(q: str = "", limit: int = 50, _: Any = READ_KEY) -> dict:
    return contacts_api.list_contacts(q=q, limit=limit)


@router.get("/digest")
def ext_digest(_: Any = READ_KEY) -> dict:
    return digest_api.get_digest()


@router.get("/jobs/{job_id}")
def ext_job(job_id: str, _: Any = READ_KEY) -> dict:
    """批量动作异步任务进度（POST /emails/actions 对慢动作返回 job_id 后在此轮询）。"""
    from app.api.jobs import get_job

    return get_job(job_id)


# ── 端点：write ─────────────────────────────────────────────

class ExtActionsIn(BaseModel):
    ids: list[int]
    action: str  # read|unread|star|unstar|move|trash|archive|unarchive
    folder: str | None = None  # action=move 的目标文件夹


@router.post("/emails/actions")
def ext_email_actions(payload: ExtActionsIn, _: Any = WRITE_KEY) -> dict:
    """批量动作：与内部 /api/emails/batch-action 同一实现——打标类同步返回，
    move/trash/archive 等服务器移动类异步（响应含 job_id，经 GET /jobs/{id} 轮询）。"""
    return emails_api.batch_action(
        emails_api.BatchActionIn(ids=payload.ids, action=payload.action, folder=payload.folder)
    )


class ExtDraftIn(BaseModel):
    account_id: int
    to: str = ""            # 逗号分隔地址串（与内部草稿同格式）
    cc: str = ""
    bcc: str = ""
    subject: str = ""
    body_html: str = ""


@router.post("/drafts")
def ext_create_draft(payload: ExtDraftIn, _: Any = WRITE_KEY) -> dict:
    """创建草稿（统一草稿体系，status=editing；不会自动发送）。"""
    return user_drafts.create_draft(user_drafts.UserDraftIn(
        account_id=payload.account_id, mode="new", to_addrs=payload.to,
        cc_addrs=payload.cc, bcc_addrs=payload.bcc,
        subject=payload.subject, body_html=payload.body_html,
    ))


@router.post("/folders/sync")
def ext_folder_sync(
    account_id: int,
    name: str,
    _: Any = WRITE_KEY,
) -> dict:
    """按需同步指定文件夹（IMAP 名含分隔符，走查询参数与内部一致）。"""
    row = get_conn().execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "账号不存在")
    return sync_engine.start_sync(
        {"id": row["id"], "email": row["email"],
         "imap_server": row["imap_server"], "imap_port": row["imap_port"]},
        folders=(name,),
    )


# ── 端点：send ──────────────────────────────────────────────

@router.post("/drafts/{draft_id}/approve")
def ext_approve_draft(draft_id: int, _: Any = SEND_KEY) -> dict:
    """发送草稿（outbox 同一通路：In-Reply-To、消毒、Sent 归档全复用）。"""
    return user_drafts.send_draft(draft_id)


# ── 端点：agent ─────────────────────────────────────────────

class ExtAgentIn(BaseModel):
    question: str
    history: list[dict] | None = None
    account_ids: list[int] = Field(default_factory=list)  # 空=全部账号
    mode: str = "approval"          # approval | auto
    session_id: int | None = None
    profile_id: str | None = None


def _ext_agent_events(payload: ExtAgentIn) -> list[dict]:
    """跑一轮 Agent 循环并收集全部事件（origin=api，动作进 ai_actions 审计）。"""
    account_ids = payload.account_ids or [
        int(r["id"]) for r in get_conn().execute("SELECT id FROM accounts").fetchall()
    ]
    if payload.mode not in ("approval", "auto"):
        raise HTTPException(400, "mode 需为 approval/auto")
    events: list[dict] = []
    for event in agent.run_stream(
        payload.question, payload.history, payload.session_id,
        account_ids, payload.mode, payload.profile_id, origin="api",
    ):
        events.append(event)
    return events


@router.post("/agent/chat")
def ext_agent_chat(payload: ExtAgentIn, _: Any = AGENT_KEY) -> dict:
    """总管家对话（非流式）：返回最终回答 + 完整事件流 + 待审批动作清单。

    审批模式下写动作会以 approval_required 结束本轮——拿 action_id 调
    POST /agent/actions/{id}/decide 批准或拒绝。
    """
    try:
        events = _ext_agent_events(payload)
    except tasks.AINotConfigured as exc:
        raise HTTPException(400, str(exc)) from None
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Agent 执行失败：{exc}") from exc
    # 循环内以 error 事件收尾（如无可用账号）→ 非流式调用方拿到明确的 HTTP 错误
    err = next((ev["error"] for ev in events if ev.get("type") == "error" and ev.get("error")), None)
    if err:
        raise HTTPException(400, err)
    answer = "".join(ev.get("text", "") for ev in events if ev.get("type") == "text")
    approvals = [
        {"action_id": ev["action_id"], "tool": ev["tool"], "args": ev["args"], "reason": ev["reason"]}
        for ev in events if ev.get("type") == "approval_required"
    ]
    return {"answer": answer, "approvals": approvals, "events": events}


@router.post("/agent/chat/stream")
def ext_agent_stream(payload: ExtAgentIn, _: Any = AGENT_KEY):
    """总管家对话（SSE）：事件同内部 /api/ai/agent/stream（text/tool_call/
    tool_result/approval_required/error/done），origin=api。"""
    from app.api.ai import _AgentSSE

    return _AgentSSE(payload, origin="api").response()


@router.post("/agent/actions/{action_id}/decide")
def ext_agent_decide(action_id: int, payload: AgentDecisionIn,
                     _: Any = AGENT_KEY) -> dict:
    """批准/拒绝 Agent 待审批动作（与内部审批端点同一实现，可改参数后批准）。"""
    if payload.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision 需为 approve/reject")
    return agent.execute_action(action_id, payload.decision, payload.args, origin="api")
