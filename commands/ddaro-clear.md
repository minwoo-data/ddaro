---
name: ddaro:clear
description: "Remove a merged ddaro worktree (run from the main worktree)."
argument-hint: "[name]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
disable-model-invocation: true
---

# /ddaro:clear

<!-- step0 -->
**Step 0.** Find `.ddaro/config.json` in cwd or a parent; in a linked worktree with none, use the main worktree's (`git rev-parse --path-format=absolute --git-common-dir`, then its parent). None found: say "not a ddaro project - run /ddaro:start" and stop (`/ddaro:start` runs first-time setup instead). Then run `python "${CLAUDE_PLUGIN_ROOT}/hooks/config_tool.py" ensure-schema <main_worktree>` once (`<main_worktree>` = cwd if in main, else `.ddaro/LOCK` `main_worktree`, else `config.main_worktree`) and show its line if it prints one. Terms: "main worktree" = the folder `config.main_worktree` (receives merges only); `<base>` = `config.base_branch` (default `main`), `origin/<base>` its remote-tracking ref; never hardcode a branch name. Reply in `config.language`. If a ddaro script exits non-zero or python is missing, print `[ddaro] <script> <subcommand> failed (exit N): <first stderr line>` and continue; never hand-write `.ddaro/context/*`, `CURRENT.md`, or the config keys `base_branch` / `auto_snapshot` / `schema_version`.
<!-- /step0 -->

Must run from the main worktree; otherwise print `cd <main_worktree>` + `/ddaro:clear <name>` and do nothing.

1. No name: list owned/adopted worktrees whose branch is in `git branch --merged <base>` and let the user pick. Name: match `LOCK.branch` or the folder name.
2. Refuse if the target is main, protected, external, or unmanaged, or if its branch is not in `git branch --merged <base>`; suggest `/ddaro:merge` first, or `/ddaro:abandon` to discard.
3. Uncommitted changes in the target: show them and stop (clear never discards uncommitted work).
4. `git worktree remove <path>`; if the folder is still on disk afterwards, remove it only when it is empty, then `git worktree prune`. `git branch -d <branch>`. If `origin/<branch>` exists ask y/n before `git push origin --delete <branch>`. After the branch is deleted: `python "${CLAUDE_PLUGIN_ROOT}/hooks/gate.py" retire <main_worktree> <branch>` (moves the merge-gate state aside; prints one line).
5. Report what was removed. cwd stays in main.
