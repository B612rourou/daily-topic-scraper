#!/usr/bin/env bash
set -euo pipefail

REPO_NAME="${1:-$(basename "$(pwd)")}" 

if ! command -v git >/dev/null 2>&1; then
  echo "缺少命令：git（请先安装）"
  exit 1
fi

PY_CMD=""
if command -v python3 >/dev/null 2>&1; then
  PY_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PY_CMD="python"
else
  echo "缺少命令：python3 或 python（请先安装）"
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "缺少命令：gh（请先安装 GitHub CLI）"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "请先执行：gh auth login"
  exit 1
fi

mkdir -p .github/workflows 每日选题

git init

git branch -M main

git add .

git commit -m "chore: init daily topic scraper"

gh repo create "$REPO_NAME" --public --source=. --remote=origin --push
