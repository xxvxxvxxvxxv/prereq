#!/usr/bin/env bash
# Creates a PUBLIC repository using your own GitHub CLI login. Never force-pushes.
set -euo pipefail
cd "$(dirname "$0")/.."
for tool in git gh; do
  command -v "$tool" >/dev/null || { printf '%s is required. See docs/PUBLISHING.md.\n' "$tool"; exit 1; }
done
name="${1:-sabanci-prerequisite-graph}"
[[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo 'Use a repository name, not a URL or owner/name.'; exit 1; }
gh auth status >/dev/null 2>&1 || gh auth login --web --git-protocol https
owner="$(gh api user --jq .login)"
repo="$owner/$name"
if gh repo view "$repo" >/dev/null 2>&1; then
  printf '%s already exists. Stopped without changing or overwriting it.\n' "$repo"
  exit 1
fi
if [[ ! -d .git ]]; then git init -b main; fi
if git remote get-url origin >/dev/null 2>&1; then
  echo 'This folder already has an origin remote. Stopped without changing it.'
  exit 1
fi
# Set a repository-local, GitHub no-reply identity only when no identity is configured.
if ! git config user.name >/dev/null; then git config user.name "$owner"; fi
if ! git config user.email >/dev/null; then
  uid="$(gh api user --jq .id)"
  git config user.email "${uid}+${owner}@users.noreply.github.com"
fi
git add .
if ! git diff --cached --quiet; then git commit -m 'Build source-backed Sabanci prerequisite graph'; fi
gh repo create "$repo" --public --source=. --remote=origin --push \
  --description 'Sabanci degree requirements and prerequisite graphs, with admission-term selection, official sources and local planning.'
echo 'Repository created. This does not deploy the live Python service.'
gh repo view "$repo" --json url --jq .url
