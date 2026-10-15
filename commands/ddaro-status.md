---
name: ddaro:status
description: "Show this worktree's ddaro state; in main, the worktree list."
argument-hint: ""
allowed-tools: [Bash, Read, Glob, Grep]
disable-model-invocation: true
---

# /ddaro:status

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python "${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py" ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

Read-only.

- cwd in the main worktree: print "You're in main - worktree inventory:" and do `${CLAUDE_PLUGIN_ROOT}/commands/ddaro-list.md`.
- cwd in an owned/adopted worktree: show path, branch (lock matches or not), topic, created (from LOCK), commits ahead of `<base>`, uncommitted files, push state vs upstream, snapshot count in `.ddaro/context/`, and one suggested next step (commit / merge / keep editing / `/ddaro:resume` if the last snapshot is old and work is uncommitted).
- anywhere else: "cwd is not under ddaro" + suggest `cd <main_worktree>` and `/ddaro:list`.
