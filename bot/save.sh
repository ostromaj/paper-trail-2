#!/usr/bin/env bash
# Saves dashboard.json to the "data" branch as a single commit, so the repo doesn't grow
# by a commit every 5 minutes. The dashboard reads it from there.
#
# EXPECTED_SHA = the data-branch commit this run loaded ("" if there was none). The push only
# succeeds if nobody else saved in the meantime (compare-and-swap), so two runs can never
# overwrite each other's trades. Exit code 3 means "someone else saved first, reload and retry".
set -uo pipefail
out="$(mktemp -d)"
cp dashboard.json "$out/"
cd "$out"
git init -q -b data
git config user.name "paper-trail-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add dashboard.json
git commit -q -m "Portfolio update $(date -u +%Y-%m-%dT%H:%M:%SZ)"
remote="${PT_REMOTE:-https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git}"
if msg=$(git push -q --force-with-lease="refs/heads/data:${EXPECTED_SHA:-}" "$remote" HEAD:refs/heads/data 2>&1); then
  echo "Saved."
  exit 0
fi
echo "$msg"
if grep -qiE "stale info|rejected|fetch first" <<<"$msg"; then
  exit 3
fi
exit 1
