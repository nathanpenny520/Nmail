# Agent 能力扩展方案（docs/AGENT_EXTEND_PLAN.md）

> 背景：用户 2026-09-15 指派调研 `reference/deer-flow` 与 `reference/smolagents`，看邮箱 agent 还能怎么扩展。
> 调研结论：Nmail 总管家（REDESIGN_PLAN §17/§18）的自研循环已覆盖两仓核心底盘（错误回灌自愈、上下文压缩、
> 参数校验、审批恢复、工具白名单、流式事件、审计），剩余是增量；本方案只记录**还没做的**。
> 调研备注：deer-flow checkout 是 **2.0 完全重写版**（单 lead agent + 中间件链 + subagent 委派，
> 无 v1 的 planner/researcher/coder/reporter 多节点图）；smolagents 为 1.27.0.dev0（CodeAgent/ToolCallingAgent）。
> **状态：方案定稿 2026-09-15，未执行**（用户指派「代码部分先落成方案不改」）。落地时并入 REDESIGN_PLAN
> 新章节并逐项拍板；本文与在途会话的 REDESIGN_PLAN WIP 避让，故独立成文（S-0914-2352 先例）。

## 1. 现状盘点：两仓机制 ↔ Nmail 现状对照（已覆盖，勿重复建设）

| 两仓机制 | 参考位置 | Nmail 现状 |
|---|---|---|
| 错误回灌自愈循环 | smolagents `memory.py` ActionStep.to_messages（error 带引导语继续下一轮） | `_append_feedback` 失败回灌带 hint（改参数/不重试/换方法），`agent.py` |
| 上下文防爆炸 | smolagents `truncate_content` + 每 tool 输出上限 | 五层管线更全：分工具预算→步数/token 双门微压缩→会话记忆→确定性折叠→AutoCompact（§17.8，context.py） |
| 运行时参数校验 | smolagents `validate_tool_arguments` | `T.normalize_args`（tools.py），类型/必填前置拦截 |
| HITL 中断+恢复 | deer-flow clarification interrupt；smolagents `interrupt()` | ai_actions pending + waiting_approval + resume（比两仓都重，§6.4/§17.2） |
| 无人值守工具收缩 | deer-flow 定时任务剔除 ask_clarification（non_interactive） | SCHEDULER_ALLOWED 白名单 + schema/执行层双拦（§18.6，同型且更严） |
| 流式事件 | deer-flow StreamBridge/SSE；smolagents stream() | run_stream 生成器事件（text_delta/tool_call/tool_result/approval/paused） |
| token 计量与预算 | smolagents Monitor | ai_logs 每步 usage + 预算 180s/25 步 + 估算→真实 EMA 校准（§17.8） |
| 审计/撤销 | 两仓均无对等物 | ai_actions 全量落库 + undo_json（§6.8） |

## 2. 方向 A：内置总管家增强（backend/app/ai/）

按性价比排序；A1-A3 快赢（一个会话量级），A4-A6 中等，A7-A8 拍板后置。

### A1 步数/预算耗尽强制收尾（快赢）
现状：`MAX_STEPS` 触顶直接 `paused_max_steps` 等用户点「继续」（agent.py `_loop`）。交互场景没问题，
但 **scheduler 晨报无人值守跑满步数只留 paused、零产出**（没人点继续）。
方案：触顶时先原地追加一次 `tool_choice=none` 模型调用（JSON 降级模式追加系统提示行，复用既有
`note_pending` 手法），强制基于已完成步骤总结收尾后 done；UI 场景总结照给、继续按钮保留。
参考：smolagents `provide_final_answer`（agents.py `_handle_max_steps_reached`）。

### A2 final answer 确定性校验闸门（快赢）
现状：循环以「无工具调用」结束，文本不校验——模型可能在未执行对应动作时声称「已发送/已归档 N 封」。
方案：done 前对文本做确定性断言比对（完成类措辞 ↔ 本 run ai_actions executed 记录），不一致时回灌一条
系统纠正消息让模型改口（最多纠 1 次防循环），仍不一致则原文附加警示后放行。
参考：smolagents `_validate_final_answer` + `final_answer_checks`。

### A3 工具结果保头尾截断（快赢）
现状：`_feedback_text` 超预算只保头（`text[:budget]`）；邮件线程的最新回复在**尾部**，截头留尾丢最新。
方案：改保头 60% + 尾 25% + 省略标注。参考：smolagents `truncate_content`（utils.py，头尾各半）。

### A4 同批只读调用并行执行
现状：`_loop` 的 `for call in calls` 串行执行；原生 function calling 常一次发多个独立读调用，串行白等。
方案：只读工具（`spec.kind == "read"`）用 ThreadPoolExecutor 并行、**结果按原序回灌**（保 tool_call_id
配对）；写类维持串行（顺序敏感+审计）。get_conn 已每线程连接（SQLite 并发竞态修复），只读并行无写锁。
参考：smolagents `process_tool_calls`（ThreadPoolExecutor）。

### A5 `ask_user` 澄清中断（模型主动求澄清）
现状：审批/暂停都是「规则触发」；模型遇到收件人歧义、多个候选 id、拿不准该不该删时只能瞎猜或硬编。
方案：新增工具 `ask_user(question, options?, fields?)`——不落审计、不执行动作，直接置
`waiting_input` 暂停（复用 agent_runs pending 机制，新 reason），前端渲染澄清卡；用户回答回灌续跑。
两点照搬 deer-flow：①同批兄弟工具调用全部丢弃并补跳过回应（现有 resume 配对补全逻辑已做一半）；
②v2 结构化表单协议（fields: text/select/checkbox，服务端校验、上限 16 字段，`agents/human_input.py`）。
参考：deer-flow `agents/middlewares/clarification_middleware.py`。

### A6 批量任务事件持久化 + 断线回填
现状：过程展示（§17.4）只活在 SSE 会话里，刷新/重连后时间线丢失（agent_runs.messages_json 有数据但无回放口）。
方案（推荐推导版，零写入成本）：`GET /api/ai/agent/runs/{id}/events`——由 messages_json 推导
tool_call/tool_result/approval 事件序列（带序号），前端 process 块重连时按 after_seq 回填；
SSE 检测到空洞发 reset 信号整体重拉（deer-flow `stream_replay_gap` 简化版）。
备选：独立 agent_events 表随 `_loop` 落库（支持 text_delta 级回放，写入成本高，观察需求再上）。
参考：deer-flow `runtime/events/`（catalog/store/after_seq 回填）、`subagents/step_events.py`。

### A7 邮件工作流技能包（拍板后动）
方案：轻量技能层——技能=目录 + SKILL.md（frontmatter: name/description/allowed_tools? + 方法论文档）；
系统提示词只注入**技能索引**（名字+一句话，prompt 缓存友好），模型用 `read_skill` 工具按需取全文；
激活后按该技能 allowed_tools 收缩当步工具面。内置首批：周报摘要、跟进提醒（谁答应过什么没兑现）、
报销/发票整理、批量归档策略；用户目录（NMAIL_DATA_DIR/agent_skills）可加自定义。
与决策 3（无规则引擎）不冲突——纯提示词层，零规则匹配代码。
参考：deer-flow `skills/`（parser/catalog/describe/projection，deferred_discovery 紧凑索引 + tool_search 晋升）。

### A8 步级可观测结构化
方案：run 详情 API 聚合 per-step（步号/工具/结果摘要/token/耗时，数据已在 ai_logs + agent_runs），
前端 run 抽屉展示。参考：smolagents ActionStep/RunResult（output/state/steps/token_usage/timing）。

## 3. 方向 B：对外 skill/CLI 层增强（nmail-cli/ + skills/SKILL.md）

| # | 改动 | 说明 |
|---|---|---|
| B1 | CLI 补 `folders list` 命令 | API 已有 `GET /api/ext/v1/folders`（read scope）CLI 未包装；`emails action move` 与 `--folder` 过滤的目标名从此有处可查（SKILL.md 现只能写「需与服务端一致」） |
| B2 | CLI 版本协商 `_notice.update` | 服务端 `/health` 回版本号，CLI 比对自身 `__version__` 落后时在输出尾附 `_notice.update`；SKILL.md 增「更新检查」节（完成当前请求后主动提议 `uvx` 升级 + 重装 skill，不静默忽略）——对齐 AgentlyMail，堵 CLI 与 SKILL.md 版本漂移 |
| B3 | CLI 包装总管家通道（默认缓发） | `nmail-cli agent ask "问题"` / `agent decide` / `agent resume`（scope=agent，走既有 `/agent/chat`、`/agent/actions/{id}/decide`、`/agent/resume` 非流式端点）——外部 agent 一条命令复用内置审批/审计/限额；与外部 agent 自身能力重叠、双 agent 职责不清，**等真实需求再拍板** |

## 4. SKILL.md 完整性审计（2026-09-15，本轮已修订 ✅）

对照 `nmail_cli/cli.py` 实际参数面与 AgentlyMail 骨架逐项核对（此前 P3 落地时文档落后于实现）：

已修（skills/SKILL.md v1.1.0，纯文档）：①草稿附件 `--attachment`（create/reply/forward，可重复——
P1 端点+CLI 均已实现但文档只字未提，最高频缺口）②`--cc/--bcc` ③分页 `--limit/--offset` + 「翻页保持
原条件只增 offset」纪律（AGENT_SKILL_PLAN §5 定了但成文时丢失）④`watch --since-id/--account-id/--interval`
⑤`auth status/logout` 入命令清单 ⑥scope↔命令对照表（read/write/send 各管什么、只读 Key 撞 exit 3 的
处理）+「参数速查」独立节 + 发送带附件示例。

遗留（依赖本方案代码项）：更新检查节待 B2；`folders` 命令待 B1。
核对无误不动的：exit code 表与 CLI EXIT_* 全量一致（0/1/2/3/4/6/7/8，无 5）；安全六条；两阶段唯一规则；
正文规范。官网 /docs/agent/ 走 sync-docs 白名单同步 docs/Agent接入指南.md（人类向简介，无需随动）。

## 5. 落地顺序与验证

A1+A2+A3（快赢，一个会话）→ A4+A5（一个会话）→ A6 → A7 → B1+B2 → B3 视需求。
每步验收照工作流规范：pytest 全绿、ruff、npm build（涉前端时）、真实实例 e2e；CHANGELOG/SESSIONS 随提交。
本方案并入 REDESIGN_PLAN 时按惯例等在途 WIP 清空后迁入。

## 6. 待拍板项（动工前逐项确认）

| # | 项 | 推荐值 |
|---|---|---|
| 1 | A1 UI 场景触顶行为 | 总结收尾 + 保留「继续」按钮（两者并存） |
| 2 | A6 事件回填方案 | 推导版先行（零写入），独立事件表观察需求 |
| 3 | A7 技能存放 | 仓库内置目录兜底 + 用户数据目录可扩展（内置被同名覆盖时以用户为准） |
| 4 | A2 纠正失败时的呈现 | 原文放行 + 末尾附加警示行（不静默、不阻断） |
| 5 | B3 | 默认不做，有真实双 agent 场景需求再启 |

## 7. 明确不做（含理由）

- **CodeAgent/代码沙箱**（smolagents local_python_executor 的 AST 解释器/import 白名单）：违背决策 1
  （只做邮件核心）与决策 3（无规则引擎），无动态执行过滤代码的场景。
- **MCP**：§19.1 已拍板远期（API+CLI+skill 已覆盖能跑命令的 agent）。
- **向量检索/embedding**：P7-E 已有顺位（先查询改写观察效果），不重复立项。
- **引入 LangGraph 级 agent 框架**：§17 自研循环已验证够用，两仓调研结论亦为「机制可借、框架不必」。

## 8. 两仓参考索引（实现时按图索骥）

- deer-flow：`agents/middlewares/`（clarification/deferred_tool_filter/skill 激活与工具策略）、
  `agents/human_input.py`（表单协议）、`skills/`（parser/catalog/describe/projection/skillscan）、
  `subagents/`（executor/report_contract/acceptance_checks）、`runtime/events/`（catalog+store+回填）、
  `runtime/stream_bridge/`、`tools/builtins/tool_search.py`；一手文档 `docs/ARCHITECTURE.md` 与各级 `AGENTS.md`。
- smolagents：`src/smolagents/agents.py`（RunResult/_validate_final_answer/provide_final_answer/
  process_tool_calls 并行）、`memory.py`（ActionStep/CallbackRegistry）、`utils.py`（truncate_content）、
  `local_python_executor.py`（仅参考其资源限制思路，见 §7 不做）。
