# 发版手册（docs/RELEASE.md）

> 给未来的 AI 会话与人：发版只跑一条命令。先读本页再动手；出问题按「故障处理」查。
> 本手册由 2026-09-11 的 v0.1.0 首发实战沉淀——上面列的坑都是真实踩过的。

## 前置条件（一次性，已全部配置好，勿重复操作）

| 项 | 状态 |
|---|---|
| gh CLI 已登录 nathanpenny520 | ✅（git-bash 下位于 `/c/Program Files/GitHub CLI/gh.exe`，脚本自动定位） |
| 仓库 Secret `PYPI_API_TOKEN` | ✅ user-scoped（Entire account，新项目名首传不 403） |
| 仓库 Secret `HOMEBREW_TAP_TOKEN` | ✅ fine-grained，可写 `nathanpenny520/homebrew-nmail` Contents |
| winget-pkgs fork | ✅ `nathanpenny520/winget-pkgs`（**默认分支是 master，不是 main**） |
| Microsoft CLA | ✅ 已签（长期有效） |

## 一条命令发版

```bash
bash scripts/release.sh 0.2.0                # 完整流程：改版本号→提交打 tag→盯 CI→提 winget PR
bash scripts/release.sh 0.2.0 --skip-winget  # 跳过 winget PR（PyPI/Release/Homebrew 照发）
bash scripts/release.sh 0.2.0 --dry-run      # 演练：只验证预检与版本号替换，随后还原
```

脚本自动完成（约 10–20 分钟，其中 CI 等待占大头）：

1. **预检**：版本文件无未提交改动、本地 main 不落后 origin、tag 不存在、gh 已登录
2. **改版本号**：`pyproject.toml`（唯一来源；`config.py` 运行时解析——源码/冻结读本文件、wheel/uvx 读包元数据，**不再需要手动改**）
3. **提交 `release: vX.Y.Z` → 打 tag → 推送**
4. **盯 CI**（release.yml）：前端构建 → wheel 发 PyPI；三平台 PyInstaller 单文件挂 GitHub Release；Homebrew tap 自动同步新版本与 SHA256
5. **winget 版本 PR**：等 Release 资产 → 取 exe SHA256 → fork 建分支写三份 manifest → 提 PR 到 `microsoft/winget-pkgs`
6. **官网联动**：`gh workflow run deploy.yml -R nathanpenny520/nmail-site` 触发官网重建（构建期拉 Releases + 主仓 docs），1–2 分钟后 nmail.whizzzest.com 同步新版；失败不阻塞发版，可手动补触发

## 脚本跑完后的 AI 收尾清单（CLAUDE.md 规范 2/8）

1. `docs/CHANGELOG.md` 追加发版条目（提交后回填哈希）
2. `docs/SESSIONS.md` 看板登记本次发版会话
3. **盯 winget PR 校验**（约 10–60 分钟，Azure 管道排队时间不定），拉结果：
   ```bash
   gh api "repos/microsoft/winget-pkgs/commits/<PR_head_sha>/check-runs?per_page=100" --paginate \
     --jq '.check_runs[] | select(.name | test("^[0-9]")) | .name + " | " + .status + " | " + (.conclusion // "-")' | sort
   ```
   全绿后等社区审核员批准；提醒用户可去 PR 页点 **Enable auto-merge**（不会自动带上，每个 PR 一次）
4. 向用户汇报：PyPI/Release/Homebrew 即时生效；winget 合并后生效

## 故障处理（按症状查）

| 症状 | 处理 |
|---|---|
| push 被拒（并行会话刚推了提交） | `git pull --rebase origin main` → `git tag -d vX.Y.Z` → 重跑脚本 |
| PyPI 403 Forbidden | token 过期/换 scope → pypi.org 重建 user-scoped token → `printf '%s' 'token' | gh secret set PYPI_API_TOKEN --repo nathanpenny520/Nmail` → Actions 页 Re-run failed jobs |
| PyPI "file already exists" | **版本号已被永久占用**（上传成功过哪怕部分失败）→ 只能 bump 新版本号，不能复用 |
| tag 推错了想重来 | 仅当该版本**从未成功上传 PyPI** 时可重指：`git push origin :refs/tags/vX && git tag -d vX` → 改完重新打 tag 推送 |
| CI 某平台失败 | `gh run view <run_id> --repo nathanpenny520/Nmail --log-failed`；homebrew-tap job 失败先查 `HOMEBREW_TAP_TOKEN` 是否过期 |
| homebrew-tap 404 | 历史坑：曾因①只等 python-package 就开跑（macOS 资产还没挂上，下载 404）②curl 误用 gh 的 `--jq` 参数——均已修复（needs 含 binaries；指纹解析改 python3）。tap 更新失败时可用 gh 手动改 formula 兜底（见 RELEASE.md 作者会话记录） |

### 发行验证清单（发完必查）
```bash
gh run view <run_id> --repo nathanpenny520/Nmail      # ① CI 全绿
curl -s https://pypi.org/pypi/nmail-app/json | grep -o '"version":"[^"]*"' | head -1   # ② PyPI 版本
gh release view vX.Y.Z --repo nathanpenny520/Nmail    # ③ 三平台资产挂齐
gh api repos/nathanpenny520/homebrew-nmail/contents/Formula/nmail.rb --jq '.content' \
  | base64 -d | grep "^version"                       # ④ tap 版本
winget search nathanpenny520.Nmail                    # ⑤ 合并后可见（PR 合并前 winget search 查不到）
```

### winget 专属坑（全部真实踩过）

1. **目录必须单层首字母折叠**：`manifests/n/nathanpenny520/Nmail/<版本>/`——写成 `n/na/` 两层会报 "path must match PackageIdentifier"
2. **locale 文件名必须带语言后缀**：`nathanpenny520.Nmail.locale.en-US.yaml`——省略后缀会报 "filename must match ... ManifestType"
3. **本地 `winget validate` 验不出上面两条**（它不查文件名/路径与标识符匹配），别因为本地绿就放心
4. `winget validate <目录>` 的目录里**不能有子目录**（哪怕 `cache/`），否则报 "Subdirectory not supported"
5. fork 的默认分支是 **master**；脚本已自动 `merge-upstream` 同步
6. 拉校验失败日志：
   ```bash
   gh api "repos/microsoft/winget-pkgs/commits/<head_sha>/check-runs?per_page=100" --paginate \
     --jq '.check_runs[] | select(.name == "02. Manifest Validation") | .output.text'
   ```
7. 修 manifest = 直接往 PR 分支推新提交，校验自动重跑；大改后等不到自动触发就在 PR 评论 `/azp run`

## nmail-cli 发包（REDESIGN_PLAN §19，2026-09-15 起）

release CI 新增 `nmail-cli-package` job：构建 `nmail-cli/` 并发布到 PyPI 包名 **`nmail-cli`**
（占用已核查，2026-09-15 可用）。注意：

1. **版本号独立**在 `nmail-cli/pyproject.toml`，发版前按需 bump（不随主包版本）。
2. **token**：默认回退主 `PYPI_API_TOKEN`；若该 token 是项目级（只限 `nmail-app`），
   到 PyPI 给账号建一个含 `nmail-cli` 项目的 token，配到 repo secrets `PYPI_CLI_API_TOKEN`
   （该 job 会优先用它）。首次发布即认领包名，之后可把 token 收窄为项目级。
3. CI 失败排查：`gh run view --job <id> --log-failed`，常见即 403=token 无 nmail-cli 权限。

## 渠道速查（用户侧如何拿到更新）

| 渠道 | 更新时机 | 用户命令 |
|---|---|---|
| PyPI | CI 即时 | `uv tool upgrade nmail-app` / `pip install -U nmail-app` |
| PyPI（nmail-cli） | CI 即时 | `uvx nmail-cli@latest` / `uv tool upgrade nmail-cli` |
| GitHub Release | CI 即时 | 下载覆盖 |
| Homebrew | CI 即时（tap 自动 bump） | `brew upgrade nmail` |
| winget | 版本 PR 合并后 | `winget upgrade nathanpenny520.Nmail` |
| 应用内提醒 | CI 即时（对比 GitHub Releases 最新 tag） | 通知中心 → 点 Releases 链接 |
