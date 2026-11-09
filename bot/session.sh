#!/usr/bin/env bash
# The all-day loop: checks the markets every 5 minutes from 7:00 AM until just after the
# close on trading days. GitHub jobs can only run ~6 hours, so before that limit it starts
# a fresh copy of itself to carry on. This makes the bot independent of GitHub's
# (unreliable) scheduled timer during market hours.
set -uo pipefail
start=$SECONDS
limit=$((5 * 3600 + 30 * 60))
handed_off=0
while python3 bot/window.py in-session; do
  # pick up any code updates pushed during the day (this script runs from a copy, so it's safe)
  git fetch -q --depth=1 origin "${GITHUB_REF_NAME:-main}" && git reset -q --hard FETCH_HEAD || true
  bash bot/cycle.sh || echo "This check failed; trying again next time."
  if [ $((SECONDS - start)) -ge $limit ]; then
    echo "Near GitHub's time limit. Handing off to a fresh run."
    gh workflow run session.yml --ref "${GITHUB_REF_NAME:-main}" && handed_off=1
    break
  fi
  s=$(python3 bot/window.py sleep)
  echo "Next check in ${s}s."
  sleep "$s"
done
[ $handed_off -eq 1 ] || echo "Session window is over for today."
