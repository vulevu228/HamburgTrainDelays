#!/bin/bash
# HamburgTrainDelays on the Pi: collect, then commit + push hamburg_delays.csv if it changed.
# Port of scripts/collect_and_push.ps1: always reset to origin/main BEFORE collecting and redo the whole
# cycle on a rejected push (the collector rewrites the whole CSV, so rebasing its diff never works).
# Shallow clone in ~/hamburg-delays (15 MB), push via deploy key (ssh alias github-htd, this repo only).
# NO_PUSH=1 -> collect only (test). Log: ~/hamburg-delays-collector.log
cd ~/hamburg-delays
LOG=~/hamburg-delays-collector.log
log() { echo "$(date '+%Y-%m-%d %H:%M:%S')  $*" >> "$LOG"; }
PY=~/venvs/collectors/bin/python
for attempt in 1 2 3 4 5; do
    git fetch -q --depth 1 origin main && git reset -q --hard origin/main
    if ! out=$($PY scripts/hamburg_collector.py 2>&1); then log "collector FAILED: $out"; exit 1; fi
    log "$(echo "$out" | tr '\n' ' ')"
    if git diff --quiet -- hamburg_delays.csv; then log "no dataset change - nothing to commit"; exit 0; fi
    if [ -n "$NO_PUSH" ]; then log "NO_PUSH test: change not committed"; git checkout -q -- hamburg_delays.csv; exit 0; fi
    stamp=$(date -u '+%Y-%m-%d %H:%M UTC')
    git -c user.name=hamburg-delays-collector -c user.email=collector@hamburg-delays.local \
        commit -q -m "data: hamburg delays $stamp" -- hamburg_delays.csv
    if push=$(git push -q origin HEAD:main 2>&1); then log "committed + pushed: $stamp (attempt $attempt)"; exit 0; fi
    log "push rejected (attempt $attempt), re-syncing: $push"
done
log "could not push after 5 attempts - next run retries"; exit 1
