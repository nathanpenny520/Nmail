# 多会话看板（docs/SESSIONS.md）

> 多个 Claude 会话并行共享同一工作树是常态。本文件是唯一的会话登记处：**开工先读这里，收工必更这里**。
> 配套铁律见 [CLAUDE.md](../CLAUDE.md) 工作流规范 8–10（开工三件事 / 即时重读 / 提交纪律）。

## 使用规则（一分钟版）

1. **开工**：读完本文件。目标文件/模块与任一「进行中」会话的范围重叠 → 换范围或等它完成；否则到「进行中」登记（ID、目标、预计触碰文件、开始时间）。
2. **进行中**：每完成一个大阶段顺手更新一次状态行；会话被压缩/重启后，先来这里恢复上下文再动手。
3. **收工 / 中断**：条目移到「已完成 / 已中断」，写清产出（提交哈希）、遗留事项、给下一个会话的提示。发现超过 24 小时无更新的「进行中」条目，任何会话可将其移入「已中断」并注明原因。
4. **撞车**：发现文件被改得与预期不符 → 以磁盘现状为准，对照 `git log` 弄清发生了什么，调整自己的方案而不是覆盖别人。

## 会话 ID 约定

`S-MMDD-HHmm-<主题>`，例：`S-0911-2230-打包`。以开工时刻为准，请勿复用他人 ID。

## 进行中

（无——有新会话开工时按下方模板登记）

```markdown
### S-MMDD-HHmm-<主题>
- 目标: 一句话
- 范围: 预计触碰的文件/目录
- 开始: YYYY-MM-DD HH:MM
- 状态: 进行中
```

## 已完成

### S-0911-2300-UI密度与侧栏拖拽 ✅
- 产出：d6dec7c（遮蔽修复见 CHANGELOG d6dec7c 条目，属高影响 bug）
- 遗留：EmailReader 拦截横幅仍为固定 text-xs（微小，可并入下轮 UI 清理）
- 提示：打包后务必跑 scripts/sync_frontend.sh 或删 backend/app/static，否则旧快照会遮蔽新构建（现已由解析顺序根治）

### S-0911-2330-设置保存UX
- 目标: 设置页保存体验修复（后端版本守护提示、通用表单粘性保存栏、字号即选即存）
- 范围: frontend/src/pages/SettingsPage.tsx
- 产出: 提交 65d208d + 20c4d77（由协作体系会话代登、后经 git log 确认收工——看板首个闭环案例）
- 时间: 2026-09-11 深夜 完成

### S-0911-2340-协作体系
- 目标: 多会话并行透明度机制化（CLAUDE.md 规范 8–10 + 本看板）
- 范围: CLAUDE.md, docs/SESSIONS.md, docs/CHANGELOG.md
- 产出: 本文件与 CLAUDE.md 新规；起因是当日两次"文件被并行会话先改"（settings.py 字号、nmail.spec 图标）靠运气未撞车
- 时间: 2026-09-11 深夜

### S-0911-2200-P4主线
- 目标: 会话持久化 + AI 配置档案 + 服务商探测 + 打包分发
- 范围: backend/app/**, frontend/src/**, pyproject.toml, nmail.spec, .github/workflows, docs/**
- 产出: 提交 7f49125（主工作）、095be6a（CHANGELOG 回填）；条目见 CHANGELOG
- 遗留: 未打 v0.1.0 tag（等 PyPI_API_TOKEN 配好）；AI 档案切换待真实账号验证
- 时间: 2026-09-11 深夜 完成

### S-0911-2100-图标
- 目标: 应用全套图标（favicon/PWA/打包图标）
- 范围: assets/, scripts/gen_icons.py, frontend/public, frontend/index.html, nmail.spec
- 产出: 提交 65bb14d；Windows 图标缓存刷新提示见 CHANGELOG
- 时间: 2026-09-11 完成
