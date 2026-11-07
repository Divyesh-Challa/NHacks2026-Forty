#!/usr/bin/env bash
# Headless screenshots of frontend pages, for checking visual changes (no backend needed).
#
#   scripts/screenshot.sh <out-dir> /patient/p1 /caregiver /demo     (default size 1280x800)
#   SIZE=390,844 scripts/screenshot.sh <out-dir> /caregiver           (phone)
#
# Starts its own Vite dev server on a spare port from this checkout (works in a worktree), saves
# <out-dir>/<page>.png, then stops the server. Read the PNGs to look at them.
set -euo pipefail
OUT="${1:?usage: scripts/screenshot.sh <out-dir> <path>...}"; shift
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
ROOT="$(git rev-parse --show-toplevel)"
MAIN="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
[[ -e "$ROOT/frontend/node_modules" ]] || ln -s "$MAIN/frontend/node_modules" "$ROOT/frontend/node_modules"
PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("",0)); print(s.getsockname()[1])')"
mkdir -p "$OUT"

(cd "$ROOT/frontend" && exec npx vite --port "$PORT" --strictPort >/dev/null 2>&1) &
VITE=$!
trap 'kill $VITE 2>/dev/null' EXIT
for _ in $(seq 50); do curl -s -o /dev/null "http://localhost:$PORT" && break; sleep 0.2; done

for path in "$@"; do
  name="$(echo "${path#/}" | tr '/' '-')"; name="${name:-index}"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size="${SIZE:-1280,800}" \
    --virtual-time-budget=3000 --screenshot="$OUT/$name.png" "http://localhost:$PORT$path" 2>/dev/null
  echo "$OUT/$name.png"
done
