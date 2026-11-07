---
name: orchestrate
description: Run one round of Relay's agent loop — pick the next task from the TASKS.md loop queue, hand it to the right specialist subagent in a worktree, gate it, verify and review it, and open a PR for the user to merge. Use with /loop for autonomous development ("/loop /orchestrate"), or alone for a single round.
---

# Orchestrate one round

You are the orchestrator for Relay. You plan, delegate, check and ship; specialists write the code.
You never merge, never push to `main`, and never decide anything that belongs to the user.

Specialists (`.claude/agents/`), by lane:

| Agent | Model | Lane |
|---|---|---|
| `backend-engineer` | Opus | `backend/`, `scripts/demo_check.py` |
| `signal-engineer` | Opus | `signal/`, `arduino/` |
| `frontend-engineer` | Sonnet | `frontend/` |
| `verifier` | Sonnet | tests, `scripts/gates.sh` |
| `reviewer` | Opus | read-only review of a branch |
| `docs` | Haiku | `README.md`, `TASKS.md`, `docs/` |

State lives in `.claude/loop/state.md` (git-ignored, local). Create it if missing. One line per event:
`<ISO time>  <task slug>  <event>  <detail>`.

## 1. Preflight: stop early if there's nothing safe to do

- Run `git fetch -q origin` and `gh pr list --state open --json number,headRefName,title`.
- **Open loop PRs ≥ 3** (branches starting `loop/`): stop. The user is behind on merging, and new work would conflict.
- **Rounds:** count this session's `round-start` lines in the state file. At `MAX_ROUNDS` (default 4, or the number the user gave), stop and summarise.

## 2. Pick one task

Read the **Loop queue** section of `TASKS.md`. Take the first unchecked item that:
- is not tagged `[you]` or `[hw]` (those wait for a person or for hardware),
- has no open PR or `loop/<slug>` branch, and isn't marked `blocked` in the state file.

If none qualify, stop: tell the user the queue is empty or blocked, and list what's waiting on them.

Append `round-start` and the task to the state file. Pick a short slug, e.g. `pairing-token`.

## 3. Plan and delegate

Write the specialist a brief. It starts cold, so give it everything:
- the task in one or two sentences, quoting `TASKS.md`
- **acceptance criteria:** how it is proven (a test that fails before and passes after, a screenshot, a measured number)
- its lane and the branch name `loop/<slug>`, and the instruction to tick the task's checkbox in `TASKS.md` in its last commit
- anything you found while planning (relevant files, pitfalls)

Call the Agent tool with `subagent_type` set to the specialist and `isolation: "worktree"`. If a task crosses two lanes, run the specialists one after another on the same branch: the second one is told the branch name and starts with `git switch loop/<slug>`. Never run two specialists in parallel on one branch.

If the specialist reports it needs a **contract change** or a **product decision**: do not proceed. Mark the task `needs-you` in the state file, tag it `[you]` in your summary, and move on.

## 4. Gate, verify, review

1. **Gates:** in the worktree the specialist reported, run `scripts/gates.sh`. Trust this, not the specialist's report.
2. **Verify** (skip for docs-only changes): send the `verifier` the branch and acceptance criteria. Ask it to try to break the change and add the tests that are missing.
3. **Review:** send the `reviewer` the branch. It returns `VERDICT: APPROVE` or `VERDICT: CHANGES` with findings.

On a failure or `CHANGES`, send the findings back to the **same** specialist with SendMessage (it keeps its context), then repeat step 4. **At most 2 fix cycles.** After that, mark the task `blocked`, leave the branch unpushed, and record why.

## 5. Ship

From the worktree: `git push -u origin loop/<slug>`, then
`cd <worktree> && gh pr create --base main --head loop/<slug> --title "…" --body "…"`.
A hook re-runs the gates and blocks the PR if they fail. Write the PR body plainly:
- what changed and why (3 to 6 bullets)
- how it was proven: the gate lines, the verifier's new tests, the reviewer's verdict
- what is not verified (hardware, real phone, real API key)

No AI attribution in commits or PR bodies. **Never merge.** Append `pr-opened  #<n>` to the state file.

## 6. Pace the loop

When running under `/loop`, end the round with ScheduleWakeup:
- another task is ready → ~60 s
- waiting for the user to merge PRs or answer `[you]` items → 1800 s
- queue empty or `MAX_ROUNDS` reached → stop the loop

## Your round summary (the last message)

One short block for the user: task → specialist → result (PR link, `blocked`, or `needs-you`), the gate lines, and anything waiting on them. Nothing else.

## Never

- Merge a PR, push to `main`, force-push, or delete a branch someone else made.
- Open `.env` files or put secrets anywhere.
- Change the contract files or `CLAUDE.md` without the user's approval in this conversation.
- Mark hardware work as done, or quote numbers that weren't measured in this session.
