---
name: ddaro:list
description: "List all worktrees grouped by ddaro tier."
argument-hint: ""
allowed-tools: [Bash, Read, Glob, Grep]
disable-model-invocation: true
---

# /ddaro:list

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python ${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

Read-only. Classify each `git worktree list --porcelain` entry (main, external, protected, OWNED -> adopted/owned, unmanaged; see `${CLAUDE_PLUGIN_ROOT}/reference/tiers.md` only if unsure).

- Owned/adopted: branch, state (`active` = uncommitted, `ready` = committed + pushed), commits ahead of `<base>`, uncommit count, push state, age from LOCK `created_at`, `STALE` past `stale_days`, `merged` if in `git branch --merged <base>` (suggest `/ddaro:clear`). Adopted: also `original_branch` and "abandon needs --force".
- Unmanaged: suggest `/ddaro:adopt <path>` or `/ddaro:config protect <path>`.
- Print `ddaro worktrees (<owned+adopted> / <max_concurrent>)`, per-tier counts, then groups in order Owned, Adopted, Unmanaged, Protected, External. Warn at `warn_threshold`.
