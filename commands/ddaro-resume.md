---
name: ddaro:resume
description: "Re-enter a worktree after a crash or days later: recap + cd + paste prompt."
argument-hint: "[name] [--recap-only] [--all]"
allowed-tools: [Bash, Read, Glob, Grep]
disable-model-invocation: true
---

# /ddaro:resume

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python "${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py" ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

Read-only.

1. Owned + adopted worktrees, each `active` (uncommitted), `ready` (committed + pushed), `stale` (past `stale_days`), or `merged` (suggest `/ddaro:clear` instead). None: "Nothing to resume. Use /ddaro:start".
2. `--all`: one or two lines per worktree, stop. `<name>` given: use it. Else numbered picker + `all` + `cancel`. In a ddaro worktree already: mention `/ddaro:status` fits better, continue if the user wants.
3. Recap from `git log <base>..HEAD`, `git diff --stat <base>..HEAD`, `git status --porcelain`, the `## What was done` / `## Next planned (inferred)` sections of `.ddaro/context/*.md` and the `## Resume hint` of `.ddaro/CURRENT.md` (no context dir: git only, say "context unavailable"). Lock vs branch mismatch: warn and continue only if confirmed.
4. Print: branch, topic, created, progress (commits, uncommitted, push); where it stopped (last commit and age, uncommitted files, inferred next step); next commands (commit if active, merge if ready, clear if merged).
5. Unless `--recap-only`: a copy-paste block `cd <path>`, `claude`, and a prompt restating topic, last state, and next step.
