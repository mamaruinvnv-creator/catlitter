#!/usr/bin/env bash
# publish.sh — 一键把 litter-scoop 发布到 GitHub（macOS / Linux）
# 用法: ./scripts/publish.sh [repo-name] [public|private]
set -euo pipefail
cd "$(dirname "$0")/.."

REPO_NAME="${1:-litter-scoop}"
VISIBILITY="${2:-public}"
DESCRIPTION="Cat-litter model redundant-code cleaner: auto-detect project, scoop dead code into a restorable garbage bag"

need() { command -v "$1" >/dev/null 2>&1 || { echo "缺少 $1，请先安装"; exit 1; }; }
need git
need gh

if ! gh auth status >/dev/null 2>&1; then
  echo "尚未登录 GitHub，启动登录流程..."
  gh auth login
fi

if [ ! -d .git ]; then
  git init -b main
fi
git add -A
if [ -n "$(git status --porcelain)" ]; then
  git commit -m "feat: initial release of litter-scoop (cat-litter redundant-code cleaner)"
fi

if ! gh repo view "$REPO_NAME" >/dev/null 2>&1; then
  gh repo create "$REPO_NAME" --"$VISIBILITY" --source=. --remote=origin --push --description "$DESCRIPTION"
else
  git push -u origin main
fi

echo "完成: $(gh repo view "$REPO_NAME" --json url -q .url)"
