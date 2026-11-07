#!/usr/bin/env bash
# The agent loop's definition of "done": every gate must pass before a PR is opened.
#
#   scripts/gates.sh            all gates (~1 min)
#   scripts/gates.sh quick      skip demo-check (inner dev loop)
#
# Runs against the checkout it's called from, including an agent's git worktree: venvs and
# node_modules are symlinked from the main checkout (.claude/settings.json worktree.symlinkDirectories)
# and fall back to the main checkout's if a worktree has none. Prints one line per gate; exits 1 if any fail.
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel)"
MAIN="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
cd "$ROOT"

dep() {  # dep <relative path>: this checkout's copy, else the main checkout's
  if [[ -e "$ROOT/$1" ]]; then echo "$ROOT/$1"; else echo "$MAIN/$1"; fi
}
BACKEND_VENV="$(dep backend/.venv)"
SIGNAL_VENV="$(dep signal/.venv)"
[[ -e frontend/node_modules ]] || ln -s "$MAIN/frontend/node_modules" frontend/node_modules

LOG="$(mktemp -t relay-gates)"
failed=0
gate() {  # gate <name> <command...>
  local name="$1"; shift
  local start=$SECONDS
  if (cd "$ROOT" && "$@") >"$LOG.$name" 2>&1; then
    printf 'PASS  %-14s %3ss  %s\n' "$name" $((SECONDS - start)) "$(tail -1 "$LOG.$name")"
  else
    failed=1
    printf 'FAIL  %-14s %3ss\n' "$name" $((SECONDS - start))
    tail -25 "$LOG.$name" | sed 's/^/      /'
  fi
}

gate backend-tests  bash -c "cd backend && '$BACKEND_VENV/bin/pytest' -q"
gate signal-tests   bash -c "cd signal && '$SIGNAL_VENV/bin/pytest' -q"
gate frontend-build bash -c "cd frontend && npm run -s build"
gate frontend-lint  bash -c "cd frontend && npm run -s lint"
gate frontend-tests bash -c "cd frontend && npm test -s"
[[ "${1:-}" == quick ]] || gate demo-check "$BACKEND_VENV/bin/python" scripts/demo_check.py

rm -f "$LOG" "$LOG".*
if [[ $failed == 0 ]]; then echo "GATES PASSED"; else echo "GATES FAILED"; fi
exit $failed
