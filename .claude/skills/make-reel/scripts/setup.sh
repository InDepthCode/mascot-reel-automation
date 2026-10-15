#!/bin/bash
# Checks the tools this skill needs (idempotent, no sudo). Prints READY on success.
cd "$(dirname "$0")/../../../.." || exit 1
PY=.venv/bin/python
[ -x "$PY" ] || { echo "MISSING: .venv (python3 -m venv .venv && .venv/bin/pip install -r requirements.txt)"; exit 1; }
"$PY" -c "import num2words, fontTools, PIL, numpy" 2>/dev/null || "$PY" -m pip install -q num2words fonttools pillow numpy || exit 1
for b in ffmpeg ffprobe; do command -v $b >/dev/null || { echo "MISSING: $b"; exit 1; }; done
echo READY
