---
name: ddaro:status
description: "Show current ddaro worktree status - branch, lock match, commits ahead of main, uncommit, push state, context snapshot count, next suggested action."
argument-hint: ""
allowed-tools: [Bash, Read, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## `/ddaro status`" and execute.

- Detect cwd category:
  - **Inside a ddaro worktree** (has `.git/ddaro-owned` OR `.ddaro/OWNED` OR LOCK with `adopted=true`) → local status view (below).
  - **Inside `config.main_worktree`** → auto-delegate to `/ddaro:list` directly (no second command needed). Print a one-line header "You're in main — showing worktree inventory:" then run list.
  - **Neither** → print "cwd is not under ddaro management" + suggest `cd <main>` + `/ddaro:list`.
- Local status view (for in-worktree case):
  - Read `.git/ddaro-lock` (or `.ddaro/LOCK` for adopted), compare with current branch.
  - Count commits ahead of main, uncommitted files, push status (origin up-to-date / ahead / behind).
  - Count context snapshots in `.ddaro/context/`.
  - Recommend next action (commit / merge / continue editing / resume if crash evidence).
