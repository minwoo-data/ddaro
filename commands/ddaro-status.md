---
name: ddaro:status
description: "Show current ddaro worktree status - branch, lock match, commits ahead of <base>, uncommit, push state, context snapshot count, next suggested action."
argument-hint: ""
allowed-tools: [Bash, Read, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## /ddaro:status" and execute.

- Detect cwd category:
  - Step 0: resolve config (walk up; linked worktree falls back to main) and run `python ${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py ensure-schema <main_worktree>`; show its line if any.
  - **Inside a ddaro worktree** (has `.ddaro/OWNED`; LOCK `adopted=true` for adopted) → local status view (below).
  - **Inside `config.main_worktree`** → auto-delegate to `/ddaro:list` directly (no second command needed). Print a one-line header "You're in main — showing worktree inventory:" then run list.
  - **Neither** → print "cwd is not under ddaro management" + suggest `cd <main>` + `/ddaro:list`.
- Local status view (for in-worktree case):
  - Read `.ddaro/LOCK`, compare with current branch.
  - Count commits ahead of <base>, uncommitted files, push status (origin up-to-date / ahead / behind).
  - Count context snapshots in `.ddaro/context/`.
  - Recommend next action (commit / merge / continue editing / resume if crash evidence).
