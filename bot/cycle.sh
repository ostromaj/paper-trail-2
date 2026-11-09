#!/usr/bin/env bash
# One full step: load the saved portfolio, run the bot, save it safely.
# Extra arguments go to run.py (e.g. --reset).
set -uo pipefail
remote_fetch="${PT_REMOTE:-origin}"
for attempt in 1 2 3 4; do
  rm -f dashboard.json notify.json
  sha=""
  if git fetch -q --depth=1 "$remote_fetch" data 2>/dev/null; then
    sha="$(git rev-parse FETCH_HEAD)"
    git show FETCH_HEAD:dashboard.json > dashboard.json || true
  fi
  python3 bot/run.py --state dashboard.json "$@" || exit 1
  EXPECTED_SHA="$sha" bash bot/save.sh
  rc=$?
  if [ $rc -eq 0 ]; then
    python3 bot/notify.py notify.json || true
    exit 0
  fi
  [ $rc -eq 3 ] || exit $rc
  echo "Another run saved first. Reloading and trying again ($attempt)."
  sleep $((attempt * 3))
done
exit 1
