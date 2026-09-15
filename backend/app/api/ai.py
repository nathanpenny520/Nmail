"""AI 能力 API：上下文问答、总管家问答、Agent 对话（工具+审批）、写作辅助、用量统计、「AI 整理」补分类。"""
from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.ai import agent, profiles, tasks
from app.api.chats import append_message, require_session
from app.api.deps import ai_config_or_400, ai_result_or_http
from app.core import jobs
from app.core.mail_html import markdown_body_html, sanitize_outgoing_html
from app.db.database import get_conn

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _sse(gen):  # noqa: ANN001 — 生成器
    """把文本增量生成器包装为 SSE 响应；中途异常以 error 事件下发，前端可见。"""

    def stream():
        try:
            for delta in gen:
                yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'error': str(exc)[:300]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ChatIn(BaseModel):
    email_id: int | None = None
    email_ids: list[int] | None = None  # 可选：多封（如搜索结果）作为上下文
    question: str
    history: list[dict] | None = None
    profile_id: str | None = None  # 可选：本次对话使用指定 AI 配置档案


class WriteIn(BaseModel):
    text: str
    op: str  # polish|formal|casual|shorten|expand|translate_zh|translate_en|custom|compose
    instruction: str | None = None
    profile_id: str | None = None
    want_html: bool = False  # 置 true 时附带 markdown→HTML 转换结果（编辑器直插）


class OrganizeIn(BaseModel):
    account_id: int | None = None
    folder: str = "INBOX"
    limit: int = 200


class ManagerChatIn(BaseModel):
    question: str
    history: list[dict] | None = None
    account_id: int | None = None
    days: int = 7
    session_id: int | None = None  # 提供时落库（会话持久化），否则保持旧的无痕行为
    profile_id: str | None = None  # 可选：本次对话使用指定 AI 配置档案


class AgentStreamIn(BaseModel):
    question: str
    history: list[dict] | None = None
    account_ids: list[int] = []     # 会话范围（空=全部账号）
    mode: str = "approval"          # approval | auto
    session_id: int | None = None
    profile_id: str | None = None


class AgentDecisionIn(BaseModel):
    decision: str                   # approve | reject
    args: dict | None = None        # 可选：改参数后批准


def _record_model(profile_id: str | None) -> str:
    """会话落库用的模型名：解析失败（未配置）时留空即可，不影响主流程。"""
    try:
        return profiles.resolve(profile_id).get("model") or ""
    except profiles.ProfileNotConfigured:
        return ""


def _persist_stream(gen, session_id: int, model: str):
    """包裹流式生成器：结束后把完整回复落库；中途异常保留已生成部分再抛出。"""
    chunks: list[str] = []
    try:
        for delta in gen:
            chunks.append(delta)
            yield delta
    except Exception:
        if chunks:
            append_message(session_id, "assistant", "".join(chunks), model=model)
        raise
    append_message(session_id, "assistant", "".join(chunks), model=model)


@router.post("/chat-manager")
def chat_manager(payload: ManagerChatIn) -> dict:
    """「AI 总管家」非流式版本（保留兼容）。"""
    context = _manager_context(payload)
    answer = ai_result_or_http(lambda: tasks.chat_with_context(
        context, payload.question, history=payload.history,
        profile_id=payload.profile_id,
    ))
    if payload.session_id is not None:
        require_session(payload.session_id)
        append_message(payload.session_id, "user", payload.question)
        append_message(payload.session_id, "assistant", answer,
                       model=_record_model(payload.profile_id))
    return {"answer": answer}


@router.post("/chat-manager/stream")
def chat_manager_stream(payload: ManagerChatIn):
    """「AI 总管家」流式版本：SSE 逐段返回。"""
    context = _manager_context(payload)
    # 先验配置：未配置/停用时用户消息不能先落库成孤儿
    ai_config_or_400(payload.profile_id)
    if payload.session_id is not None:
        require_session(payload.session_id)
        append_message(payload.session_id, "user", payload.question)
    gen = tasks.chat_with_context_stream(
        context, payload.question, history=payload.history,
        profile_id=payload.profile_id,
    )
    if payload.session_id is not None:
        gen = _persist_stream(gen, payload.session_id, _record_model(payload.profile_id))
    return _sse(gen)


def _manager_context(payload: ManagerChatIn) -> str:
    conn = get_conn()
    # date_sort 为统一 UTC 的排序键（迁移 v7）；边界必须同样以 UTC 生成——
    # naive 本地时间直接比较会差一个时区偏移（UTC+8 下「最近 N 天」少 8 小时，审查 F3）
    since_local = datetime.now().astimezone() - timedelta(days=max(1, payload.days))
    since = since_local.astimezone(UTC).isoformat(timespec="seconds")
    where = " WHERE COALESCE(e.date_sort, e.date) >= ?"
    params: list = [since]
    if payload.account_id is not None:
        where += " AND e.account_id = ?"
        params.append(payload.account_id)
    rows = conn.execute(
        "SELECT e.subject, e.sender_name, e.sender_email, e.date, e.category,"
        " e.importance, e.needs_reply, e.archived_local, e.snippet, a.email AS account_email"
        f" FROM emails e JOIN accounts a ON a.id = e.account_id{where}"
        " ORDER BY COALESCE(e.date_sort, e.date) DESC LIMIT 150",
        params,
    ).fetchall()

    lines = []
    cat_count: Counter = Counter()
    for r in rows:
        cat = r["category"] or "未分类"
        cat_count[cat] += 1
        flags = []
        if r["needs_reply"]:
            flags.append("需回复")
        if r["archived_local"]:
            flags.append("已归档")
        flags_str = f" [{'|'.join(flags)}]" if flags else ""
        snippet = (r["snippet"] or "")[:60]
        lines.append(
            f'{(r["date"] or "")[:10]} {r["account_email"]} <{r["sender_email"]}> '
            f'「{r["subject"]}」({cat}/{r["importance"] or "-"}){flags_str} {snippet}'
        )

    unread_row = conn.execute(
        f"SELECT COUNT(*) AS n FROM emails e{where} AND e.is_read = 0 AND e.archived_local = 0",
        params,
    ).fetchone()

    cats_str = "、".join(f"{k} {v}" for k, v in cat_count.most_common())
    return (
        f"邮箱最近 {payload.days} 天概况：共 {len(rows)} 封（{cats_str}），"
        f"未读 {unread_row['n']} 封。明细（新→旧，最多 150 条）：\n" + "\n".join(lines)
    )


def _build_context(email_id: int) -> tuple[str, int]:
    row = get_conn().execute(
        "SELECT subject, sender_name, sender_email, date, body_text, body_html, account_id"
        " FROM emails WHERE id = ?",
        (email_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "邮件不存在")
    body = row["body_text"] or ""
    if not body.strip():
        from bs4 import BeautifulSoup

        body = BeautifulSoup(row["body_html"] or "", "html.parser").get_text("\n", strip=True)
    context = (
        f'主题: {row["subject"]}\n'
        f'发件人: {row["sender_name"]} <{row["sender_email"]}>\n'
        f'日期: {row["date"] or ""}\n\n{body.strip()[:6000]}'
    )
    return context, int(row["account_id"])


@router.post("/chat")
def chat(payload: ChatIn) -> dict:
    ids = payload.email_ids or ([payload.email_id] if payload.email_id else [])
    if not ids:
        raise HTTPException(400, "需要提供 email_id 或 email_ids 作为上下文")
    contexts, account_id = _chat_contexts(ids)
    answer = ai_result_or_http(lambda: tasks.chat_with_context(
        "\n\n".join(contexts), payload.question,
        history=payload.history, account_id=account_id,
        profile_id=payload.profile_id,
    ))
    return {"answer": answer}


@router.post("/chat/stream")
def chat_stream(payload: ChatIn):
    ids = payload.email_ids or ([payload.email_id] if payload.email_id else [])
    if not ids:
        raise HTTPException(400, "需要提供 email_id 或 email_ids 作为上下文")
    contexts, account_id = _chat_contexts(ids)
    gen = ai_result_or_http(lambda: tasks.chat_with_context_stream(
        "\n\n".join(contexts), payload.question,
        history=payload.history, account_id=account_id,
        profile_id=payload.profile_id,
    ))
    return _sse(gen)


def _chat_contexts(ids: list[int]) -> tuple[list[str], int | None]:
    contexts = []
    account_id = None
    for eid in ids[:5]:  # 上下文最多取 5 封，防 token 失控
        ctx, account_id = _build_context(eid)
        contexts.append(f"===== 邮件 {eid} =====\n{ctx}")
    return contexts, account_id


@router.post("/write")
def write(payload: WriteIn) -> dict:
    result = ai_result_or_http(lambda: tasks.write_assist(
        payload.text, payload.op, payload.instruction, profile_id=payload.profile_id))
    resp: dict = {"text": result}
    if payload.want_html:
        html = markdown_body_html(result)
        resp["html"] = sanitize_outgoing_html(html)
    return resp


# ── AI 总管家 Agent（v0.4 P6；v0.4.x Agent 化 §17）────────────────

def _build_segments(events: list[dict]) -> list[dict]:
    """事件流 → 持久化分段（text / step / approval / error），与前端渲染同构。"""
    segs: list[dict] = []

    def last_text() -> dict | None:
        return segs[-1] if segs and segs[-1]["kind"] == "text" else None

    for ev in events:
        t = ev.get("type")
        if t == "text_delta":
            seg = last_text()
            if seg is None:
                segs.append({"kind": "text", "content": ev.get("delta") or ""})
            else:
                seg["content"] += ev.get("delta") or ""
        elif t == "text":
            seg = last_text()
            if seg is None:
                segs.append({"kind": "text", "content": ev.get("text") or ""})
            else:
                seg["content"] = ev.get("text") or ""  # 全量事件覆盖同轮累积
        elif t == "tool_call":
            segs.append({"kind": "step", "tool": ev.get("tool"), "call_id": ev.get("call_id"),
                         "args": ev.get("args") or {}, "status": "running"})
        elif t == "tool_result":
            matched = False
            for seg in reversed(segs):
                if seg["kind"] != "step" or seg.get("status") in ("ok", "fail"):
                    continue
                if ev.get("action_id") is not None:
                    if seg.get("action_id") == ev["action_id"]:
                        matched = True
                elif seg.get("tool") == ev.get("tool"):
                    matched = True
                if matched:
                    seg["status"] = "ok" if ev.get("ok") else "fail"
                    seg["summary"] = ev.get("summary")
                    if ev.get("action_id") is not None:
                        seg["action_id"] = ev["action_id"]
                    break
            if not matched:
                # 续跑流里回放审批结果的 tool_result（原 step 在前一条消息）→ 标记 echo，
                # 前端不重复渲染（消息1 的 waiting step 已由 _patch_history_step 落定）
                segs.append({"kind": "step", "tool": ev.get("tool"), "call_id": ev.get("call_id"),
                             "args": {}, "status": "ok" if ev.get("ok") else "fail",
                             "summary": ev.get("summary"),
                             **({"echo": True} if ev.get("action_id") is not None else {})})
        elif t == "approval_required":
            # 前一个 running step 转入 waiting（决定后前端就地更新）
            for seg in reversed(segs):
                if seg["kind"] == "step" and seg.get("status") == "running" \
                        and seg.get("tool") == ev.get("tool"):
                    seg["status"] = "waiting"
                    seg["action_id"] = ev.get("action_id")
                    break
            segs.append({"kind": "approval", "action_id": ev.get("action_id"),
                         "tool": ev.get("tool"), "args": ev.get("args") or {},
                         "reason": ev.get("reason"), "meta": ev.get("meta") or {},
                         "run_id": ev.get("run_id")})
        elif t == "error":
            segs.append({"kind": "error", "content": ev.get("error") or "执行出错"})
    return segs


def _patch_history_step(session_id: int, action_id: int, ok: bool, summary: str) -> None:
    """审批决定后把前一条助手消息里的 waiting step / 审批卡落定为最终状态（还原一致）。"""
    rows = get_conn().execute(
        "SELECT id, segments_json FROM chat_messages"
        " WHERE session_id = ? AND role = 'assistant' AND segments_json IS NOT NULL"
        " ORDER BY id DESC LIMIT 5", (session_id,)).fetchall()
    for row in rows:
        try:
            segs = json.loads(row["segments_json"] or "[]")
        except ValueError:
            continue
        hit = False
        for seg in segs:
            if seg.get("action_id") != action_id:
                continue
            if seg.get("kind") == "step" and seg.get("status") == "waiting":
                seg["status"] = "ok" if ok else "fail"
                seg["summary"] = summary
                hit = True
            elif seg.get("kind") == "approval" and not seg.get("status"):
                seg["status"] = "已拒绝" if "拒绝" in summary else ("已执行" if ok else "失败")
                hit = True
        if hit:
            get_conn().execute("UPDATE chat_messages SET segments_json = ? WHERE id = ?",
                               (json.dumps(segs, ensure_ascii=False), row["id"]))
            get_conn().commit()
            return


class _AgentSSE:
    """把 agent 事件生成器包装为 SSE；结束后把分段轨迹落库（会话持久化）。
    origin 随调用方区分（内部 ui / 对外 API api，审计字段 §6.8）。

    两种来源：新问题（run_stream）与续跑（resume_stream——决定回灌 + 继续
    循环）。续跑前把审批决定回写进前一条消息的 waiting step（§17.4）。"""

    def __init__(self, payload: AgentStreamIn | None = None, origin: str = "ui",
                 resume_run_id: int | None = None):
        self.payload = payload
        self.origin = origin
        self.resume_run_id = resume_run_id
        self.events: list[dict] = []

    def stream(self):
        payload = self.payload
        if self.resume_run_id is not None:
            gen = agent.resume_stream(self.resume_run_id)
        else:
            account_ids = payload.account_ids or [
                int(r["id"]) for r in get_conn().execute("SELECT id FROM accounts").fetchall()
            ]
            if payload.mode not in ("approval", "auto"):
                yield f"data: {json.dumps({'type': 'error', 'error': 'mode 需为 approval/auto'})}\n\n"
                yield "data: [DONE]\n\n"
                return
            gen = agent.run_stream(payload.question, payload.history, payload.session_id,
                                   account_ids, payload.mode, payload.profile_id,
                                   origin=self.origin)
        try:
            for event in gen:
                self.events.append(event)
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        except tasks.AINotConfigured:
            self.events.append({"type": "error", "error": "AI 未配置或已停用，请到 设置-AI 配置 检查"})
            yield "data: " + json.dumps(self.events[-1], ensure_ascii=False) + "\n\n"
        except Exception as exc:  # noqa: BLE001
            self.events.append({"type": "error", "error": str(exc)[:300]})
            yield "data: " + json.dumps(self.events[-1], ensure_ascii=False) + "\n\n"
        yield "data: [DONE]\n\n"
        self._persist()

    def _persist(self) -> None:
        payload = self.payload
        session_id = payload.session_id if payload is not None else None
        if self.resume_run_id is not None:
            state = agent._load_run(self.resume_run_id)
            session_id = state.session_id if state else None
        if session_id is None:
            return
        # 审批决定的事件已在续跑流里回放（tool_result 带 action_id）——
        # 同步落定前一条消息中的 waiting step，保证刷新后还原一致
        for ev in self.events:
            if ev.get("type") == "tool_result" and ev.get("action_id") is not None:
                _patch_history_step(session_id, ev["action_id"],
                                    bool(ev.get("ok")), ev.get("summary") or "")
        segs = _build_segments(self.events)
        text_parts = [s["content"] for s in segs if s["kind"] == "text" and s["content"].strip()]
        content = "\n\n".join(text_parts) or "（已执行工具调用，见过程）"
        append_message(session_id, "assistant", content,
                       model=_record_model(payload.profile_id if payload else None),
                       segments=segs)

    def response(self) -> StreamingResponse:
        return StreamingResponse(
            self.stream(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


@router.post("/agent/stream")
def agent_stream(payload: AgentStreamIn):
    """总管家 Agent 对话（SSE）：run_started / text_delta / text / tool_call /
    tool_result / approval_required / paused / error / done。"""
    # 用户提问随流落库（此前只存 AI 回复，刷新后只剩 AI 内容）；先验配置
    # 与会话，避免未配置/无效会话产生孤儿消息
    if payload.session_id is not None:
        require_session(payload.session_id)
        ai_config_or_400(payload.profile_id)
        append_message(payload.session_id, "user", payload.question)
    return _AgentSSE(payload).response()


class AgentResumeIn(BaseModel):
    run_id: int


@router.post("/agent/resume")
def agent_resume(payload: AgentResumeIn):
    """续跑 Agent 运行（SSE）：审批决定后 / 步数预算触顶后由前端自动调用。"""
    return _AgentSSE(resume_run_id=payload.run_id).response()


@router.post("/agent/action/{action_id}/decide")
def agent_decide(action_id: int, payload: AgentDecisionIn) -> dict:
    """审批动作：批准执行（可改参数）或拒绝。"""
    if payload.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision 需为 approve/reject")
    return agent.execute_action(action_id, payload.decision, payload.args)


@router.post("/agent/action/{action_id}/undo")
def agent_undo(action_id: int) -> dict:
    """撤销已执行动作（标记/移动/归档类；发送不可撤销）。"""
    return agent.undo_action(action_id)


@router.get("/agent/actions")
def agent_actions(status: str | None = None, limit: int = 100) -> dict:
    """AI 操作记录（设置页审计查看器）。"""
    limit = max(1, min(limit, 500))
    where, params = "", []
    if status:
        where = " WHERE a.status = ?"  # 限定主表：accounts 同名列会让裸 status 歧义（500）
        params = [status]
    rows = get_conn().execute(
        f"SELECT a.*, ac.email AS account_email FROM ai_actions a"
        f" LEFT JOIN accounts ac ON ac.id = a.account_id{where}"
        f" ORDER BY a.id DESC LIMIT {limit}",
        params,
    ).fetchall()
    return {"actions": [
        {
            "id": r["id"], "session_id": r["session_id"], "account_id": r["account_id"],
            "account_email": r["account_email"], "tool": r["tool"],
            "params": json.loads(r["params_json"] or "{}"),
            "mode": r["mode"], "origin": r["origin"], "status": r["status"],
            "result": json.loads(r["result_json"]) if r["result_json"] else None,
            "undoable": bool(r["undo_json"]), "error": r["error"],
            "created_at": r["created_at"], "decided_at": r["decided_at"],
        }
        for r in rows
    ]}


@router.delete("/agent/actions/{action_id}")
def agent_action_delete(action_id: int) -> dict:
    """删除单条操作记录（历史管理 §18.3：纯审计行删除，与撤销无关）。"""
    return agent.delete_action(action_id)


@router.delete("/agent/actions")
def agent_actions_clear(scope: str = "failed") -> dict:
    """批量清理操作记录：scope=old（90 天前，已发送审计保留）/failed（失败与拒绝）/all（全部）。"""
    return agent.clear_actions(scope)


@router.get("/memory")
def memory_list() -> dict:
    """用户长期偏好（agent_memory，§18.5）：设置页查看。"""
    rows = get_conn().execute(
        "SELECT id, content, evidence, source, created_at, updated_at"
        " FROM agent_memory ORDER BY updated_at DESC"
    ).fetchall()
    return {"memories": [dict(r) for r in rows]}


@router.delete("/memory/{memory_id}")
def memory_delete(memory_id: int) -> dict:
    """删除一条用户长期偏好。"""
    cur = get_conn().execute("DELETE FROM agent_memory WHERE id = ?", (memory_id,))
    get_conn().commit()
    if cur.rowcount == 0:
        return {"error": "记忆不存在"}
    return {"ok": True, "deleted": memory_id}


@router.post("/organize")
def organize(payload: OrganizeIn) -> dict:
    """为未分类邮件补跑分类（「AI 整理」按钮）——异步任务。

    立即返回 {job_id}；进度/结果经 GET /api/jobs/{id} 轮询（前端 useJob）。
    同账号重复点击去重复用同一任务。
    """
    job_id = jobs.submit("organize", account_id=payload.account_id, dedupe=True,
                         folder=payload.folder, limit=payload.limit)
    return {"job_id": job_id}


@router.get("/usage")
def usage() -> dict:
    return tasks.usage_stats()
