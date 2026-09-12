#!/usr/bin/env bash
# Nmail 一条命令发版：改版本号 → 提交打 tag → 盯 CI → 自动提 winget 版本 PR。
# 详细说明与故障处理见 docs/RELEASE.md。用法:
#   bash scripts/release.sh 0.2.0                  # 完整流程
#   bash scripts/release.sh 0.2.0 --skip-winget    # 跳过 winget PR（CI 部分照跑）
#   bash scripts/release.sh 0.2.0 --dry-run        # 演练：改版本号并校验后还原，不提交不推送
set -euo pipefail
cd "$(dirname "$0")/.."

die() { echo "❌ $*" >&2; exit 1; }
info() { echo "▶ $*"; }

VERSION="${1:-}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "用法: bash scripts/release.sh X.Y.Z [--skip-winget] [--dry-run]"
TAG="v$VERSION"
SKIP_WINGET=0
DRY_RUN=0
for arg in "${@:2}"; do
  case "$arg" in
    --skip-winget) SKIP_WINGET=1 ;;
    --dry-run) DRY_RUN=1 ;;
    *) die "未知参数: $arg" ;;
  esac
done

# gh 定位（git-bash 下可能不在 PATH）
GH_BIN="$(command -v gh || true)"
[ -n "$GH_BIN" ] || GH_BIN="/c/Program Files/GitHub CLI/gh.exe"
[ -x "$GH_BIN" ] || die "找不到 gh CLI（安装: winget install GitHub.cli）"
gh() { "$GH_BIN" "$@"; }

# ── 0. 预检 ──
git diff --quiet -- pyproject.toml \
  || die "pyproject.toml 有未提交改动，先处理再发版"
git fetch origin main --quiet
BEHIND=$(git rev-list --count main..origin/main)
[ "$BEHIND" -eq 0 ] || die "本地 main 落后 origin $BEHIND 个提交，先 git pull --rebase origin main"
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then die "本地 tag $TAG 已存在"; fi
if git ls-remote --tags origin "refs/tags/$TAG" | grep -q "refs/tags/$TAG"; then die "远端 tag $TAG 已存在"; fi
gh auth status >/dev/null 2>&1 || die "gh 未登录：gh auth login"
info "预检通过：版本 $VERSION（$TAG）"

# ── 1. 改版本号 ──
# 版本唯一来源是 pyproject.toml；config.py 自 0.2.0 起 importlib.metadata 动态读取，无需改
sed -i.bak "s/^version = \"[0-9][0-9.]*\"/version = \"$VERSION\"/" pyproject.toml
rm -f pyproject.toml.bak
grep -q "version = \"$VERSION\"" pyproject.toml || die "pyproject.toml 版本号替换失败"
info "版本号已更新：pyproject.toml → $VERSION"

if [ "$DRY_RUN" = 1 ]; then
  git checkout -- pyproject.toml
  info "dry-run 结束：版本号已还原，未提交/未推送。预检与替换逻辑均验证通过。"
  exit 0
fi

# ── 2. 提交 + tag + 推送 ──
git add pyproject.toml
git commit -m "release: v$VERSION"
git tag "$TAG"
if ! git push origin main "$TAG"; then
  die "推送被拒（可能并行会话刚推了提交）。处理：git pull --rebase origin main && git tag -d $TAG 后重跑本脚本"
fi
info "已推送 $TAG，release CI 已触发"

# ── 3. 盯 CI（PyPI + 三平台二进制 + Homebrew tap 同步）──
sleep 15
RUN_ID=$(gh run list --repo nathanpenny520/Nmail --workflow=release.yml --limit 10 \
  --json databaseId,headBranch --jq ".[] | select(.headBranch == \"$TAG\") | .databaseId" | head -1)
[ -n "$RUN_ID" ] || die "找不到 $TAG 的 release run，请到 https://github.com/nathanpenny520/Nmail/actions 手查"
info "CI run: https://github.com/nathanpenny520/Nmail/actions/runs/$RUN_ID（约 5–15 分钟）"
if ! gh run watch "$RUN_ID" --repo nathanpenny520/Nmail --exit-status --interval 30 > /dev/null; then
  die "CI 失败。看日志: gh run view $RUN_ID --repo nathanpenny520/Nmail --log-failed"
fi
info "CI 全绿：PyPI 已发布、Release 已挂三平台二进制、Homebrew tap 已同步"

# ── 4. winget 版本更新 PR ──
if [ "$SKIP_WINGET" = 0 ]; then
  info "等待 Release 资产出现并取 Windows exe 的 SHA256…"
  SHA256=""
  for _ in $(seq 1 30); do
    SHA256=$(gh api "repos/nathanpenny520/Nmail/releases/tags/$TAG" \
      --jq '.assets[] | select(.name == "nmail-windows-x64.exe") | .digest // "none"' 2>/dev/null || true)
    if [ -n "$SHA256" ] && [ "$SHA256" != "none" ]; then break; fi
    sleep 20
  done
  [ -n "$SHA256" ] && [ "$SHA256" != "none" ] || die "拿不到 exe SHA256。手动按 docs/RELEASE.md『故障处理』提 winget PR"
  SHA256="${SHA256#sha256:}"

  FORK="nathanpenny520/winget-pkgs"
  BRANCH="nmail-$VERSION"
  # 同步 fork 的 master（winget-pkgs 默认分支是 master，不是 main！）
  gh api "repos/$FORK/merge-upstream" -f branch=master >/dev/null 2>&1 || info "（fork master 同步跳过，沿用现有）"
  BASE=$(gh api "repos/$FORK/branches/master" --jq '.commit.sha')
  if ! gh api "repos/$FORK/git/refs" -f ref="refs/heads/$BRANCH" -f sha="$BASE" --jq '.ref' >/dev/null 2>&1; then
    info "（分支 $BRANCH 已存在，复用）"
  fi

  TMP_MANIFEST="/tmp/nmail-winget-$VERSION"
  rm -rf "$TMP_MANIFEST"
  mkdir -p "$TMP_MANIFEST"
  # 路径规则：单层首字母折叠 manifests/n/nathanpenny520/...（不能写成 n/na 两层！）
  DEST="manifests/n/nathanpenny520/Nmail/$VERSION"
  cat > "$TMP_MANIFEST/nathanpenny520.Nmail.yaml" <<EOF
PackageIdentifier: nathanpenny520.Nmail
PackageVersion: $VERSION
DefaultLocale: en-US
ManifestType: version
ManifestVersion: 1.6.0
EOF
  cat > "$TMP_MANIFEST/nathanpenny520.Nmail.installer.yaml" <<EOF
PackageIdentifier: nathanpenny520.Nmail
PackageVersion: $VERSION
Installers:
  - Architecture: x64
    InstallerType: portable
    InstallerUrl: https://github.com/nathanpenny520/Nmail/releases/download/$TAG/nmail-windows-x64.exe
    InstallerSha256: $SHA256
    Commands:
      - nmail
ManifestType: installer
ManifestVersion: 1.6.0
EOF
  # locale 文件名必须带语言后缀 .locale.en-US.yaml（不能省略！）
  cat > "$TMP_MANIFEST/nathanpenny520.Nmail.locale.en-US.yaml" <<EOF
PackageIdentifier: nathanpenny520.Nmail
PackageVersion: $VERSION
PackageLocale: en-US
Publisher: nathanpenny520
PublisherUrl: https://github.com/nathanpenny520
Author: nathanpenny520
PackageName: Nmail
PackageUrl: https://github.com/nathanpenny520/Nmail
License: MIT
LicenseUrl: https://github.com/nathanpenny520/Nmail/blob/$TAG/LICENSE
Copyright: Copyright (c) 2026 nathanpenny520
ShortDescription: AI-driven, local-first aggregated email client
Description: |-
  Nmail is a local-first AI-powered email client that aggregates multiple IMAP/SMTP accounts.
  AI classification, reply drafting and daily digests run on the user's own OpenAI-compatible
  API key (cloud or local Ollama / LM Studio). All mail data stays on the device; the app runs
  a localhost-only service and involves no servers.
Tags:
  - email
  - imap
  - smtp
  - ai
  - local-first
Moniker: nmail
ManifestType: defaultLocale
ManifestVersion: 1.6.0
EOF

  for f in nathanpenny520.Nmail.yaml nathanpenny520.Nmail.installer.yaml nathanpenny520.Nmail.locale.en-US.yaml; do
    C=$(base64 -w0 "$TMP_MANIFEST/$f")
    gh api -X PUT "repos/$FORK/contents/$DEST/$f" \
      -f message="nathanpenny520.Nmail version $VERSION" \
      -f content="$C" -f branch="$BRANCH" --jq '.content.path' > /dev/null
  done
  info "manifest 已推到 fork 分支 $BRANCH（本地复验: winget validate \"$(cygpath -w "$TMP_MANIFEST" 2>/dev/null || echo "$TMP_MANIFEST")\"）"

  PR_URL=$(gh api "repos/microsoft/winget-pkgs/pulls" \
    -f title="New version: nathanpenny520.Nmail version $VERSION" \
    -f head="nathanpenny520:$BRANCH" -f base="master" \
    -f body="New version: nathanpenny520.Nmail version $VERSION

Version update for the existing package nathanpenny520.Nmail.
- InstallerUrl / InstallerSha256 match the GitHub Release $TAG assets
- Source repo: https://github.com/nathanpenny520/Nmail (MIT)" \
    --jq '.html_url' 2>/dev/null || true)
  if [ -n "$PR_URL" ]; then
    info "winget PR: $PR_URL（校验自动跑，全绿后等社区审核员批准）"
  else
    info "winget 同版本 PR 已存在或创建失败——分支 $BRANCH 已更新，旧 PR 会自动重跑校验"
  fi
fi

# ── 5. 官网联动：触发 nmail-site 重建部署（站点内容全是构建期拉取——Releases + 主仓 docs）──
if gh workflow run deploy.yml -R nathanpenny520/nmail-site 2>/dev/null; then
  info "官网联动：已触发 nmail-site 部署，1-2 分钟后 nmail.whizzzest.com 同步"
else
  info "官网联动触发失败（gh 未登录/网络）——可手动: gh workflow run deploy.yml -R nathanpenny520/nmail-site"
fi

info "✅ v$VERSION 发版流程完成"
info "收尾提醒：docs/CHANGELOG.md 追加发版条目；docs/SESSIONS.md 看板登记（CLAUDE.md 规范 2/8）"
