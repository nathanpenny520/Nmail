#!/usr/bin/env bash
# 构建前端并把产物同步进 Python 包（wheel 打包与 PyInstaller 均从 backend/app/static 取）。
# 用法：bash scripts/sync_frontend.sh  （在仓库根执行或任意位置均可）
set -euo pipefail
cd "$(dirname "$0")/.."

(cd frontend && npm ci && npm run build)

rm -rf backend/app/static
mkdir -p backend/app/static
cp -r frontend/dist/. backend/app/static/
echo "前端产物已同步到 backend/app/static"
