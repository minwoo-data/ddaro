---
name: ddaro:spec
description: "Scaffold a design doc and lock decisions before building."
argument-hint: "<name> [target-path]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
disable-model-invocation: true
---

# /ddaro:spec

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python "${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py" ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

1. Target `$2` or `docs/design/<name>.md`; existing -> show it and ask before overwriting (offer appending a revision section).
2. Search before building: grep the dirs the project's CLAUDE.md names (and `src/`) for related symbols; record a "Reuse inventory" table (capability | file:line | reuse / extend / new). An empty inventory for non-greenfield work is incomplete; say so.
3. Skeleton (use a `doc-template` skill if installed): TL;DR (decision) / Problem / Evidence / Reuse inventory / Options (verdict per row) / Locked decisions / Slices + gates / Schema / UI / Test plan / Rollback / Open questions (each with a default) / Out of scope. Drop sections the feature does not need.
4. Fill what is settled; mark gray areas `[DECIDE: <question>]` and ask the user each one now. Never default a decision the user owns.
5. Output the path, remaining `[DECIDE]` items, and "next: /ddaro:review <path>".
