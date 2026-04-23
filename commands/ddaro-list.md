---
name: ddaro:list
description: "List all worktrees grouped by the 6-tier model (owned / adopted / unmanaged / protected / external / main). Surfaces unmanaged worktrees as /ddaro:adopt candidates. Shows branch, commits, uncommit, push state, stale flag per entry."
argument-hint: ""
allowed-tools: [Bash, Read, Glob, Grep]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/ddaro/SKILL.md` sections "## Worktree tiers" and "## /ddaro:list" and execute.

- Walk `git worktree list --porcelain`.
- Classify each worktree via the tier algorithm (priority: main > external > protected > owned/adopted > unmanaged).
- For owned / adopted entries, collect: branch, commits ahead of main, uncommit count, push state, merge state (`git branch --merged main`), created date (from LOCK), stale flag (past `stale_days`).
- For adopted entries, also show `original_branch` from LOCK and a hint that `/ddaro:abandon` is refused for the tier.
- For unmanaged entries, surface three actions: `/ddaro:adopt <path>`, `/ddaro:config protect <path>`, or leave alone.
- Group output by tier in this order: Owned, Adopted, Unmanaged, Protected, External.
- Print summary counts: `ddaro worktrees (owned+adopted / max_concurrent)` plus per-tier sub-counts.
- Flag warnings: `warn_threshold` exceeded, stale entries, owned worktrees whose branch is already merged (suggest `/ddaro:clear`).
