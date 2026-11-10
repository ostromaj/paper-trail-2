#!/usr/bin/env bash
# The always-on loop. During the market-day window (7:00 AM to just after the close) it
# checks every minute; nights and weekends it checks crypto every 5 minutes. GitHub jobs
# can only run ~6 hours, so before that limit it starts a fresh copy of itself to carry on.
# This keeps the bot running without depending on GitHub's scheduled timer, which can go
# hours without firing (that's what made it miss the 7 AM start on Nov 10).
set -uo pipefail
start=$SECONDS
limit=$((5 * 3600 + 30 * 60))
while true; do
  # pick up any code updates pushed during the day (this script runs from a copy, so it's safe)
  git fetch -q --depth=1 origin "${GITHUB_REF_NAME:-main}" && git reset -q --hard FETCH_HEAD || true
  bash bot/cycle.sh || echo "This check failed; trying again next time."
  if [ $((SECONDS - start)) -ge $limit ]; then
    echo "Near GitHub's time limit. Handing off to a fresh run."
    for try in 1 2 3; do
      gh workflow run session.yml --ref "${GITHUB_REF_NAME:-main}" && exit 0
      sleep 20
    done
    echo "Couldn't start the next run; the 'Trading bot' watchdog will restart it."
    exit 1
  fi
  s=$(python3 bot/window.py sleep)
  echo "Next check in ${s}s."
  sleep "$s"
done
