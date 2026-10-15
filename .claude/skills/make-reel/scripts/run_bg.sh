#!/bin/bash
# run_bg.sh WORKDIR  -> starts the resumable render detached; poll WORKDIR/progress.json / render.log
W="$1"; D="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$W/render.lock" ] && kill -0 "$(cat "$W/render.lock")" 2>/dev/null; then echo "already running (pid $(cat "$W/render.lock"))"; exit 0; fi
setsid nohup "${PYTHON:-python3}" "$D/render.py" "$W" --run > "$W/render.log" 2>&1 < /dev/null &
echo "started"
