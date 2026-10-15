---
name: ddaro:abandon
description: "Force-discard a worktree and its unmerged commits (typed confirmation)."
argument-hint: "<name> [--force] [--delete-remote]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
disable-model-invocation: true
---

# /ddaro:abandon

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python "${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py" ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

Destructive. `<name>` is required. Must run from the main worktree (else print `cd <main_worktree>` + `/ddaro:abandon <name>` and stop).

1. Tier gate (`${CLAUDE_PLUGIN_ROOT}/reference/tiers.md`): owned -> continue; adopted -> only with `--force` (else refuse: "adopted; re-run with --force to delete the worktree and its branch"), and show "ADOPTED target - original_branch: <...>" in the preview; main / protected / unmanaged / external -> refuse with the reason.
2. Re-check: path not in `protected_worktrees`; `.ddaro/OWNED` present.
3. Preview: commits lost (unpushed / pushed), worktree path, snapshot count, and whether the remote branch is deleted (`--delete-remote`, or ask). Require the user to type exactly `yes, I'm sure`.
4. `git worktree remove --force <path>`, `git branch -D <LOCK.branch>`, and if chosen `git push origin --delete <LOCK.branch>`. cwd stays in main.
