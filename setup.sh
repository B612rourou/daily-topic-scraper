#!/usr/bin/env bash
set -euo pipefail

REPO_NAME="${1:-$(basename "$(pwd)")}" 

for cmd in git python3 gh; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "缺少命令：$cmd（请先安装）"
    exit 1
  fi
done

if ! gh auth status >/dev/null 2>&1; then
  echo "请先执行：gh auth login"
  exit 1
fi

mkdir -p .github/workflows daily_drafts

git init

git branch -M main

git add .

git commit -m "chore: init daily topic scraper"

gh repo create "$REPO_NAME" --public --source=. --remote=origin --push
