#!/usr/bin/env bash
# Saves dashboard.json to the "data" branch as a single commit (force-pushed),
# so the repo doesn't grow by a commit every 5 minutes. The dashboard reads it from there.
set -euo pipefail
out="$(mktemp -d)"
cp dashboard.json "$out/"
cd "$out"
git init -q -b data
git config user.name "paper-trail-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add dashboard.json
git commit -q -m "Portfolio update $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git push -q -f "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" HEAD:data
echo "Saved."
