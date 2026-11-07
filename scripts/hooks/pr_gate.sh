#!/usr/bin/env bash
# PreToolUse hook (Bash, `gh pr create`): no PR unless scripts/gates.sh passes in the checkout
# the PR is being opened from. Exit 2 blocks the tool call and shows Claude the failing gates.
set -uo pipefail
GATES="$(cd "$(dirname "$0")/.." && pwd)/gates.sh"

input="$(cat)"
cwd="$(jq -r '.cwd // empty' <<<"$input")"
cmd="$(jq -r '.tool_input.command // empty' <<<"$input")"
# Honour a leading `cd <dir> &&` so a PR opened from a worktree is gated on that worktree.
if [[ "$cmd" =~ ^cd[[:space:]]+([^&;]+)[[:space:]]*\&\& ]]; then
  dir="${BASH_REMATCH[1]%"${BASH_REMATCH[1]##*[![:space:]]}"}"
  dir="${dir/#\~/$HOME}"; dir="${dir%\"}"; dir="${dir#\"}"; dir="${dir%\'}"; dir="${dir#\'}"
  [[ "$dir" = /* ]] || dir="$cwd/$dir"
  cwd="$dir"
fi
cd "${cwd:-.}" || { echo "pr_gate: can't cd to $cwd" >&2; exit 2; }

if out="$("$GATES" 2>&1)"; then
  exit 0
fi
{
  echo "PR blocked: gates failed in $(git rev-parse --show-toplevel). Fix these, then retry:"
  echo "$out"
} >&2
exit 2
