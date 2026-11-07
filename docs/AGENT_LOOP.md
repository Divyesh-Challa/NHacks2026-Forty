# Agent loop

Claude Code can develop Relay on its own between human check-ins. An orchestrator picks tasks, specialist agents write the code, gates and reviewers check it, and every change arrives as a PR. **A human merges every PR.**

```
You           merge PRs · hardware · decisions tagged [you]
 └─ orchestrator  (your Claude Code session, /loop /orchestrate)
      ├─ backend-engineer   Opus    backend/
      ├─ signal-engineer    Opus    signal/, arduino/
      ├─ frontend-engineer  Sonnet  frontend/
      ├─ verifier           Sonnet  tests, gates
      ├─ reviewer           Opus    read-only review
      └─ docs               Haiku   README, TASKS, docs/
```

Opus handles the input manager and signal processing, where subtle mistakes break the demo. Sonnet handles the UI and verification, which are many well-shaped edits. Haiku handles docs.

## Running it

```bash
claude                        # in the repo root
/orchestrate                  # one round: one task → one PR
/loop /orchestrate            # keep going until the queue is empty, 4 rounds pass, or 3 PRs await merging
```

The queue is the **Loop queue** section at the top of [TASKS.md](../TASKS.md). The orchestrator takes the first unchecked item without `[you]` or `[hw]`. Add work there; say who owns it and how it's proven.

## One round

1. **Pick** the next queue item.
2. **Delegate** it to the specialist in its own git worktree, on branch `loop/<slug>`.
3. **Gate:** `scripts/gates.sh` runs backend + signal tests, frontend build + lint, and `make demo-check`.
4. **Verify:** the verifier tries to break the change and adds the missing tests.
5. **Review:** the reviewer reads the diff and returns APPROVE or CHANGES. Up to 2 fix cycles, then the task is marked `blocked`.
6. **Ship:** push the branch and open a PR. A hook re-runs the gates and blocks the PR if anything fails.

The local run log is `.claude/loop/state.md`.

## Guardrails (`.claude/settings.json`)

- Denied: `gh pr merge`, pushing to `main`, force-push, reading or editing `.env`.
- `gh pr create` is blocked unless `scripts/gates.sh` passes in that checkout (`scripts/hooks/pr_gate.sh`).
- No AI attribution on commits or PRs.
- Contract changes (`models.py`, `types.ts`, `messages.py`, the CLAUDE.md contract) and hardware results always come back to a human.

## Tools the agents use (you can too)

- `make gates` (or `scripts/gates.sh quick` to skip demo-check)
- `scripts/screenshot.sh <dir> /patient/p1 /caregiver`: headless screenshots with no backend needed (`SIZE=390,844` for a phone)
