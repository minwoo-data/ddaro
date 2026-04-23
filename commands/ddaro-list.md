---
name: ddaro:list
description: "List all ddaro-owned worktrees with technical status — branch, commits, uncommit, push, merge status, stale flag. Shows count / max and warnings."
argument-hint: ""
allowed-tools: [Bash, Read, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` section "## `/ddaro list`" and execute.

- Walk `git worktree list --porcelain`.
- Filter to those with `.git/ddaro-owned`.
- For each: branch, commits ahead, uncommit count, push state, merge state (`git branch --merged main`), created date (from lock file), stale flag (past `stale_days`).
- Group by state: active (uncommit) / ready (pushed, mergeable) / merged (clean recommended) / stale (needs attention).
- Print summary counts: `ddaro worktrees (N / max_concurrent)`.
- Flag warnings: warn_threshold exceeded, stale entries.
